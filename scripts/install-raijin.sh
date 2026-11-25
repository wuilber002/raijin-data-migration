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
update_repository="https://github.com/wuilber002/raijin-data-migration.git"
password_file=""
console_password_file=""
oci_runtime_config_file=""
admin_username="admin"
clean=false
skip_start=false
iam_only=false
generated_postgres_password=false
generated_console_password=false

usage() {
  cat <<'EOF'
Usage: sudo scripts/install-raijin.sh [options]

Options:
  --source PATH     checked-out Raijin repository (default: this repository)
  --ref GIT_REF     revision to install (default: current source HEAD)
  --update-repository HTTPS_URL
                    canonical HTTPS repository used by installed platform updates
                    (default: https://github.com/wuilber002/raijin-data-migration.git)
  --postgres-password-file PATH
                    protected existing PostgreSQL password file (optional)
  --console-bootstrap-password-file PATH
                    protected existing temporary ADMIN password file (optional)
  --oci-runtime-config PATH
                    OCI runtime metadata JSON; merged with generated local secrets
  --admin-username USERNAME
                    initial console administrator (default: admin)
  --iam-only        validate only OCI IAM on an installed, running Raijin host
  --clean           remove the existing Raijin installation and its data
  --skip-start       install files but do not start the service
  -h, --help         show this help

When omitted, both passwords are generated with Python's cryptographic random
source and stored root-only. The one-time ADMIN password is printed only at
the successful end of a clean installation; change it on first login.

--iam-only neither installs nor restarts Raijin. It writes and prints the IAM
report for the existing installation.

The --clean option deletes only /opt, /etc, /var/lib and /run paths owned by
raijin-data-migration, plus the named Raijin systemd units and containers.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source) source_root="$2"; shift 2 ;;
    --ref) revision="$2"; shift 2 ;;
    --update-repository) update_repository="$2"; shift 2 ;;
    --postgres-password-file) password_file="$2"; shift 2 ;;
    --console-bootstrap-password-file) console_password_file="$2"; shift 2 ;;
    --oci-runtime-config) oci_runtime_config_file="$2"; shift 2 ;;
    --admin-username) admin_username="$2"; shift 2 ;;
    --iam-only) iam_only=true; shift ;;
    --clean) clean=true; shift ;;
    --skip-start) skip_start=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$(id -u)" -eq 0 ]] || { echo "Run this installer as root." >&2; exit 1; }
if [[ "$iam_only" == true ]]; then
  [[ "$clean" == false && "$skip_start" == false && -z "$password_file" && -z "$console_password_file" && -z "$oci_runtime_config_file" ]] || {
    echo "--iam-only cannot be combined with installation options." >&2; exit 2;
  }
else
  [[ -d "$source_root/.git" ]] || { echo "--source must be a Git checkout." >&2; exit 2; }
