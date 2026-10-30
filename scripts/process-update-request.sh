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
selective_web_only="${RAIJIN_UPDATE_SELECTIVE_WEB_ONLY:-false}"
selective_controller="${RAIJIN_UPDATE_SELECTIVE_CONTROLLER:-false}"
selective_restore="${RAIJIN_UPDATE_SELECTIVE_RESTORE:-false}"
selective_discovery="${RAIJIN_UPDATE_SELECTIVE_DISCOVERY:-false}"
selective_audit="${RAIJIN_UPDATE_SELECTIVE_AUDIT:-false}"
selective_transfer="${RAIJIN_UPDATE_SELECTIVE_TRANSFER:-false}"

valid_remote='^[A-Za-z0-9_.-]+$'
[[ "$update_enabled" == true && "$remote" =~ $valid_remote ]] || exit 0

update_impact() {
  local current="$1" available="$2"
  [[ "$current" =~ ^[0-9a-f]{40}$ && "$available" =~ ^[0-9a-f]{40}$ ]] || {
    printf '%s\n' '{}'; return 0;
  }
  python3 - "$install_root" "$current" "$available" "$selective_web_only" "$selective_controller" "$selective_restore" "$selective_discovery" "$selective_audit" "$selective_transfer" <<'PY'
import json
import subprocess
import sys

root, current, available, selective_web_only, selective_controller, selective_restore, selective_discovery, selective_audit, selective_transfer = sys.argv[1:]
try:
    all_paths = subprocess.check_output(
        ["git", "-C", root, "diff", "--name-only", "--diff-filter=ACDMRTUXB", current, available],
        text=True, stderr=subprocess.DEVNULL,
    ).splitlines()
except Exception:
    all_paths = []

# Classification is a security decision, so it always examines the complete
# diff. Only the administrative evidence sent to the web console is capped.
paths = all_paths[:100]
web_ui = lambda path: path.startswith(("app/static/", "images/"))
controller = lambda path: path == "app/controller_worker.py"
restore = lambda path: path == "app/restore_execution.py"
discovery = lambda path: path == "app/discovery_execution.py"
audit = lambda path: path == "app/audit_execution.py"
transfer = lambda path: path == "app/transfer_execution.py"
validation = lambda path: path.startswith("tests/")
docs = lambda path: path.startswith("docs/") or path in {"README.md", "LICENSE"}
host = lambda path: path.startswith(("scripts/", "docker/", "terraform/")) or path in {"Dockerfile", "docker-compose.yml", "requirements.txt", "requirements-dev.txt"}
worker = lambda path: path in {"app/real_worker.py", "app/cloud_backends.py", "app/aws_restore_semantics.py"}
database = lambda path: path.startswith("app/") and any(token in path for token in ("migration", "schema", "main.py"))

# Test files provide release evidence but are not copied into the runtime
# image. They must not turn an otherwise static-only rollout into a platform
# restart. Every other path remains part of the runtime classification.
runtime_paths = [path for path in all_paths if not validation(path)]
components = []
if any(web_ui(path) for path in runtime_paths): components.append("WEB_UI")
if any(controller(path) for path in runtime_paths): components.append("CONTROLLER")
if any(restore(path) for path in runtime_paths): components.append("RESTORE_WORKER")
if any(discovery(path) for path in runtime_paths): components.append("DISCOVERY_WORKER")
if any(audit(path) for path in runtime_paths): components.append("AUDIT_WORKER")
if any(transfer(path) for path in runtime_paths): components.append("TRANSFER_WORKER")
if any(worker(path) for path in runtime_paths): components.append("WORKERS")
if any(database(path) for path in runtime_paths): components.append("DATABASE_OR_API")
if any(host(path) for path in runtime_paths): components.append("HOST_RUNTIME")
if not components and runtime_paths: components.append("DOCUMENTATION")

manifest = {}
try:
    manifest = json.loads(subprocess.check_output(
        ["git", "-C", root, "show", f"{available}:release-manifest.json"],
        text=True, stderr=subprocess.DEVNULL,
    ))
except Exception:
    manifest = {}

web_rollout = manifest.get("selective_rollout", {}).get("web_ui", {}) if isinstance(manifest, dict) else {}
controller_rollout = manifest.get("selective_rollout", {}).get("controller", {}) if isinstance(manifest, dict) else {}
restore_rollout = manifest.get("selective_rollout", {}).get("restore_worker", {}) if isinstance(manifest, dict) else {}
discovery_rollout = manifest.get("selective_rollout", {}).get("discovery_worker", {}) if isinstance(manifest, dict) else {}
audit_rollout = manifest.get("selective_rollout", {}).get("audit_worker", {}) if isinstance(manifest, dict) else {}
transfer_rollout = manifest.get("selective_rollout", {}).get("transfer_worker", {}) if isinstance(manifest, dict) else {}
manifest_authorizes_web = (
    isinstance(manifest, dict)
    and manifest.get("manifest_version") == 1
    and isinstance(web_rollout, dict)
    and web_rollout.get("enabled") is True
    and web_rollout.get("contract_version") == 1
    and web_rollout.get("allowed_path_prefixes") == ["app/static/", "images/"]
    and web_rollout.get("validation_path_prefixes") == ["tests/"]
)
manifest_authorizes_controller = (
    isinstance(manifest, dict)
    and manifest.get("manifest_version") == 1
    and isinstance(controller_rollout, dict)
    and controller_rollout.get("enabled") is True
    and controller_rollout.get("contract_version") == 1
    and controller_rollout.get("allowed_paths") == ["app/controller_worker.py"]
    and controller_rollout.get("validation_path_prefixes") == ["tests/"]
)
def authorized_worker_rollout(value, path):
    return (
        isinstance(manifest, dict)
        and manifest.get("manifest_version") == 1
        and isinstance(value, dict)
        and value.get("enabled") is True
        and value.get("contract_version") == 1
        and value.get("allowed_paths") == [path]
        and value.get("validation_path_prefixes") == ["tests/"]
    )
manifest_authorizes_restore = authorized_worker_rollout(restore_rollout, "app/restore_execution.py")
manifest_authorizes_discovery = authorized_worker_rollout(discovery_rollout, "app/discovery_execution.py")
manifest_authorizes_audit = authorized_worker_rollout(audit_rollout, "app/audit_execution.py")
manifest_authorizes_transfer = authorized_worker_rollout(transfer_rollout, "app/transfer_execution.py")
web_only_candidate = (
    bool(runtime_paths)
    and all(web_ui(path) for path in runtime_paths)
    and all(web_ui(path) or validation(path) for path in all_paths)
)
web_rollout_enabled = selective_web_only.lower() == "true"
controller_only_candidate = (
    bool(runtime_paths)
    and all(controller(path) for path in runtime_paths)
    and all(controller(path) or validation(path) for path in all_paths)
)
controller_rollout_enabled = selective_controller.lower() == "true"
def isolated_candidate(predicate):
    return bool(runtime_paths) and all(predicate(path) for path in runtime_paths) and all(predicate(path) or validation(path) for path in all_paths)
restore_only_candidate = isolated_candidate(lambda path: path == "app/restore_execution.py")
discovery_only_candidate = isolated_candidate(lambda path: path == "app/discovery_execution.py")
audit_only_candidate = isolated_candidate(lambda path: path == "app/audit_execution.py")
transfer_only_candidate = isolated_candidate(lambda path: path == "app/transfer_execution.py")
restore_rollout_enabled = selective_restore.lower() == "true"
discovery_rollout_enabled = selective_discovery.lower() == "true"
audit_rollout_enabled = selective_audit.lower() == "true"
transfer_rollout_enabled = selective_transfer.lower() == "true"

if web_only_candidate:
    classification, transfer_impact = "WEB_UI_ONLY", "NONE"
elif controller_only_candidate:
    classification, transfer_impact = "CONTROLLER_ONLY", "NONE"
elif restore_only_candidate:
    classification, transfer_impact = "RESTORE_WORKER_ONLY", "NONE"
elif discovery_only_candidate:
    classification, transfer_impact = "DISCOVERY_WORKER_ONLY", "NONE"
elif audit_only_candidate:
    classification, transfer_impact = "AUDIT_WORKER_ONLY", "NONE"
elif transfer_only_candidate:
    classification, transfer_impact = "TRANSFER_WORKER_ONLY", "CHECKPOINTED_RESTART"
elif all_paths and all(docs(path) or validation(path) for path in all_paths):
    classification, transfer_impact = "DOCUMENTATION_ONLY", "NONE"
else:
    classification, transfer_impact = "FULL_PLATFORM", "CONTROLLED_PAUSE"

print(json.dumps({
    "classification": classification,
    "components": components,
    "transfer_impact": transfer_impact,
    "installation_strategy": "WEB_ONLY_ROLLING" if web_only_candidate and manifest_authorizes_web and web_rollout_enabled else "CONTROLLER_ONLY_ROLLING" if controller_only_candidate and manifest_authorizes_controller and controller_rollout_enabled else "RESTORE_WORKER_ROLLING" if restore_only_candidate and manifest_authorizes_restore and restore_rollout_enabled else "DISCOVERY_WORKER_ROLLING" if discovery_only_candidate and manifest_authorizes_discovery and discovery_rollout_enabled else "AUDIT_WORKER_ROLLING" if audit_only_candidate and manifest_authorizes_audit and audit_rollout_enabled else "TRANSFER_WORKER_ROLLING" if transfer_only_candidate and manifest_authorizes_transfer and transfer_rollout_enabled else "FULL_CONTROLLED_RESTART",
    "rollout_eligible": bool((web_only_candidate and manifest_authorizes_web and web_rollout_enabled) or (controller_only_candidate and manifest_authorizes_controller and controller_rollout_enabled) or (restore_only_candidate and manifest_authorizes_restore and restore_rollout_enabled) or (discovery_only_candidate and manifest_authorizes_discovery and discovery_rollout_enabled) or (audit_only_candidate and manifest_authorizes_audit and audit_rollout_enabled) or (transfer_only_candidate and manifest_authorizes_transfer and transfer_rollout_enabled)),
    "rollout_eligibility_reason": (
        "manifest_authorized" if web_only_candidate and manifest_authorizes_web and web_rollout_enabled
        else "manifest_authorized" if controller_only_candidate and manifest_authorizes_controller and controller_rollout_enabled
        else "host_policy_disabled" if web_only_candidate and manifest_authorizes_web
        else "host_policy_disabled" if controller_only_candidate and manifest_authorizes_controller
        else "manifest_not_authorized" if web_only_candidate
        else "manifest_not_authorized" if controller_only_candidate
        else "manifest_authorized" if restore_only_candidate and manifest_authorizes_restore and restore_rollout_enabled
        else "manifest_authorized" if discovery_only_candidate and manifest_authorizes_discovery and discovery_rollout_enabled
        else "manifest_authorized" if audit_only_candidate and manifest_authorizes_audit and audit_rollout_enabled
        else "manifest_authorized" if transfer_only_candidate and manifest_authorizes_transfer and transfer_rollout_enabled
        else "host_policy_disabled" if restore_only_candidate and manifest_authorizes_restore
        else "host_policy_disabled" if discovery_only_candidate and manifest_authorizes_discovery
        else "host_policy_disabled" if audit_only_candidate and manifest_authorizes_audit
        else "host_policy_disabled" if transfer_only_candidate and manifest_authorizes_transfer
        else "manifest_not_authorized" if restore_only_candidate or discovery_only_candidate or audit_only_candidate or transfer_only_candidate
        else "not_web_ui_only"
    ),
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

update_strategy() {
  local current="$1" available="$2"
  update_impact "$current" "$available" | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get("installation_strategy", "FULL_CONTROLLED_RESTART"))
except Exception:
    print("FULL_CONTROLLED_RESTART")
'
}

release_image_for_revision() {
  local revision="$1"
  printf 'localhost/s3-oci-migration:%s\n' "$revision"
}

build_release_image() {
  local revision="$1" version image
  version="$(tr -d '[:space:]' <"$install_root/VERSION")"
  [[ -n "$version" ]] || return 1
  image="$(release_image_for_revision "$revision")"
  podman build --no-cache \
    --build-arg "RAIJIN_SERVICE_VERSION=$version" \
    --build-arg "RAIJIN_BUILD_REVISION=$revision" \
    -t "$image" "$install_root"
}

required_database_revision() {
  local revision="$1"
  git -C "$install_root" show "$revision:release-manifest.json" 2>/dev/null | python3 -c '
import json, sys
try:
    value = json.load(sys.stdin).get("database_migration", {})
    required = value.get("required_revision")
    mode = value.get("mode")
    if isinstance(required, int) and required >= 1 and mode == "EXPAND_ONLY":
        print(required)
except Exception:
    pass
'
}

apply_database_migration() {
  local revision="$1" required current
  required="$(required_database_revision "$revision")"
  [[ "$required" =~ ^[0-9]+$ ]] || {
    write_result FAILED "Approved release has no valid expand-only database migration declaration." "$(revision HEAD)" "$revision"
    return 1
  }
  current="$(podman exec s3-oci-postgres psql -U migration -d migration -Atc 'SELECT coalesce(max(version), 0) FROM raijin_schema_revisions' 2>/dev/null || true)"
  if [[ "$current" =~ ^[0-9]+$ && "$current" -gt "$required" ]]; then
    write_result FAILED "Database schema is newer than the approved release requires." "$(revision HEAD)" "$revision"
    return 1
  fi
  write_result DEPLOYING "Applying approved expand-only database migrations." "$(revision HEAD)" "$revision" "" 60
  podman run --rm --network s3-oci-migration \
    -e RAIJIN_OPERATION_MODE=REAL \
    -e DATABASE_URL=postgresql+psycopg://migration@postgres:5432/migration \
    -e POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password \
    -v /etc/s3-oci-migration/secrets/postgres_password:/run/secrets/postgres_password:ro,z \
    "$(release_image_for_revision "$revision")" env PYTHONPATH=/app python3 scripts/migrate-production.py
}

apply_web_only_update() {
  local current="$1" available="$2" previous_image candidate_image
  previous_image="$(podman inspect --format '{{.ImageName}}' s3-oci-app 2>/dev/null || true)"
  [[ -n "$previous_image" ]] || {
    write_result FAILED "Could not identify the running web container image." "$current" "$available" "$current"
    return 1
  }
  write_result DEPLOYING "Building and installing the approved web-only revision." "$current" "$available" "$current" 55
  if ! git -C "$install_root" checkout --detach --quiet "$available"; then
    write_result FAILED "Could not checkout the approved web-only revision." "$current" "$available" "$current"
    return 1
  fi
  if ! build_release_image "$available"; then
    git -C "$install_root" checkout --detach --quiet "$current" || true
    write_result FAILED "Could not build the approved web-only revision." "$current" "$available" "$current"
    return 1
  fi
  candidate_image="$(release_image_for_revision "$available")"
  write_result VERIFYING "Replacing only the web console and validating its local health check." "$available" "$available" "$current" 85
  if RAIJIN_IMAGE="$candidate_image" RAIJIN_RUNTIME_COMPONENT=web "$install_root/scripts/start-runtime.sh" REAL; then
    write_result SUCCEEDED "Web-only update completed; migration workers remained running." "$available" "$available" "$current" 100
    return 0
  fi
  git -C "$install_root" checkout --detach --quiet "$current" || true
  RAIJIN_IMAGE="$previous_image" RAIJIN_RUNTIME_COMPONENT=web "$install_root/scripts/start-runtime.sh" REAL || true
  write_result ROLLED_BACK "Web-only update failed health validation; the previous web revision was restored." "$current" "$available" "$current" 100
  return 1
}

apply_controller_only_update() {
  local current="$1" available="$2" previous_image candidate_image
  previous_image="$(podman inspect --format '{{.ImageName}}' s3-oci-raikou-shin 2>/dev/null || true)"
  [[ -n "$previous_image" ]] || {
    write_result FAILED "Could not identify the running controller image." "$current" "$available" "$current"
    return 1
  }
  write_result DEPLOYING "Draining the controller transaction and building the approved controller revision." "$current" "$available" "$current" 55
  if ! git -C "$install_root" checkout --detach --quiet "$available"; then
    write_result FAILED "Could not checkout the approved controller revision." "$current" "$available" "$current"
    return 1
  fi
  if ! build_release_image "$available"; then
    git -C "$install_root" checkout --detach --quiet "$current" || true
    write_result FAILED "Could not build the approved controller revision." "$current" "$available" "$current"
    return 1
  fi
  candidate_image="$(release_image_for_revision "$available")"
  write_result VERIFYING "Replacing only the controller and validating its heartbeat." "$available" "$available" "$current" 85
  if RAIJIN_IMAGE="$candidate_image" RAIJIN_RUNTIME_COMPONENT=controller "$install_root/scripts/start-runtime.sh" REAL; then
    write_result SUCCEEDED "Controller-only update completed; restore and transfer workers remained running." "$available" "$available" "$current" 100
    return 0
  fi
  git -C "$install_root" checkout --detach --quiet "$current" || true
  RAIJIN_IMAGE="$previous_image" RAIJIN_RUNTIME_COMPONENT=controller "$install_root/scripts/start-runtime.sh" REAL || true
  write_result ROLLED_BACK "Controller-only update failed heartbeat validation; the previous controller was restored." "$current" "$available" "$current" 100
  return 1
}

apply_isolated_worker_update() {
  local current="$1" available="$2" component="$3" container="$4" label="$5" previous_image candidate_image
  previous_image="$(podman inspect --format '{{.ImageName}}' "$container" 2>/dev/null || true)"
  [[ -n "$previous_image" ]] || {
    write_result FAILED "Could not identify the running ${label} container image." "$current" "$available" "$current"
    return 1
  }
  write_result DEPLOYING "Building the approved isolated ${label} revision." "$current" "$available" "$current" 55
  if ! git -C "$install_root" checkout --detach --quiet "$available"; then
    write_result FAILED "Could not checkout the approved ${label} revision." "$current" "$available" "$current"
    return 1
  fi
  if ! build_release_image "$available"; then
    git -C "$install_root" checkout --detach --quiet "$current" || true
    write_result FAILED "Could not build the approved ${label} revision." "$current" "$available" "$current"
    return 1
  fi
  candidate_image="$(release_image_for_revision "$available")"
  write_result VERIFYING "Replacing only the ${label} worker and validating its heartbeat." "$available" "$available" "$current" 85
  if RAIJIN_IMAGE="$candidate_image" RAIJIN_RUNTIME_COMPONENT="$component" "$install_root/scripts/start-runtime.sh" REAL; then
    write_result SUCCEEDED "${label} worker-only update completed; other workers remained running." "$available" "$available" "$current" 100
    return 0
  fi
  git -C "$install_root" checkout --detach --quiet "$current" || true
  RAIJIN_IMAGE="$previous_image" RAIJIN_RUNTIME_COMPONENT="$component" "$install_root/scripts/start-runtime.sh" REAL || true
  write_result ROLLED_BACK "${label} worker-only update failed heartbeat validation; the previous revision was restored." "$current" "$available" "$current" 100
  return 1
}

apply_update() {
  local requested="$1" current available previous strategy
  current="$(revision HEAD)"
  write_result VALIDATING "Validating the approved revision and drained queue." "$current" "$requested" "" 10
  available="$(check_update false)" || return 1
  # check_update prints only the SHA on stdout; its state is in result.json.
  available="${available##*$'\n'}"
  if [[ ! "$requested" =~ ^[0-9a-f]{40}$ || "$requested" != "$available" ]]; then
    write_result REJECTED "Requested revision is not the currently approved update." "$current" "$available"
    return 0
  fi
  strategy="$(update_strategy "$current" "$available")"
  if [[ "$strategy" != WEB_ONLY_ROLLING && "$strategy" != CONTROLLER_ONLY_ROLLING && "$strategy" != RESTORE_WORKER_ROLLING && "$strategy" != DISCOVERY_WORKER_ROLLING && "$strategy" != AUDIT_WORKER_ROLLING && "$strategy" != TRANSFER_WORKER_ROLLING ]] && ! runtime_is_drained; then
    write_result REJECTED "Update requires a fully drained queue and no active restore or transfer." "$current" "$available"
    return 0
  fi
  if [[ -n "$(git -C "$install_root" status --porcelain)" ]]; then
    write_result REJECTED "Installed release contains local source changes; automatic update is unsafe." "$current" "$available"
    return 0
  fi
  if [[ "$strategy" == WEB_ONLY_ROLLING ]]; then
    apply_web_only_update "$current" "$available"
    return $?
  fi
  if [[ "$strategy" == CONTROLLER_ONLY_ROLLING ]]; then
    apply_controller_only_update "$current" "$available"
    return $?
  fi
  case "$strategy" in
    RESTORE_WORKER_ROLLING)
      apply_isolated_worker_update "$current" "$available" restore s3-oci-raikou-sei "restore"
      return $?
      ;;
    DISCOVERY_WORKER_ROLLING)
      apply_isolated_worker_update "$current" "$available" discovery s3-oci-raikou-ko "discovery"
      return $?
      ;;
    AUDIT_WORKER_ROLLING)
      apply_isolated_worker_update "$current" "$available" audit s3-oci-raikou-kai "audit"
      return $?
      ;;
    TRANSFER_WORKER_ROLLING)
      apply_isolated_worker_update "$current" "$available" transfer s3-oci-transfer-worker "transfer"
      return $?
      ;;
  esac
  write_result BACKING_UP "Creating a PostgreSQL backup before update." "$current" "$available" "" 35
  if ! "$backup"; then
    write_result FAILED "PostgreSQL backup failed; no update was applied." "$current" "$available"
    return 1
  fi
  previous="$current"
  write_result DEPLOYING "Building the approved source revision before the controlled restart." "$current" "$available" "$previous" 55
  if ! git -C "$install_root" checkout --detach --quiet "$available"; then
    write_result FAILED "Could not checkout the approved revision." "$current" "$available" "$previous"
    return 1
  fi
  if ! build_release_image "$available"; then
    git -C "$install_root" checkout --detach --quiet "$previous" || true
    write_result FAILED "Could not build the approved revision." "$current" "$available" "$previous"
    return 1
  fi
  if ! apply_database_migration "$available"; then
    git -C "$install_root" checkout --detach --quiet "$previous" || true
    return 1
  fi
  # Console sessions are revoked on every service restart by design. Publish a
  # terminal pre-restart state briefly while the old web process can still
  # answer, so the operator sees why the next page is the login screen.
  write_result RESTARTING "The platform will restart now; the current console session will be closed." "$current" "$available" "$previous" 80
  sleep 2
  systemctl stop "$service"
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
