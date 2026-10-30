"""Explicit, locked migrations for the Raijin production control-plane schema."""

from __future__ import annotations

from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.engine import Engine


PRODUCTION_SCHEMA_VERSION = 1
REVISION_TABLE = "raijin_schema_revisions"


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
            ), {"description": "Initial versioned Raijin production control-plane schema"})
            revision = 1
        if revision != PRODUCTION_SCHEMA_VERSION:
            raise ProductionMigrationError(f"No migration path from revision {revision}")
    return revision


def migrate_url(database_url: str, metadata: MetaData) -> int:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        return migrate(engine, metadata)
    finally:
        engine.dispose()
