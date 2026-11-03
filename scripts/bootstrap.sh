#!/usr/bin/env bash
set -euo pipefail

install_root=/opt/raijin-data-migration/release
data_root=/var/lib/raijin-data-migration
secret_root=/etc/raijin-data-migration/secrets
runtime_root=/run/raijin-data-migration
application_log_control_root=/var/lib/raijin-data-migration/application-log-control
oci_runtime_config=/etc/raijin-data-migration/oci-runtime.json
web_bind_config=/etc/raijin-data-migration/web-bind.env
web_auth_config=/etc/raijin-data-migration/web-auth.env
update_config=/etc/raijin-data-migration/update.env
temporary_local_secrets_marker=/etc/raijin-data-migration/temporary-local-secrets
bootstrap_complete=false

service_version="${RAIJIN_SERVICE_VERSION:-$(tr -d '[:space:]' <"$install_root/VERSION")}"
build_revision="${RAIJIN_BUILD_REVISION:-}"
if [[ -z "$build_revision" ]]; then
  build_revision="$(git -C "$install_root" rev-parse --short HEAD 2>/dev/null || basename "$(readlink -f "$install_root")")"
fi
[[ -n "$service_version" && -n "$build_revision" ]] || {
  echo "Release version and revision must not be empty" >&2
  exit 1
}
release_image="localhost/raijin-data-migration:$build_revision"

cleanup_failed_bootstrap() {
  local exit_status=$?
  trap - EXIT
  if (( exit_status == 0 )) || [[ "$bootstrap_complete" == true ]]; then
    exit "$exit_status"
  fi

  echo "RAIJIN bootstrap failed; stopping partially started containers" >&2
  if command -v podman >/dev/null 2>&1; then
    local containers=(
      raijin-governance-worker
      raijin-raikou-shin
      raijin-raikou-sei
      raijin-raikou-ko
      raijin-raikou-kai
      raijin-transfer-worker
      raijin-app
      raijin-postgres
    )
    # Explicit stop overrides each container's restart policy and releases the
    # systemd service cgroup. Persistent PostgreSQL data remains on the host
    # volume and the next start can retry safely.
    podman stop -t 10 --ignore "${containers[@]}" >/dev/null 2>&1 || true
    podman rm -f --ignore "${containers[@]}" >/dev/null 2>&1 || true
  fi
  exit "$exit_status"
}

trap cleanup_failed_bootstrap EXIT

if [[ ! -e "$web_bind_config" ]]; then
  install -d -m 0755 "$(dirname "$web_bind_config")"
  cat >"$web_bind_config" <<'EOF'
# Raijin web console host publication. The container continues to listen on
# port 8080 internally; only this host endpoint is configurable.
WEB_BIND_HOST=127.0.0.1
WEB_BIND_PORT=1604
WEB_TRANSPORT=http
WEB_TRUSTED_UPSTREAM_IPS=
EOF
  chmod 0600 "$web_bind_config"
fi
if [[ ! -e "$web_auth_config" ]]; then
  install -d -m 0755 "$(dirname "$web_auth_config")"
  cat >"$web_auth_config" <<'EOF'
# Web-console authentication remains opt-in during the compatibility release.
# Do not use local mode with a public bind before configuring HTTPS and the
# exact CIDR(s) of the trusted reverse proxy.
RAIJIN_WEB_AUTH_MODE=disabled
RAIJIN_WEB_EXTERNAL_HTTPS=false
RAIJIN_WEB_AUTH_TRUSTED_PROXY_CIDRS=
RAIJIN_WEB_AUTH_SESSION_IDLE_MINUTES=30
RAIJIN_WEB_AUTH_SESSION_ABSOLUTE_MINUTES=720
RAIJIN_WEB_AUTH_BOOTSTRAP_USERNAME=admin
EOF
  chmod 0600 "$web_auth_config"
fi
if [[ ! -e "$update_config" ]]; then
  cat >"$update_config" <<'EOF'
# Root-owned source update policy. The web console cannot edit this file,
# select a repository, or supply a Git ref. `origin/main` is intentionally
# fixed here until signed release tags become the configured channel.
RAIJIN_UPDATE_ENABLED=true
RAIJIN_UPDATE_REMOTE=origin
RAIJIN_UPDATE_REF=refs/remotes/origin/main
# Selective rollout is a root-owned opt-in. It only applies to a candidate
# whose immutable Git manifest authorizes WEB_UI_ONLY and whose changed paths
# are exclusively static assets. All other updates retain the full protocol.
RAIJIN_UPDATE_SELECTIVE_WEB_ONLY=true
RAIJIN_UPDATE_SELECTIVE_CONTROLLER=true
RAIJIN_UPDATE_SELECTIVE_RESTORE=true
RAIJIN_UPDATE_SELECTIVE_DISCOVERY=true
RAIJIN_UPDATE_SELECTIVE_AUDIT=true
RAIJIN_UPDATE_SELECTIVE_TRANSFER=true
EOF
  chmod 0600 "$update_config"
