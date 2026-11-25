"""Safe OCI IAM preflight for a Raijin instance principal.

The runtime identity should normally *not* receive tenancy-wide IAM inspection
privileges.  This module therefore separates two facts that are often confused:

* effective access, proven by harmless Vault/Object Storage calls; and
* IAM declaration, proven only when the identity is allowed to inspect the
  relevant Dynamic Group and policy compartment.

An IAM inspection denial is reported as ``UNKNOWN`` rather than ``MISSING``.
That distinction keeps the preflight useful without encouraging a broader
production policy just to make a diagnostic green.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.oci_runtime import object_storage_client, resolve_object_storage_namespace


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _safe_error(error: Exception) -> str:
    """Keep reports actionable without leaking service messages or tokens."""
    status = getattr(error, "status", None)
    code = getattr(error, "code", None)
    suffix = " ".join(str(item) for item in (status, code) if item)
    return f"{type(error).__name__}{f' ({suffix})' if suffix else ''}"


def _check(name: str, status: str, detail: str, **extra: object) -> dict[str, object]:
    return {"name": name, "status": status, "detail": detail, **extra}


def instance_ocid_from_metadata() -> str:
    """Read only the local OCI instance identifier, never cloud credentials."""
    request = Request(
        "http://169.254.169.254/opc/v2/instance/id",
        headers={"Authorization": "Bearer Oracle"},
    )
    try:
        with urlopen(request, timeout=2) as response:  # nosec B310: fixed OCI IMDS address
            return response.read().decode("utf-8").strip()
    except (OSError, URLError):
        return ""


def iam_requirements(runtime: dict[str, Any]) -> dict[str, object]:
    """Build the expected least-privilege declaration from non-secret config."""
    configured = runtime.get("iam_preflight")
    configured = configured if isinstance(configured, dict) else {}
    dynamic_group = _text(configured.get("dynamic_group_name"))
    policy_compartment = _text(configured.get("policy_compartment_ocid"))
    secret_compartments = configured.get("secret_compartment_ocids")
    if not isinstance(secret_compartments, list):
        secret_compartments = runtime.get("secret_compartment_ocids", [])
    secret_compartments = sorted({_text(value) for value in secret_compartments if _text(value)})
    destinations = configured.get("destination_buckets", [])
    if not isinstance(destinations, list):
        destinations = []

    normalized_destinations: dict[str, list[str]] = {}
    for destination in destinations:
        if not isinstance(destination, dict):
            continue
        compartment = _text(destination.get("compartment_id"))
        bucket = _text(destination.get("name"))
        if compartment and bucket:
            normalized_destinations.setdefault(compartment, []).append(bucket)
    for buckets in normalized_destinations.values():
        buckets.sort()

    statements: list[str] = []
    if dynamic_group:
        for compartment in secret_compartments:
            statements.extend([
                f"Allow dynamic-group {dynamic_group} to inspect secret-family in compartment id {compartment}",
                f"Allow dynamic-group {dynamic_group} to read secret-bundles in compartment id {compartment}",
            ])
        for compartment, buckets in sorted(normalized_destinations.items()):
            statements.append(
                f"Allow dynamic-group {dynamic_group} to inspect buckets in compartment id {compartment}"
            )
            targets = ", ".join(f"target.bucket.name='{bucket}'" for bucket in buckets)
            statements.append(
                f"Allow dynamic-group {dynamic_group} to manage objects in compartment id {compartment} where any {{{targets}}}"
            )
    return {
        "dynamic_group_name": dynamic_group,
        "policy_compartment_ocid": policy_compartment,
        "secret_compartment_ocids": secret_compartments,
        "destination_buckets": [
            {"compartment_id": compartment, "name": bucket}
            for compartment, buckets in sorted(normalized_destinations.items())
            for bucket in buckets
        ],
        "statements": statements,
    }


def _identity_declarations(signer: object, requirements: dict[str, object], instance_ocid: str) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Inspect declarations only when explicitly authorized by OCI IAM."""
    dynamic_group_name = str(requirements["dynamic_group_name"])
    policy_compartment = str(requirements["policy_compartment_ocid"])
    statements = list(requirements["statements"])
    group = {
        "name": dynamic_group_name,
        "matching_rule": f"ALL {{instance.id = '{instance_ocid or '<VM_OCID>'}'}}",
        "status": "CONFIGURATION_REQUIRED",
        "detail": "Configure iam_preflight.dynamic_group_name to inspect this declaration.",
    }
    statement_rows = [
        {"statement": statement, "status": "CONFIGURATION_REQUIRED",
         "detail": "Configure Dynamic Group and policy compartment metadata first."}
        for statement in statements
    ]
    if not dynamic_group_name or not policy_compartment:
        return group, statement_rows

    try:
        import oci
        identity = oci.identity.IdentityClient({}, signer=signer)
        tenancy_id = _text(getattr(signer, "tenancy_id", ""))
        if not tenancy_id:
            raise RuntimeError("Instance principal tenancy identifier unavailable")
        groups = identity.list_dynamic_groups(tenancy_id).data
        matched = next((candidate for candidate in groups if candidate.name == dynamic_group_name), None)
        if not matched:
            group.update(status="MISSING", detail="Dynamic Group was not found by its configured name.")
        else:
            matching_rule = _text(getattr(matched, "matching_rule", ""))
            group["matching_rule"] = matching_rule
            if instance_ocid and f"instance.id = '{instance_ocid}'" in matching_rule:
                group.update(status="OK", detail="The matching rule includes this VM instance OCID.")
            elif instance_ocid:
                group.update(status="MISSING", detail="The Dynamic Group exists but its matching rule does not include this VM.")
            else:
                group.update(status="UNKNOWN", detail="Dynamic Group found, but the local VM OCID could not be read from OCI metadata.")

        policies = identity.list_policies(policy_compartment).data
        declared = {
            statement.strip()
            for policy in policies
            for statement in (getattr(policy, "statements", None) or [])
        }
        statement_rows = [
            {"statement": statement,
             "status": "OK" if statement in declared else "MISSING",
             "detail": "Found in the inspected policy compartment." if statement in declared else "Not found in the inspected policy compartment."}
            for statement in statements
        ]
    except Exception as error:
        detail = f"IAM declarations could not be inspected: {_safe_error(error)}"
        group.update(status="UNKNOWN", detail=detail)
        statement_rows = [
            {"statement": statement, "status": "UNKNOWN", "detail": detail}
            for statement in statements
        ]
    return group, statement_rows


