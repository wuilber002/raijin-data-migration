#!/usr/bin/env bash
set -euo pipefail

# This utility is intentionally host-only. It consumes a root-owned password
# file, mounts it read-only into a transient application container, and never
# places the password in argv, environment, logs, or the shell history.
[[ "${EUID:-$(id -u)}" -eq 0 ]] || { echo "Run this recovery utility as root." >&2; exit 1; }
[[ $# -ge 3 ]] || { echo "Usage: raijin-console-admin <create|reset|unlock> <username> --confirm [--role ROLE]" >&2; exit 2; }

action="$1"
username="$2"
shift 2
case "$action" in create|reset|unlock) ;; *) echo "Invalid recovery action." >&2; exit 2;; esac

confirm=false
role=ADMIN
while [[ $# -gt 0 ]]; do
  case "$1" in
    --confirm) confirm=true; shift ;;
    --role) role="${2:?--role requires a value}"; shift 2 ;;
    *) echo "Unsupported argument: $1" >&2; exit 2 ;;
  esac
done
[[ "$confirm" == true ]] || { echo "Recovery requires --confirm." >&2; exit 2; }

secret_root=/etc/s3-oci-migration/secrets
password_file="${RAIJIN_CONSOLE_ADMIN_PASSWORD_FILE:-}"
if [[ "$action" != unlock ]]; then
  [[ -n "$password_file" && -f "$password_file" && ! -L "$password_file" ]] || { echo "Set RAIJIN_CONSOLE_ADMIN_PASSWORD_FILE to a protected regular file." >&2; exit 2; }
  owner="$(stat -c '%u' "$password_file")"
  mode="$(stat -c '%a' "$password_file")"
  [[ "$owner" == 0 ]] && (( (8#$mode & 8#077) == 0 )) || { echo "Recovery password file must be root-owned and mode 0600 or stricter." >&2; exit 2; }
fi
image="${RAIJIN_IMAGE:-$(podman inspect --format '{{.ImageName}}' s3-oci-app 2>/dev/null || true)}"
[[ -n "$image" ]] || { echo "Cannot determine the Raijin image; set RAIJIN_IMAGE." >&2; exit 2; }
args=("$action" "$username" --role "$role" --confirm)
mounts=(-v "$secret_root/postgres_password:/run/secrets/postgres_password:ro,z")
if [[ "$action" != unlock ]]; then
  mounts+=(-v "$password_file:/run/secrets/console_admin_password:ro,z")
  args+=(--password-file /run/secrets/console_admin_password)
fi
podman run --rm --network s3-oci-migration \
  -e RAIJIN_OPERATION_MODE=REAL -e RAIJIN_WEB_AUTH_MODE=disabled \
  -e DATABASE_URL=postgresql+psycopg://migration@postgres:5432/migration \
  -e POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password \
  "${mounts[@]}" "$image" python3 scripts/console-admin.py "${args[@]}"
