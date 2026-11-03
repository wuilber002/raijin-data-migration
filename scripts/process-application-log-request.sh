#!/usr/bin/env bash
# Export bounded application logs through a constrained, root-owned channel.
set -euo pipefail

control_root=/var/lib/raijin-data-migration/application-log-control
request="$control_root/request.json"
result="$control_root/result.json"
output="$control_root/application.log"
mkdir -p "$control_root"
chmod 0750 "$control_root"
[[ -s "$request" ]] || exit 0
mv "$request" "$request.processing"

finish() {
  local status="$1" message="$2" from="${3:-}" until="${4:-}" component="${5:-all}" level="${6:-all}"
  python3 - "$status" "$message" "$from" "$until" "$component" "$level" >"$result.tmp" <<'PY'
import json, sys
print(json.dumps({"status":sys.argv[1],"message":sys.argv[2],"from":sys.argv[3],"until":sys.argv[4],"component":sys.argv[5],"level":sys.argv[6]}))
PY
  chmod 0640 "$result.tmp"; mv "$result.tmp" "$result"; rm -f "$request.processing"
}
trap 'finish FAILED "The host could not collect application logs."' ERR

readarray -t range < <(python3 - "$request.processing" <<'PY'
import datetime as dt, json, sys
try:
    value=json.load(open(sys.argv[1], encoding="utf-8"))
    start=dt.datetime.fromisoformat(str(value["from"]).replace("Z", "+00:00"))
    end=dt.datetime.fromisoformat(str(value["until"]).replace("Z", "+00:00"))
    now=dt.datetime.now(dt.timezone.utc)
    if start.tzinfo is None or end.tzinfo is None or start >= end or end > now + dt.timedelta(minutes=1) or end-start > dt.timedelta(days=7): raise ValueError()
    print(start.astimezone(dt.timezone.utc).isoformat())
    print(end.astimezone(dt.timezone.utc).isoformat())
    component=str(value.get("component", "all")).strip().lower()
    if component not in {"all", "app", "controller", "restore", "discovery", "audit", "transfer", "runtime"}: raise ValueError()
    print(component)
    level=str(value.get("level", "all")).strip().lower()
    if level not in {"all", "debug", "info", "warning", "error", "critical"}: raise ValueError()
    print(level)
except Exception: raise SystemExit(2)
PY
)
[[ ${#range[@]} -eq 4 ]] || { finish REJECTED "Invalid log interval."; exit 0; }
from="${range[0]}"; until="${range[1]}"; component="${range[2]}"; level="${range[3]}"
temporary="$(mktemp "$control_root/application.log.XXXXXX")"
filter_by_level() {
  case "$level" in
    all) cat ;;
    debug) grep -Ei '(^|[^[:alpha:]])DEBUG([^[:alpha:]]|$)' || true ;;
    info) grep -Ei '(^|[^[:alpha:]])INFO([^[:alpha:]]|$)' || true ;;
    warning) grep -Ei '(^|[^[:alpha:]])WARN(ING)?([^[:alpha:]]|$)' || true ;;
    error) grep -Ei '(^|[^[:alpha:]])(ERROR|ERR)([^[:alpha:]]|$)|exception|traceback' || true ;;
    critical) grep -Ei '(^|[^[:alpha:]])(CRITICAL|FATAL)([^[:alpha:]]|$)' || true ;;
  esac
}
{
  printf 'RAIJIN %s %s logs: %s to %s\n\n' "$component" "$level" "$from" "$until"
  declare -A containers=([app]=raijin-app [controller]=raijin-raikou-shin [restore]=raijin-raikou-sei [discovery]=raijin-raikou-ko [audit]=raijin-raikou-kai [transfer]=raijin-transfer-worker)
  selected=()
  if [[ "$component" == all ]]; then selected=("${containers[@]}"); elif [[ "$component" != runtime ]]; then selected=("${containers[$component]}"); fi
  for container in "${selected[@]}"; do
    podman container exists "$container" 2>/dev/null || continue
    printf '\n===== %s =====\n' "$container"
    podman logs --timestamps --since "$from" --until "$until" "$container" 2>&1 || true
  done
  if [[ "$component" == all || "$component" == runtime ]]; then
    printf '\n===== raijin-data-migration.service =====\n'
    journalctl --no-pager --output=short-iso --since "$from" --until "$until" -u raijin-data-migration.service 2>&1 || true
  fi
# ``head`` intentionally closes the pipe at the export limit; do not treat
# that expected SIGPIPE from the redactor as a failed host collection.
set +o pipefail
} | sed -E 's/((password|secret|token|authorization)[=:][[:space:]]*)[^[:space:],}]+/\1[REDACTED]/Ig' | filter_by_level | head -c 4194304 >"$temporary"
set -o pipefail
chmod 0640 "$temporary"; mv "$temporary" "$output"
finish SUCCEEDED "Application logs collected." "$from" "$until" "$component" "$level"