fi
# Existing deployments retain their administrator-owned update policy. Add the
# new conservative default once, rather than replacing that file.
if ! grep -q '^RAIJIN_UPDATE_SELECTIVE_WEB_ONLY=' "$update_config"; then
  printf '\n# Permit only manifest-authorized static UI rollouts; every other update remains full.\nRAIJIN_UPDATE_SELECTIVE_WEB_ONLY=true\n' >>"$update_config"
fi
if ! grep -q '^RAIJIN_UPDATE_SELECTIVE_CONTROLLER=' "$update_config"; then
  printf '\n# Permit only manifest-authorized controller entrypoint rollouts.\nRAIJIN_UPDATE_SELECTIVE_CONTROLLER=true\n' >>"$update_config"
fi
if ! grep -q '^RAIJIN_UPDATE_SELECTIVE_RESTORE=' "$update_config"; then
  printf '\n# Permit only manifest-authorized isolated worker-entrypoint rollouts.\nRAIJIN_UPDATE_SELECTIVE_RESTORE=true\nRAIJIN_UPDATE_SELECTIVE_DISCOVERY=true\nRAIJIN_UPDATE_SELECTIVE_AUDIT=true\nRAIJIN_UPDATE_SELECTIVE_TRANSFER=true\n' >>"$update_config"
fi
source "$install_root/scripts/web-auth.sh"
source "$install_root/scripts/console-auth-lifecycle.sh"
raijin_load_web_auth
runtime_complete=true
for container in raijin-postgres raijin-app raijin-raikou-shin raijin-raikou-sei raijin-raikou-ko raijin-raikou-kai raijin-transfer-worker; do
  if [[ "$(podman inspect --format '{{.State.Running}}' "$container" 2>/dev/null || true)" != true ]]; then
    runtime_complete=false
    break
  fi
done
if [[ "$runtime_complete" == true ]]; then
  for container in raijin-app raijin-raikou-shin raijin-raikou-sei raijin-raikou-ko raijin-raikou-kai raijin-transfer-worker; do
    if [[ "$(podman inspect --format '{{.ImageName}}' "$container" 2>/dev/null || true)" != "$release_image" ]]; then
      runtime_complete=false
      break
    fi
  done
fi
if [[ "$runtime_complete" == true ]]; then
  bootstrap_complete=true
  trap - EXIT
  exit 0
fi

web_bind_control_root="$data_root/web-bind-control"
update_control_root="$data_root/update-control"
mkdir -p "$data_root/postgres" "$secret_root" "$runtime_root" "$web_bind_control_root" "$update_control_root" "$application_log_control_root"
chmod 0750 "$web_bind_control_root"
chmod 0750 "$update_control_root"
chmod 0750 "$application_log_control_root"
chmod 700 "$secret_root"
# The web service is loopback-only. SSH is the sole administrative entrypoint,
# and it accepts only the public key provisioned by Terraform/cloud-init.
install -d -m 0755 /etc/ssh/sshd_config.d
cat >/etc/ssh/sshd_config.d/99-raijin-key-only.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
PubkeyAuthentication yes
PermitRootLogin no
EOF
sshd -t && systemctl reload sshd
if [[ ! -f "$oci_runtime_config" ]]; then
  printf '{"secret_ocids":{}}\n' >"$oci_runtime_config"
fi
# The runtime config contains only secret references (Vault OCIDs or protected
# local file paths), never secret values. The application container reads it
# only when it needs OCI metadata.
chmod 644 "$oci_runtime_config"

# A host that starts from a protected local password needs an explicit durable
# marker. On a later restart, changing only oci-runtime.json from
# secret_file_paths to secret_ocids is enough for bootstrap to rotate the
# database role to Vault and retire this marker safely.
postgres_secret_source="$(python3 - "$oci_runtime_config" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    runtime = json.load(source)
ocid = (runtime.get("secret_ocids") or {}).get("postgres_password")
local_path = (runtime.get("secret_file_paths") or {}).get("postgres_password")
if bool(ocid) == bool(local_path):
    raise SystemExit(
        "Configure exactly one postgres_password source: secret_ocids or secret_file_paths"
    )
