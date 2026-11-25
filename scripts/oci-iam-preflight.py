#!/usr/bin/env python3
"""Write a secret-free OCI IAM preflight report for the Raijin installer."""

from __future__ import annotations

import argparse
import json
import os
import tempfile

from app.oci_iam_preflight import read_and_build


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = read_and_build(args.runtime_config)
    directory = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(directory, mode=0o700, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".oci-iam-preflight-", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
            json.dump(report, destination, indent=2, sort_keys=True)
            destination.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, args.output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == "__main__":
    main()