fi
[[ "$admin_username" =~ ^[a-z0-9][a-z0-9._@+-]{1,127}$ ]] || {
  echo "--admin-username must be a lowercase username or email-style login." >&2; exit 2;
}
[[ "$update_repository" =~ ^https://[^[:space:]]+\.git$ ]] || {
  echo "--update-repository must be an HTTPS Git URL ending in .git." >&2
  exit 2
}
for candidate in "$password_file" "$console_password_file" "$oci_runtime_config_file"; do
  [[ -z "$candidate" ]] && continue
  [[ -s "$candidate" && -f "$candidate" && ! -L "$candidate" ]] || {
    echo "Password-file options must name non-empty regular files." >&2; exit 2;
  }
done

render_iam_report() {
  local report_path="$1"
  python3 - "$report_path" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    report = json.load(source)

def line(status, subject, detail):
    labels = {
        "OK": "LIBERADA",
        "FAILED": "BLOQUEADA",
        "MISSING": "AUSENTE",
        "NOT_CONFIGURED": "PENDENTE_CONFIG",
        "CONFIGURATION_REQUIRED": "PENDENTE_CONFIG",
        "UNKNOWN": "NAO_VERIFICAVEL",
    }
    print(f"  [{labels.get(status, status):<22}] {subject}: {detail}")

print("\nRELATORIO DE VALIDACAO IAM OCI")
print("Permissoes efetivas")
for check in report.get("checks", []):
    line(check.get("status", "UNKNOWN"), check.get("name", "check"), check.get("detail", ""))
group = report.get("dynamic_group", {})
print("Dynamic Group")
line(group.get("status", "UNKNOWN"), group.get("matching_rule") or group.get("name", "Dynamic Group"), group.get("detail", ""))
policy = report.get("policy", {})
print(f"Policies necessarias ({policy.get('compartment_id', '<POLICY_COMPARTMENT_OCID>')})")
for statement in policy.get("statements", []):
    line(statement.get("status", "UNKNOWN"), statement.get("statement", "statement"), statement.get("detail", ""))
if not policy.get("statements"):
    print("  [PENDENTE_CONFIG] Preencha iam_preflight em oci-runtime.json para gerar os statements.")
print(f"Resultado: {'PRONTO' if report.get('ready') else 'PENDENTE'}")
print("Nota: NAO_VERIFICAVEL significa que a VM nao pode inspecionar IAM; nao significa que a policy esteja ausente.")
raise SystemExit(0 if report.get("ready") else 3)
PY
}

run_iam_preflight() {
  local report_path="$data_root/oci-iam-preflight.json"
  [[ -f "$config_root/oci-runtime.json" ]] || {
    echo "OCI runtime configuration is missing: $config_root/oci-runtime.json" >&2
    return 1
  }
  podman inspect --format '{{.State.Running}}' raijin-app 2>/dev/null | grep -qx true || {
    echo "Raijin application container is not running; start raijin-data-migration.service first." >&2
    return 1
  }
  podman exec raijin-app python3 scripts/oci-iam-preflight.py \
    --runtime-config /run/oci-runtime/oci-runtime.json \
    --output /tmp/oci-iam-preflight.json
  install -d -m 0700 "$data_root"
  podman cp raijin-app:/tmp/oci-iam-preflight.json "$report_path"
  chmod 0600 "$report_path"
  echo "OCI IAM preflight report: $report_path"
  render_iam_report "$report_path"
}

if [[ "$iam_only" == true ]]; then
  for required in podman python3; do
    command -v "$required" >/dev/null || { echo "Missing required command: $required" >&2; exit 1; }
  done
  run_iam_preflight
  exit $?
fi
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
# The installation source may be a disposable local checkout (for example
# /tmp/raijin-data-migration).  Never retain that path as the update remote:
# the root-owned update service must fetch from the stable HTTPS repository.
git -C "$install_root/release" remote set-url origin "$update_repository"

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
if [[ -n "$oci_runtime_config_file" ]]; then
  install -o root -g root -m 0600 "$oci_runtime_config_file" "$config_root/oci-runtime.json"
else
  install -m 0600 /dev/null "$config_root/oci-runtime.json"
fi
python3 - "$config_root/oci-runtime.json" "$postgres_secret" "$bootstrap_secret" <<'PY'
import json
import os
import sys

target, postgres_path, bootstrap_path = sys.argv[1:]
if not os.path.isabs(postgres_path) or not os.path.isabs(bootstrap_path):
    raise SystemExit("password file paths must be absolute")
try:
    with open(target, encoding="utf-8") as source:
        runtime = json.load(source)
except json.JSONDecodeError as error:
    raise SystemExit(f"OCI runtime configuration is not valid JSON: {error.msg}") from error
if not isinstance(runtime, dict):
    raise SystemExit("OCI runtime configuration must be a JSON object")
secret_ocids = runtime.get("secret_ocids", {})
if not isinstance(secret_ocids, dict):
    raise SystemExit("secret_ocids must be a JSON object when configured")
for name in ("postgres_password", "console_bootstrap_password"):
    if secret_ocids.get(name):
        raise SystemExit(
            f"{name} must not be supplied in secret_ocids during manual installation; "
            "the installer generates and owns its local bootstrap secret"
        )
paths = runtime.get("secret_file_paths", {})
if not isinstance(paths, dict):
    raise SystemExit("secret_file_paths must be a JSON object when configured")
paths.update({
    "postgres_password": postgres_path,
    "console_bootstrap_password": bootstrap_path,
})
runtime["secret_file_paths"] = paths
runtime["secret_ocids"] = secret_ocids
with open(target, "w", encoding="utf-8") as output:
    json.dump(runtime, output, indent=2, sort_keys=True)
    output.write("\n")
PY
chmod 0600 "$config_root/oci-runtime.json"
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

# The IAM report is always generated after the complete runtime is healthy.
# It is diagnostic: a local-secret bootstrap or a least-privilege Instance
# Principal can legitimately leave declaration inspection as UNKNOWN.
if [[ "$skip_start" != true ]]; then
  if ! run_iam_preflight; then
    echo "Raijin was installed and is healthy, but OCI IAM validation is pending or blocked; review the report above." >&2
  fi
fi

echo "Raijin revision $revision installed. Console: http://127.0.0.1:1604"
if [[ "$generated_console_password" == true ]]; then
  printf '\nINITIAL ADMIN LOGIN (displayed only by this installer)\n'
  printf 'Username: %s\n' "$admin_username"
  printf 'Temporary password: %s\n' "$console_bootstrap_password"
  printf '%s\n' 'Open the console through the SSH tunnel, change this password immediately, then create your personal administrator account.'
  unset console_bootstrap_password
fi
