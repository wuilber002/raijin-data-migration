#!/usr/bin/env python3
"""Host-only recovery actions for local Raijin console users.

The wrapper invokes this inside a short-lived container on the private
PostgreSQL network. Passwords are accepted only from a mounted protected file;
they are never accepted as process arguments or printed.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, update

from app.main import Base, ConsoleAuthAuditEvent, ConsoleRole, ConsoleSession, ConsoleUser, SessionLocal, engine, utcnow
from app.web_auth import PasswordHasher, normalize_username, read_password_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Raijin local console recovery")
    parser.add_argument("action", choices=("create", "reset", "unlock"))
    parser.add_argument("username")
    parser.add_argument("--role", choices=[role.value for role in ConsoleRole], default=ConsoleRole.ADMIN.value)
    parser.add_argument("--password-file")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    if not args.confirm:
        raise SystemExit("Refusing recovery action without --confirm")
    if args.action in {"create", "reset"} and not args.password_file:
        raise SystemExit("create/reset requires --password-file")
    username = normalize_username(args.username)
    password = read_password_file(args.password_file) if args.password_file else None
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        user = session.scalar(select(ConsoleUser).where(ConsoleUser.username == username))
        if args.action == "create":
            if user:
                raise SystemExit("Console user already exists; use reset or unlock")
            user = ConsoleUser(username=username, password_hash=PasswordHasher().hash(password),
                               role=args.role, enabled=True, must_change_password=True)
            session.add(user); session.flush()
            event = "HOST_RECOVERY_USER_CREATED"
        elif args.action == "reset":
            if not user:
                raise SystemExit("Console user not found; use create")
            user.password_hash = PasswordHasher().hash(password)
            user.enabled, user.must_change_password = True, True
            event = "HOST_RECOVERY_PASSWORD_RESET"
        else:
            if not user:
                raise SystemExit("Console user not found")
            user.enabled = True
            event = "HOST_RECOVERY_USER_UNLOCKED"
        session.execute(update(ConsoleSession).where(ConsoleSession.user_id == user.id,
            ConsoleSession.revoked_at.is_(None)).values(revoked_at=utcnow(), revoke_reason="host_recovery"))
        session.add(ConsoleAuthAuditEvent(actor_user_id=user.id, event_type=event, target=username,
            result="SUCCEEDED", detail_json='{"channel":"host-cli"}'))
        session.commit()
    print(f"Console user '{username}' recovery action completed.")


if __name__ == "__main__":
    main()
