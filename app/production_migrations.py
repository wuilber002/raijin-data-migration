"""Explicit, locked migrations for the Raijin production control-plane schema."""

from __future__ import annotations

import hashlib

from sqlalchemy import MetaData, create_engine, inspect, text
from sqlalchemy.engine import Engine


PRODUCTION_SCHEMA_VERSION = 6
REVISION_TABLE = "raijin_schema_revisions"
MIGRATION_DESCRIPTIONS = {
    1: "Initial versioned Raijin production control-plane schema",
    2: "Add append-only production schema metadata",
    3: "Add immutable checksums to production schema revision history",
    4: "Add durable import-driven continuous pipeline items",
    5: "Store encrypted OCI diagnostic bundle PAR",
    6: "Store OCI diagnostic bundle PAR prefix",
}


class ProductionMigrationError(RuntimeError):
    pass


def current_revision(engine: Engine) -> int:
    with engine.connect() as connection:
        exists = connection.dialect.has_table(connection, REVISION_TABLE)
        if not exists:
            return 0
        value = connection.execute(text(
            f"SELECT max(version) FROM {REVISION_TABLE}"
        )).scalar_one_or_none()
        return int(value or 0)


def migration_checksum(version: int, description: str) -> str:
    """Return the stable audit digest for one append-only migration record."""
    return hashlib.sha256(f"raijin-schema-v{version}:{description}".encode("utf-8")).hexdigest()


def ensure_revision_checksums(connection) -> None:
    """Add and validate immutable migration evidence without rewriting history."""
    columns = {column["name"] for column in inspect(connection).get_columns(REVISION_TABLE)}
    if "checksum" not in columns:
        connection.execute(text(f"ALTER TABLE {REVISION_TABLE} ADD COLUMN checksum VARCHAR(64)"))
    for version, description in MIGRATION_DESCRIPTIONS.items():
        if version > PRODUCTION_SCHEMA_VERSION:
            continue
        checksum = migration_checksum(version, description)
        connection.execute(text(
            f"UPDATE {REVISION_TABLE} SET checksum = :checksum "
            "WHERE version = :version AND checksum IS NULL"
        ), {"checksum": checksum, "version": version})
    rows = connection.execute(text(
        f"SELECT version, description, checksum FROM {REVISION_TABLE} WHERE version <= :version"
    ), {"version": PRODUCTION_SCHEMA_VERSION}).mappings()
    for row in rows:
        version = int(row["version"])
        expected_description = MIGRATION_DESCRIPTIONS.get(version)
        if expected_description is None:
            continue
        if row["description"] != expected_description or row["checksum"] != migration_checksum(version, expected_description):
            raise ProductionMigrationError(f"Schema migration history checksum mismatch at revision {version}")


