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

start_raijin() {
  local image="$1" role worker_role
  podman run -d --name s3-oci-app --replace --restart unless-stopped \
    --network-alias local-app "${common[@]}" "$image"
  podman network connect "$data_network" s3-oci-app
  podman network connect --alias local-app "$ui_network" s3-oci-app
  configure_private_dns s3-oci-app
  for attempt in $(seq 1 60); do
    if podman exec s3-oci-app python3 -c \
      "import json,urllib.request; data=json.load(urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=2)); assert data['status']=='ok'" \
      >/dev/null 2>&1; then
      break
    fi
    [[ "$attempt" -lt 60 ]] || return 1
    sleep 1
  done
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

rollback() {
  local status=$?
  trap - ERR
  echo "Target rollout failed; restoring $rollback_image" >&2
  remove_raijin || true
  start_raijin "$rollback_image"
  exit "$status"
}
trap rollback ERR

remove_raijin
start_raijin "$target_image"
sleep 3
for name in s3-oci-app s3-oci-governance-worker s3-oci-transfer-worker; do
  [[ "$(podman inspect --format '{{.State.Running}}' "$name")" == true ]]
done
curl --fail --silent --show-error http://127.0.0.1:8080/raijin/healthz
trap - ERR
echo
echo "Raijin LOCAL control plane updated to $target_image"
