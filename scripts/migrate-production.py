#!/usr/bin/env python3
"""Apply the explicit Raijin production schema migrations."""

from app.main import Base, engine
from app.production_migrations import migrate


if __name__ == "__main__":
    print(migrate(engine, Base.metadata))
