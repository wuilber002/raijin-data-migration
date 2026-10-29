#!/usr/bin/env bash
# Apply a console endpoint request.  This runs from a root-owned systemd
# service; the web container can only write a constrained request file.
set -euo pipefail

install_root=/opt/s3-oci-migration/release
control_root=/var/lib/s3-oci-migration/web-bind-control
request="$control_root/request.json"
result="$control_root/result.json"
retire_request="$control_root/retire-bootstrap"
config=/etc/s3-oci-migration/web-bind.env
secret_root=/etc/s3-oci-migration/secrets

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

if [[ -e "$retire_request" ]]; then
  source "$install_root/scripts/web-auth.sh"
  source "$install_root/scripts/console-auth-lifecycle.sh"
  raijin_load_web_auth
  if [[ "$RAIJIN_WEB_AUTH_MODE" == local && "$(raijin_console_auth_lifecycle_state)" == READY ]]; then
    rm -f "$secret_root/console_bootstrap_password" "$retire_request"
    printf '{"status":"SUCCEEDED","message":"Bootstrap password retired; reconnect to continue."}\n' >"$result"
    systemctl restart s3-oci-migration.service
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
  python3 - "$status" "$message" >"$result.tmp" <<'PY'
import json, sys
print(json.dumps({"status": sys.argv[1], "message": sys.argv[2]}))
PY
  mv "$result.tmp" "$result"
  rm -f "$request.processing"
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
if [[ "$transport" == https ]]; then
  tls_root=/etc/s3-oci-migration/web-tls
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
umask 077
cat >"$config.tmp" <<EOF
# Managed by the Raijin ADMIN console. Do not edit while the service is active.
WEB_BIND_HOST=$host
WEB_BIND_PORT=$port
WEB_TRANSPORT=$transport
WEB_TRUSTED_UPSTREAM_IPS=$upstreams
EOF
mv "$config.tmp" "$config"
systemctl restart s3-oci-migration.service
finish SUCCEEDED "Console endpoint request applied; the service was restarted."
