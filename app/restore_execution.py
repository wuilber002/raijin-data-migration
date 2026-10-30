"""Role-specific orchestration for the Raikou::Sei restore worker.

Only durable restore task claiming and dispatch live here. Shared task
primitives stay in ``real_worker`` so the first extraction is backwards
compatible; changes to those shared primitives still require a full rollout.
"""

from __future__ import annotations

from app.real_worker import (
    DeepAuditQueuePaused,
    GracefulWorkerShutdown,
    RAIKOU_RESTORE_TASK_KINDS,
    SessionLocal,
    SimulatedNetworkRecoveryPending,
    classify_task_error,
    claim_task,
    cloud_backend,
    fail_permanently,
    poll_restore,
    release_task_for_graceful_shutdown,
    retry,
    runtime_context,
    runtime_settings,
    submit_restore,
)
from app.runtime_context import mode_switch_requested


ROLE = "raikou-sei"
# Controlled Phase 2 rollout probe: restore-only replacement validation.
ROLLOUT_PROBE = "phase2-restore-1"


def run_once(role: str = ROLE) -> None:
    """Claim and execute one restore task at a durable task boundary."""
    if role != ROLE:
        raise RuntimeError(f"Restore execution does not support role {role!r}")
    if mode_switch_requested():
        return
    if runtime_context.is_simulation:
        cloud_backend.readiness(require_operations=True)
    with SessionLocal() as session:
        settings = runtime_settings(session)
        allowed_task_kinds = RAIKOU_RESTORE_TASK_KINDS
        task = claim_task(session, settings.task_lease_seconds, allowed_task_kinds)
        if not task:
            return
        try:
            if task.kind == "SUBMIT_BATCH_RESTORE":
                submit_restore(session, task, settings)
            elif task.kind == "POLL_RESTORE":
                poll_restore(session, task, settings)
            else:
                raise RuntimeError(f"Unsupported restore worker task {task.kind}")
        except DeepAuditQueuePaused:
            session.rollback()
        except GracefulWorkerShutdown as error:
            release_task_for_graceful_shutdown(session, task, str(error))
        except Exception as error:
            disposition, summary = classify_task_error(error)
            if disposition == "retry":
                retry(
                    session,
                    task,
                    summary,
                    seconds=1 if isinstance(error, SimulatedNetworkRecoveryPending) else None,
                )
            else:
                fail_permanently(session, task, summary)
