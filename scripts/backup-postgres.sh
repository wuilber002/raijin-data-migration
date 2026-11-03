#!/usr/bin/env bash
set -euo pipefail

backup_root=/var/lib/raijin-data-migration/backups
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
retention_days=${RAIJIN_LOGICAL_BACKUP_RETENTION_DAYS:-35}
[[ "$retention_days" =~ ^[0-9]+$ ]] && ((retention_days >= 30)) || {
  echo "RAIJIN_LOGICAL_BACKUP_RETENTION_DAYS must be an integer of at least 30" >&2
  exit 2
}
mkdir -p "$backup_root"

podman exec raijin-postgres pg_dump -U migration -d migration --format=custom \
  >"$backup_root/migration-$timestamp.dump"

# Boot-volume backup remains the recovery layer for the complete machine and
# its PostgreSQL WAL directory.
find "$backup_root" -type f -name 'migration-*.dump' -mtime +"$retention_days" -delete
