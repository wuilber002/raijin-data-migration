#!/usr/bin/env bash
set -euo pipefail

# Installs a clean, single-runtime Raijin host directly from a checked-out
# repository. Terraform is intentionally not required. The caller supplies a
# root-readable PostgreSQL password file; no secret is accepted on argv.

install_root=/opt/raijin-data-migration
config_root=/etc/raijin-data-migration
data_root=/var/lib/raijin-data-migration
runtime_root=/run/raijin-data-migration
source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
revision=""
password_file=""
clean=false
skip_start=false

usage() {
  cat <<'EOF'
Usage: sudo scripts/install-raijin.sh --postgres-password-file PATH [options]

Options:
  --source PATH     checked-out Raijin repository (default: this repository)
  --ref GIT_REF     revision to install (default: current source HEAD)
  --clean           remove the existing Raijin installation and its data
  --skip-start       install files but do not start the service
  -h, --help         show this help

The --clean option deletes only /opt, /etc, /var/lib and /run paths owned by
raijin-data-migration, plus the named Raijin systemd units and containers.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source) source_root="$2"; shift 2 ;;
    --ref) revision="$2"; shift 2 ;;
    --postgres-password-file) password_file="$2"; shift 2 ;;
    --clean) clean=true; shift ;;
    --skip-start) skip_start=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$(id -u)" -eq 0 ]] || { echo "Run this installer as root." >&2; exit 1; }
[[ -d "$source_root/.git" ]] || { echo "--source must be a Git checkout." >&2; exit 2; }
[[ -n "$password_file" && -s "$password_file" && -f "$password_file" ]] || {
  echo "--postgres-password-file must name a non-empty regular file." >&2; exit 2;
}
for command in git podman systemctl python3; do
  command -v "$command" >/dev/null || { echo "Missing required command: $command" >&2; exit 1; }
done

source_root="$(cd "$source_root" && pwd -P)"
revision="${revision:-$(git -C "$source_root" rev-parse HEAD)}"
git -C "$source_root" rev-parse --verify "${revision}^{commit}" >/dev/null

units=(
  raijin-data-migration.service
  raijin-web-bind-request.timer raijin-web-bind-request.service
  raijin-application-log-request.timer raijin-application-log-request.service
  raijin-update-request.timer raijin-update-request.service
  raijin-backup-postgres.timer raijin-backup-postgres.service
  raijin-platform-status.timer raijin-platform-status.service
  raijin-mode-request.timer raijin-mode-request.service
)
containers=(
  raijin-app raijin-postgres raijin-raikou-shin raijin-raikou-sei
  raijin-raikou-ko raijin-raikou-kai raijin-transfer-worker
)

if [[ -e "$install_root" || -e "$config_root" || -e "$data_root" ]]; then
  [[ "$clean" == true ]] || {
    echo "A Raijin installation already exists. Re-run with --clean to replace it." >&2
    exit 1
  }
  for unit in "${units[@]}"; do systemctl disable --now "$unit" 2>/dev/null || true; done
  podman stop --ignore "${containers[@]}" >/dev/null 2>&1 || true
  podman rm --force --ignore "${containers[@]}" >/dev/null 2>&1 || true
  rm -rf "$install_root" "$config_root" "$data_root" "$runtime_root"
  for unit in "${units[@]}"; do rm -f "/etc/systemd/system/$unit"; done
  systemctl daemon-reload
fi

install -d -m 0755 "$install_root"
git clone --quiet "$source_root" "$install_root/release"
git -C "$install_root/release" checkout --quiet --detach "$revision"

install -d -m 0700 "$config_root/secrets"
install -m 0600 /dev/null "$config_root/oci-runtime.json"
python3 - "$config_root/oci-runtime.json" "$password_file" <<'PY'
import json
import os
import sys

target, password_path = sys.argv[1:]
if not os.path.isabs(password_path):
    raise SystemExit("password file path must be absolute")
with open(target, "w", encoding="utf-8") as output:
    json.dump({"secret_file_paths": {"postgres_password": password_path}}, output)
    output.write("\n")
PY
chmod 0644 "$config_root/oci-runtime.json"

"$install_root/release/scripts/bootstrap.sh"
if [[ "$skip_start" == true ]]; then
  systemctl stop raijin-data-migration.service
else
  systemctl start raijin-data-migration.service
fi

echo "Raijin revision $revision installed. Console: http://127.0.0.1:1604"
