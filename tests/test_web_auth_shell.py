import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def load_auth_config(tmp_path, contents: str):
    config = tmp_path / "web-auth.env"
    config.write_text(contents, encoding="utf-8")
    environment = os.environ | {"RAIJIN_WEB_AUTH_CONFIG": str(config)}
    return subprocess.run(
        ["bash", "-c", 'source scripts/web-auth.sh; raijin_load_web_auth || exit $?; env | grep "^RAIJIN_WEB_AUTH_"'],
        cwd=ROOT, env=environment, text=True, capture_output=True,
    )


def test_web_auth_loader_exports_documented_values(tmp_path):
    result = load_auth_config(tmp_path, "\n".join((
        "RAIJIN_WEB_AUTH_MODE=disabled",
        "RAIJIN_WEB_EXTERNAL_HTTPS=false",
        "RAIJIN_WEB_AUTH_TRUSTED_PROXY_CIDRS=",
        "RAIJIN_WEB_AUTH_SESSION_IDLE_MINUTES=15",
        "RAIJIN_WEB_AUTH_SESSION_ABSOLUTE_MINUTES=180",
        "",
    )))
    assert result.returncode == 0, result.stderr
    assert "RAIJIN_WEB_AUTH_SESSION_IDLE_MINUTES=15" in result.stdout
    assert "RAIJIN_WEB_AUTH_SESSION_ABSOLUTE_MINUTES=180" in result.stdout


def test_web_auth_loader_rejects_unknown_keys(tmp_path):
    result = load_auth_config(tmp_path, "RAIJIN_WEB_AUTH_UNSAFE=true\n")
    assert result.returncode != 0
    assert "Unsupported web authentication configuration key" in result.stderr
