#!/usr/bin/env bash

# Shared host-side web bind configuration. This file is sourced by runtime
# launchers and recovery utilities; it deliberately does not set shell flags.
# Keep the published host endpoint separate from the container's internal
# listener, which remains on port 8080.

raijin_load_web_bind() {
  local config_file configured_host=127.0.0.1 configured_port=1604 configured_transport=http configured_upstreams=""
  local key value line host port transport upstreams probe_host probe_host_url publish_host

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
        WEB_TRANSPORT) configured_transport="$value" ;;
        WEB_TRUSTED_UPSTREAM_IPS) configured_upstreams="$value" ;;
        *)
          echo "Unsupported web bind configuration key in $config_file: $key" >&2
          return 2
          ;;
      esac
    done <"$config_file"
  fi

  host="${RAIJIN_WEB_BIND_HOST:-$configured_host}"
  port="${RAIJIN_WEB_BIND_PORT:-$configured_port}"
  transport="${RAIJIN_WEB_TRANSPORT:-$configured_transport}"
  upstreams="${RAIJIN_WEB_TRUSTED_UPSTREAM_IPS:-$configured_upstreams}"
  python3 - "$host" "$port" "$transport" "$upstreams" <<'PY' || return $?
import ipaddress
import sys

host, port, transport, upstreams = sys.argv[1:]
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
if transport not in {"https", "http"}:
    raise SystemExit("WEB_TRANSPORT must be https or http")
if transport == "http" and not ipaddress.ip_address(host).is_loopback:
    entries = [entry.strip() for entry in upstreams.split(",") if entry.strip()]
    if not entries:
        raise SystemExit("HTTP outside loopback requires WEB_TRUSTED_UPSTREAM_IPS")
    for entry in entries:
        network = ipaddress.ip_network(entry, strict=False)
        if network.version != 4 or network.prefixlen != 32:
            raise SystemExit("WEB_TRUSTED_UPSTREAM_IPS accepts IPv4 /32 entries only")
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
  RAIJIN_WEB_TRANSPORT="$transport"
  RAIJIN_WEB_TRUSTED_UPSTREAM_IPS="$upstreams"
  RAIJIN_WEB_BIND_PUBLISH="$publish_host:$port:8080"
  RAIJIN_WEB_BIND_PROBE_URL="http://$probe_host_url:$port"
  export RAIJIN_WEB_BIND_HOST RAIJIN_WEB_BIND_PORT RAIJIN_WEB_TRANSPORT RAIJIN_WEB_TRUSTED_UPSTREAM_IPS RAIJIN_WEB_BIND_PUBLISH RAIJIN_WEB_BIND_PROBE_URL
}
