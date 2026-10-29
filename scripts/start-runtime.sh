#!/usr/bin/env bash
set -euo pipefail

mode="${1:-REAL}"
install_root=/opt/s3-oci-migration/release
secret_root=/etc/s3-oci-migration/secrets
runtime_root=/run/s3-oci-migration
mode_control_root=/var/lib/s3-oci-migration/mode-control
web_bind_control_root=/var/lib/s3-oci-migration/web-bind-control
oci_runtime_config=/etc/s3-oci-migration/oci-runtime.json
image="${RAIJIN_IMAGE:-localhost/s3-oci-migration:latest}"
network=s3-oci-migration

# The web console is loopback-only by default. Operators can persist a
# different host interface/port in /etc/s3-oci-migration/web-bind.env.
# See scripts/web-bind.sh for validation and supported values.
# shellcheck source=web-bind.sh
source "$install_root/scripts/web-bind.sh"
raijin_load_web_bind
source "$install_root/scripts/console-auth-lifecycle.sh"
# Older release directories can be used by the pre-auth update workflow. Keep
# their launcher usable with the compatibility-safe disabled defaults.
if [[ -r "$install_root/scripts/web-auth.sh" ]]; then
  # shellcheck source=web-auth.sh
  source "$install_root/scripts/web-auth.sh"
  raijin_load_web_auth
else
  RAIJIN_WEB_AUTH_MODE=disabled
  RAIJIN_WEB_EXTERNAL_HTTPS=false
  RAIJIN_WEB_AUTH_TRUSTED_PROXY_CIDRS=
  RAIJIN_WEB_AUTH_SESSION_IDLE_MINUTES=30
  RAIJIN_WEB_AUTH_SESSION_ABSOLUTE_MINUTES=720
  RAIJIN_WEB_AUTH_BOOTSTRAP_USERNAME=admin
fi

console_auth_lifecycle=READY
if [[ "$RAIJIN_WEB_AUTH_MODE" == local ]]; then
  console_auth_lifecycle="$(raijin_console_auth_lifecycle_state)"
  if [[ "$console_auth_lifecycle" == BOOTSTRAP_REQUIRED ]]; then
    # The first administrator credential is intentionally local-only even if
    # web-bind.env already asks for a public/private interface.
    raijin_force_loopback_web_bind "$RAIJIN_WEB_BIND_PORT"
  elif [[ -e "$secret_root/console_bootstrap_password" ]]; then
    # A completed bootstrap cannot expose a host interface until the temporary
    # local bootstrap file has been retired by the administrator.
    echo "Console bootstrap file is still present; keeping the web bind on 127.0.0.1." >&2
    raijin_force_loopback_web_bind "$RAIJIN_WEB_BIND_PORT"
  fi
fi

web_auth_environment=(
  -e "RAIJIN_WEB_BIND_HOST=$RAIJIN_WEB_BIND_HOST"
  -e "RAIJIN_WEB_BIND_PORT=$RAIJIN_WEB_BIND_PORT"
  -e "RAIJIN_WEB_TRANSPORT=$RAIJIN_WEB_TRANSPORT"
  -e "RAIJIN_WEB_TRUSTED_UPSTREAM_IPS=$RAIJIN_WEB_TRUSTED_UPSTREAM_IPS"
  -e "RAIJIN_WEB_AUTH_MODE=$RAIJIN_WEB_AUTH_MODE"
  -e "RAIJIN_WEB_AUTH_SESSION_IDLE_MINUTES=$RAIJIN_WEB_AUTH_SESSION_IDLE_MINUTES"
  -e "RAIJIN_WEB_AUTH_SESSION_ABSOLUTE_MINUTES=$RAIJIN_WEB_AUTH_SESSION_ABSOLUTE_MINUTES"
  -e "RAIJIN_WEB_AUTH_BOOTSTRAP_REQUIRED=$([[ "$console_auth_lifecycle" == BOOTSTRAP_REQUIRED ]] && echo true || echo false)"
  -e "RAIJIN_WEB_AUTH_BOOTSTRAP_USERNAME=$RAIJIN_WEB_AUTH_BOOTSTRAP_USERNAME"
)

# The endpoint configuration is authoritative for transport security.  An
# HTTP publication is accepted only from its TLS terminator, which is also the
# only peer permitted to supply forwarded client headers.
if [[ "$RAIJIN_WEB_TRANSPORT" == https ]]; then
  web_auth_environment+=( -e RAIJIN_WEB_EXTERNAL_HTTPS=true -e RAIJIN_WEB_AUTH_TRUSTED_PROXY_CIDRS= )
