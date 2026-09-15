from sqlalchemy import create_engine

from app.backend_contracts import ObjectIdentity
import asyncio
import os
import time

import app.fujin_payloads as payloads
from app.fujin_payloads import (
    FujinPayloadError,
    FujinPayloadRepository,
    LocalFilesystemPayloadReader,
    PayloadReference,
    PayloadSnapshotError,
    payload_read_limits,
)
from app.simulated_data import consume_and_discard
from app.simulation_engine import SimulationEngine
from app.simulation_migrations import migrate
from app.simulator_store import ScenarioCreate, SimulatorStore
from app import simulator


def _ready_dataset(store, root):
    repository = FujinPayloadRepository(store, root=root)
    dataset = repository.create_dataset(
        name="physical-sample", quota_bytes=2_000, seed="payload-seed",
        profile={"file_count": 2, "file_size_bytes": 100}, model="REPRESENTATIVE",
    )
    for _ in range(4):
        repository.process_generation_jobs()
    return repository, dataset


def test_representative_payload_streams_generated_file_and_respects_restore(tmp_path, monkeypatch):
    monkeypatch.setenv("RAIJIN_FUJIN_PAYLOAD_ROOT", str(tmp_path))
    database = create_engine("sqlite+pysqlite:///:memory:")
    migrate(database)
    store = SimulatorStore(database)
    repository, dataset = _ready_dataset(store, tmp_path)
    assert repository.list_datasets()[0]["state"] == "READY"
    assert repository.validate_dataset(dataset.id)["state"] == "VALID"
    validated = repository.list_datasets()[0]
    assert validated["last_validation_state"] == "VALID"
    assert validated["last_validated_at"] is not None

    scenario = store.create_scenario(ScenarioCreate(
        name="physical-data", fidelity="DATA", seed="scenario-seed", logical_size_bytes=400,
        physical_budget_bytes=2_000, configuration={"bulk_restore_min_hours": 0, "bulk_restore_max_hours": 0},
    ))
    engine = SimulationEngine(store)
    result = engine.materialize(
        scenario.id, source_bucket="source", destination_bucket="destination", region="us-east-1",
        object_count=4, logical_size_bytes=400, prefixes=["sample"], storage_class="DEEP_ARCHIVE",
        payload_model="REPRESENTATIVE", payload_dataset_id=dataset.id,
    )
    assert result["payload_model"] == "REPRESENTATIVE"
    assert result["physical_object_count"] == 4
    execution = store.create_execution(scenario.id)
    item = engine.list_objects(execution.id, "source", "", None, 1).objects[0]

    try:
        list(engine.read_range(execution.id, "source", item.key, 0, item.size_bytes))
        assert False, "archived physical object must remain unavailable"
    except PermissionError:
        pass
    assert engine.restore_object(execution.id, "source", item.key, "BULK", 1, "restore-1").accepted
    content = consume_and_discard(engine.read_range(execution.id, "source", item.key, 0, item.size_bytes))
    assert content.size_bytes == 100
    assert content.checksum_sha256 == item.checksum
    report = store.execution_report(execution.id)
    assert report["physical_local_bytes_read"] == 100
    assert report["physical_read_operations"] == 1
    assert report["physical_read_seconds"] >= 0


def test_physical_snapshot_change_fails_explicitly(tmp_path, monkeypatch):
    monkeypatch.setenv("RAIJIN_FUJIN_PAYLOAD_ROOT", str(tmp_path))
    database = create_engine("sqlite+pysqlite:///:memory:")
    migrate(database)
    store = SimulatorStore(database)
    repository, dataset = _ready_dataset(store, tmp_path)
    reference = repository.dataset_reference(dataset.id, 0)
    path = tmp_path / reference.relative_path
    path.write_bytes(b"changed")
    try:
        list(LocalFilesystemPayloadReader(tmp_path, reference).stream_range(0, 1))
        assert False, "changed physical sample must invalidate the snapshot"
    except PayloadSnapshotError:
        pass
    try:
        repository.validate_dataset(dataset.id)
        assert False, "administrative validation must persist the invalid snapshot"
    except PayloadSnapshotError:
        pass
    invalid = repository.list_datasets()[0]
    assert invalid["last_validation_state"] == "INVALID"
    assert "immutable snapshot" in invalid["last_validation_error"]


def test_durable_validation_resumes_one_file_at_a_time(tmp_path, monkeypatch):
    monkeypatch.setenv("RAIJIN_FUJIN_PAYLOAD_ROOT", str(tmp_path))
    database = create_engine("sqlite+pysqlite:///:memory:")
    migrate(database)
    store = SimulatorStore(database)
    repository, dataset = _ready_dataset(store, tmp_path)

    queued = repository.enqueue_validation(dataset.id)
    assert queued["state"] == "READY"
    assert repository.list_datasets()[0]["last_validation_state"] == "QUEUED"

    first = repository.process_validation_jobs(max_files=1)
    assert first["validated_files"] == 1
    progress = repository.list_datasets()[0]["validation_job"]
    assert progress["files_validated"] == 1
    assert progress["files_total"] == 2
    assert repository.list_datasets()[0]["last_validation_state"] == "VALIDATING"

    repository.process_validation_jobs(max_files=1)
    repository.process_validation_jobs(max_files=1)
    result = repository.list_datasets()[0]
    assert result["last_validation_state"] == "VALID"
    assert result["validation_job"]["state"] == "SUCCEEDED"
    assert result["validation_job"]["bytes_validated"] == 200


