"""Dedicated Raikō::Shin controller process.

The controller is deliberately isolated from the restore, discovery, audit and
transfer consumers.  It only commits short planning/reconciliation
transactions; SIGTERM is observed between those transactions, which provides a
safe boundary for a controller-only rollout.
"""

from __future__ import annotations

import json
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

from app.real_worker import request_worker_shutdown, run_once, worker_loop_sleep_seconds, worker_shutdown_requested


ROLE = "raikou-shin"
# Controlled Phase 2 rollout probe: controller-only replacement validation.
ROLLOUT_PROBE = "phase2-controller-1"
HEARTBEAT_FILE = Path(os.getenv("RAIJIN_COMPONENT_HEARTBEAT_FILE", "/run/platform-status/raikou-shin.json"))


def write_heartbeat(*, state: str) -> None:
    """Publish a host-readable liveness proof after a transaction boundary."""
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
        print(f"controller heartbeat write failed: {type(error).__name__}", flush=True)


def main() -> None:
    signal.signal(signal.SIGTERM, request_worker_shutdown)
    signal.signal(signal.SIGINT, request_worker_shutdown)
    failure_delay = 5
    write_heartbeat(state="STARTING")
    while not worker_shutdown_requested():
        try:
            run_once(ROLE)
            failure_delay = 5
            write_heartbeat(state="READY")
        except Exception as error:
            print(f"controller worker loop error: {type(error).__name__}: {error}", flush=True)
            write_heartbeat(state="RETRYING")
            if worker_shutdown_requested():
                break
            # Keep the same bounded failure cadence as the generic worker,
            # without retaining a reference to its internal event.
            time.sleep(failure_delay)
            failure_delay = min(60, failure_delay * 2)
            continue
        time.sleep(worker_loop_sleep_seconds(ROLE))
    write_heartbeat(state="STOPPED")
    print("controller worker stopped after transaction boundary", flush=True)


if __name__ == "__main__":
    main()
