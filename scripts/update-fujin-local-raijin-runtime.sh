#!/usr/bin/env bash
set -euo pipefail

# Update only Raijin in an existing Fujin LOCAL topology. PostgreSQL, Fujin,
# materializer, DNS and the UI gateway remain online throughout the rollout.

target_image="${1:-}"
rollback_image="${2:-}"
data_root="${RAIJIN_DATA_ROOT:-/var/lib/s3-oci-migration}"
secret_root="${RAIJIN_SECRET_ROOT:-/etc/s3-oci-migration/secrets}"
runtime_root="${RAIJIN_RUNTIME_ROOT:-/run/s3-oci-migration}"
main_network="${RAIJIN_MAIN_NETWORK:-s3-oci-migration}"
data_network="${FUJIN_LOCAL_DATA_NETWORK:-s3-oci-fujin-local-data}"
ui_network="${FUJIN_LOCAL_UI_NETWORK:-s3-oci-fujin-local-ui}"
local_oci_runtime="${RAIJIN_LOCAL_OCI_RUNTIME_CONFIG:-/etc/s3-oci-migration/oci-runtime-local.json}"
stop_timeout="${RAIJIN_UPDATE_STOP_TIMEOUT_SECONDS:-180}"
candidate_name="s3-oci-app-candidate"
handoff_started=0
release_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

[[ -n "$target_image" && -n "$rollback_image" ]] || {
  echo "Usage: $0 TARGET_IMAGE ROLLBACK_IMAGE" >&2
  exit 2
}
[[ "$stop_timeout" =~ ^[0-9]+$ ]] && ((stop_timeout >= 30)) || {
  echo "RAIJIN_UPDATE_STOP_TIMEOUT_SECONDS must be an integer of at least 30" >&2
  exit 2
}
for image in "$target_image" "$rollback_image"; do
  podman image exists "$image" || { echo "Image not found: $image" >&2; exit 2; }
done
for name in s3-oci-postgres s3-oci-fujin-local s3-oci-fujin-local-materializer s3-oci-fujin-local-dns s3-oci-local-ui-gateway; do
  [[ "$(podman inspect --format '{{.State.Running}}' "$name" 2>/dev/null || true)" == true ]] || {
    echo "Required LOCAL container is not running: $name" >&2
    exit 2
  }
done
[[ -s "$local_oci_runtime" ]] || { echo "Missing $local_oci_runtime" >&2; exit 2; }
mountpoint -q "$data_root/fujin-payloads" || {
  echo "Fujin payload volume is not mounted" >&2
  exit 2
}

# Restore polling in READY is recoverable. An admitted transfer or leased
# queue item must first reach a durable boundary.
running_dispatchers="$(podman exec s3-oci-postgres psql -U migration -d migration -Atc \
  "SELECT count(*) FROM tasks WHERE kind='TRANSFER_CONTINUOUS' AND state='RUNNING'")"
leased_items="$(podman exec s3-oci-postgres psql -U migration -d migration -Atc \
  "SELECT count(*) FROM transfer_queue_items WHERE state='LEASED'")"
if ((running_dispatchers + leased_items > 0)); then
  echo "Refusing update: $((running_dispatchers + leased_items)) active transfer/lease record(s) remain" >&2
  exit 3
fi

common=(
  --network "$main_network" --dns 172.30.0.53
  -e RAIJIN_OPERATION_MODE=REAL
  -e DATABASE_URL=postgresql+psycopg://migration@postgres:5432/migration
  -e POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password
  -e OCI_RUNTIME_CONFIG_FILE=/run/oci-runtime/oci-runtime.json
  -v "$secret_root/postgres_password:/run/secrets/postgres_password:ro,z"
  -v "$runtime_root:/run/platform-status:ro,z"
  -v "$local_oci_runtime:/run/oci-runtime/oci-runtime.json:ro,z"
  -v "$data_root/fujin-local/ca:/etc/fujin-local-ca:ro,z"
)

