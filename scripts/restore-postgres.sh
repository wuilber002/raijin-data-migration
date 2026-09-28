#!/usr/bin/env bash
set -euo pipefail

# Deliberately explicit recovery tool.  It is never called by the platform and
# refuses ambiguous paths or an omitted confirmation because it replaces the
# durable control-plane state (inventory, tasks, waves and audit evidence).
backup_root=/var/lib/s3-oci-migration/backups
confirm=false
backup_file=''

usage() {
  cat <<'EOF'
Usage: s3-oci-restore-postgres --backup /var/lib/s3-oci-migration/backups/migration-<timestamp>.dump --confirm-restore
       s3-oci-restore-postgres --backup /var/lib/s3-oci-migration/backups/migration-simulation-<timestamp>.dump --confirm-restore

Restores one logical PostgreSQL backup into the Raijin control plane. The
current database is backed up immediately before replacement. This operation
does not alter S3 or OCI objects, but it can roll the Raijin task state back.
EOF
}

while (($#)); do
  case "$1" in
    --backup) backup_file=${2:-}; shift 2 ;;
    --confirm-restore) confirm=true; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$confirm" == true && -n "$backup_file" ]] || { usage >&2; exit 2; }
[[ -f "$backup_file" ]] || { echo "Backup file not found: $backup_file" >&2; exit 2; }

backup_root_real=$(realpath "$backup_root")
backup_file_real=$(realpath "$backup_file")
[[ "$backup_file_real" == "$backup_root_real"/* ]] || {
  echo "Backup must be inside $backup_root_real" >&2
  exit 2
}

if [[ "$(podman inspect --format '{{.State.Running}}' s3-oci-postgres 2>/dev/null || true)" != true ]]; then
  echo "The PostgreSQL container must be running before a logical restore." >&2
  echo "Start s3-oci-migration.service first, then retry this command." >&2
  exit 1
fi

target_database=migration
target_owner=migration
writers=(s3-oci-app s3-oci-governance-worker s3-oci-transfer-worker)
if [[ "$(basename "$backup_file_real")" == migration-simulation-* ]]; then
  target_database=migration_simulation
  target_owner=migration_simulation
  writers=(s3-oci-fujin-local s3-oci-fujin-local-materializer)
fi

# Quiesce only processes that can write to the selected database. Stopping the
# platform unit would invoke ExecStop, remove PostgreSQL itself and make the
# subsequent pg_restore impossible.
running_writers=()
for container in "${writers[@]}"; do
  if [[ "$(podman inspect --format '{{.State.Running}}' "$container" 2>/dev/null || true)" == true ]]; then
    running_writers+=("$container")
  fi
done
if ((${#running_writers[@]})); then
  podman stop -t 30 "${running_writers[@]}" >/dev/null
fi

restore_succeeded=false
finish_restore() {
  if [[ "$restore_succeeded" != true ]]; then
    echo "Restore failed; database writers remain stopped for operator recovery." >&2
    return
  fi
  if ((${#running_writers[@]})); then
    podman start "${running_writers[@]}" >/dev/null || true
  fi
}
trap finish_restore EXIT

# Preserve the current state before a potentially irreversible logical restore.
/usr/local/sbin/s3-oci-backup-postgres
# Recreate only the selected logical database. Restoring with --clean into an
# evolved schema can fail when newly added foreign keys depend on constraints
# that did not exist in the older dump.
podman exec s3-oci-postgres dropdb -U migration --force "$target_database"
podman exec s3-oci-postgres createdb -U migration -O "$target_owner" "$target_database"
podman exec -i s3-oci-postgres pg_restore -U migration -d "$target_database" \
  --no-owner --exit-on-error <"$backup_file_real"

restore_succeeded=true
finish_restore
trap - EXIT
if ((${#running_writers[@]} == 0)); then
  echo "PostgreSQL restore completed; database writers were already stopped."
  exit 0
fi
for attempt in $(seq 1 30); do
  if curl --fail --silent http://127.0.0.1:8080/healthz >/dev/null; then
    echo "Raijin PostgreSQL restore completed and API is healthy."
    exit 0
  fi
  sleep 2
done

echo "PostgreSQL restore completed, but the Raijin API did not become healthy." >&2
exit 1
