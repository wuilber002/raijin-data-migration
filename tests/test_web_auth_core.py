import os
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import base64
import hmac
import hashlib
import struct
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
    assert main.auth_route_requirement("/api/admin/auth-security-summary", "GET") is ConsoleRole.ADMIN
    assert main.auth_route_requirement("/api/admin/active-sessions", "GET") is ConsoleRole.ADMIN


def test_admin_web_bind_request_is_constrained_and_written_atomically(tmp_path, monkeypatch):
    control = tmp_path / "web-bind" / "request.json"
    monkeypatch.setenv("RAIJIN_WEB_BIND_REQUEST_FILE", str(control))
    monkeypatch.setenv("RAIJIN_WEB_BIND_RESULT_FILE", str(tmp_path / "web-bind" / "result.json"))
    monkeypatch.setattr(main, "web_auth_settings", load_web_auth_settings({
        "RAIJIN_WEB_AUTH_MODE": "local", "RAIJIN_WEB_BIND_HOST": "127.0.0.1",
        "RAIJIN_WEB_AUTH_BOOTSTRAP_REQUIRED": "false", "RAIJIN_WEB_AUTH_BOOTSTRAP_USERNAME": "admin",
    }))
    database = create_engine(f"sqlite+pysqlite:///{tmp_path / 'web-bind.db'}")
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=database, expire_on_commit=False))
    main.Base.metadata.create_all(database)
    with main.SessionLocal() as session:
        admin = main.ConsoleUser(username="admin", password_hash=PasswordHasher().hash("a secure test password"),
                                 role=ConsoleRole.ADMIN)
        session.add(admin); session.commit()
        request = SimpleNamespace(state=SimpleNamespace(console_principal={"id": admin.id}), client=None, headers={})
        payload = main.ConsoleWebBindUpdate(host="192.0.2.12", port=9443, transport="https")
        response = main.console_update_web_bind(payload, request, session)
    assert response["accepted"] is True
    assert control.exists()
    assert control.read_text(encoding="utf-8").find('"transport": "https"') >= 0
    with pytest.raises(main.HTTPException, match="IPv4 /32"):
        main.console_update_web_bind(main.ConsoleWebBindUpdate(host="192.0.2.12", port=8080, transport="http",
                                                               trusted_upstream_ips=["192.0.2.0/24"]), request, session)


def test_admin_web_bind_addresses_come_from_host_inventory(tmp_path, monkeypatch):
    control = tmp_path / "web-bind" / "request.json"
    control.parent.mkdir()
    control.parent.joinpath("interfaces.json").write_text(
        '[{"value":"127.0.0.1","label":"127.0.0.1 — Loopback only"},'
        '{"value":"10.0.0.12","label":"10.0.0.12 — ens3"}]', encoding="utf-8"
    )
    monkeypatch.setenv("RAIJIN_WEB_BIND_REQUEST_FILE", str(control))
    assert main.console_get_web_bind_addresses()["addresses"][1]["value"] == "10.0.0.12"


def test_totp_accepts_current_window_and_rejects_wrong_pin():
    secret = main.generate_totp_secret()
    timestamp = 1_700_000_000
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", timestamp // 30), hashlib.sha1).digest()
    start = digest[-1] & 0x0F
    pin = str((struct.unpack(">I", digest[start:start + 4])[0] & 0x7fffffff) % 1_000_000).zfill(6)
    assert main.verify_totp(secret, pin, now=timestamp)
    assert not main.verify_totp(secret, "000000", now=timestamp)


def test_pending_mfa_qr_is_session_protected_and_contains_an_otpauth_payload(tmp_path, monkeypatch):
    database = create_engine(f"sqlite+pysqlite:///{tmp_path / 'mfa-qr.db'}")
    monkeypatch.setattr(main, "engine", database)
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=database, expire_on_commit=False))
    main.Base.metadata.create_all(database)
    with main.SessionLocal() as session:
        user = main.ConsoleUser(username="mfa-user", password_hash=PasswordHasher().hash("a secure test password"),
                                role=ConsoleRole.VIEWER, mfa_pending_secret_encrypted=main.mfa_encrypt("JBSWY3DPEHPK3PXP"))
        session.add(user); session.commit()
        request = SimpleNamespace(state=SimpleNamespace(console_principal={"id": user.id}))
        response = main.console_mfa_enrollment_qr(request, session)
    assert response.media_type == "image/svg+xml"
    assert b"<svg" in response.body
    assert main.auth_route_requirement("/api/auth/mfa/enrollment/qr", "GET") is ConsoleRole.VIEWER


