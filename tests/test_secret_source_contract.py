import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("fetch_oci_secret", ROOT / "scripts" / "fetch-oci-secret.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_runtime_secret_source_requires_exactly_one_reference():
    with pytest.raises(RuntimeError, match="exactly one source"):
        MODULE.resolve_secret_value({"secret_ocids": {}, "secret_file_paths": {}}, "postgres_password")
    with pytest.raises(RuntimeError, match="exactly one source"):
        MODULE.resolve_secret_value(
            {
                "secret_ocids": {"postgres_password": "ocid1.vaultsecret.oc1..example"},
                "secret_file_paths": {"postgres_password": "/etc/s3-oci-migration/bootstrap/postgres_password"},
            },
            "postgres_password",
        )


def test_runtime_secret_source_rejects_unprotected_local_files(tmp_path):
    candidate = tmp_path / "postgres_password"
    candidate.write_text("not-a-root-secret\n", encoding="utf-8")
    candidate.chmod(0o644)

    with pytest.raises(RuntimeError, match="root-owned and mode 0600"):
        MODULE.resolve_secret_value(
            {"secret_file_paths": {"postgres_password": str(candidate)}},
            "postgres_password",
        )
