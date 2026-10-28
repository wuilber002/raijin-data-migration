#!/usr/bin/env bash
set -euo pipefail

# A read-only host-side gate for disabled -> local activation. It deliberately
# mounts only the database credential, non-secret policy and bootstrap file.
[[ "${EUID:-$(id -u)}" -eq 0 ]] || { echo "Run this preflight as root." >&2; exit 1; }
install_root=/opt/s3-oci-migration/release
secret_root=/etc/s3-oci-migration/secrets
runtime_config=/etc/s3-oci-migration/oci-runtime.json
source "$install_root/scripts/web-auth.sh"
raijin_load_web_auth
[[ "$RAIJIN_WEB_AUTH_MODE" == local ]] || { echo "Set RAIJIN_WEB_AUTH_MODE=local before preflight." >&2; exit 2; }
[[ -s "$secret_root/console_bootstrap_password" ]] || { echo "Materialized console_bootstrap_password is missing." >&2; exit 2; }
image="${RAIJIN_IMAGE:-$(podman inspect --format '{{.ImageName}}' s3-oci-app 2>/dev/null || true)}"
[[ -n "$image" ]] || { echo "Cannot determine the Raijin image; set RAIJIN_IMAGE." >&2; exit 2; }

podman run --rm --network s3-oci-migration \
  -e RAIJIN_OPERATION_MODE=REAL \
  -e DATABASE_URL=postgresql+psycopg://migration@postgres:5432/migration \
  -e POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password \
  -e "RAIJIN_WEB_BIND_HOST=127.0.0.1" \
  -e "RAIJIN_WEB_AUTH_MODE=$RAIJIN_WEB_AUTH_MODE" \
  -e "RAIJIN_WEB_EXTERNAL_HTTPS=$RAIJIN_WEB_EXTERNAL_HTTPS" \
  -e "RAIJIN_WEB_AUTH_TRUSTED_PROXY_CIDRS=$RAIJIN_WEB_AUTH_TRUSTED_PROXY_CIDRS" \
  -e "RAIJIN_WEB_AUTH_SESSION_IDLE_MINUTES=$RAIJIN_WEB_AUTH_SESSION_IDLE_MINUTES" \
  -e "RAIJIN_WEB_AUTH_SESSION_ABSOLUTE_MINUTES=$RAIJIN_WEB_AUTH_SESSION_ABSOLUTE_MINUTES" \
  -e "RAIJIN_WEB_AUTH_BOOTSTRAP_USERNAME=$RAIJIN_WEB_AUTH_BOOTSTRAP_USERNAME" \
  -e RAIJIN_WEB_AUTH_BOOTSTRAP_PASSWORD_FILE=/run/secrets/console_bootstrap_password \
  -v "$secret_root/postgres_password:/run/secrets/postgres_password:ro,z" \
  -v "$secret_root/console_bootstrap_password:/run/secrets/console_bootstrap_password:ro,z" \
  -v "$runtime_config:/run/oci-runtime/oci-runtime.json:ro,z" \
  "$image" python3 scripts/console-auth-preflight.py
