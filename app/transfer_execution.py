"""Role-specific orchestration for the Raiju transfer worker."""

from __future__ import annotations

import oci

from app.oci_runtime import resolve_object_storage_namespace
from app.real_worker import (
    GracefulWorkerShutdown, MigrationProject, SessionLocal,
    Source, Task, TaskState, TRANSFER_TASK_KINDS, Wave,
    classify_task_error, claim_task, cloud_backend, fail_permanently, or_,
    event, read_oci_runtime_config,
    reconcile_completed_continuous_item_leases, release_task_for_graceful_shutdown,
    retry, runtime_context, runtime_settings, select, transfer_continuous, utcnow,
)


ROLE = "raiju"
# Controlled Phase 2 rollout probe. This inert marker proves that the Raiju
# transfer worker can restart independently and retain its durable checkpoint.
ROLLOUT_PROBE = "phase2-transfer-1"
LEGACY_NAMESPACE_CONFIGURATION_ERROR = "OCI Object Storage namespace is absent from runtime configuration"


def recover_legacy_namespace_blocked_transfers(session) -> int:
    """Requeue only transfers blocked by the pre-auto-discovery worker.

    This lives at the Raiju entrypoint intentionally: it makes the corrective
    release eligible for an isolated transfer-worker rollout while a live lane
    is active.  No restore, discovery or source configuration is changed.
    """
    tasks = list(session.scalars(select(Task).join(Wave).join(Source).where(
        Task.kind == "TRANSFER_CONTINUOUS",
        Task.state == TaskState.FAILED,
        Task.error.contains(LEGACY_NAMESPACE_CONFIGURATION_ERROR),
        Wave.status != "PAUSED",
        Source.archived_at.is_(None),
    )))
    if not tasks:
        return 0
    try:
        resolve_object_storage_namespace(
            oci.auth.signers.InstancePrincipalsSecurityTokenSigner(),
            read_oci_runtime_config(),
        )
    except Exception:
        return 0
    for task in tasks:
        task.state, task.worker_id, task.lease_expires_at = TaskState.READY, None, None
        task.available_at, task.error = utcnow(), None
        wave = session.get(Wave, task.wave_id)
        if wave:
            wave.status = "TRANSFER_DRAINING"
            event(
                session,
                "TRANSFER_NAMESPACE_AUTO_RECOVERED",
                "Raiju resumed a legacy namespace-blocked transfer after OCI namespace auto-discovery; no new AWS restore was submitted.",
                source_id=wave.source_id,
                wave_id=wave.id,
            )
    session.commit()
    return len(tasks)


def run_once(role: str = ROLE) -> None:
    """Reconcile durable transfer leases then execute one transfer task."""
    if role not in {ROLE, "transfer"}:
        raise RuntimeError(f"Transfer execution does not support role {role!r}")
    with SessionLocal() as session:
        settings = runtime_settings(session)
        recover_legacy_namespace_blocked_transfers(session)
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
                retry(session, task, summary)
            else:
                fail_permanently(session, task, summary)
