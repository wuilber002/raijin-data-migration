"""Raijin's production cloud backend boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from app.runtime_context import OperationMode, RuntimeContext


@dataclass(frozen=True)
class BackendReadiness:
    mode: OperationMode
    contract_version: str | None
    operations_enabled: bool
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class BackendClock:
    real_now: datetime
    effective_now: datetime
    acceleration: float = 1.0
    paused: bool = False
    held: bool = False


class CloudBackend(Protocol):
    def readiness(self, require_operations: bool = False) -> BackendReadiness: ...
    def clock(self, execution_id: str | None = None) -> BackendClock: ...


class RealCloudBackend:
    def readiness(self, require_operations: bool = False) -> BackendReadiness:
        return BackendReadiness(OperationMode.REAL, None, True)

    def clock(self, execution_id: str | None = None) -> BackendClock:
        now = datetime.now(timezone.utc)
        return BackendClock(now, now)


def backend_for(context: RuntimeContext) -> CloudBackend:
    return RealCloudBackend()