def migrate(engine: Engine, metadata: MetaData) -> int:
    """Install the append-only baseline under a database-wide transaction lock."""
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(818001604)"))
        connection.execute(text(
            f"CREATE TABLE IF NOT EXISTS {REVISION_TABLE} ("
            "version INTEGER PRIMARY KEY, applied_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "description TEXT NOT NULL)"
        ))
        revision = int(connection.execute(text(
            f"SELECT max(version) FROM {REVISION_TABLE}"
        )).scalar_one_or_none() or 0)
        if revision > PRODUCTION_SCHEMA_VERSION:
            raise ProductionMigrationError(
                f"Database revision {revision} is newer than supported revision {PRODUCTION_SCHEMA_VERSION}"
            )
        if revision == 0:
            metadata.create_all(connection)
            connection.execute(text(
                f"INSERT INTO {REVISION_TABLE} (version, description) VALUES (1, :description)"
            ), {"description": MIGRATION_DESCRIPTIONS[1]})
            revision = 1
        # v2 is deliberately expansive: it introduces immutable migration
        # metadata without changing any control-plane table or application
        # read/write path. It is the first N/N+1 compatibility exercise.
        if revision < 2:
            connection.execute(text(
                "CREATE TABLE IF NOT EXISTS raijin_schema_metadata ("
                "key VARCHAR(128) PRIMARY KEY, value TEXT NOT NULL)"
            ))
            connection.execute(text(
                f"INSERT INTO {REVISION_TABLE} (version, description) VALUES (2, :description)"
            ), {"description": MIGRATION_DESCRIPTIONS[2]})
            revision = 2
        # v3 adds immutable audit evidence to the existing append-only
        # revision records. Older application versions ignore this new column,
        # so the migration remains safe for N/N+1 controlled rollouts.
        if revision < 3:
            ensure_revision_checksums(connection)
            connection.execute(text(
                f"INSERT INTO {REVISION_TABLE} (version, description, checksum) VALUES (3, :description, :checksum)"
            ), {
                "description": MIGRATION_DESCRIPTIONS[3],
                "checksum": migration_checksum(3, MIGRATION_DESCRIPTIONS[3]),
            })
            revision = 3
        # The file-import pipeline needs a durable membership list so the
        # scheduler can materialize only the accepted import objects while
        # leaving every other discovered object untouched for later work.
        if revision < 4:
            import_items = metadata.tables.get("import_pipeline_items")
            if import_items is not None:
                import_items.create(connection, checkfirst=True)
            connection.execute(text(
                f"INSERT INTO {REVISION_TABLE} (version, description, checksum) VALUES (4, :description, :checksum)"
            ), {
                "description": MIGRATION_DESCRIPTIONS[4],
                "checksum": migration_checksum(4, MIGRATION_DESCRIPTIONS[4]),
            })
            revision = 4
        # The diagnostic-upload PAR is a bearer capability.  Keep the column
        # additive so existing installations can be upgraded without exposing
        # or rewriting any persisted operational evidence.
        if revision < 5:
            columns = ({column["name"] for column in inspect(connection).get_columns("runtime_settings")}
                       if connection.dialect.has_table(connection, "runtime_settings") else set())
            if columns and "diagnostic_par_encrypted" not in columns:
                connection.execute(text(
                    "ALTER TABLE runtime_settings ADD COLUMN diagnostic_par_encrypted TEXT"
                ))
            connection.execute(text(
                f"INSERT INTO {REVISION_TABLE} (version, description, checksum) VALUES (5, :description, :checksum)"
            ), {
                "description": MIGRATION_DESCRIPTIONS[5],
                "checksum": migration_checksum(5, MIGRATION_DESCRIPTIONS[5]),
            })
            revision = 5
        if revision < 6:
            columns = ({column["name"] for column in inspect(connection).get_columns("runtime_settings")}
                       if connection.dialect.has_table(connection, "runtime_settings") else set())
            # Be defensive about a partially applied prior release: the v6
            # expansion must leave the complete diagnostic-PAR schema.
            if columns and "diagnostic_par_encrypted" not in columns:
                connection.execute(text(
                    "ALTER TABLE runtime_settings ADD COLUMN diagnostic_par_encrypted TEXT"
                ))
                columns.add("diagnostic_par_encrypted")
            if columns and "diagnostic_par_prefix" not in columns:
                connection.execute(text(
                    "ALTER TABLE runtime_settings ADD COLUMN diagnostic_par_prefix VARCHAR(1024)"
                ))
            connection.execute(text(
                f"INSERT INTO {REVISION_TABLE} (version, description, checksum) VALUES (6, :description, :checksum)"
            ), {
                "description": MIGRATION_DESCRIPTIONS[6],
                "checksum": migration_checksum(6, MIGRATION_DESCRIPTIONS[6]),
            })
            revision = 6
        if revision >= 3:
            ensure_revision_checksums(connection)
        if revision != PRODUCTION_SCHEMA_VERSION:
            raise ProductionMigrationError(f"No migration path from revision {revision}")
    return revision


def migrate_url(database_url: str, metadata: MetaData) -> int:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        return migrate(engine, metadata)
    finally:
        engine.dispose()