print("vault" if ocid else "local")
PY
)"

# Vault is the source of truth. A first boot materializes the Terraform-created
# password locally without writing its value to a command line or service log.
if [[ ! -s "$secret_root/postgres_password" ]]; then
  python3 "$install_root/scripts/fetch-oci-secret.py" \
    --runtime-config "$oci_runtime_config" \
    --secret-name postgres_password \
    --output "$secret_root/postgres_password"
fi
if [[ "$postgres_secret_source" == local ]]; then
  install -o root -g root -m 0600 /dev/null "$temporary_local_secrets_marker"
fi
podman network exists raijin-data-migration 2>/dev/null || podman network create raijin-data-migration
podman rm -f raijin-app raijin-postgres raijin-governance-worker raijin-raikou-shin raijin-raikou-sei raijin-raikou-ko raijin-raikou-kai raijin-transfer-worker 2>/dev/null || true

podman run -d --name raijin-postgres --replace --restart unless-stopped \
  --shm-size=512m \
  --network raijin-data-migration --network-alias postgres \
  -e POSTGRES_DB=migration \
  -e POSTGRES_USER=migration \
  -e POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password \
  -v "$data_root/postgres:/var/lib/postgresql/data:Z" \
  -v "$secret_root/postgres_password:/run/secrets/postgres_password:ro,z" \
  docker.io/library/postgres:16-alpine

postgres_ready=false
for attempt in $(seq 1 30); do
  if podman exec raijin-postgres pg_isready -U migration -d migration >/dev/null 2>&1; then
    postgres_ready=true
    break
  fi
  sleep 2
done
if [[ "$postgres_ready" != true ]]; then
  echo "PostgreSQL did not become ready" >&2
  exit 1
fi

if [[ "$RAIJIN_WEB_AUTH_MODE" == local && "$(raijin_console_auth_lifecycle_state)" == BOOTSTRAP_REQUIRED ]]; then
  # Initial administrator material is intentionally never fetched from Vault:
  # it must originate from a root-owned local file and the launcher will bind
  # the console to loopback for this one-time ceremony.
  python3 - "$oci_runtime_config" <<'PY'
import json
import os
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    runtime = json.load(source)
local_path = (runtime.get("secret_file_paths") or {}).get("console_bootstrap_password")
ocid = (runtime.get("secret_ocids") or {}).get("console_bootstrap_password")
if ocid or not isinstance(local_path, str) or not os.path.isabs(local_path):
    raise SystemExit(
        "Initial console bootstrap requires secret_file_paths.console_bootstrap_password; Vault is not allowed"
    )
PY
  python3 "$install_root/scripts/fetch-oci-secret.py" \
    --runtime-config "$oci_runtime_config" \
    --secret-name console_bootstrap_password \
    --output "$secret_root/console_bootstrap_password"
fi

if [[ "$postgres_secret_source" == vault && -f "$temporary_local_secrets_marker" ]]; then
  "$install_root/scripts/adopt-vault-secrets.sh"
fi

if ! podman image exists "$release_image"; then
  # Some Podman releases do not include changed ARG values in every cached
  # layer key. A release image is built only once, without cache, and then
  # addressed by its immutable revision on every subsequent boot.
  podman build --no-cache \
    --build-arg "RAIJIN_SERVICE_VERSION=$service_version" \
    --build-arg "RAIJIN_BUILD_REVISION=$build_revision" \
    -t "$release_image" "$install_root"
fi
install -m 0750 "$install_root/scripts/start-runtime.sh" /usr/local/sbin/raijin-start-runtime
install -m 0750 "$install_root/scripts/stop-runtime.sh" /usr/local/sbin/raijin-stop-runtime
install -m 0750 "$install_root/scripts/console-admin.sh" /usr/local/sbin/raijin-console-admin
install -m 0750 "$install_root/scripts/console-auth-preflight.sh" /usr/local/sbin/raijin-console-auth-preflight
install -m 0750 "$install_root/scripts/process-web-bind-request.sh" /usr/local/sbin/raijin-process-web-bind-request
install -m 0750 "$install_root/scripts/process-update-request.sh" /usr/local/sbin/raijin-process-update-request
install -m 0750 "$install_root/scripts/process-application-log-request.sh" /usr/local/sbin/raijin-process-application-log-request
RAIJIN_IMAGE="$release_image" /usr/local/sbin/raijin-start-runtime