def test_control_rejects_physical_models(tmp_path):
    database = create_engine("sqlite+pysqlite:///:memory:")
    migrate(database)
    store = SimulatorStore(database)
    scenario = store.create_scenario(ScenarioCreate(name="control", fidelity="CONTROL", seed="seed", logical_size_bytes=100))
    try:
        SimulationEngine(store).materialize(
            scenario.id, source_bucket="source", destination_bucket="destination", region="us-east-1",
            object_count=1, logical_size_bytes=100, prefixes=["x"], storage_class="STANDARD",
            payload_model="REPRESENTATIVE", payload_dataset_id="missing",
        )
        assert False, "CONTROL must stay logical-only"
    except ValueError as error:
        assert "DATA" in str(error)


def test_physical_materialization_freezes_cache_and_reader_limits(tmp_path, monkeypatch):
    monkeypatch.setenv("RAIJIN_FUJIN_PAYLOAD_ROOT", str(tmp_path))
    database = create_engine("sqlite+pysqlite:///:memory:")
    migrate(database)
    store = SimulatorStore(database)
    repository, dataset = _ready_dataset(store, tmp_path)
    scenario = store.create_scenario(ScenarioCreate(
        name="frozen-physical-controls", fidelity="DATA", seed="limits-seed",
        logical_size_bytes=200, physical_budget_bytes=1_000,
        configuration={
            "payload_cache_mode": "WARM",
            "payload_resource_limits": {
                "chunk_bytes": 4096, "max_open_files": 2, "max_read_mbps": 12,
            },
        },
    ))
    SimulationEngine(store).materialize(
        scenario.id, source_bucket="source", destination_bucket="destination", region="us-east-1",
        object_count=2, logical_size_bytes=200, prefixes=["sample"], storage_class="STANDARD",
        payload_model="REPRESENTATIVE", payload_dataset_id=dataset.id,
    )
    execution = store.create_execution(scenario.id)
    report = store.execution_report(execution.id)
    assert report["payload"]["cache_mode"] == "WARM"
    assert report["payload"]["resource_limits"] == {
        "chunk_bytes": 4096, "max_open_files": 2, "max_read_mbps": 12.0,
    }


def test_local_reader_rejects_path_escape_symlink_and_special_file(tmp_path):
    database = create_engine("sqlite+pysqlite:///:memory:")
    migrate(database)
    store = SimulatorStore(database)
    repository, dataset = _ready_dataset(store, tmp_path)
    reference = repository.dataset_reference(dataset.id, 0)

    escaped = PayloadReference(
        dataset_id=reference.dataset_id, relative_path="../outside.bin", size_bytes=reference.size_bytes,
        mtime_ns=reference.mtime_ns, identity=reference.identity, sha256=reference.sha256,
    )
    try:
        list(LocalFilesystemPayloadReader(tmp_path, escaped).stream_range(0, 1))
        assert False, "a reader must never traverse outside its managed root"
    except FujinPayloadError:
        pass

    target = tmp_path / reference.relative_path
    target.unlink()
    target.symlink_to(tmp_path / "outside.bin")
    try:
        list(LocalFilesystemPayloadReader(tmp_path, reference).stream_range(0, 1))
        assert False, "a managed payload symlink must be rejected"
    except PayloadSnapshotError:
        pass

    target.unlink()
    if hasattr(os, "mkfifo"):
        os.mkfifo(target)
        try:
            list(LocalFilesystemPayloadReader(tmp_path, reference).stream_range(0, 1))
            assert False, "a FIFO must not be treated as a physical source file"
        except PayloadSnapshotError:
            pass


def test_local_reader_surfaces_permission_and_resource_limit_failures(tmp_path, monkeypatch):
    database = create_engine("sqlite+pysqlite:///:memory:")
    migrate(database)
    store = SimulatorStore(database)
    repository, dataset = _ready_dataset(store, tmp_path)
    reference = repository.dataset_reference(dataset.id, 0)
    reader = LocalFilesystemPayloadReader(tmp_path, reference)
    monkeypatch.setattr(payloads.os, "open", lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError("denied")))
    for _ in range(2):
        try:
            list(reader.stream_range(0, 1))
            assert False, "permission errors must be explicit and release the descriptor slot"
        except PayloadSnapshotError:
            pass
    for invalid in (
        {"payload_resource_limits": {"chunk_bytes": 1}},
        {"payload_resource_limits": {"max_open_files": 0}},
        {"payload_resource_limits": {"max_read_mbps": -1}},
    ):
        try:
            payload_read_limits(invalid)
            assert False, "unsafe reader bounds must be rejected"
        except FujinPayloadError:
            pass


def test_background_generation_does_not_block_simulator_event_loop(monkeypatch):
    stop = asyncio.Event()
    loop = {}

    class SlowRepository:
        def process_generation_jobs(self, max_files):
            assert max_files == 1
            time.sleep(0.15)
            loop["event_loop"].call_soon_threadsafe(stop.set)

        def process_validation_jobs(self, max_files):
            assert max_files == 1

    monkeypatch.setattr(simulator, "payload_repository", lambda: SlowRepository())

    async def run():
        loop["event_loop"] = asyncio.get_running_loop()
        task = asyncio.create_task(simulator.payload_generation(stop))
        started = time.monotonic()
        await asyncio.sleep(0.02)
        elapsed = time.monotonic() - started
        await asyncio.wait_for(task, timeout=2)
        return elapsed

    assert asyncio.run(run()) < 0.1
