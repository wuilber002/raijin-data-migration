#!/usr/bin/env bash

# Shared host-side web bind configuration. This file is sourced by runtime
# launchers and recovery utilities; it deliberately does not set shell flags.
# Keep the published host endpoint separate from the container's internal
# listener, which remains on port 8080.

raijin_load_web_bind() {
  local config_file configured_host=127.0.0.1 configured_port=1604
  local key value line host port probe_host probe_host_url publish_host

  config_file="${RAIJIN_WEB_BIND_CONFIG:-/etc/s3-oci-migration/web-bind.env}"
  if [[ -e "$config_file" ]]; then
    [[ -f "$config_file" && -r "$config_file" ]] || {
      echo "Web bind configuration is not a readable file: $config_file" >&2
      return 2
    }
    while IFS= read -r line || [[ -n "$line" ]]; do
      [[ -z "$line" || "$line" == \#* ]] && continue
      [[ "$line" == *=* ]] || {
        echo "Invalid web bind configuration line in $config_file" >&2
        return 2
      }
      key="${line%%=*}"
      value="${line#*=}"
      case "$key" in
        WEB_BIND_HOST) configured_host="$value" ;;
        WEB_BIND_PORT) configured_port="$value" ;;
        *)
          echo "Unsupported web bind configuration key in $config_file: $key" >&2
          return 2
          ;;
      esac
    done <"$config_file"
  fi

  host="${RAIJIN_WEB_BIND_HOST:-$configured_host}"
  port="${RAIJIN_WEB_BIND_PORT:-$configured_port}"
  python3 - "$host" "$port" <<'PY' || return $?
import ipaddress
import sys

host, port = sys.argv[1:]
try:
    ipaddress.ip_address(host)
except ValueError:
    raise SystemExit("WEB_BIND_HOST must be an IPv4 or IPv6 address")
try:
    numeric_port = int(port)
except ValueError:
    raise SystemExit("WEB_BIND_PORT must be an integer from 1 through 65535")
if not 1 <= numeric_port <= 65535:
    raise SystemExit("WEB_BIND_PORT must be an integer from 1 through 65535")
PY

  probe_host="$host"
  [[ "$probe_host" == 0.0.0.0 ]] && probe_host=127.0.0.1
  [[ "$probe_host" == :: ]] && probe_host=::1
  if [[ "$host" == *:* ]]; then
    publish_host="[$host]"
  else
    publish_host="$host"
  fi
  if [[ "$probe_host" == *:* ]]; then
    probe_host_url="[$probe_host]"
  else
    probe_host_url="$probe_host"
  fi

  RAIJIN_WEB_BIND_HOST="$host"
  RAIJIN_WEB_BIND_PORT="$port"
  RAIJIN_WEB_BIND_PUBLISH="$publish_host:$port:8080"
  RAIJIN_WEB_BIND_PROBE_URL="http://$probe_host_url:$port"
  export RAIJIN_WEB_BIND_HOST RAIJIN_WEB_BIND_PORT RAIJIN_WEB_BIND_PUBLISH RAIJIN_WEB_BIND_PROBE_URL
}
