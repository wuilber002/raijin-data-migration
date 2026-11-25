#!/usr/bin/env bash
# Apply a console endpoint request.  This runs from a root-owned systemd
# service; the web container can only write a constrained request file.
set -euo pipefail

install_root=/opt/raijin-data-migration/release
control_root=/var/lib/raijin-data-migration/web-bind-control
request="$control_root/request.json"
result="$control_root/result.json"
retire_request="$control_root/retire-bootstrap"
config=/etc/raijin-data-migration/web-bind.env
secret_root=/etc/raijin-data-migration/secrets
runtime_service=raijin-data-migration.service
runtime_network=raijin-data-migration

# The container sees only its Podman interfaces. Collect candidate bind
# addresses on the host, where the listener is actually published.
publish_bind_addresses() {
  python3 >"$control_root/interfaces.json.tmp" <<'PY'
import json
import subprocess

addresses = [
    {"value": "127.0.0.1", "label": "127.0.0.1 — Loopback only"},
    {"value": "0.0.0.0", "label": "0.0.0.0 — All IPv4 interfaces"},
]
try:
    rows = json.loads(subprocess.check_output(
        ["ip", "-j", "-4", "addr", "show", "up"], text=True, stderr=subprocess.DEVNULL
    ))
    for row in rows:
        name = str(row.get("ifname") or "interface")
        # Container bridges are host-local plumbing, not operator-facing
        # listener choices. Keep physical/VNIC and ordinary named interfaces.
        if name == "lo" or name.startswith(("podman", "docker", "cni", "veth", "br-")):
            continue
        for info in row.get("addr_info") or []:
            address = str(info.get("local") or "")
            if info.get("family") != "inet" or address in {"", "127.0.0.1"}:
                continue
            addresses.append({"value": address, "label": f"{address} — {name}"})
except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
    pass
seen = set()
print(json.dumps([item for item in addresses if not (item["value"] in seen or seen.add(item["value"]))]))
PY
  chmod 0640 "$control_root/interfaces.json.tmp"
  mv "$control_root/interfaces.json.tmp" "$control_root/interfaces.json"
}

publish_bind_addresses

verify_published_endpoint() {
  local probe_host probe_url
  probe_host="$host"
  [[ "$probe_host" == 0.0.0.0 ]] && probe_host=127.0.0.1
  [[ "$probe_host" == :: ]] && probe_host=::1
  if [[ "$probe_host" == *:* ]]; then
    probe_host="[$probe_host]"
  fi
  probe_url="$transport://$probe_host:$port/healthz"
  if [[ "$transport" == https ]]; then
    curl --insecure --fail --silent --show-error --connect-timeout 5 --max-time 10 "$probe_url" >/dev/null
  else
    curl --fail --silent --show-error --connect-timeout 5 --max-time 10 "$probe_url" >/dev/null
  fi
}

if [[ -e "$retire_request" ]]; then
  source "$install_root/scripts/web-auth.sh"
  source "$install_root/scripts/console-auth-lifecycle.sh"
  raijin_load_web_auth
  if [[ "$RAIJIN_WEB_AUTH_MODE" == local && "$(raijin_console_auth_lifecycle_state)" == READY ]]; then
    rm -f "$secret_root/console_bootstrap_password" "$retire_request"
    printf '{"status":"SUCCEEDED","message":"Bootstrap password retired; reconnect to continue."}\n' >"$result"
    systemctl restart raijin-data-migration.service
  else
    rm -f "$retire_request"
    printf '{"status":"REJECTED","message":"Bootstrap password can only be retired after an enabled administrator changes it."}\n' >"$result"
  fi
  exit 0
fi
[[ -s "$request" ]] || exit 0
mv "$request" "$request.processing"
finish() {
  local status="$1" message="$2"
  publish_result "$status" "$message"
  rm -f "$request.processing"
}
publish_result() {
  local status="$1" message="$2"
  python3 - "$status" "$message" >"$result.tmp" <<'PY'
import json, sys
print(json.dumps({"status": sys.argv[1], "message": sys.argv[2]}))
PY
  mv "$result.tmp" "$result"
}
trap 'finish FAILED "Host endpoint request could not be processed"' ERR

source "$install_root/scripts/web-auth.sh"
source "$install_root/scripts/console-auth-lifecycle.sh"
raijin_load_web_auth
if [[ "$RAIJIN_WEB_AUTH_MODE" == local ]] && { [[ "$(raijin_console_auth_lifecycle_state)" == BOOTSTRAP_REQUIRED ]] || [[ -e "$secret_root/console_bootstrap_password" ]]; }; then
  finish REJECTED "Console endpoint stays locked until the bootstrap password is changed and retired."
  exit 0
fi

readarray -t values < <(python3 - "$request.processing" <<'PY'
import ipaddress, json, sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    host = str(data["host"]).strip()
    port = int(data["port"])
    transport = str(data["transport"]).strip().lower()
    upstreams = data.get("trusted_upstream_ips", [])
    if data.get("confirm_network_recreation") is not True:
        raise ValueError("network recreation was not explicitly confirmed")
    if not isinstance(upstreams, list): raise ValueError("trusted_upstream_ips must be a list")
    ipaddress.ip_address(host)
    if not 1 <= port <= 65535: raise ValueError("port must be 1-65535")
    if transport not in {"http", "https"}: raise ValueError("transport must be http or https")
    entries=[]
    for item in upstreams:
        network=ipaddress.ip_network(str(item).strip(), strict=True)
        if network.version != 4 or network.prefixlen != 32: raise ValueError("trusted upstreams must be IPv4 /32")
        entries.append(str(network))
    if transport == "http" and not ipaddress.ip_address(host).is_loopback and not entries:
        raise ValueError("non-loopback HTTP requires trusted upstream IPv4 /32 entries")
    if transport == "https" and entries: raise ValueError("trusted upstreams are only valid for HTTP")
    print(host); print(port); print(transport); print(",".join(entries))
except Exception as exc:
    print(f"INVALID: {exc}", file=sys.stderr); raise SystemExit(2)
PY
)

