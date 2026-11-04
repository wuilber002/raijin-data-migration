#!/usr/bin/env bash
set -euo pipefail

# Installs a clean, single-runtime Raijin host directly from a checked-out
# repository. Terraform is intentionally not required. On a clean host it
# creates the PostgreSQL and one-time console-bootstrap secrets locally; no
# secret is accepted on argv.

install_root=/opt/raijin-data-migration
config_root=/etc/raijin-data-migration
data_root=/var/lib/raijin-data-migration
runtime_root=/run/raijin-data-migration
source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
revision=""
password_file=""
console_password_file=""
admin_username="admin"
clean=false
skip_start=false
generated_postgres_password=false
generated_console_password=false

usage() {
  cat <<'EOF'
Usage: sudo scripts/install-raijin.sh [options]

Options:
  --source PATH     checked-out Raijin repository (default: this repository)
  --ref GIT_REF     revision to install (default: current source HEAD)
  --postgres-password-file PATH
                    protected existing PostgreSQL password file (optional)
  --console-bootstrap-password-file PATH
                    protected existing temporary ADMIN password file (optional)
  --admin-username USERNAME
                    initial console administrator (default: admin)
  --clean           remove the existing Raijin installation and its data
  --skip-start       install files but do not start the service
  -h, --help         show this help

When omitted, both passwords are generated with Python's cryptographic random
source and stored root-only. The one-time ADMIN password is printed only at
the successful end of a clean installation; change it on first login.

The --clean option deletes only /opt, /etc, /var/lib and /run paths owned by
raijin-data-migration, plus the named Raijin systemd units and containers.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source) source_root="$2"; shift 2 ;;
    --ref) revision="$2"; shift 2 ;;
    --postgres-password-file) password_file="$2"; shift 2 ;;
    --console-bootstrap-password-file) console_password_file="$2"; shift 2 ;;
    --admin-username) admin_username="$2"; shift 2 ;;
    --clean) clean=true; shift ;;
    --skip-start) skip_start=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$(id -u)" -eq 0 ]] || { echo "Run this installer as root." >&2; exit 1; }
[[ -d "$source_root/.git" ]] || { echo "--source must be a Git checkout." >&2; exit 2; }
[[ "$admin_username" =~ ^[a-z0-9][a-z0-9._@+-]{1,127}$ ]] || {
  echo "--admin-username must be a lowercase username or email-style login." >&2; exit 2;
}
for candidate in "$password_file" "$console_password_file"; do
  [[ -z "$candidate" ]] && continue
  [[ -s "$candidate" && -f "$candidate" && ! -L "$candidate" ]] || {
    echo "Password-file options must name non-empty regular files." >&2; exit 2;
  }
done
install_dependencies() {
  local missing=()
  local required
  for required in git podman systemctl python3 curl; do
    command -v "$required" >/dev/null 2>&1 || missing+=("$required")
  done
  ((${#missing[@]} == 0)) && return 0
  if command -v dnf >/dev/null 2>&1; then
    dnf install -y podman git python3 curl
  elif command -v apt-get >/dev/null 2>&1; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y podman git python3 curl
  else
    echo "Missing required commands: ${missing[*]}. Install Podman, Git, Python and curl first." >&2
    return 1
  fi
  for required in "${missing[@]}"; do
    command -v "$required" >/dev/null || {
      echo "Dependency installation did not provide $required" >&2
      return 1
    }
  done
}

install_dependencies

source_root="$(cd "$source_root" && pwd -P)"
revision="${revision:-$(git -C "$source_root" rev-parse HEAD)}"
git -C "$source_root" rev-parse --verify "${revision}^{commit}" >/dev/null

generate_password() {
  python3 - <<'PY'
import secrets
import string

alphabet = string.ascii_letters + string.digits + "!@#%^+=_-"
print("".join(secrets.choice(alphabet) for _ in range(32)))
PY
}

copy_or_generate_secret() {
  local source_path="$1" target_path="$2" label="$3"
  if [[ -n "$source_path" ]]; then
    install -o root -g root -m 0600 "$source_path" "$target_path"
    return 1
  fi
  local generated
  generated="$(generate_password)"
  umask 077
  printf '%s\n' "$generated" >"$target_path"
  chmod 0600 "$target_path"
  GENERATED_SECRET="$generated"
  echo "Generated protected ${label} secret." >&2
  return 0
}

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
postgres_secret="$config_root/secrets/postgres_password"
bootstrap_secret="$config_root/secrets/console_bootstrap_password"
GENERATED_SECRET=""
if copy_or_generate_secret "$password_file" "$postgres_secret" "PostgreSQL"; then
  generated_postgres_password=true
fi
unset GENERATED_SECRET
if copy_or_generate_secret "$console_password_file" "$bootstrap_secret" "console bootstrap"; then
  generated_console_password=true
  console_bootstrap_password="$GENERATED_SECRET"
fi
unset GENERATED_SECRET
install -m 0600 /dev/null "$config_root/oci-runtime.json"
python3 - "$config_root/oci-runtime.json" "$postgres_secret" "$bootstrap_secret" <<'PY'
import json
import os
import sys

target, postgres_path, bootstrap_path = sys.argv[1:]
if not os.path.isabs(postgres_path) or not os.path.isabs(bootstrap_path):
    raise SystemExit("password file paths must be absolute")
with open(target, "w", encoding="utf-8") as output:
    json.dump({"secret_file_paths": {
        "postgres_password": postgres_path,
        "console_bootstrap_password": bootstrap_path,
    }}, output)
    output.write("\n")
PY
chmod 0644 "$config_root/oci-runtime.json"
cat >"$config_root/web-auth.env" <<EOF
# Created by the manual installer. The bootstrap account remains loopback-only
# until the temporary password is changed and retired by the platform.
RAIJIN_WEB_AUTH_MODE=local
RAIJIN_WEB_EXTERNAL_HTTPS=false
RAIJIN_WEB_AUTH_TRUSTED_PROXY_CIDRS=
RAIJIN_WEB_AUTH_SESSION_IDLE_MINUTES=30
RAIJIN_WEB_AUTH_SESSION_ABSOLUTE_MINUTES=720
RAIJIN_WEB_AUTH_BOOTSTRAP_USERNAME=$admin_username
EOF
chmod 0600 "$config_root/web-auth.env"

"$install_root/release/scripts/bootstrap.sh"
if [[ "$skip_start" == true ]]; then
  systemctl stop raijin-data-migration.service
else
  systemctl start raijin-data-migration.service
fi

if [[ "$skip_start" != true ]]; then
  for attempt in $(seq 1 30); do
    if curl --fail --silent http://127.0.0.1:1604/healthz >/dev/null; then
      break
    fi
    [[ "$attempt" -lt 30 ]] || { echo "Raijin console did not become healthy" >&2; exit 1; }
    sleep 2
  done
fi

echo "Raijin revision $revision installed. Console: http://127.0.0.1:1604"
if [[ "$generated_console_password" == true ]]; then
  printf '\nINITIAL ADMIN LOGIN (displayed only by this installer)\n'
  printf 'Username: %s\n' "$admin_username"
  printf 'Temporary password: %s\n' "$console_bootstrap_password"
  printf '%s\n' 'Open the console through the SSH tunnel, change this password immediately, then create your personal administrator account.'
  unset console_bootstrap_password
fi
