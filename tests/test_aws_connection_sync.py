import json
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


_password = Path("/tmp/raijin-test-password-connection-sync")
_password.write_text("test-password", encoding="utf-8")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("POSTGRES_PASSWORD_FILE", str(_password))
os.environ.setdefault("OCI_RUNTIME_CONFIG_FILE", "/tmp/raijin-test-oci-runtime.json")

from app.main import AwsConnection, Base, Source, sync_aws_connection


def test_sync_updates_secret_endpoint_and_failed_discovery_snapshot(tmp_path, monkeypatch):
    import app.main as module

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'connection-sync.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    secret_ocid = "ocid1.vaultsecret.oc1..connection-sync"
    secret = {
        "schema_version": 1,
        "connection_name": "Updated endpoint",
        "aws_account_id": "123456789012",
        "default_region": "sa-east-1",
        "bootstrap_access_key_id": "AKIAEXAMPLE",
        "bootstrap_secret_access_key": "secret",
        "migration_role_arn": "arn:aws:iam::123456789012:role/migration",
        "batch_operations_role_arn": "arn:aws:iam::123456789012:role/batch",
        "control_bucket": "updated-control-bucket",
        "private_endpoint": {
            "s3_endpoint_url": "https://bucket.vpce-0123456789abcdef0-abc.s3.sa-east-1.vpce.amazonaws.com",
            "s3_addressing_style": "auto",
        },
    }
    monkeypatch.setattr(module, "aws_secret_payload", lambda _ocid: secret)
    monkeypatch.setattr(module, "record_event", lambda *_args, **_kwargs: None)

    with Session() as session:
        connection = AwsConnection(
            label="Connection", secret_ocid=secret_ocid, aws_account_id="123456789012",
            default_region="us-east-1", control_bucket="old-control-bucket",
            s3_endpoint_url="https://bucket.vpce-old.s3.us-east-1.vpce.amazonaws.com",
        )
        failed = Source(
            name="failed-discovery", s3_bucket="source", aws_region="us-east-1",
            destination_bucket="destination", status="DISCOVERY_FAILED", aws_connection=connection,
            aws_endpoint_snapshot_json=json.dumps({"s3_endpoint_url": connection.s3_endpoint_url}),
        )
        active = Source(
            name="active-discovery", s3_bucket="source-two", aws_region="us-east-1",
            destination_bucket="destination-two", status="DISCOVERING", aws_connection=connection,
            aws_endpoint_snapshot_json=json.dumps({"s3_endpoint_url": connection.s3_endpoint_url}),
        )
        session.add_all([connection, failed, active])
        session.commit()

        result = sync_aws_connection(connection.id, session)

        assert connection.default_region == "sa-east-1"
        assert connection.control_bucket == "updated-control-bucket"
        assert connection.s3_endpoint_url == secret["private_endpoint"]["s3_endpoint_url"]
        assert connection.s3control_endpoint_url == "https://control.vpce-0123456789abcdef0-abc.s3.sa-east-1.vpce.amazonaws.com"
        assert json.loads(failed.aws_endpoint_snapshot_json)["s3_endpoint_url"] == connection.s3_endpoint_url
        assert json.loads(active.aws_endpoint_snapshot_json)["s3_endpoint_url"] != connection.s3_endpoint_url
        assert result["failed_discovery_sources_refreshed"] == 1