host="${values[0]}" port="${values[1]}" transport="${values[2]}" upstreams="${values[3]}"
umask 077
previous_config=""
previous_config_exists=false
previous_tls_root=""
tls_root=/etc/raijin-data-migration/web-tls
if [[ -e "$config" ]]; then
  previous_config="$(mktemp "$control_root/web-bind.env.previous.XXXXXX")"
  cp --preserve=mode,ownership "$config" "$previous_config"
  previous_config_exists=true
fi
if [[ -d "$tls_root" ]]; then
  previous_tls_root="$(mktemp -d "$control_root/web-tls.previous.XXXXXX")"
  cp -a "$tls_root/." "$previous_tls_root/"
fi

restore_previous_endpoint_files() {
  if [[ "$previous_config_exists" == true ]]; then
    mv "$previous_config" "$config"
  else
    rm -f "$config"
  fi
  if [[ -n "$previous_tls_root" ]]; then
    rm -rf "$tls_root"
    install -d -m 0750 "$tls_root"
    cp -a "$previous_tls_root/." "$tls_root/"
  else
    rm -rf "$tls_root"
  fi
}

recreate_runtime_network() {
  # A listener can still accept TCP while conmon no longer relays bytes after
  # a published-port change. Recreate the exclusive Raijin network after all
  # runtime containers have stopped; bootstrap creates it again on start.
  systemctl stop "$runtime_service" || return 1
  if podman network exists "$runtime_network"; then
    podman network rm "$runtime_network" || return 1
  fi
  systemctl start "$runtime_service" || return 1
}

if [[ "$transport" == https ]]; then
  install -d -m 0750 "$tls_root"
  command -v openssl >/dev/null || { finish FAILED "openssl is required to generate the local TLS certificate"; exit 0; }
  # A wildcard listener is reached through one of the host's real VNIC
  # addresses, never through 0.0.0.0. Include those addresses in the SAN so
  # clients do not receive a name-mismatch warning merely because the admin
  # selected "all IPv4 interfaces".
  readarray -t certificate_ips < <(python3 - "$host" <<'PY'
import ipaddress
import json
import subprocess
import sys

addresses = {"127.0.0.1", sys.argv[1]}
try:
    rows = json.loads(subprocess.check_output(
        ["ip", "-j", "-4", "addr", "show", "up"], text=True, stderr=subprocess.DEVNULL
    ))
    for row in rows:
        name = str(row.get("ifname") or "")
        if name == "lo" or name.startswith(("podman", "docker", "cni", "veth", "br-")):
            continue
        for info in row.get("addr_info") or []:
            address = str(info.get("local") or "")
            if info.get("family") == "inet":
                addresses.add(address)
except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
    pass
for address in sorted(addresses, key=lambda item: int(ipaddress.ip_address(item))):
    print(address)
PY
)
  san=$(printf 'IP:%s,' "${certificate_ips[@]}")
  san="${san%,}"
  # Regenerate on each HTTPS endpoint change. The old certificate may have
  # been issued for a previous address (or, historically, for 0.0.0.0).
  openssl req -x509 -newkey rsa:3072 -nodes -days 825 \
    -subj "/CN=raijin-console" -addext "subjectAltName=$san" \
    -keyout "$tls_root/key.pem.tmp" -out "$tls_root/cert.pem.tmp" >/dev/null 2>&1
  chmod 0640 "$tls_root/key.pem.tmp" "$tls_root/cert.pem.tmp"
  mv "$tls_root/key.pem.tmp" "$tls_root/key.pem"
  mv "$tls_root/cert.pem.tmp" "$tls_root/cert.pem"
fi
cat >"$config.tmp" <<EOF
# Managed by the Raijin ADMIN console. Do not edit while the service is active.
WEB_BIND_HOST=$host
WEB_BIND_PORT=$port
WEB_TRANSPORT=$transport
WEB_TRUSTED_UPSTREAM_IPS=$upstreams
EOF
mv "$config.tmp" "$config"
publish_result RUNNING "Recreating the Raijin network and runtime containers for the new console endpoint."
if recreate_runtime_network && verify_published_endpoint; then
  rm -f "$previous_config"
  [[ -n "$previous_tls_root" ]] && rm -rf "$previous_tls_root"
  finish SUCCEEDED "Console endpoint applied. The Raijin network and runtime containers were recreated and the new endpoint passed its local health check. Reconnect using the selected endpoint."
  exit 0
fi

# Return the platform to the exact prior endpoint, including its certificate,
# then use another clean network recreation so a failed publish never leaves
# a stale conmon forwarding path behind.
restore_previous_endpoint_files
if ! recreate_runtime_network || ! verify_published_endpoint; then
  finish RECOVERY_FAILED "Console endpoint failed its local health check and the previous endpoint could not be restored automatically. Run the documented recovery procedure before retrying."
  exit 0
fi
[[ -n "$previous_tls_root" ]] && rm -rf "$previous_tls_root"
finish ROLLED_BACK "Console endpoint failed its local health check; the previous endpoint was restored after recreating the Raijin network and runtime containers."