configure_private_dns() {
  local container="$1" resolver_ip resolv_conf
  resolver_ip="$(podman inspect --format "{{(index .NetworkSettings.Networks \"$main_network\").IPAddress}}" s3-oci-fujin-local-dns)"
  resolv_conf="$(podman inspect --format '{{.ResolvConfPath}}' "$container")"
  [[ -n "$resolver_ip" && -n "$resolv_conf" && -e "$resolv_conf" ]] || return 1
  printf 'nameserver %s\noptions ndots:1\n' "$resolver_ip" >"$resolv_conf"
}

remove_raijin() {
  podman stop -t "$stop_timeout" --ignore \
    s3-oci-transfer-worker s3-oci-governance-worker s3-oci-app
  podman rm -f --ignore \
    s3-oci-transfer-worker s3-oci-governance-worker s3-oci-app
}

start_app() {
  local name="$1" image="$2" expected_revision="${2##*:}"
  podman run -d --name "$name" --restart unless-stopped \
    --network-alias local-app --network-alias local-app-candidate "${common[@]}" "$image"
  podman network connect "$data_network" "$name"
  podman network connect --alias local-app --alias local-app-candidate "$ui_network" "$name"
  configure_private_dns "$name"
  for attempt in $(seq 1 60); do
    if podman exec "$name" python3 -c \
      "import json,urllib.request; health=json.load(urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=2)); identity=json.load(urllib.request.urlopen('http://127.0.0.1:8080/api/runtime',timeout=2)); assert health['status']=='ok'; assert '$expected_revision' in ('latest', identity['raijin_build_revision'])" \
      >/dev/null 2>&1; then
      break
    fi
    [[ "$attempt" -lt 60 ]] || return 1
    sleep 1
  done
}

start_workers() {
  local image="$1" role worker_role
  for role in governance transfer; do
    worker_role=raikou
    [[ "$role" == transfer ]] && worker_role=raiju
    podman run -d --name "s3-oci-${role}-worker" --replace --restart unless-stopped \
      "${common[@]}" -e RAIJIN_WORKER_ID="${worker_role}-local" \
      -e RAIJIN_WORKER_ROLE="$worker_role" "$image" python3 -m app.real_worker
    podman network connect "$data_network" "s3-oci-${role}-worker"
    configure_private_dns "s3-oci-${role}-worker"
  done
}

start_raijin() {
  local image="$1"
  start_app s3-oci-app "$image"
  start_workers "$image"
}

validate_release_images() {
  local image="$1" name actual
  for name in s3-oci-app s3-oci-governance-worker s3-oci-transfer-worker; do
    actual="$(podman inspect --format '{{.ImageName}}' "$name")"
    [[ "$actual" == "$image" ]] || {
      echo "Release mismatch: $name uses $actual, expected $image" >&2
      return 1
    }
  done
  actual="$(podman inspect --format '{{.ImageName}}' s3-oci-fujin-local)"
  if [[ "$actual" != "$image" ]]; then
    echo "Alignment notice: Fujin remains on $actual while Raijin targets $image; Fujin was intentionally not replaced."
  fi
}

install_platform_status_runtime() {
  local next_monotonic
  # Host telemetry is part of the release contract even though it runs
  # outside the containers. Reinstall and restart it on every rollout so an
  # already-active timer cannot retain an elapsed schedule from an older unit.
  install -m 0750 "$release_root/scripts/write-platform-status.sh" \
    /usr/local/sbin/s3-oci-write-platform-status
  cat >/etc/systemd/system/s3-oci-platform-status.service <<'EOF'
[Unit]
Description=Write S3 to OCI migration platform status
After=s3-oci-migration.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/s3-oci-write-platform-status
EOF
  cat >/etc/systemd/system/s3-oci-platform-status.timer <<'EOF'
[Unit]
Description=Refresh S3 to OCI migration platform status

[Timer]
OnActiveSec=30
OnUnitActiveSec=60
AccuracySec=5
Persistent=true

[Install]
WantedBy=timers.target
EOF
  systemctl daemon-reload
  systemctl enable s3-oci-platform-status.timer
  systemctl restart s3-oci-platform-status.timer
  systemctl start s3-oci-platform-status.service
  next_monotonic="$(systemctl show s3-oci-platform-status.timer -p NextElapseUSecMonotonic --value)"
  [[ -n "$next_monotonic" && "$next_monotonic" != 0 ]]
}

rollback() {
  local status=$?
  trap - ERR
  echo "Target rollout failed; restoring $rollback_image" >&2
  podman rm -f --ignore "$candidate_name" || true
  if ((handoff_started)); then
    remove_raijin || true
    start_raijin "$rollback_image"
    validate_release_images "$rollback_image"
  else
    echo "Candidate failed before handoff; the existing Raijin runtime remains online." >&2
  fi
  exit "$status"
}
trap rollback ERR

# Blue/green handoff: validate the candidate while the existing API remains
# reachable through the shared private alias. Only then stop the old control
# plane. The active-transfer guard above makes the worker boundary safe.
podman rm -f --ignore "$candidate_name"
start_app "$candidate_name" "$target_image"
handoff_started=1
podman stop -t "$stop_timeout" --ignore s3-oci-transfer-worker s3-oci-governance-worker
podman rm -f --ignore s3-oci-transfer-worker s3-oci-governance-worker
podman stop -t "$stop_timeout" --ignore s3-oci-app
podman rm -f --ignore s3-oci-app
podman rename "$candidate_name" s3-oci-app
# Force the local gateway to discard any cached address of the retired app.
podman exec s3-oci-local-ui-gateway nginx -s reload
start_workers "$target_image"
sleep 3
for name in s3-oci-app s3-oci-governance-worker s3-oci-transfer-worker; do
  [[ "$(podman inspect --format '{{.State.Running}}' "$name")" == true ]]
done
curl --fail --silent --show-error http://127.0.0.1:8080/raijin/healthz
validate_release_images "$target_image"
install_platform_status_runtime
# The freshly generated host snapshot must be accepted by the target API.
podman exec s3-oci-app python3 -c \
  "import json,urllib.request; status=json.load(urllib.request.urlopen('http://127.0.0.1:8080/api/platform/status',timeout=2)); assert status['available'] and not status.get('stale')"
trap - ERR
echo
echo "Raijin LOCAL control plane updated to $target_image"
