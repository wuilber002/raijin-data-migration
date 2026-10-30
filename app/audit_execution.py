"""Role-specific orchestration for the Raikou::Kai audit worker."""

from __future__ import annotations

from app.real_worker import (
    DeepAuditQueuePaused, GracefulWorkerShutdown, RAIKOU_AUDIT_TASK_KINDS,
    SessionLocal, SimulatedNetworkRecoveryPending, classify_task_error,
    claim_task, cloud_backend, fail_permanently, release_task_for_graceful_shutdown,
    retry, runtime_context, runtime_settings, task_lease_heartbeat, verify_wave,
)
from app.runtime_context import mode_switch_requested


ROLE = "raikou-kai"
# Controlled Phase 2 rollout probe. This inert marker proves that the audit
# worker can be replaced independently of the other runtime components.
ROLLOUT_PROBE = "phase2-audit-1"


def run_once(role: str = ROLE) -> None:
    """Claim and verify one wave while maintaining its durable lease."""
    if role != ROLE:
        raise RuntimeError(f"Audit execution does not support role {role!r}")
    if mode_switch_requested():
        return
    if runtime_context.is_simulation:
        cloud_backend.readiness(require_operations=True)
    with SessionLocal() as session:
        settings = runtime_settings(session)
        allowed_task_kinds = RAIKOU_AUDIT_TASK_KINDS
        if settings.deep_audit_queue_paused:
            allowed_task_kinds = frozenset()
        task = claim_task(session, settings.task_lease_seconds, allowed_task_kinds)
        if not task:
            return
        try:
            if task.kind != "VERIFY_WAVE":
                raise RuntimeError(f"Unsupported audit worker task {task.kind}")
            with task_lease_heartbeat(task.id, settings.task_lease_seconds):
                verify_wave(session, task)
        except DeepAuditQueuePaused:
            session.rollback()
        except GracefulWorkerShutdown as error:
            release_task_for_graceful_shutdown(session, task, str(error))
        except Exception as error:
            disposition, summary = classify_task_error(error)
            if disposition == "retry":
                retry(session, task, summary, seconds=1 if isinstance(error, SimulatedNetworkRecoveryPending) else None)
            else:
                fail_permanently(session, task, summary)
