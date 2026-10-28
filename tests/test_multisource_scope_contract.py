"""Contract tests for the project/runtime boundaries of multi-source Raijin."""

import os
from datetime import datetime, timezone
from pathlib import Path

_password = Path("/tmp/raijin-multisource-test-password")
_password.write_text("test", encoding="utf-8")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("POSTGRES_PASSWORD_FILE", str(_password))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import (
    Base, DynamicPipelineRun, MigrationProject, ProjectRestoreAdmissionState,
    RuntimeLaneControlState, RuntimeLaneMeasurement, RuntimeSettings, Source,
    TransferLaneMeasurement, Wave, hierarchical_lane_capacity_profile,
    project_restore_admission_allocations, record_event, Event,
)


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_cold_source_uses_project_evidence_before_runtime_fallback():
    session = _session()
    project = MigrationProject(id=1, name="multi")
    session.add(project); session.flush()
    measured = Source(id=1, name="measured", s3_bucket="a", aws_region="us-east-1",
                      destination_bucket="a-d", migration_project_id=project.id)
    cold = Source(id=2, name="cold", s3_bucket="b", aws_region="us-east-1",
                  destination_bucket="b-d", migration_project_id=project.id)
    session.add_all([measured, cold]); session.flush()
    session.add(TransferLaneMeasurement(id=1, source_id=measured.id,
                                        observed_at=datetime.now(timezone.utc),
                                        aggregate_mbps=700, active_workers=5))
    session.commit()

    profile = hierarchical_lane_capacity_profile(session, cold.id, 1100)

    assert profile["scope"] == "PROJECT"
    assert profile["basis"] == "PROJECT_LANE_MEASUREMENTS"
    assert profile["effective_mbps"] == 700


def test_restore_admission_is_global_and_fair_between_projects():
    session = _session()
    settings = RuntimeSettings(id=1, dynamic_restore_max_slots=2)
    alpha, beta = MigrationProject(id=1, name="alpha"), MigrationProject(id=2, name="beta")
    session.add_all([settings, alpha, beta]); session.flush()
    for index, (project, name) in enumerate(((alpha, "a"), (beta, "b")), start=1):
        source = Source(id=index, name=name, s3_bucket=f"{name}-bucket", aws_region="us-east-1",
                        destination_bucket=f"{name}-dest", migration_project_id=project.id)
        session.add(source); session.flush()
        run = DynamicPipelineRun(id=index, source_id=source.id, scheduled_restores=True, status="RUNNING")
        session.add(run); session.flush()
        session.add(Wave(id=index, source_id=source.id, pipeline_run_id=run.id, name=f"{name}-wave",
                         max_bytes=1, restore_days=1, restore_tier="BULK", status="RESTORE_SCHEDULED"))
    session.commit()

    allocation = project_restore_admission_allocations(session, settings)
    states = list(session.query(ProjectRestoreAdmissionState).order_by(
        ProjectRestoreAdmissionState.migration_project_id))

    assert {item["grant"] for item in allocation.values()} == {1}
    assert [state.admitted_slots for state in states] == [1, 1]
    assert all("fair grant=1" in state.decision_reason for state in states)


def test_event_infers_project_context_from_source_and_wave():
    session = _session()
    project = MigrationProject(id=1, name="audit")
    session.add(project); session.flush()
    source = Source(id=1, name="source", s3_bucket="audit", aws_region="us-east-1",
                    destination_bucket="audit-d", migration_project_id=project.id)
    session.add(source); session.flush()
    wave = Wave(id=1, source_id=source.id, name="audit-wave", max_bytes=1,
                restore_days=1, restore_tier="BULK")
    session.add(wave); session.flush()

    record_event(session, "SOURCE_CONTEXT", "source event", source_id=source.id)
    next(item for item in session.new if isinstance(item, Event)).id = 1
    session.flush()
    record_event(session, "WAVE_CONTEXT", "wave event", wave_id=wave.id)
    next(item for item in session.new if isinstance(item, Event)).id = 2
    session.commit()

    assert {event.migration_project_id for event in session.query(Event)} == {project.id}


def test_runtime_lane_controller_is_a_single_durable_row():
    session = _session()
    state = RuntimeLaneControlState(id=1, target_workers=5, observed_lane_mbps=800)
    session.add(state); session.commit()
    restored = session.get(RuntimeLaneControlState, 1)
    assert restored.target_workers == 5
    assert restored.observed_lane_mbps == 800
