import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_bind(tmp_path, config, **environment):
    config_file = tmp_path / "web-bind.env"
    config_file.write_text(config, encoding="utf-8")
    command = (
        f'set -e; source "{ROOT}/scripts/web-bind.sh"; '
        'raijin_load_web_bind; '
        'printf "%s|%s|%s|%s\\n" "$RAIJIN_WEB_BIND_HOST" '
        '"$RAIJIN_WEB_BIND_PORT" "$RAIJIN_WEB_BIND_PUBLISH" "$RAIJIN_WEB_BIND_PROBE_URL"'
    )
    env = os.environ | {"RAIJIN_WEB_BIND_CONFIG": str(config_file)} | environment
    return subprocess.run(["bash", "-c", command], text=True, capture_output=True, env=env)


def test_web_bind_defaults_to_private_1604_when_config_is_absent(tmp_path):
    run = load_bind(tmp_path, "")
    assert run.returncode == 0, run.stderr
    assert run.stdout == "127.0.0.1|1604|127.0.0.1:1604:8080|http://127.0.0.1:1604\n"


def test_web_bind_accepts_wildcard_https_and_probes_it_through_loopback(tmp_path):
    run = load_bind(tmp_path, "WEB_BIND_HOST=0.0.0.0\nWEB_BIND_PORT=9443\nWEB_TRANSPORT=https\n")
    assert run.returncode == 0, run.stderr
    assert run.stdout == "0.0.0.0|9443|0.0.0.0:9443:8080|https://127.0.0.1:9443\n"


def test_web_bind_environment_override_wins_over_persisted_config(tmp_path):
    run = load_bind(
        tmp_path,
        "WEB_BIND_HOST=127.0.0.1\nWEB_BIND_PORT=1604\n",
        RAIJIN_WEB_BIND_HOST="192.0.2.10",
        RAIJIN_WEB_BIND_PORT="8088",
        RAIJIN_WEB_TRANSPORT="https",
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout == "192.0.2.10|8088|192.0.2.10:8088:8080|https://192.0.2.10:8088\n"


def test_web_bind_rejects_non_address_or_invalid_port(tmp_path):
    run = load_bind(tmp_path, "WEB_BIND_HOST=outside.example\nWEB_BIND_PORT=1604\n")
    assert run.returncode != 0
    assert "WEB_BIND_HOST" in run.stderr
    run = load_bind(tmp_path, "WEB_BIND_HOST=127.0.0.1\nWEB_BIND_PORT=70000\n")
    assert run.returncode != 0
    assert "WEB_BIND_PORT" in run.stderr


def test_non_loopback_http_requires_closed_ipv4_upstream_allowlist(tmp_path):
    run = load_bind(tmp_path, "WEB_BIND_HOST=10.0.0.10\nWEB_BIND_PORT=8080\nWEB_TRANSPORT=http\n")
    assert run.returncode != 0
    assert "WEB_TRUSTED_UPSTREAM_IPS" in run.stderr
    run = load_bind(tmp_path, "WEB_BIND_HOST=10.0.0.10\nWEB_BIND_PORT=8080\nWEB_TRANSPORT=http\nWEB_TRUSTED_UPSTREAM_IPS=10.0.0.21/24\n")
    assert run.returncode != 0
    assert "/32" in run.stderr
    run = load_bind(tmp_path, "WEB_BIND_HOST=10.0.0.10\nWEB_BIND_PORT=8080\nWEB_TRANSPORT=http\nWEB_TRUSTED_UPSTREAM_IPS=10.0.0.21/32,10.0.0.22/32\n")
    assert run.returncode == 0, run.stderr
