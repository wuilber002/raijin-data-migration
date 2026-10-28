#!/usr/bin/env python3
"""Read-only preflight for enabling local Raijin console authentication."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, inspect, select

from app.main import ConsoleUser, SessionLocal, web_auth_settings
from app.web_auth import read_password_file


def main() -> None:
    if not web_auth_settings.enabled:
        raise SystemExit("RAIJIN_WEB_AUTH_MODE must be local for this preflight")
    # Reading validates the protected materialized value without printing it.
    read_password_file(str(web_auth_settings.bootstrap_password_file))
    with SessionLocal() as session:
        session.execute(select(1))
        if inspect(session.bind).has_table(ConsoleUser.__tablename__):
            user_count = int(session.scalar(select(func.count(ConsoleUser.id))) or 0)
        else:
            user_count = 0
    state = "will create bootstrap administrator" if user_count == 0 else "existing console users preserved"
    print(f"Console authentication preflight passed: {state}.")


if __name__ == "__main__":
    main()
