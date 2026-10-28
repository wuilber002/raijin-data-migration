#!/usr/bin/env bash
set -euo pipefail

# Converts a new host that was intentionally bootstrapped with random local
# PostgreSQL passwords into the normal OCI Vault-backed installation. It never
# prints password values. Run only after the OCI runtime config, Dynamic Group
# and Vault policies have been configured and validated.
install_root=/opt/s3-oci-migration/release
secret_root=/etc/s3-oci-migration/secrets
runtime_config=/etc/s3-oci-migration/oci-runtime.json
temporary_marker=/etc/s3-oci-migration/temporary-local-secrets
simulation_candidate="$secret_root/.simulation_postgres_password.vault"
mode_file=/etc/s3-oci-migration/operation-mode

[[ "$(id -u)" -eq 0 ]] || { echo "Run as root." >&2; exit 1; }
[[ -f "$temporary_marker" ]] || {
  echo "This host is not marked as a temporary-local-secrets installation." >&2
  exit 1
}
[[ -s "$secret_root/postgres_password" ]] || {
  echo "Temporary PostgreSQL password file is missing." >&2
  exit 1
}
[[ -f "$runtime_config" ]] || { echo "OCI runtime configuration is missing." >&2; exit 1; }
podman inspect s3-oci-postgres >/dev/null 2>&1 || {
  echo "PostgreSQL container must be running before adopting Vault secrets." >&2
  exit 1
}

trap 'rm -f "$simulation_candidate"' EXIT

# The existing rotation script reads Vault into a candidate, changes the
# running migration role, then atomically installs the file.
"$install_root/scripts/sync-postgres-password-from-vault.sh"

operation_mode=REAL
if [[ -s "$mode_file" ]]; then
  operation_mode="$(tr '[:lower:]' '[:upper:]' <"$mode_file")"
fi
if [[ "$operation_mode" != SIMULATION ]]; then
  rm -f "$temporary_marker"
  echo "Vault PostgreSQL Secret adopted for REAL mode."
  exit 0
fi

[[ -s "$secret_root/simulation_postgres_password" ]] || {
  echo "Temporary simulation PostgreSQL password file is missing." >&2
  exit 1
}

python3 "$install_root/scripts/fetch-oci-secret.py" \
  --runtime-config "$runtime_config" \
  --secret-name simulation_postgres_password \
  --output "$simulation_candidate"

install -o root -g root -m 0600 "$simulation_candidate" "$secret_root/simulation_postgres_password"
chown 70:70 "$secret_root/simulation_postgres_password"
chmod 0400 "$secret_root/simulation_postgres_password"

# The auxiliary role is isolated from the REAL control plane, but align it now
# so a future LOCAL Fujin profile starts with the Vault value as well.
podman exec -i s3-oci-postgres psql -U migration -d migration -v ON_ERROR_STOP=1 <<'SQL'
DO $block$
DECLARE
  simulation_password text := btrim(
    pg_read_file('/run/secrets/simulation_postgres_password'),
    E' \n\r\t'
  );
BEGIN
  EXECUTE format('ALTER ROLE migration_simulation PASSWORD %L', simulation_password);
END
$block$;
SQL

rm -f "$temporary_marker"
echo "Vault secrets adopted. Restart the Raijin service to verify the normal startup path."
