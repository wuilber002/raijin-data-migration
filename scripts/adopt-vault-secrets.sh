#!/usr/bin/env bash
set -euo pipefail

# Converts a new host that was intentionally bootstrapped with random local
# PostgreSQL passwords into the normal OCI Vault-backed installation. It never
# prints password values. Run only after the OCI runtime config, Dynamic Group
# and Vault policies have been configured and validated.
install_root=/opt/raijin-data-migration/release
secret_root=/etc/raijin-data-migration/secrets
runtime_config=/etc/raijin-data-migration/oci-runtime.json
temporary_marker=/etc/raijin-data-migration/temporary-local-secrets

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
podman inspect raijin-postgres >/dev/null 2>&1 || {
  echo "PostgreSQL container must be running before adopting Vault secrets." >&2
  exit 1
}

# The existing rotation script reads Vault into a candidate, changes the
# running migration role, then atomically installs the file.
"$install_root/scripts/sync-postgres-password-from-vault.sh"

rm -f "$temporary_marker"
echo "Vault PostgreSQL Secret adopted. Restart the Raijin service to verify the normal startup path."
