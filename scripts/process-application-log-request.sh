#!/usr/bin/env bash
# Export bounded application logs through a constrained, root-owned channel.
set -euo pipefail

control_root=/var/lib/s3-oci-migration/application-log-control
request="$control_root/request.json"
result="$control_root/result.json"
output="$control_root/application.log"
mkdir -p "$control_root"
chmod 0750 "$control_root"
[[ -s "$request" ]] || exit 0
mv "$request" "$request.processing"

finish() {
  local status="$1" message="$2" from="${3:-}" until="${4:-}"
  python3 - "$status" "$message" "$from" "$until" >"$result.tmp" <<'PY'
import json, sys
print(json.dumps({"status":sys.argv[1],"message":sys.argv[2],"from":sys.argv[3],"until":sys.argv[4]}))
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
except Exception: raise SystemExit(2)
PY
)
[[ ${#range[@]} -eq 2 ]] || { finish REJECTED "Invalid log interval."; exit 0; }
from="${range[0]}"; until="${range[1]}"
temporary="$(mktemp "$control_root/application.log.XXXXXX")"
{
  printf 'RAIJIN application logs: %s to %s\n\n' "$from" "$until"
  for container in s3-oci-app s3-oci-raikou-shin s3-oci-raikou-sei s3-oci-raikou-ko s3-oci-raikou-kai s3-oci-transfer-worker; do
    podman container exists "$container" 2>/dev/null || continue
    printf '\n===== %s =====\n' "$container"
    podman logs --timestamps --since "$from" --until "$until" "$container" 2>&1 || true
  done
  printf '\n===== s3-oci-migration.service =====\n'
  journalctl --no-pager --output=short-iso --since "$from" --until "$until" -u s3-oci-migration.service 2>&1 || true
# ``head`` intentionally closes the pipe at the export limit; do not treat
# that expected SIGPIPE from the redactor as a failed host collection.
set +o pipefail
} | sed -E 's/((password|secret|token|authorization)[=:][[:space:]]*)[^[:space:],}]+/\1[REDACTED]/Ig' | head -c 4194304 >"$temporary"
set -o pipefail
chmod 0640 "$temporary"; mv "$temporary" "$output"
finish SUCCEEDED "Application logs collected." "$from" "$until"
