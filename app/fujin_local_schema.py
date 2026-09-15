"""Persistent, isolated catalogue for Fujin LOCAL.

LOCAL must never reuse the ``sim_*`` execution state.  This module owns only
the provider-side catalogue; it deliberately does not import Raijin models or
the Simulation schema.  Physical payload paths are always relative to the
Fujin-managed repository root.
"""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text, create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


LOCAL_SCHEMA_VERSION = 17


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class LocalBase(DeclarativeBase):
    pass


class LocalSchemaRevision(LocalBase):
    __tablename__ = "local_schema_revisions"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LocalProviderState(LocalBase):
    """The explicit LOCAL data-plane switch, owned solely by Fujin.

    A Raijin process never reads this table.  Keeping the provider disabled
    until an administrator enables it makes accidental use of synthetic
    endpoints much less likely while preserving Raijin's normal REAL mode.
    """
    __tablename__ = "local_provider_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LocalCloudProviderState(LocalBase):
    """Independent data-plane switch for each emulated cloud provider."""
    __tablename__ = "local_cloud_provider_states"

    provider: Mapped[str] = mapped_column(String(8), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LocalDataset(LocalBase):
    __tablename__ = "local_datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    state: Mapped[str] = mapped_column(String(24), default="READY", index=True)
    model: Mapped[str] = mapped_column(String(24), default="REPRESENTATIVE")
    snapshot_id: Mapped[str] = mapped_column(String(64), unique=True)
    repository_relative_path: Mapped[str] = mapped_column(String(1024), unique=True)
    manifest_json: Mapped[str] = mapped_column(Text, default="{}")
    quota_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    validated_objects: Mapped[int] = mapped_column(Integer, default=0)
    validated_bytes: Mapped[int] = mapped_column(BigInteger, default=0)


class LocalS3Bucket(LocalBase):
    __tablename__ = "local_s3_buckets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(63), unique=True, index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("local_datasets.id"), index=True)
    region: Mapped[str] = mapped_column(String(64), default="us-east-1")
    # Storage class belongs to the S3 projection, not to immutable payload
    # bytes.  Nullable preserves the legacy per-object manifest fallback while
    # existing catalogues are upgraded; every newly created bucket sets it.
    storage_class: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Project the immutable physical dataset into multiple independent S3
    # keyspaces without duplicating payload bytes on disk. Existing buckets
    # retain their original one-to-one namespace through the default value.
    logical_multiplier: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    account_id: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    control_bucket: Mapped[str] = mapped_column(String(63), unique=True)
    migration_role_arn: Mapped[str] = mapped_column(String(2048), unique=True)
    batch_role_arn: Mapped[str] = mapped_column(String(2048), unique=True)
    access_key_id: Mapped[str] = mapped_column(String(128), unique=True)
    secret_access_key: Mapped[str] = mapped_column(String(256))
    restore_policy_json: Mapped[str] = mapped_column(Text, default="{}")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LocalStsSession(LocalBase):
    __tablename__ = "local_sts_sessions"

    access_key_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    secret_access_key: Mapped[str] = mapped_column(String(256))
    session_token: Mapped[str] = mapped_column(String(1024), unique=True)
    bucket_id: Mapped[str] = mapped_column(ForeignKey("local_s3_buckets.id"), index=True)
    role_arn: Mapped[str] = mapped_column(String(2048))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LocalControlObject(LocalBase):
    """Small control-plane artifacts: manifests and Batch reports only."""
    __tablename__ = "local_control_objects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    bucket_id: Mapped[str] = mapped_column(ForeignKey("local_s3_buckets.id"), index=True)
    object_key: Mapped[str] = mapped_column(String(2048), index=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    etag: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LocalBatchJob(LocalBase):
    __tablename__ = "local_batch_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    bucket_id: Mapped[str] = mapped_column(ForeignKey("local_s3_buckets.id"), index=True)
    state: Mapped[str] = mapped_column(String(64), default="Complete", index=True)
    manifest_key: Mapped[str] = mapped_column(String(2048))
    total_objects: Mapped[int] = mapped_column(Integer, default=0)
    succeeded_objects: Mapped[int] = mapped_column(Integer, default=0)
    failed_objects: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LocalRestore(LocalBase):
    __tablename__ = "local_restores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    bucket_id: Mapped[str] = mapped_column(ForeignKey("local_s3_buckets.id"), index=True)
    object_key: Mapped[str] = mapped_column(String(2048), index=True)
    state: Mapped[str] = mapped_column(String(24), default="IN_PROGRESS", index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    request_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)


class LocalOciBucket(LocalBase):
    __tablename__ = "local_oci_buckets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    namespace: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    configuration_json: Mapped[str] = mapped_column(Text, default="{}")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LocalOciObject(LocalBase):
    __tablename__ = "local_oci_objects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    bucket_id: Mapped[str] = mapped_column(ForeignKey("local_oci_buckets.id"), index=True)
    object_key: Mapped[str] = mapped_column(String(2048), index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("local_datasets.id"), index=True)
    source_relative_path: Mapped[str] = mapped_column(String(2048))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    etag: Mapped[str] = mapped_column(String(128), index=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(256), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LocalMultipartUpload(LocalBase):
    __tablename__ = "local_multipart_uploads"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    bucket_id: Mapped[str] = mapped_column(ForeignKey("local_oci_buckets.id"), index=True)
    object_key: Mapped[str] = mapped_column(String(2048), index=True)
    staging_relative_path: Mapped[str] = mapped_column(String(2048))
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    source_dataset_id: Mapped[str | None] = mapped_column(ForeignKey("local_datasets.id"), nullable=True, index=True)
    source_relative_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class LocalMultipartPart(LocalBase):
    __tablename__ = "local_multipart_parts"

    upload_id: Mapped[str] = mapped_column(ForeignKey("local_multipart_uploads.id"), primary_key=True)
    part_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    staging_relative_path: Mapped[str] = mapped_column(String(2048))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    etag: Mapped[str] = mapped_column(String(128))
    checksum_sha256: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source_verified: Mapped[bool] = mapped_column(Boolean, default=False)


class LocalAuditEvent(LocalBase):
    __tablename__ = "local_audit_events"

    # SQLite requires the literal INTEGER type for auto-increment primary
    # keys; production PostgreSQL still maps it to its normal integer serial.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    operation: Mapped[str] = mapped_column(String(128), index=True)
    bucket: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    object_key: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    status_code: Mapped[int] = mapped_column(Integer)
    detail: Mapped[str] = mapped_column(Text, default="")
    endpoint: Mapped[str | None] = mapped_column(String(2300), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bytes_transferred: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    retry_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    caller_identity: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


def migrate(database_url: str) -> None:
    """Explicit LOCAL migration; never invoked by Raijin application startup."""
    engine = create_engine(database_url)
    LocalBase.metadata.create_all(engine)
    # ``create_all`` does not add columns to a database created by an earlier
    # LOCAL preview.  Keep this narrow, idempotent migration explicit and
    # isolated from Raijin's own database migrations.
    expected_audit_columns = {
        "endpoint": "VARCHAR(2300)", "latency_ms": "INTEGER",
        "bytes_transferred": "BIGINT", "retry_count": "INTEGER",
        "caller_identity": "VARCHAR(512)", "error_code": "VARCHAR(128)",
    }
    existing_audit_columns = {column["name"] for column in inspect(engine).get_columns("local_audit_events")}
    with engine.begin() as connection:
        for name, definition in expected_audit_columns.items():
            if name not in existing_audit_columns:
                connection.exec_driver_sql(f"ALTER TABLE local_audit_events ADD COLUMN {name} {definition}")
        # Content-Length on HEAD is object metadata, not bytes carried in the
        # response. Repair observations produced before this distinction was
        # enforced by the request middleware.
        connection.exec_driver_sql(
            "UPDATE local_audit_events SET bytes_transferred = NULL "
            "WHERE operation = 'S3_HEAD_OBJECT' AND bytes_transferred IS NOT NULL"
        )
    expected_resource_columns = {
        "local_s3_buckets": {
            "deleted_at": "TIMESTAMP",
            "storage_class": "VARCHAR(32)",
            "logical_multiplier": "INTEGER NOT NULL DEFAULT 1",
        },
        "local_multipart_uploads": {
            "source_dataset_id": "VARCHAR(36)",
            "source_relative_path": "VARCHAR(2048)",
        },
        "local_multipart_parts": {
            "source_verified": "BOOLEAN NOT NULL DEFAULT 0",
        },
    }
    with engine.begin() as connection:
        for table, columns in expected_resource_columns.items():
            existing = {column["name"] for column in inspect(engine).get_columns(table)}
            for name, definition in columns.items():
                if name not in existing:
                    connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
    expected_restore_columns = {"request_attempts": "INTEGER NOT NULL DEFAULT 0", "last_error": "VARCHAR(512)"}
    existing_restore_columns = {column["name"] for column in inspect(engine).get_columns("local_restores")}
    with engine.begin() as connection:
        for name, definition in expected_restore_columns.items():
            if name not in existing_restore_columns:
                connection.exec_driver_sql(f"ALTER TABLE local_restores ADD COLUMN {name} {definition}")
    expected_dataset_columns = {
        "last_validated_at": "TIMESTAMP", "last_validation_error": "TEXT",
        "validated_objects": "INTEGER NOT NULL DEFAULT 0", "validated_bytes": "BIGINT NOT NULL DEFAULT 0",
    }
    existing_dataset_columns = {column["name"] for column in inspect(engine).get_columns("local_datasets")}
    with engine.begin() as connection:
        for name, definition in expected_dataset_columns.items():
            if name not in existing_dataset_columns:
                connection.exec_driver_sql(f"ALTER TABLE local_datasets ADD COLUMN {name} {definition}")
    # Schema 15 removes the unused governance-template preview.  It never
    # influenced provider behavior, so only its own metadata is discarded.
    with engine.begin() as connection:
        tables = set(inspect(engine).get_table_names())
        for table in ("local_s3_buckets", "local_oci_buckets"):
            if table not in tables:
                continue
            columns = {column["name"] for column in inspect(engine).get_columns(table)}
            if "governance_template_snapshot_json" in columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE {table} DROP COLUMN governance_template_snapshot_json"
                )
        if "local_governance_templates" in tables:
            connection.exec_driver_sql("DROP TABLE local_governance_templates")
    with Session(engine) as session:
        if session.get(LocalSchemaRevision, LOCAL_SCHEMA_VERSION) is None:
            session.add(LocalSchemaRevision(version=LOCAL_SCHEMA_VERSION))
            session.commit()
