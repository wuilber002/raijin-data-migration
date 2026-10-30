#!/usr/bin/env bash
# Apply a constrained source update requested by an authenticated ADMIN.
#
# This script is installed root-owned and executed by systemd. The web
# container can write only a small request document; it cannot select a Git
# remote, execute shell, access the deploy key, Podman or systemd directly.
set -euo pipefail

install_root=/opt/s3-oci-migration/release
control_root=/var/lib/s3-oci-migration/update-control
request="$control_root/request.json"
result="$control_root/result.json"
config=/etc/s3-oci-migration/update.env
service=s3-oci-migration.service
backup=/usr/local/sbin/s3-oci-backup-postgres

mkdir -p "$control_root"
chmod 0750 "$control_root"

[[ -r "$config" ]] || exit 0
# shellcheck disable=SC1090
source "$config"
update_enabled="${RAIJIN_UPDATE_ENABLED:-false}"
remote="${RAIJIN_UPDATE_REMOTE:-origin}"
ref="${RAIJIN_UPDATE_REF:-refs/remotes/origin/main}"

valid_remote='^[A-Za-z0-9_.-]+$'
[[ "$update_enabled" == true && "$remote" =~ $valid_remote ]] || exit 0

update_impact() {
  local current="$1" available="$2"
  [[ "$current" =~ ^[0-9a-f]{40}$ && "$available" =~ ^[0-9a-f]{40}$ ]] || {
    printf '%s\n' '{}'; return 0;
  }
  python3 - "$install_root" "$current" "$available" <<'PY'
import json
import subprocess
import sys

root, current, available = sys.argv[1:]
try:
    paths = subprocess.check_output(
        ["git", "-C", root, "diff", "--name-only", "--diff-filter=ACDMRTUXB", current, available],
        text=True, stderr=subprocess.DEVNULL,
    ).splitlines()
except Exception:
    paths = []

paths = paths[:100]
web_ui = lambda path: path.startswith(("app/static/", "images/"))
docs = lambda path: path.startswith("docs/") or path in {"README.md", "LICENSE"}
host = lambda path: path.startswith(("scripts/", "docker/", "terraform/")) or path in {"Dockerfile", "docker-compose.yml", "requirements.txt", "requirements-dev.txt"}
worker = lambda path: path in {"app/real_worker.py", "app/cloud_backends.py", "app/aws_restore_semantics.py"}
database = lambda path: path.startswith("app/") and any(token in path for token in ("migration", "schema", "main.py"))

components = []
if any(web_ui(path) for path in paths): components.append("WEB_UI")
if any(worker(path) for path in paths): components.append("WORKERS")
if any(database(path) for path in paths): components.append("DATABASE_OR_API")
if any(host(path) for path in paths): components.append("HOST_RUNTIME")
if not components and paths: components.append("DOCUMENTATION")

if paths and all(web_ui(path) for path in paths):
    classification, transfer_impact = "WEB_UI_ONLY", "NONE"
elif paths and all(docs(path) for path in paths):
    classification, transfer_impact = "DOCUMENTATION_ONLY", "NONE"
else:
    classification, transfer_impact = "FULL_PLATFORM", "CONTROLLED_PAUSE"

print(json.dumps({
    "classification": classification,
    "components": components,
    "transfer_impact": transfer_impact,
    # Phase 1 is intentionally conservative: every accepted source revision
    # follows the existing backup + full-service restart protocol.
    "installation_strategy": "FULL_CONTROLLED_RESTART",
    "changed_files": paths,
}, separators=(",", ":")))
PY
}

