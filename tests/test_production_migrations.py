from sqlalchemy import Column, Integer, MetaData, Table, create_engine, text

from app.production_migrations import (
    MIGRATION_DESCRIPTIONS,
    PRODUCTION_SCHEMA_VERSION,
    ProductionMigrationError,
    current_revision,
    migration_checksum,
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
        columns = {column["name"] for column in connection.dialect.get_columns(connection, "raijin_schema_revisions")}
        assert "checksum" in columns
        rows = connection.execute(text(
            "SELECT version, description, checksum FROM raijin_schema_revisions ORDER BY version"
        )).all()
        assert [(version, description) for version, description, _ in rows] == list(MIGRATION_DESCRIPTIONS.items())
        assert all(checksum == migration_checksum(version, description) for version, description, checksum in rows)
    assert migrate(engine, metadata) == PRODUCTION_SCHEMA_VERSION


def test_production_schema_checksum_detects_history_tampering():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    migrate(engine, MetaData())
    with engine.begin() as connection:
        connection.execute(text("UPDATE raijin_schema_revisions SET description = 'changed' WHERE version = 2"))
    try:
        migrate(engine, MetaData())
    except ProductionMigrationError as error:
        assert "checksum mismatch" in str(error)
    else:  # pragma: no cover
        raise AssertionError("tampered schema history must be rejected")


def test_v2_schema_expands_to_v3_without_recreating_control_plane_tables():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE raijin_schema_revisions ("
            "version INTEGER PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, description TEXT NOT NULL)"
        ))
        connection.execute(text("CREATE TABLE raijin_schema_metadata (key VARCHAR(128) PRIMARY KEY, value TEXT NOT NULL)"))
        for version in (1, 2):
            connection.execute(text(
                "INSERT INTO raijin_schema_revisions (version, description) VALUES (:version, :description)"
            ), {"version": version, "description": MIGRATION_DESCRIPTIONS[version]})
    assert migrate(engine, MetaData()) == 3
    with engine.connect() as connection:
        assert connection.execute(text("SELECT checksum FROM raijin_schema_revisions WHERE version = 3")).scalar_one() == migration_checksum(3, MIGRATION_DESCRIPTIONS[3])


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
