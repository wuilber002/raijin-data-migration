#!/usr/bin/env python3
"""Materialize one configured secret source into a root-only local file.

The default source is OCI Vault through the VM instance principal. A protected
local file is also supported for a deliberately offline/bootstrap deployment.
Secret values are never printed.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import stat
import tempfile
from pathlib import Path

import oci


def validate_secret_value(name: str, value: str) -> str:
    value = value.strip()
    if not value or value.startswith("REPLACE_THIS_PLACEHOLDER"):
        raise RuntimeError(f"Secret {name} is empty or still a placeholder")
    return value


def read_local_secret(path_value: object, secret_name: str) -> str:
    path = Path(str(path_value))
    if not path.is_absolute():
        raise RuntimeError(f"Local Secret file for {secret_name} must use an absolute path")
    try:
        path_stat = path.lstat()
    except OSError as error:
        raise RuntimeError(f"Local Secret file for {secret_name} is unavailable") from error
    if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISREG(path_stat.st_mode):
        raise RuntimeError(f"Local Secret file for {secret_name} must be a regular file")
    if path_stat.st_uid != 0 or path_stat.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise RuntimeError(f"Local Secret file for {secret_name} must be root-owned and mode 0600 or stricter")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened_stat = os.fstat(descriptor)
        if not stat.S_ISREG(opened_stat.st_mode) or opened_stat.st_uid != 0:
            raise RuntimeError(f"Local Secret file for {secret_name} changed while being opened")
        with os.fdopen(descriptor, "r", encoding="utf-8") as source_file:
            descriptor = -1
            return validate_secret_value(secret_name, source_file.read())
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def resolve_secret_value(runtime: dict, secret_name: str) -> str:
    secret_ocid = (runtime.get("secret_ocids") or {}).get(secret_name)
    local_path = (runtime.get("secret_file_paths") or {}).get(secret_name)
    if bool(secret_ocid) == bool(local_path):
        raise RuntimeError(f"Configure exactly one source for Secret {secret_name}: secret_ocids or secret_file_paths")
    if local_path:
        return read_local_secret(local_path, secret_name)

    signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    client = oci.secrets.SecretsClient({}, signer=signer)
    bundle = client.get_secret_bundle(secret_ocid).data
    return validate_secret_value(
        secret_name,
        base64.b64decode(bundle.secret_bundle_content.content).decode("utf-8"),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-config", required=True)
    parser.add_argument("--secret-name", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    with open(args.runtime_config, encoding="utf-8") as config_file:
        runtime = json.load(config_file)
    value = resolve_secret_value(runtime, args.secret_name)

    directory = os.path.dirname(args.output)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(prefix=".secret-", dir=directory)
    try:
        os.fchmod(descriptor, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output_file:
            output_file.write(value)
            output_file.write("\n")
        os.replace(temporary_path, args.output)
        os.chmod(args.output, stat.S_IRUSR | stat.S_IWUSR)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


if __name__ == "__main__":
    main()
