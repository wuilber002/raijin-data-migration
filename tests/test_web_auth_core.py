import os
from pathlib import Path

import pytest
from sqlalchemy import BigInteger, create_engine, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker


@compiles(BigInteger, "sqlite")
def _compile_big_integer_as_sqlite_integer(_type, _compiler, **_kwargs):
    return "INTEGER"


password_file = Path("/tmp/raijin-web-auth-import-password")
password_file.write_text("test-password", encoding="utf-8")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("POSTGRES_PASSWORD_FILE", str(password_file))
os.environ.setdefault("OCI_RUNTIME_CONFIG_FILE", "/tmp/raijin-test-oci-runtime.json")

import app.main as main
from app.web_auth import ConsoleRole, PasswordHasher, load_web_auth_settings, validate_password


def test_bootstrap_creates_exactly_one_argon_admin(tmp_path, monkeypatch):
    bootstrap = tmp_path / "bootstrap-password"
    bootstrap.write_text("a locally protected bootstrap password", encoding="utf-8")
    database = create_engine(f"sqlite+pysqlite:///{tmp_path / 'auth.db'}")
    monkeypatch.setattr(main, "engine", database)
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=database, expire_on_commit=False))
    monkeypatch.setattr(main, "web_auth_settings", load_web_auth_settings({
        "RAIJIN_WEB_AUTH_MODE": "local", "RAIJIN_WEB_BIND_HOST": "127.0.0.1",
        "RAIJIN_WEB_AUTH_BOOTSTRAP_USERNAME": "admin",
        "RAIJIN_WEB_AUTH_BOOTSTRAP_PASSWORD_FILE": str(bootstrap),
    }))
    main.Base.metadata.create_all(database)
    main.ensure_console_auth_bootstrap()
    main.ensure_console_auth_bootstrap()
    with main.SessionLocal() as session:
        users = list(session.scalars(select(main.ConsoleUser)))
        assert len(users) == 1
        assert users[0].role == ConsoleRole.ADMIN
        assert users[0].password_hash.startswith("$argon2id$")
        assert PasswordHasher().verify(users[0].password_hash, "a locally protected bootstrap password")
        events = list(session.scalars(select(main.ConsoleAuthAuditEvent)))
        assert [event.event_type for event in events] == ["BOOTSTRAP_ADMIN_CREATED"]


def test_roles_and_route_policy_are_server_side_and_deny_unknown_paths():
    assert main.auth_route_requirement("/api/sources", "GET") is ConsoleRole.VIEWER
    assert main.auth_route_requirement("/api/sources", "POST") is ConsoleRole.OPERATOR
    assert main.auth_route_requirement("/api/settings", "GET") is ConsoleRole.VIEWER
    assert main.auth_route_requirement("/api/tasks/claim", "POST") == "INTERNAL"
    assert main.auth_route_requirement("/unclassified", "GET") == "DENY"
    assert main.auth_role_permits(ConsoleRole.ADMIN, ConsoleRole.OPERATOR)
    assert not main.auth_role_permits(ConsoleRole.VIEWER, ConsoleRole.OPERATOR)
    assert main.login_throttled(0, 5)
    assert main.login_throttled(10, 0)
    assert not main.login_throttled(9, 4)


def test_safe_dashboard_configuration_reads_are_available_to_viewers():
    assert main.auth_route_requirement("/api/runtime", "GET") is ConsoleRole.VIEWER
    assert main.auth_route_requirement("/api/settings", "GET") is ConsoleRole.VIEWER
    assert main.auth_route_requirement("/api/settings", "PUT") is ConsoleRole.ADMIN
    assert main.auth_route_requirement("/api/activity-refresh-settings", "GET") is ConsoleRole.VIEWER
    assert main.auth_route_requirement("/api/activity-refresh-settings", "PUT") is ConsoleRole.ADMIN
    assert main.auth_route_requirement("/api/auth/profile", "GET") is ConsoleRole.VIEWER
    assert main.auth_route_requirement("/api/auth/profile", "PATCH") is ConsoleRole.VIEWER
    assert main.auth_route_requirement("/api/console-presence/heartbeat", "POST") is ConsoleRole.VIEWER