def test_auth_security_summary_is_aggregate_and_detects_lockouts_and_denial_spikes(tmp_path, monkeypatch):
    database = create_engine(f"sqlite+pysqlite:///{tmp_path / 'auth-security.db'}")
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=database, expire_on_commit=False))
    main.Base.metadata.create_all(database)
    now = main.utcnow()
    with main.SessionLocal() as session:
        admin = main.ConsoleUser(username="admin", password_hash=PasswordHasher().hash("a secure test password"),
                                 role=ConsoleRole.ADMIN)
        session.add(admin)
        for index in range(main.CONSOLE_LOGIN_MAX_FAILURES):
            session.add(main.ConsoleLoginAttempt(identity_hash=f"origin-{index // main.CONSOLE_LOGIN_MAX_FAILURES}",
                                                  succeeded=False, created_at=now - timedelta(seconds=10)))
        for _ in range(main.CONSOLE_AUTH_DENIED_ALERT_THRESHOLD):
            session.add(main.ConsoleAuthAuditEvent(event_type="AUTHORIZATION_DENIED", result="DENIED",
                                                   target="/api/admin/users", created_at=now - timedelta(seconds=10)))
        session.add(main.ConsoleAuthAuditEvent(event_type="LOGIN_RATE_LIMITED", result="DENIED",
                                               target="redacted", created_at=now - timedelta(seconds=10)))
        session.commit()
        summary = main.console_auth_security_summary(session, now=now)
    assert summary["ready_admins"] == 1
    assert summary["bootstrap_required"] is False
    assert summary["active_lockouts"] == 1
    assert summary["rate_limited"] == 1
    assert summary["authorization_denied"] == main.CONSOLE_AUTH_DENIED_ALERT_THRESHOLD
    assert "origin" not in repr(summary)


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


def test_administrator_can_revoke_other_sessions_but_not_the_current_one(tmp_path, monkeypatch):
    database = create_engine(f"sqlite+pysqlite:///{tmp_path / 'session-revoke-policy.db'}")
    monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=database, expire_on_commit=False))
    main.Base.metadata.create_all(database)
    with main.SessionLocal() as session:
        admin = main.ConsoleUser(username="admin", password_hash=PasswordHasher().hash("a secure test password"),
                                 role=ConsoleRole.ADMIN)
        operator = main.ConsoleUser(username="operator-hml", password_hash=PasswordHasher().hash("another secure test password"),
                                    role=ConsoleRole.OPERATOR)
        session.add_all([admin, operator]); session.flush()
        main.create_console_session(session, admin)
        main.create_console_session(session, admin)
        main.create_console_session(session, operator)
        session.flush()
        own_sessions = list(session.scalars(select(main.ConsoleSession).where(main.ConsoleSession.user_id == admin.id)))
        own_session, other_own_session = own_sessions
        other_session = session.scalar(select(main.ConsoleSession).where(main.ConsoleSession.user_id == operator.id))
        request = SimpleNamespace(
            state=SimpleNamespace(console_principal={"id": admin.id}, console_session_id=own_session.id),
            client=None, headers={},
        )
        listed = main.console_list_sessions(request, session)
        assert next(row for row in listed if row["id"] == own_session.id)["is_current_user"] is True
        assert next(row for row in listed if row["id"] == own_session.id)["is_current"] is True
        assert next(row for row in listed if row["id"] == other_own_session.id)["is_current"] is False
        assert next(row for row in listed if row["id"] == other_session.id)["is_current_user"] is False
        with pytest.raises(main.HTTPException, match="cannot revoke their current"):
            main.console_revoke_session(own_session.id, request, session)
        assert own_session.revoked_at is None
        assert main.console_revoke_session(other_own_session.id, request, session)["id"] == other_own_session.id
        assert other_own_session.revoked_at is not None
        assert main.console_revoke_session(other_session.id, request, session)["id"] == other_session.id
        assert other_session.revoked_at is not None


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


def test_console_username_accepts_existing_aliases_and_corporate_email_logins():
    assert main.normalize_username("operator-hml") == "operator-hml"
    assert main.normalize_username("Igor.Nicoli@Oracle.Com") == "igor.nicoli@oracle.com"
    with pytest.raises(ValueError, match="email address"):
        main.normalize_username("igor.nicoli@oracle")


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