def build_iam_preflight(runtime: dict[str, Any]) -> dict[str, object]:
    """Return a non-mutating, secret-free IAM preflight report."""
    requirements = iam_requirements(runtime)
    checks: list[dict[str, object]] = []
    instance_ocid = instance_ocid_from_metadata()
    try:
        import oci
        signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
        checks.append(_check("OCI Instance Principal", "OK", "Instance Principal token acquired."))
    except Exception as error:
        checks.append(_check("OCI Instance Principal", "FAILED", _safe_error(error)))
        return {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "ready": False,
            "checks": checks,
            "dynamic_group": {"status": "UNKNOWN", "detail": "Cannot inspect before Instance Principal authentication succeeds."},
            "policy": {"status": "UNKNOWN", "statements": []},
        }

    secret_ocids = runtime.get("secret_ocids") if isinstance(runtime.get("secret_ocids"), dict) else {}
    try:
        secrets = oci.secrets.SecretsClient({}, signer=signer)
        for name, ocid in sorted(secret_ocids.items()):
            if not _text(ocid):
                continue
            try:
                bundle = secrets.get_secret_bundle(ocid).data
                # Decode only enough to identify a placeholder. It is never retained or emitted.
                value = base64.b64decode(bundle.secret_bundle_content.content).decode("utf-8").strip()
                checks.append(_check(f"Vault Secret {name}", "OK" if value else "FAILED",
                                     "Read authorized." if value else "Secret is empty."))
            except Exception as error:
                checks.append(_check(f"Vault Secret {name}", "FAILED", _safe_error(error)))
    except Exception as error:
        checks.append(_check("OCI Vault", "FAILED", _safe_error(error)))

    destinations = list(requirements["destination_buckets"])
    try:
        storage = object_storage_client(signer, runtime)
        namespace, namespace_source = resolve_object_storage_namespace(signer, runtime, client=storage)
        namespace_detail = (
            "Discovered automatically with the Instance Principal."
            if namespace_source == "AUTO_DISCOVERED" else "Configured explicitly."
        )
        checks.append(_check("OCI Object Storage namespace", "OK", namespace_detail))
    except Exception as error:
        namespace = ""
        storage = None
        checks.append(_check("OCI Object Storage namespace", "FAILED", _safe_error(error)))

    if namespace and not destinations:
        checks.append(_check("OCI destination buckets", "NOT_CONFIGURED",
                             "iam_preflight.destination_buckets is empty."))
    elif namespace:
        try:
            for destination in destinations:
                bucket = _text(destination.get("name")) if isinstance(destination, dict) else ""
                if not bucket:
                    continue
                try:
                    storage.list_objects(namespace, bucket, limit=1)
                    checks.append(_check(f"OCI destination bucket {bucket}", "OK",
                                         "List authorization confirmed; no objects were changed."))
                except Exception as error:
                    checks.append(_check(f"OCI destination bucket {bucket}", "FAILED", _safe_error(error)))
        except Exception as error:
            checks.append(_check("OCI Object Storage", "FAILED", _safe_error(error)))

    group, statements = _identity_declarations(signer, requirements, instance_ocid)
    declaration_statuses = [str(group.get("status"))] + [str(row["status"]) for row in statements]
    operational_ok = all(row["status"] == "OK" for row in checks)
    declaration_ok = all(status in {"OK", "CONFIGURATION_REQUIRED", "UNKNOWN"} for status in declaration_statuses)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ready": operational_ok and declaration_ok,
        "checks": checks,
        "dynamic_group": group,
        "policy": {
            "name": f"{requirements['dynamic_group_name']}-policy" if requirements["dynamic_group_name"] else "<DYNAMIC_GROUP_NAME>-policy",
            "compartment_id": requirements["policy_compartment_ocid"] or "<POLICY_COMPARTMENT_OCID>",
            "status": "OK" if statements and all(row["status"] == "OK" for row in statements) else "PENDING",
            "statements": statements,
        },
        "note": "UNKNOWN means the VM lacks IAM inspection permission; it does not mean a policy is missing.",
    }


def read_and_build(runtime_config_path: str) -> dict[str, object]:
    with open(runtime_config_path, encoding="utf-8") as source:
        runtime = json.load(source)
    if not isinstance(runtime, dict):
        raise ValueError("OCI runtime configuration must be a JSON object")
    return build_iam_preflight(runtime)
