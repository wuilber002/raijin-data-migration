"""Immutable execution context for the Raijin production runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os


RAIJIN_SERVICE_VERSION = os.environ.get("RAIJIN_SERVICE_VERSION", "0.8.11").strip() or "0.8.11"
RAIJIN_BUILD_REVISION = os.environ.get("RAIJIN_BUILD_REVISION", "development").strip() or "development"
# Kept only while the generic request models are simplified; it is not a
# selectable runtime or an integration endpoint in Raijin.
SIMULATOR_CONTRACT_VERSION = "2"


class OperationMode(str, Enum):
    REAL = "REAL"


class RuntimeIsolationError(RuntimeError):
    """Raised when a host attempts to enable a retired execution profile."""


@dataclass(frozen=True)
class RuntimeContext:
    mode: OperationMode
    database_url: str

    @classmethod
    def from_environ(cls, environ: dict[str, str] | None = None) -> "RuntimeContext":
        values = os.environ if environ is None else environ
        requested = str(values.get("RAIJIN_OPERATION_MODE", "REAL")).strip().upper()
        if requested != "REAL":
            raise RuntimeIsolationError("Raijin supports only the REAL runtime")
        database_url = values.get("DATABASE_URL", "")
        if not database_url:
            raise RuntimeIsolationError("DATABASE_URL is required")
        return cls(mode=OperationMode.REAL, database_url=database_url)

    @property
    def is_real(self) -> bool:
        return True

    @property
    def is_simulation(self) -> bool:
        return False

    def require_real_cloud(self, operation: str) -> None:
        return None


def load_runtime_context(environ: dict[str, str] | None = None) -> RuntimeContext:
    return RuntimeContext.from_environ(environ)
