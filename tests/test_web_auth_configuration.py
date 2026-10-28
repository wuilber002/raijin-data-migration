import pytest

from app.web_auth import WebAuthConfigurationError, WebAuthMode, load_web_auth_settings


def test_web_auth_defaults_to_compatible_disabled_loopback_mode():
    settings = load_web_auth_settings({})
    assert settings.mode is WebAuthMode.DISABLED
    assert settings.bind_host == "127.0.0.1"
    assert settings.enabled is False
    assert settings.session_idle_minutes == 30
    assert settings.session_absolute_minutes == 720


@pytest.mark.parametrize("mode", ["", "oidc", "LOCALHOST"])
def test_web_auth_rejects_unknown_mode(mode):
    with pytest.raises(WebAuthConfigurationError, match="RAIJIN_WEB_AUTH_MODE"):
        load_web_auth_settings({"RAIJIN_WEB_AUTH_MODE": mode})


def test_local_auth_on_non_loopback_requires_https_and_trusted_proxy():
    with pytest.raises(WebAuthConfigurationError, match="non-loopback"):
        load_web_auth_settings({
            "RAIJIN_WEB_AUTH_MODE": "local",
            "RAIJIN_WEB_BIND_HOST": "0.0.0.0",
        })


def test_local_auth_accepts_explicit_https_and_trusted_proxy():
    settings = load_web_auth_settings({
        "RAIJIN_WEB_AUTH_MODE": "local",
        "RAIJIN_WEB_BIND_HOST": "192.0.2.12",
        "RAIJIN_WEB_EXTERNAL_HTTPS": "true",
        "RAIJIN_WEB_AUTH_TRUSTED_PROXY_CIDRS": "192.0.2.0/24, 2001:db8::/32",
        "RAIJIN_WEB_AUTH_BOOTSTRAP_USERNAME": "admin",
        "RAIJIN_WEB_AUTH_BOOTSTRAP_PASSWORD_FILE": "/run/secrets/console_bootstrap_password",
    })
    assert settings.enabled is True
    assert settings.trusted_proxy_networks == ("192.0.2.0/24", "2001:db8::/32")


def test_local_auth_requires_protected_bootstrap_references():
    with pytest.raises(WebAuthConfigurationError, match="bootstrap"):
        load_web_auth_settings({"RAIJIN_WEB_AUTH_MODE": "local"})


@pytest.mark.parametrize("value", ["maybe", "yes please"])
def test_web_auth_rejects_ambiguous_booleans(value):
    with pytest.raises(WebAuthConfigurationError, match="RAIJIN_WEB_EXTERNAL_HTTPS"):
        load_web_auth_settings({"RAIJIN_WEB_EXTERNAL_HTTPS": value})


def test_web_auth_rejects_session_absolute_timeout_shorter_than_idle_timeout():
    with pytest.raises(WebAuthConfigurationError, match="must not be lower"):
        load_web_auth_settings({
            "RAIJIN_WEB_AUTH_SESSION_IDLE_MINUTES": "60",
            "RAIJIN_WEB_AUTH_SESSION_ABSOLUTE_MINUTES": "30",
        })


def test_local_auth_requires_explicit_bootstrap_configuration():
    with pytest.raises(WebAuthConfigurationError, match="bootstrap"):
        load_web_auth_settings({"RAIJIN_WEB_AUTH_MODE": "local"})