def test_password_policy_rejects_obvious_common_bootstrap_passwords():
    with pytest.raises(ValueError, match="too common"):
        validate_password("passwordpassword")


def test_sessions_are_opaque_and_csrf_is_independently_hashed(tmp_path, monkeypatch):
    database = create_engine(f"sqlite+pysqlite:///{tmp_path / 'sessions.db'}")
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=database, expire_on_commit=False))
    main.Base.metadata.create_all(database)
    with main.SessionLocal() as session:
        user = main.ConsoleUser(username="admin", password_hash=PasswordHasher().hash("a secure test password"),
                                role=ConsoleRole.ADMIN)
        session.add(user); session.flush()
        token, csrf = main.create_console_session(session, user)
        session.commit()
        stored = session.scalar(select(main.ConsoleSession))
        assert stored.token_hash == main.hash_opaque_token(token)
        assert stored.csrf_hash == main.hash_opaque_token(csrf)
        assert token not in stored.token_hash and csrf not in stored.csrf_hash


def test_password_history_rejects_current_and_last_configured_passwords(tmp_path, monkeypatch):
    database = create_engine(f"sqlite+pysqlite:///{tmp_path / 'password-history.db'}")
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=database, expire_on_commit=False))
    main.Base.metadata.create_all(database)
    with main.SessionLocal() as session:
        user = main.ConsoleUser(username="operator-hml", password_hash=PasswordHasher().hash("first secure test password"),
                                role=ConsoleRole.OPERATOR)
        session.add(user); session.flush()
        with pytest.raises(ValueError, match="current password"):
            main.replace_console_password(session, user, "first secure test password", history_count=3)
        main.replace_console_password(session, user, "second secure test password", history_count=3)
        session.commit()
        with pytest.raises(ValueError, match="last 3"):
            main.replace_console_password(session, user, "first secure test password", history_count=3)
        main.replace_console_password(session, user, "third secure test password", history_count=0)
        session.commit()
        assert main.console_password_reused(session, user, "second secure test password", 3)


def test_console_profile_normalization_is_safe_and_does_not_change_username():
    assert main.normalize_console_profile(" Ana Maria ", " ANA@example.COM ") == ("Ana Maria", "ana@example.com")
    assert main.normalize_console_profile("", "") == (None, None)
    with pytest.raises(ValueError, match="Email"):
        main.normalize_console_profile("Ana", "not-an-email")


def test_bootstrap_revokes_existing_sessions_after_service_restart(tmp_path, monkeypatch):
    bootstrap = tmp_path / "bootstrap-password"
    bootstrap.write_text("a locally protected bootstrap password", encoding="utf-8")
    database = create_engine(f"sqlite+pysqlite:///{tmp_path / 'restart.db'}")
    monkeypatch.setattr(main, "engine", database)
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=database, expire_on_commit=False))
    monkeypatch.setattr(main, "web_auth_settings", load_web_auth_settings({
        "RAIJIN_WEB_AUTH_MODE": "local", "RAIJIN_WEB_BIND_HOST": "127.0.0.1",
        "RAIJIN_WEB_AUTH_BOOTSTRAP_USERNAME": "admin",
        "RAIJIN_WEB_AUTH_BOOTSTRAP_PASSWORD_FILE": str(bootstrap),
    }))
    main.Base.metadata.create_all(database)
    main.ensure_console_auth_bootstrap()
    with main.SessionLocal() as session:
        admin = session.scalar(select(main.ConsoleUser).where(main.ConsoleUser.username == "admin"))
        main.create_console_session(session, admin)
        session.commit()
    main.ensure_console_auth_bootstrap()
    with main.SessionLocal() as session:
        restored = session.scalar(select(main.ConsoleSession))
        assert restored.revoked_at is not None
        assert restored.revoke_reason == "service_restart"
