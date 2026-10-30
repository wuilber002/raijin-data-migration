from sqlalchemy import Column, Integer, MetaData, Table, create_engine, text

from app.production_migrations import (
    PRODUCTION_SCHEMA_VERSION,
    ProductionMigrationError,
    current_revision,
    migrate,
)


def test_production_baseline_is_explicit_and_idempotent():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()
    Table("example", metadata, Column("id", Integer, primary_key=True))
    assert migrate(engine, metadata) == PRODUCTION_SCHEMA_VERSION
    assert current_revision(engine) == PRODUCTION_SCHEMA_VERSION
    with engine.connect() as connection:
        assert connection.dialect.has_table(connection, "raijin_schema_metadata")
    assert migrate(engine, metadata) == PRODUCTION_SCHEMA_VERSION


def test_newer_production_schema_is_rejected():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()
    migrate(engine, metadata)
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM raijin_schema_revisions"))
        connection.execute(text(
            "INSERT INTO raijin_schema_revisions (version, description) VALUES (999, 'future')"
        ))
    try:
        migrate(engine, metadata)
    except ProductionMigrationError:
        pass
    else:  # pragma: no cover
        raise AssertionError("newer schema must be rejected")