write_result() {
  local state="$1" message="$2" current="${3:-}" available="${4:-}" previous="${5:-}"
  local progress="${6:-0}"
  local impact
  impact="$(update_impact "$current" "$available")" || impact='{}'
  python3 - "$state" "$message" "$current" "$available" "$previous" "$progress" "$impact" >"$result.tmp" <<'PY'
import datetime
import json
import sys
try:
    impact = json.loads(sys.argv[7])
except (json.JSONDecodeError, IndexError):
    impact = {}
print(json.dumps({
    "state": sys.argv[1], "message": sys.argv[2],
    "current_revision": sys.argv[3] or None,
    "available_revision": sys.argv[4] or None,
    "previous_revision": sys.argv[5] or None,
    "progress": max(0, min(100, int(sys.argv[6] or 0))),
    "impact": impact,
    "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}, separators=(",", ":")))
PY
  chmod 0640 "$result.tmp"
  mv "$result.tmp" "$result"
}

revision() { git -C "$install_root" rev-parse --verify "$1^{commit}"; }

check_update() {
  local emit_result="${1:-true}" current available
  current="$(revision HEAD)"
  if ! git -C "$install_root" fetch --quiet --tags "$remote"; then
    write_result FAILED "Could not fetch the configured Git remote." "$current"
    return 1
  fi
  if ! available="$(revision "$ref")"; then
    write_result FAILED "Configured update reference is unavailable." "$current"
    return 1
  fi
  if ! git -C "$install_root" merge-base --is-ancestor "$current" "$available"; then
    write_result FAILED "Configured update is not a fast-forward descendant of the installed revision." "$current" "$available"
    return 1
  fi
  if [[ "$current" == "$available" ]]; then
    [[ "$emit_result" == true ]] && write_result CURRENT "The installed revision is current." "$current" "$available" "" 100
  else
    [[ "$emit_result" == true ]] && write_result AVAILABLE "An approved source revision is available." "$current" "$available" "" 100
  fi
  printf '%s\n' "$available"
}

runtime_is_drained() {
  local counts
  counts="$(podman exec s3-oci-postgres psql -U migration -d migration -Atc \
    "select count(*) from tasks where state in ('READY','RUNNING'); select count(*) from discovery_jobs where state in ('READY','RUNNING'); select count(*) from waves where status in ('RESTORE_REQUESTED','RESTORE_REQUEST_ACCEPTED','RESTORING','RESTORE_DRAINING','TRANSFERRING','TRANSFER_DRAINING');" 2>/dev/null || true)"
  local task_count discovery_count wave_count
  task_count="$(sed -n '1p' <<<"$counts")"; discovery_count="$(sed -n '2p' <<<"$counts")"; wave_count="$(sed -n '3p' <<<"$counts")"
  [[ "$task_count" =~ ^[0-9]+$ && "$discovery_count" =~ ^[0-9]+$ && "$wave_count" =~ ^[0-9]+$ && "$task_count" == 0 && "$discovery_count" == 0 && "$wave_count" == 0 ]]
}

apply_update() {
  local requested="$1" current available previous
  current="$(revision HEAD)"
  write_result VALIDATING "Validating the approved revision and drained queue." "$current" "$requested" "" 10
  available="$(check_update false)" || return 1
  # check_update prints only the SHA on stdout; its state is in result.json.
  available="${available##*$'\n'}"
  if [[ ! "$requested" =~ ^[0-9a-f]{40}$ || "$requested" != "$available" ]]; then
    write_result REJECTED "Requested revision is not the currently approved update." "$current" "$available"
    return 0
  fi
  if ! runtime_is_drained; then
    write_result REJECTED "Update requires a fully drained queue and no active restore or transfer." "$current" "$available"
    return 0
  fi
  if [[ -n "$(git -C "$install_root" status --porcelain)" ]]; then
    write_result REJECTED "Installed release contains local source changes; automatic update is unsafe." "$current" "$available"
    return 0
  fi
  write_result BACKING_UP "Creating a PostgreSQL backup before update." "$current" "$available" "" 35
  if ! "$backup"; then
    write_result FAILED "PostgreSQL backup failed; no update was applied." "$current" "$available"
    return 1
  fi
  previous="$current"
  write_result DEPLOYING "Installing the approved source revision." "$current" "$available" "$previous" 65
  # Console sessions are revoked on every service restart by design. Publish a
  # terminal pre-restart state briefly while the old web process can still
  # answer, so the operator sees why the next page is the login screen.
  write_result RESTARTING "The platform will restart now; the current console session will be closed." "$current" "$available" "$previous" 80
  sleep 2
  systemctl stop "$service"
  if ! git -C "$install_root" checkout --detach --quiet "$available"; then
    git -C "$install_root" checkout --detach --quiet "$previous" || true
    systemctl start "$service" || true
    write_result FAILED "Could not checkout the approved revision." "$previous" "$available" "$previous"
    return 1
  fi
  write_result VERIFYING "Restarting the platform and validating the local health check." "$available" "$available" "$previous" 90
  if systemctl start "$service"; then
    write_result SUCCEEDED "Update completed and the new revision passed the local health check." "$available" "$available" "$previous" 100
    return 0
  fi
  git -C "$install_root" checkout --detach --quiet "$previous" || true
  if systemctl start "$service"; then
    write_result ROLLED_BACK "New revision failed startup; the previous release was restored." "$previous" "$available" "$previous" 100
  else
    write_result FAILED "New revision failed and automatic rollback could not restore the service." "$previous" "$available" "$previous"
  fi
  return 1
}

[[ -s "$request" ]] || exit 0
exec 9>"$control_root/lock"
flock -n 9 || exit 0
mv "$request" "$request.processing"
trap 'rm -f "$request.processing"' EXIT

readarray -t values < <(python3 - "$request.processing" <<'PY'
import json
import re
import sys
try:
    data=json.load(open(sys.argv[1], encoding="utf-8"))
    action=str(data.get("action") or "")
    revision=str(data.get("revision") or "")
    if action not in {"check", "apply"}: raise ValueError("invalid action")
    if action == "apply" and not re.fullmatch(r"[0-9a-f]{40}", revision): raise ValueError("invalid revision")
    print(action); print(revision)
except Exception:
    raise SystemExit(2)
PY
)
action="${values[0]:-}"; requested_revision="${values[1]:-}"
if [[ "$action" == check ]]; then
  check_update >/dev/null || true
else
  apply_update "$requested_revision" || true
fi
