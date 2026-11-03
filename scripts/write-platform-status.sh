#!/usr/bin/env bash
set -euo pipefail

runtime_root=/run/raijin-data-migration
status_file="$runtime_root/status.json"
backup_root=/var/lib/raijin-data-migration/backups
mkdir -p "$runtime_root"

unit_state() {
  if systemctl is-active --quiet "$1"; then
    printf 'active'
  else
    printf 'inactive'
  fi
}

container_state() {
  podman inspect --format '{{.State.Status}}' "$1" 2>/dev/null || printf 'absent'
}

latest_backup_json() {
  local pattern=$1 latest_backup_file='' latest_backup=''
  if latest_backup_file=$(find "$backup_root" -maxdepth 1 -type f -name "$pattern" -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -n1); then
    latest_backup=${latest_backup_file#* }
  fi
  if [[ -z "$latest_backup" ]]; then
    printf 'null'
    return
  fi
  printf '{"path":"%s","modified_at":"%s","size_bytes":%s}' \
    "$latest_backup" \
    "$(date -u -r "$latest_backup" +%Y-%m-%dT%H:%M:%SZ)" \
    "$(stat -c %s "$latest_backup")"
}

real_backup_json=$(latest_backup_json 'migration-[0-9]*.dump')

# CPU is calculated from consecutive host-wide /proc/stat samples. The status
# timer runs every minute, so this represents VM utilization during the last
# interval rather than container-only consumption.
read -r cpu_total cpu_idle < <(awk '/^cpu / {total=0; for(i=2;i<=NF;i++) total+=$i; print total, $5+$6}' /proc/stat)
cpu_state_file="$runtime_root/cpu-ticks"
cpu_percent=0
if [[ -f "$cpu_state_file" ]]; then
  read -r previous_total previous_idle <"$cpu_state_file" || true
  total_delta=$((cpu_total - ${previous_total:-cpu_total}))
  idle_delta=$((cpu_idle - ${previous_idle:-cpu_idle}))
  if (( total_delta > 0 )); then
    cpu_percent=$(awk -v total="$total_delta" -v idle="$idle_delta" 'BEGIN { printf "%.2f", (total-idle)*100/total }')
  fi
fi
printf '%s %s\n' "$cpu_total" "$cpu_idle" >"$cpu_state_file"
cpu_count=$(getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || echo 0)
[[ "$cpu_count" =~ ^[1-9][0-9]*$ ]] || cpu_count=0

memory_total_kb=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
memory_available_kb=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
memory_used_kb=$((memory_total_kb - memory_available_kb))
memory_percent=$(awk -v total="$memory_total_kb" -v used="$memory_used_kb" 'BEGIN { printf "%.2f", used*100/total }')

temporary_file=$(mktemp "$runtime_root/status.XXXXXX")
printf '{"available":true,"generated_at":"%s","resources":{"cpu_percent":%s,"cpu_count":%s,"memory_total_bytes":%s,"memory_used_bytes":%s,"memory_percent":%s},"services":{"migration_systemd":"%s","postgres_container":"%s","app_container":"%s","raikou_shin_worker":"%s","raikou_sei_worker":"%s","raikou_ko_worker":"%s","raikou_kai_worker":"%s","transfer_worker":"%s","postgres_backup_timer":"%s","platform_status_timer":"%s"},"last_postgres_backups":{"REAL":%s}}\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  "$cpu_percent" \
  "$cpu_count" \
  "$((memory_total_kb * 1024))" \
  "$((memory_used_kb * 1024))" \
  "$memory_percent" \
  "$(unit_state raijin-data-migration.service)" \
  "$(container_state raijin-postgres)" \
  "$(container_state raijin-app)" \
  "$(container_state raijin-raikou-shin)" \
  "$(container_state raijin-raikou-sei)" \
  "$(container_state raijin-raikou-ko)" \
  "$(container_state raijin-raikou-kai)" \
  "$(container_state raijin-transfer-worker)" \
  "$(unit_state raijin-backup-postgres.timer)" \
  "$(unit_state raijin-platform-status.timer)" \
  "$real_backup_json" >"$temporary_file"
chmod 644 "$temporary_file"
mv "$temporary_file" "$status_file"
