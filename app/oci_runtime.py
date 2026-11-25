"""Shared OCI Object Storage runtime resolution.

The Object Storage namespace is tenancy metadata, not a secret.  A deployment
may pin it in the root-owned runtime configuration, but an Instance Principal
can safely discover it when it was omitted.  Keep that fallback centralized so
workers, health checks and IAM diagnostics behave identically.
"""

from __future__ import annotations

import threading
import time
from typing import Any


_NAMESPACE_CACHE_TTL_SECONDS = 60 * 60
_namespace_cache: dict[tuple[str, str], tuple[float, str]] = {}
_namespace_cache_lock = threading.Lock()


def configured_object_storage_namespace(runtime: dict[str, Any] | None) -> str:
    """Return an explicitly configured namespace, if present."""
    if not isinstance(runtime, dict):
        return ""
    value = runtime.get("object_storage_namespace")
    return value.strip() if isinstance(value, str) else ""


def object_storage_client(signer: object, runtime: dict[str, Any] | None = None):
    """Create an OCI client honoring the deployment's endpoint and CA bundle."""
    import oci

    values = runtime if isinstance(runtime, dict) else {}
    endpoint = str(values.get("object_storage_endpoint_url") or "").strip()
    ca_bundle = str(values.get("object_storage_ca_bundle_path") or "").strip()
    kwargs: dict[str, object] = {"signer": signer}
    if endpoint:
        kwargs["service_endpoint"] = endpoint
    client = oci.object_storage.ObjectStorageClient({}, **kwargs)
    # OCI SDK configuration does not map an arbitrary CA path to its session.
    if ca_bundle:
        client.base_client.session.verify = ca_bundle
    return client


def resolve_object_storage_namespace(
    signer: object,
    runtime: dict[str, Any] | None,
    *,
    client: object | None = None,
) -> tuple[str, str]:
    """Return ``(namespace, source)`` using config first, then Instance Principal.

    The fallback is cached per endpoint/CA combination.  It never writes the
    host configuration: containers intentionally receive that file read-only.
    """
    configured = configured_object_storage_namespace(runtime)
    if configured:
        return configured, "CONFIGURED"

    values = runtime if isinstance(runtime, dict) else {}
    cache_key = (
        str(values.get("object_storage_endpoint_url") or "").strip(),
        str(values.get("object_storage_ca_bundle_path") or "").strip(),
    )
    now = time.monotonic()
    with _namespace_cache_lock:
        cached = _namespace_cache.get(cache_key)
        if cached and cached[0] > now:
            return cached[1], "AUTO_DISCOVERED"

    storage = client if client is not None else object_storage_client(signer, values)
    namespace = str(storage.get_namespace().data or "").strip()
    if not namespace:
        raise RuntimeError("OCI Object Storage returned an empty namespace for the Instance Principal")
    with _namespace_cache_lock:
        _namespace_cache[cache_key] = (now + _NAMESPACE_CACHE_TTL_SECONDS, namespace)
    return namespace, "AUTO_DISCOVERED"


def clear_namespace_cache() -> None:
    """Test support; production callers do not need to invalidate tenancy metadata."""
    with _namespace_cache_lock:
        _namespace_cache.clear()
