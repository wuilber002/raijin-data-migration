#!/usr/bin/env bash
set -euo pipefail

# Rotates the already-running local PostgreSQL only after Vault contains the
# new value. The secret is never printed or written to a log.
install_root=/opt/raijin-data-migration/release
secret_root=/etc/raijin-data-migration/secrets
runtime_config=/etc/raijin-data-migration/oci-runtime.json
current_password_file="$secret_root/postgres_password"
candidate_password_file="$secret_root/.postgres_password.vault"
container_candidate_file=/tmp/.raijin-postgres-password.vault

[[ -s "$current_password_file" ]] || {
  echo "Local PostgreSQL password file is missing; use bootstrap for first initialization." >&2
  exit 1
}

python3 "$install_root/scripts/fetch-oci-secret.py" \
  --runtime-config "$runtime_config" \
  --secret-name postgres_password \
  --output "$candidate_password_file"

if cmp -s "$current_password_file" "$candidate_password_file"; then
  rm -f "$candidate_password_file"
  exit 0
fi

cleanup_candidate() {
  rm -f "$candidate_password_file"
  podman exec raijin-postgres rm -f "$container_candidate_file" >/dev/null 2>&1 || true
}
trap cleanup_candidate EXIT

# Do not interpolate the password into an argument or environment variable.
# PostgreSQL reads a short-lived, owner-only candidate inside its own
# container, then quotes it server-side with format(%L). This supports normal
# Vault-generated punctuation without logging or exposing the value to ps.
podman cp "$candidate_password_file" "raijin-postgres:$container_candidate_file"
podman exec raijin-postgres chown 70:70 "$container_candidate_file"
podman exec raijin-postgres chmod 0600 "$container_candidate_file"
podman exec -i raijin-postgres psql -v ON_ERROR_STOP=1 -U migration -d migration <<SQL >/dev/null
DO \$block\$
DECLARE
  vault_password text := btrim(pg_read_file('$container_candidate_file'), E' \\n\\r\\t');
BEGIN
  IF vault_password = '' THEN
    RAISE EXCEPTION 'Vault PostgreSQL password is empty';
  END IF;
  EXECUTE format('ALTER ROLE migration PASSWORD %L', vault_password);
END
\$block\$;
SQL

install -o root -g root -m 0600 "$candidate_password_file" "$current_password_file"
cleanup_candidate
trap - EXIT
