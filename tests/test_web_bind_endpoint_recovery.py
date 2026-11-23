from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_endpoint_processor_verifies_and_rolls_back_unhealthy_publish():
    script = (ROOT / "scripts/process-web-bind-request.sh").read_text(encoding="utf-8")
    assert "verify_published_endpoint()" in script
    assert "--connect-timeout 5 --max-time 10" in script
    assert "previous endpoint configuration was restored" in script
    assert "podman network rm" not in script
