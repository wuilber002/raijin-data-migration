#!/usr/bin/env python3
"""Create the dated Raijin validation corpus as sparse files.

`os.truncate` avoids allocating the logical payload locally.  It is used here
instead of one shell process per file because the corpus intentionally has
tens of thousands of objects.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


PROFILES = (
    ("Smoke_test", "small", 1_800, 64 * 1024),
    ("Smoke_test", "medium", 180, 4 * 1024 * 1024),
    ("Smoke_test", "large", 20, 64 * 1024 * 1024),
    ("Operational_test", "small", 16_000, 64 * 1024),
    ("Operational_test", "medium", 3_000, 4 * 1024 * 1024),
    ("Operational_test", "large", 60, 300 * 1024 * 1024),
    ("Resilience_test", "multipart", 2, 4 * 1024 * 1024 * 1024),
)


def main() -> None:
    target = Path(sys.argv[1]).resolve()
    target.mkdir(parents=True, exist_ok=True)
    files = 0
    logical_bytes = 0
    for prefix, group, count, size in PROFILES:
        directory = target / prefix / group
        directory.mkdir(parents=True, exist_ok=True)
        for index in range(1, count + 1):
            path = directory / f"{index:06d}.bin"
            path.touch(exist_ok=True)
            os.truncate(path, size)
            files += 1
            logical_bytes += size
    print(f"files={files}")
    print(f"logical_bytes={logical_bytes}")
    print(f"logical_gib={logical_bytes / 1024 ** 3:.3f}")


if __name__ == "__main__":
    main()
