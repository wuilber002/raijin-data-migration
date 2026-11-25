from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_endpoint_processor_recreates_network_and_rolls_back_unhealthy_publish():
    script = (ROOT / "scripts/process-web-bind-request.sh").read_text(encoding="utf-8")
    assert "verify_published_endpoint()" in script
    assert "--connect-timeout 5 --max-time 10" in script
    assert "previous endpoint was restored after recreating" in script
    assert "confirm_network_recreation" in script
    assert "podman network rm" in script
    assert 'systemctl stop "$runtime_service"' in script
    assert "restore_previous_endpoint_files" in script