elif [[ -n "$RAIJIN_WEB_TRUSTED_UPSTREAM_IPS" ]]; then
  web_auth_environment+=( -e RAIJIN_WEB_EXTERNAL_HTTPS=true -e "RAIJIN_WEB_AUTH_TRUSTED_PROXY_CIDRS=$RAIJIN_WEB_TRUSTED_UPSTREAM_IPS" )
else
  web_auth_environment+=( -e "RAIJIN_WEB_EXTERNAL_HTTPS=$RAIJIN_WEB_EXTERNAL_HTTPS" -e "RAIJIN_WEB_AUTH_TRUSTED_PROXY_CIDRS=$RAIJIN_WEB_AUTH_TRUSTED_PROXY_CIDRS" )
fi

web_server_command=()
web_tls_mounts=()
if [[ "$RAIJIN_WEB_TRANSPORT" == https ]]; then
  web_tls_root=/etc/s3-oci-migration/web-tls
  [[ -s "$web_tls_root/cert.pem" && -s "$web_tls_root/key.pem" ]] || {
    echo "HTTPS console publication requires host TLS certificate material" >&2; exit 2;
  }
  web_tls_mounts+=( -v "$web_tls_root:/run/web-tls:ro,z" )
  web_server_command=(uvicorn app.main:app --host 0.0.0.0 --port 8080 --ssl-certfile /run/web-tls/cert.pem --ssl-keyfile /run/web-tls/key.pem)
fi

web_probe() {
  if [[ "$RAIJIN_WEB_TRANSPORT" == https ]]; then
    curl --insecure --fail --silent "$RAIJIN_WEB_BIND_PROBE_URL/healthz"
  else
    curl --fail --silent "$RAIJIN_WEB_BIND_PROBE_URL/healthz"
  fi
}

web_auth_secret_mounts=()
if [[ "$RAIJIN_WEB_AUTH_MODE" == local && "$console_auth_lifecycle" == BOOTSTRAP_REQUIRED ]]; then
  [[ -s "$secret_root/console_bootstrap_password" ]] || {
    echo "Local web authentication requires console_bootstrap_password" >&2
    exit 2
  }
  web_auth_environment+=( -e RAIJIN_WEB_AUTH_BOOTSTRAP_PASSWORD_FILE=/run/secrets/console_bootstrap_password )
  web_auth_secret_mounts+=( -v "$secret_root/console_bootstrap_password:/run/secrets/console_bootstrap_password:ro,z" )
fi

