from pathlib import Path

import pytest

from app.cloud_backends import RealCloudBackend
from app.runtime_context import OperationMode, load_runtime_context


def test_real_mode_is_the_only_raijin_runtime():
    context = load_runtime_context({"DATABASE_URL": "sqlite+pysqlite:///:memory:"})
    assert context.mode is OperationMode.REAL
    assert RealCloudBackend().readiness().operations_enabled


def test_launcher_does_not_expose_a_profile_selection():
    bootstrap = Path("scripts/bootstrap.sh").read_text(encoding="utf-8")
    runtime = Path("scripts/start-runtime.sh").read_text(encoding="utf-8")
    assert "mode_file=" not in bootstrap
    assert "SIMULATION)" not in runtime


def test_host_bootstrap_contains_one_real_runtime_and_no_fujin_topology():
    bootstrap = Path("scripts/bootstrap.sh").read_text(encoding="utf-8")
    runtime = Path("scripts/start-runtime.sh").read_text(encoding="utf-8")

    assert "deployment_profile_file" not in bootstrap
    assert 'install -m 0750 "$install_root/scripts/start-fujin-local-runtime.sh"' not in bootstrap
    assert "simulation_postgres_password" not in bootstrap
    assert "raijin-data-migration.service" in bootstrap
    assert "RAIJIN_OPERATION_MODE=SIMULATION" not in runtime
    assert runtime.count("RAIJIN_OPERATION_MODE=REAL") == 3


def test_manual_installer_is_explicit_about_clean_replacement_and_secret_source():
    installer = Path("scripts/install-raijin.sh").read_text(encoding="utf-8")
    assert "--postgres-password-file" in installer
    assert "--clean" in installer
    assert '"secret_file_paths": {"postgres_password": password_path}' in installer
    assert "/opt/raijin-data-migration" in installer


def test_fujin_code_has_a_separate_repository_boundary():
    plan = Path("operacional/plan/plan-raijin-fujin-separation.md").read_text(encoding="utf-8")
    assert "Fujin passa a ser um produto independente" in plan
