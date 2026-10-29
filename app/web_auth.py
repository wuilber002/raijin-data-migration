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
import hashlib
import re
import secrets
from pathlib import Path


class WebAuthConfigurationError(RuntimeError):
    """Raised when the web-console security boundary is unsafe or ambiguous."""


class WebAuthMode(StrEnum):
    DISABLED = "disabled"
    LOCAL = "local"


class ConsoleRole(StrEnum):
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    VIEWER = "VIEWER"


USERNAME_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{2,63}$")
MINIMUM_PASSWORD_LENGTH = 14
# A small denylist is intentionally a floor, not a substitute for length and
# future breached-password screening. It rejects the obvious credentials that
# routinely appear in first-boot attacks without making password contents part
# of logs or persistence.
COMMON_PASSWORDS = frozenset({
    "passwordpassword", "changemechangeme", "administratoradmin", "raijinraijin", "welcome12345678",
    "qwertyuiopasdfgh", "1234567890123456", "letmeinletmein", "adminadminadmin", "oracleoracleoracle",
})


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
    bootstrap_required: bool = True
    bootstrap_username: str | None = None
    bootstrap_password_file: str | None = None

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
        bootstrap_required = _boolean(
            values.get("RAIJIN_WEB_AUTH_BOOTSTRAP_REQUIRED", "true"),
            "RAIJIN_WEB_AUTH_BOOTSTRAP_REQUIRED",
        )
        bootstrap_username = (values.get("RAIJIN_WEB_AUTH_BOOTSTRAP_USERNAME") or "").strip().lower() or None
        bootstrap_password_file = (values.get("RAIJIN_WEB_AUTH_BOOTSTRAP_PASSWORD_FILE") or "").strip() or None
        if bootstrap_username and not USERNAME_PATTERN.fullmatch(bootstrap_username):
            raise WebAuthConfigurationError(
                "RAIJIN_WEB_AUTH_BOOTSTRAP_USERNAME must be 3-64 lowercase username characters"
            )
        if bootstrap_password_file and not Path(bootstrap_password_file).is_absolute():
            raise WebAuthConfigurationError(
                "RAIJIN_WEB_AUTH_BOOTSTRAP_PASSWORD_FILE must be an absolute path"
            )
        if mode is WebAuthMode.LOCAL and not loopback_bind:
            if not external_https or not trusted_proxy_networks:
                raise WebAuthConfigurationError(
                    "local web authentication on a non-loopback bind requires external HTTPS "
                    "and RAIJIN_WEB_AUTH_TRUSTED_PROXY_CIDRS"
                )
        if mode is WebAuthMode.LOCAL and bootstrap_required and not loopback_bind:
            raise WebAuthConfigurationError(
                "initial local web-auth bootstrap requires RAIJIN_WEB_BIND_HOST=127.0.0.1 or ::1"
            )
        if mode is WebAuthMode.LOCAL and bootstrap_required and (not bootstrap_username or not bootstrap_password_file):
            raise WebAuthConfigurationError(
                "initial local web authentication requires bootstrap username and password file references"
            )
        return cls(
            mode=mode,
            bind_host=bind_host,
            external_https=external_https,
            trusted_proxy_networks=trusted_proxy_networks,
            session_idle_minutes=idle,
            session_absolute_minutes=absolute,
            bootstrap_required=bootstrap_required,
            bootstrap_username=bootstrap_username,
            bootstrap_password_file=bootstrap_password_file,
        )


def load_web_auth_settings(environ: dict[str, str] | None = None) -> WebAuthSettings:
    return WebAuthSettings.from_environ(environ)


def normalize_username(value: str) -> str:
    username = str(value or "").strip().lower()
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("Username must contain 3-64 lowercase letters, numbers, dots, hyphens, or underscores")
    return username


def validate_password(value: str) -> str:
    password = str(value or "")
    if len(password) < MINIMUM_PASSWORD_LENGTH:
        raise ValueError(f"Password must contain at least {MINIMUM_PASSWORD_LENGTH} characters")
    if password.strip() != password or not password.strip():
        raise ValueError("Password must not be empty or start/end with whitespace")
    if password.casefold() in COMMON_PASSWORDS:
        raise ValueError("Password is too common; choose a unique passphrase")
    return password


def read_password_file(path_value: str) -> str:
    try:
        value = Path(path_value).read_text(encoding="utf-8").rstrip("\r\n")
    except OSError as error:
        raise WebAuthConfigurationError("Configured bootstrap password file is unavailable") from error
    return validate_password(value)


class PasswordHasher:
    """Versioned Argon2id password hashing with a deliberately small surface."""

    def __init__(self) -> None:
        try:
            from argon2 import PasswordHasher as Argon2PasswordHasher
            from argon2.low_level import Type
        except ImportError as error:  # pragma: no cover - image dependency contract
            raise RuntimeError("argon2-cffi is required for local web authentication") from error
        self._hasher = Argon2PasswordHasher(
            time_cost=3, memory_cost=65536, parallelism=2,
            hash_len=32, salt_len=16, type=Type.ID,
        )

    def hash(self, password: str) -> str:
        return self._hasher.hash(validate_password(password))

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return bool(self._hasher.verify(password_hash, password))
        except Exception as error:
            from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
            if isinstance(error, (InvalidHashError, VerificationError, VerifyMismatchError)):
                return False
            raise

    def needs_rehash(self, password_hash: str) -> bool:
        return self._hasher.check_needs_rehash(password_hash)


def generate_session_token() -> str:
    return secrets.token_urlsafe(48)


def hash_opaque_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)