# The single-runtime release retires the old mode switch and the temporary
# Fujin co-location helpers. Remove them explicitly on upgrade so they cannot
# be selected again after a reboot.
systemctl disable --now raijin-mode-request.timer 2>/dev/null || true
rm -f \
  /etc/systemd/system/raijin-mode-request.service \
  /etc/systemd/system/raijin-mode-request.timer \
  /usr/local/sbin/raijin-mode \
  /usr/local/sbin/raijin-process-mode-request \
  /usr/local/sbin/raijin-start-fujin-local-runtime \
  /usr/local/sbin/raijin-mount-fujin-payload \
  /usr/local/sbin/configure-fujin-local-oci-runtime \
  /etc/raijin-data-migration/operation-mode \
  /etc/raijin-data-migration/deployment-profile

cat >/etc/systemd/system/raijin-data-migration.service <<'EOF'
[Unit]
Description=Raijin Data Migration platform
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/opt/raijin-data-migration/release/scripts/bootstrap.sh
ExecStop=/usr/local/sbin/raijin-stop-runtime

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable raijin-data-migration.service

cat >/etc/systemd/system/raijin-web-bind-request.service <<'EOF'
[Unit]
Description=Process a validated RAIJIN console endpoint request
After=raijin-data-migration.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/raijin-process-web-bind-request
EOF
cat >/etc/systemd/system/raijin-web-bind-request.timer <<'EOF'
[Unit]
Description=Watch for RAIJIN console endpoint requests

[Timer]
OnBootSec=10
OnUnitActiveSec=5
AccuracySec=1
Persistent=true

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now raijin-web-bind-request.timer

cat >/etc/systemd/system/raijin-application-log-request.service <<'EOF'
[Unit]
Description=Collect bounded RAIJIN application logs
After=raijin-data-migration.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/raijin-process-application-log-request
EOF
cat >/etc/systemd/system/raijin-application-log-request.timer <<'EOF'
[Unit]
Description=Watch for RAIJIN application log requests

[Timer]
OnBootSec=15
OnUnitActiveSec=3
AccuracySec=1
Persistent=true

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now raijin-application-log-request.timer

cat >/etc/systemd/system/raijin-update-request.service <<'EOF'
[Unit]
Description=Process a validated RAIJIN source update request
After=raijin-data-migration.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/raijin-process-update-request
EOF
cat >/etc/systemd/system/raijin-update-request.timer <<'EOF'
[Unit]
Description=Watch for RAIJIN source update requests

[Timer]
OnBootSec=20
OnUnitActiveSec=5
AccuracySec=1
Persistent=true

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now raijin-update-request.timer

install -m 0750 "$install_root/scripts/backup-postgres.sh" /usr/local/sbin/raijin-backup-postgres
install -m 0750 "$install_root/scripts/restore-postgres.sh" /usr/local/sbin/raijin-restore-postgres
cat >/etc/systemd/system/raijin-backup-postgres.service <<'EOF'
[Unit]
Description=Local PostgreSQL backup for S3 to OCI migration platform
After=raijin-data-migration.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/raijin-backup-postgres
EOF
cat >/etc/systemd/system/raijin-backup-postgres.timer <<'EOF'
[Unit]
Description=Daily local PostgreSQL backup for S3 to OCI migration platform

[Timer]
OnCalendar=*-*-* 02:15:00 UTC
Persistent=true

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now raijin-backup-postgres.timer

install -m 0750 "$install_root/scripts/write-platform-status.sh" /usr/local/sbin/raijin-write-platform-status
cat >/etc/systemd/system/raijin-platform-status.service <<'EOF'
[Unit]
Description=Write S3 to OCI migration platform status
After=raijin-data-migration.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/raijin-write-platform-status
EOF
cat >/etc/systemd/system/raijin-platform-status.timer <<'EOF'
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
systemctl enable raijin-platform-status.timer
systemctl restart raijin-platform-status.timer
/usr/local/sbin/raijin-write-platform-status

# Remove the legacy task-advancing simulation worker. The replacement backend
# simulator is intentionally not installed until the exclusive Simulation mode
# and its isolated database are available.
systemctl disable --now raijin-simulated-worker.service 2>/dev/null || true
rm -f /etc/systemd/system/raijin-simulated-worker.service /usr/local/sbin/raijin-simulated-worker
systemctl daemon-reload

bootstrap_complete=true
trap - EXIT
