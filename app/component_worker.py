"""Isolated entrypoint for a non-controller Raijin worker component.

The execution functions remain in :mod:`app.real_worker` while the rollout
boundary, signal handling and liveness evidence are independent per role.
This is the prerequisite for later extraction of role-specific execution code.
"""

from __future__ import annotations

import json
import os
import signal
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from app.real_worker import request_worker_shutdown, run_once, worker_loop_sleep_seconds, worker_shutdown_requested


ROLE = os.getenv("RAIJIN_WORKER_ROLE", "").strip().lower()
SUPPORTED_ROLES = frozenset({"raikou-sei", "raikou-ko", "raikou-kai", "raiju"})
HEARTBEAT_FILE = Path(os.getenv("RAIJIN_COMPONENT_HEARTBEAT_FILE", f"/run/platform-status/{ROLE}.json"))


def write_heartbeat(*, state: str) -> None:
    try:
        HEARTBEAT_FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = HEARTBEAT_FILE.with_suffix(".tmp")
        temporary.write_text(json.dumps({
            "component": ROLE,
            "state": state,
            "revision": os.getenv("RAIJIN_BUILD_REVISION", "unknown"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, separators=(",", ":")), encoding="utf-8")
        temporary.replace(HEARTBEAT_FILE)
    except OSError as error:
        print(f"{ROLE} heartbeat write failed: {type(error).__name__}", flush=True)


def main(execute_once: Callable[[str], None] = run_once) -> None:
    if ROLE not in SUPPORTED_ROLES:
        raise RuntimeError(f"Unsupported component worker role: {ROLE or 'unset'}")
    signal.signal(signal.SIGTERM, request_worker_shutdown)
    signal.signal(signal.SIGINT, request_worker_shutdown)
    failure_delay = 5
    write_heartbeat(state="STARTING")
    while not worker_shutdown_requested():
        try:
            execute_once(ROLE)
            failure_delay = 5
            write_heartbeat(state="READY")
        except Exception as error:
            print(f"{ROLE} worker loop error: {type(error).__name__}: {error}", flush=True)
            write_heartbeat(state="RETRYING")
            # A failure is bounded before retry. SIGTERM may still be observed
            # at the following loop boundary, which is sufficient for the
            # host's controlled replacement timeout.
            time.sleep(failure_delay)
            failure_delay = min(60, failure_delay * 2)
            continue
        time.sleep(worker_loop_sleep_seconds(ROLE))
    write_heartbeat(state="STOPPED")
    print(f"{ROLE} worker stopped after durable work boundary", flush=True)


if __name__ == "__main__":
    main()