case "$mode" in
  REAL)
    podman run -d --name s3-oci-app --replace --restart unless-stopped \
      --network "$network" -p "$RAIJIN_WEB_BIND_PUBLISH" \
      -e RAIJIN_OPERATION_MODE=REAL \
      -e DATABASE_URL=postgresql+psycopg://migration@postgres:5432/migration \
      -e POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password \
      "${web_auth_environment[@]}" \
      "${web_auth_secret_mounts[@]}" \
      -e OCI_RUNTIME_CONFIG_FILE=/run/oci-runtime/oci-runtime.json \
      -e RAIJIN_MODE_REQUEST_FILE=/run/mode-control/request \
      -e RAIJIN_WEB_BIND_REQUEST_FILE=/run/web-bind-control/request.json \
      -e RAIJIN_WEB_BIND_RESULT_FILE=/run/web-bind-control/result.json \
      -v "$secret_root/postgres_password:/run/secrets/postgres_password:ro,z" \
      -v "$runtime_root:/run/platform-status:ro,z" \
      -v "$mode_control_root:/run/mode-control:rw,z" \
      -v "$web_bind_control_root:/run/web-bind-control:rw,z" \
      -v "$oci_runtime_config:/run/oci-runtime/oci-runtime.json:ro,z" \
      "${web_tls_mounts[@]}" \
      "$image" "${web_server_command[@]}"
    for attempt in $(seq 1 30); do
      web_probe >/dev/null && break
      [[ "$attempt" -lt 30 ]] || { echo "REAL API did not become healthy" >&2; exit 1; }
      sleep 2
    done
    for worker_role in raikou-shin raikou-sei raikou-ko raikou-kai raiju; do
      container="s3-oci-${worker_role}"
      [[ "$worker_role" == raiju ]] && container=s3-oci-transfer-worker
      podman run -d --name "$container" --replace --restart unless-stopped \
        --network "$network" \
        -e "RAIJIN_WORKER_ID=${worker_role}-vm" -e "RAIJIN_WORKER_ROLE=$worker_role" \
        -e RAIJIN_OPERATION_MODE=REAL \
        -e RAIJIN_MODE_REQUEST_FILE=/run/mode-control/request \
        -e DATABASE_URL=postgresql+psycopg://migration@postgres:5432/migration \
        -e POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password \
        -e OCI_RUNTIME_CONFIG_FILE=/run/oci-runtime/oci-runtime.json \
        -v "$secret_root/postgres_password:/run/secrets/postgres_password:ro,z" \
        -v "$mode_control_root:/run/mode-control:ro,z" \
        -v "$oci_runtime_config:/run/oci-runtime/oci-runtime.json:ro,z" \
        "$image" python3 -m app.real_worker
    done
    ;;
  SIMULATION)
    podman run --rm --network "$network" \
      -e PYTHONPATH=/app \
      -e RAIJIN_OPERATION_MODE=SIMULATION \
      -e RAIJIN_SIMULATOR_BASE_URL=http://simulator:8090 \
      -e DATABASE_URL=postgresql+psycopg://migration_simulation@postgres:5432/migration_simulation \
      -e RAIJIN_SIMULATOR_DATABASE_URL=postgresql+psycopg://migration_simulation@postgres:5432/migration_simulation \
      -e POSTGRES_PASSWORD_FILE=/run/secrets/simulation_postgres_password \
      -e RAIJIN_SIMULATOR_POSTGRES_PASSWORD_FILE=/run/secrets/simulation_postgres_password \
      -v "$secret_root/simulation_postgres_password:/run/secrets/simulation_postgres_password:ro,z" \
      "$image" python3 scripts/migrate-simulation.py
    podman run -d --name s3-oci-simulator --replace --restart unless-stopped \
      --network "$network" --network-alias simulator \
      -e RAIJIN_OPERATION_MODE=SIMULATION \
      -e RAIJIN_SIMULATOR_DATABASE_URL=postgresql+psycopg://migration_simulation@postgres:5432/migration_simulation \
      -e RAIJIN_SIMULATOR_POSTGRES_PASSWORD_FILE=/run/secrets/simulation_postgres_password \
      -v "$secret_root/simulation_postgres_password:/run/secrets/simulation_postgres_password:ro,z" \
      "$image" uvicorn app.simulator:app --host 0.0.0.0 --port 8090
    for attempt in $(seq 1 30); do
      podman exec s3-oci-simulator python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/healthz', timeout=2)" >/dev/null 2>&1 && break
      [[ "$attempt" -lt 30 ]] || { echo "Simulator did not become healthy" >&2; exit 1; }
      sleep 2
    done
    podman run -d --name s3-oci-app --replace --restart unless-stopped \
      --network "$network" -p "$RAIJIN_WEB_BIND_PUBLISH" \
      -e RAIJIN_OPERATION_MODE=SIMULATION \
      -e RAIJIN_SIMULATOR_BASE_URL=http://simulator:8090 \
      -e DATABASE_URL=postgresql+psycopg://migration_simulation@postgres:5432/migration_simulation \
      -e POSTGRES_PASSWORD_FILE=/run/secrets/simulation_postgres_password \
      "${web_auth_environment[@]}" \
      "${web_auth_secret_mounts[@]}" \
      -e RAIJIN_MODE_REQUEST_FILE=/run/mode-control/request \
      -v "$runtime_root:/run/platform-status:ro,z" \
      -v "$mode_control_root:/run/mode-control:rw,z" \
      -v "$secret_root/simulation_postgres_password:/run/secrets/simulation_postgres_password:ro,z" "$image"
    for attempt in $(seq 1 30); do
      curl --fail --silent "$RAIJIN_WEB_BIND_PROBE_URL/healthz" >/dev/null && break
      [[ "$attempt" -lt 30 ]] || { echo "SIMULATION API did not become healthy" >&2; exit 1; }
      sleep 2
    done
    for worker_role in raikou-shin raikou-sei raikou-ko raikou-kai raiju; do
      container="s3-oci-${worker_role}"
      [[ "$worker_role" == raiju ]] && container=s3-oci-transfer-worker
      podman run -d --name "$container" --replace --restart unless-stopped \
        --network "$network" \
        -e "RAIJIN_WORKER_ID=${worker_role}-simulation" -e "RAIJIN_WORKER_ROLE=$worker_role" \
        -e RAIJIN_OPERATION_MODE=SIMULATION \
        -e RAIJIN_MODE_REQUEST_FILE=/run/mode-control/request \
        -e RAIJIN_SIMULATOR_BASE_URL=http://simulator:8090 \
        -e DATABASE_URL=postgresql+psycopg://migration_simulation@postgres:5432/migration_simulation \
        -e POSTGRES_PASSWORD_FILE=/run/secrets/simulation_postgres_password \
        -v "$mode_control_root:/run/mode-control:ro,z" \
        -v "$secret_root/simulation_postgres_password:/run/secrets/simulation_postgres_password:ro,z" \
        "$image" python3 -m app.real_worker
    done
    ;;
  *) echo "Mode must be REAL or SIMULATION" >&2; exit 2 ;;
esac
