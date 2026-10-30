"""Role-specific orchestration for the Raikou::Kō discovery worker."""

from __future__ import annotations

from app.real_worker import (
    DiscoveryJob, MigrationProject, SessionLocal, Source, TaskState,
    claim_discovery_job, cloud_backend, discover, event,
    import_s3_inventory_manifest, or_, runtime_context, runtime_settings,
    select, utcnow,
)
from app.runtime_context import mode_switch_requested


ROLE = "raikou-ko"


def run_once(role: str = ROLE) -> None:
    """Recover, claim and execute one durable discovery job."""
    if role != ROLE:
        raise RuntimeError(f"Discovery execution does not support role {role!r}")
    if mode_switch_requested():
        return
    if runtime_context.is_simulation:
        cloud_backend.readiness(require_operations=True)
    with SessionLocal() as session:
        settings = runtime_settings(session)
        scope = Source.archived_at.is_(None), or_(MigrationProject.id.is_(None), MigrationProject.status != "PAUSED")
        interrupted = list(session.scalars(select(Source).outerjoin(MigrationProject, Source.migration_project_id == MigrationProject.id).where(Source.status == "DISCOVERING", *scope)))
        for pending_source in interrupted:
            pending_source.status, pending_source.discovery_started_at = "DISCOVERY_QUEUED", None
            pending_job = session.scalar(select(DiscoveryJob).where(DiscoveryJob.source_id == pending_source.id, DiscoveryJob.state == TaskState.RUNNING).order_by(DiscoveryJob.id.desc()).limit(1))
            if pending_job:
                pending_job.state, pending_job.worker_id, pending_job.lease_expires_at = TaskState.READY, None, None
                pending_job.available_at = utcnow()
            else:
                session.add(DiscoveryJob(source_id=pending_source.id))
            event(session, "DISCOVERY_RECOVERED", "Discovery worker interruption recovered from durable page checkpoint", source_id=pending_source.id)
        if interrupted:
            session.commit()
        legacy_queued = list(session.scalars(select(Source).outerjoin(MigrationProject, Source.migration_project_id == MigrationProject.id).where(Source.status == "DISCOVERY_QUEUED", *scope)))
        for queued_source in legacy_queued:
            exists = session.scalar(select(DiscoveryJob.id).where(DiscoveryJob.source_id == queued_source.id, DiscoveryJob.state.in_([TaskState.READY, TaskState.RUNNING])).limit(1))
            if not exists:
                session.add(DiscoveryJob(source_id=queued_source.id))
        if legacy_queued:
            session.commit()
        discovery_job = claim_discovery_job(session, settings.task_lease_seconds)
        if not discovery_job:
            return
        source = session.get(Source, discovery_job.source_id)
        if not source or source.status != "DISCOVERY_QUEUED":
            discovery_job.state, discovery_job.error, discovery_job.lease_expires_at, discovery_job.completed_at = TaskState.FAILED, "Source is no longer eligible for remote discovery", None, utcnow()
            session.commit()
            return
        try:
            if discovery_job.mode == "REMOTE_LIST":
                discover(session, source, settings, discovery_job)
            elif discovery_job.mode == "S3_INVENTORY_MANIFEST":
                import_s3_inventory_manifest(session, source, settings, discovery_job)
            else:
                raise RuntimeError(f"Unsupported discovery job mode {discovery_job.mode}")
        except Exception as error:
            finished_at = utcnow()
            if source.discovery_started_at:
                source.discovery_elapsed_seconds = float(source.discovery_elapsed_seconds or 0) + max(0, (finished_at - source.discovery_started_at).total_seconds())
            source.discovery_started_at = None
            source.status, source.discovery_error = "DISCOVERY_FAILED", str(error)[:8000]
            discovery_job.state, discovery_job.error, discovery_job.lease_expires_at, discovery_job.completed_at = TaskState.FAILED, source.discovery_error, None, finished_at
            event(session, "DISCOVERY_FAILED", source.discovery_error, source_id=source.id)
            session.commit()
