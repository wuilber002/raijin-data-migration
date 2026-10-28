"""Configuration contract for the Raijin web-console authentication boundary.

The module deliberately contains no FastAPI or database dependency.  It is
loaded before the application is exposed, so a malformed authentication
configuration fails the container rather than silently downgrading access.
Authentication itself remains disabled by default during the compatibility
release.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
try:  # Keep local validation possible on Oracle Linux Python 3.10 too.
    from enum import StrEnum
except ImportError:  # pragma: no cover - exercised only on Python < 3.11
    class StrEnum(str, Enum):
        pass
import ipaddress
import os


class WebAuthConfigurationError(RuntimeError):
    """Raised when the web-console security boundary is unsafe or ambiguous."""


class WebAuthMode(StrEnum):
    DISABLED = "disabled"
    LOCAL = "local"


def _boolean(value: str | None, name: str) -> bool:
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise WebAuthConfigurationError(f"{name} must be true or false")


def _bounded_integer(value: str | None, name: str, minimum: int, maximum: int) -> int:
    try:
        result = int(str(value or "").strip())
    except ValueError as error:
        raise WebAuthConfigurationError(f"{name} must be an integer") from error
    if not minimum <= result <= maximum:
        raise WebAuthConfigurationError(
            f"{name} must be between {minimum} and {maximum}"
        )
    return result


def _trusted_proxy_networks(value: str | None) -> tuple[str, ...]:
    entries = tuple(item.strip() for item in str(value or "").split(",") if item.strip())
    for entry in entries:
        try:
            ipaddress.ip_network(entry, strict=False)
        except ValueError as error:
            raise WebAuthConfigurationError(
                "RAIJIN_WEB_AUTH_TRUSTED_PROXY_CIDRS must contain CIDR networks"
            ) from error
    return entries


def _loopback_bind(value: str | None) -> bool:
    host = str(value or "127.0.0.1").strip()
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError as error:
        raise WebAuthConfigurationError("RAIJIN_WEB_BIND_HOST must be an IP address") from error


@dataclass(frozen=True)
class WebAuthSettings:
    """Validated, non-secret runtime configuration for the console boundary."""

    mode: WebAuthMode
    bind_host: str
    external_https: bool
    trusted_proxy_networks: tuple[str, ...]
    session_idle_minutes: int
    session_absolute_minutes: int

    @property
    def enabled(self) -> bool:
        return self.mode is WebAuthMode.LOCAL

    @classmethod
    def from_environ(cls, environ: dict[str, str] | None = None) -> "WebAuthSettings":
        values = os.environ if environ is None else environ
        raw_mode = str(values.get("RAIJIN_WEB_AUTH_MODE", WebAuthMode.DISABLED.value)).strip().lower()
        try:
            mode = WebAuthMode(raw_mode)
        except ValueError as error:
            raise WebAuthConfigurationError(
                "RAIJIN_WEB_AUTH_MODE must be disabled or local"
            ) from error

        bind_host = str(values.get("RAIJIN_WEB_BIND_HOST", "127.0.0.1")).strip()
        loopback_bind = _loopback_bind(bind_host)
        external_https = _boolean(values.get("RAIJIN_WEB_EXTERNAL_HTTPS", "false"), "RAIJIN_WEB_EXTERNAL_HTTPS")
        trusted_proxy_networks = _trusted_proxy_networks(
            values.get("RAIJIN_WEB_AUTH_TRUSTED_PROXY_CIDRS", "")
        )
        idle = _bounded_integer(
            values.get("RAIJIN_WEB_AUTH_SESSION_IDLE_MINUTES", "30"),
            "RAIJIN_WEB_AUTH_SESSION_IDLE_MINUTES", 5, 120,
        )
        absolute = _bounded_integer(
            values.get("RAIJIN_WEB_AUTH_SESSION_ABSOLUTE_MINUTES", "720"),
            "RAIJIN_WEB_AUTH_SESSION_ABSOLUTE_MINUTES", 30, 1440,
        )
        if absolute < idle:
            raise WebAuthConfigurationError(
                "RAIJIN_WEB_AUTH_SESSION_ABSOLUTE_MINUTES must not be lower than idle timeout"
            )
        if mode is WebAuthMode.LOCAL and not loopback_bind:
            if not external_https or not trusted_proxy_networks:
                raise WebAuthConfigurationError(
                    "local web authentication on a non-loopback bind requires external HTTPS "
                    "and RAIJIN_WEB_AUTH_TRUSTED_PROXY_CIDRS"
                )
        return cls(
            mode=mode,
            bind_host=bind_host,
            external_https=external_https,
            trusted_proxy_networks=trusted_proxy_networks,
            session_idle_minutes=idle,
            session_absolute_minutes=absolute,
        )


def load_web_auth_settings(environ: dict[str, str] | None = None) -> WebAuthSettings:
    return WebAuthSettings.from_environ(environ)
