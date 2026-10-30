"""Role-specific orchestration for the Raiju transfer worker."""

from __future__ import annotations

from app.real_worker import (
    GracefulWorkerShutdown, MigrationProject, SessionLocal,
    SimulatedNetworkRecoveryPending, Source, TRANSFER_TASK_KINDS,
    classify_task_error, claim_task, cloud_backend, fail_permanently, or_,
    reconcile_completed_continuous_item_leases, release_task_for_graceful_shutdown,
    retry, runtime_context, runtime_settings, select, transfer_continuous,
)
from app.runtime_context import mode_switch_requested


ROLE = "raiju"
# Controlled Phase 2 rollout probe. This inert marker proves that the Raiju
# transfer worker can restart independently and retain its durable checkpoint.
ROLLOUT_PROBE = "phase2-transfer-1"


def run_once(role: str = ROLE) -> None:
    """Reconcile durable transfer leases then execute one transfer task."""
    if role not in {ROLE, "transfer"}:
        raise RuntimeError(f"Transfer execution does not support role {role!r}")
    if mode_switch_requested():
        return
    if runtime_context.is_simulation:
        cloud_backend.readiness(require_operations=True)
    with SessionLocal() as session:
        settings = runtime_settings(session)
        reconciled = sum(
            reconcile_completed_continuous_item_leases(session, source)
            for source in session.scalars(select(Source).outerjoin(MigrationProject, Source.migration_project_id == MigrationProject.id).where(Source.archived_at.is_(None), or_(MigrationProject.id.is_(None), MigrationProject.status != "PAUSED")))
        )
        if reconciled:
            session.commit()
        task = claim_task(session, settings.task_lease_seconds, TRANSFER_TASK_KINDS)
        if not task:
            return
        try:
            if task.kind != "TRANSFER_CONTINUOUS":
                raise RuntimeError(f"Unsupported transfer worker task {task.kind}")
            transfer_continuous(session, task, settings)
        except GracefulWorkerShutdown as error:
            release_task_for_graceful_shutdown(session, task, str(error))
        except Exception as error:
            disposition, summary = classify_task_error(error)
            if disposition == "retry":
                retry(session, task, summary, seconds=1 if isinstance(error, SimulatedNetworkRecoveryPending) else None)
            else:
                fail_permanently(session, task, summary)
