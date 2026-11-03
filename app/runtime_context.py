"""Immutable execution context for the Raijin production runtime."""

from __future__ import annotations

from dataclasses import dataclass
import os


RAIJIN_SERVICE_VERSION = os.environ.get("RAIJIN_SERVICE_VERSION", "0.8.11").strip() or "0.8.11"
RAIJIN_BUILD_REVISION = os.environ.get("RAIJIN_BUILD_REVISION", "development").strip() or "development"
@dataclass(frozen=True)
class RuntimeContext:
    database_url: str

    @classmethod
    def from_environ(cls, environ: dict[str, str] | None = None) -> "RuntimeContext":
        values = os.environ if environ is None else environ
        database_url = values.get("DATABASE_URL", "")
        if not database_url:
            raise RuntimeError("DATABASE_URL is required")
        return cls(database_url=database_url)

def load_runtime_context(environ: dict[str, str] | None = None) -> RuntimeContext:
    return RuntimeContext.from_environ(environ)
