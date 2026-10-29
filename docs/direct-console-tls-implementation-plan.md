# Direct console TLS and bind configuration

## Decision

Raijin publishes its own console endpoint. Initial non-loopback publication is
HTTPS-only and uses a persistent self-signed certificate generated on the host.
HTTP remains supported only for loopback or a trusted load balancer that
terminates TLS upstream. In that latter mode, each upstream must be an explicit
IPv4 `/32`; broad CIDRs and `0.0.0.0/0` are rejected.

## Guardrails

1. During bootstrap, bind is effectively `127.0.0.1:1604`; Settings displays
   the configuration as locked.
2. Unlock requires an enabled ADMIN with a changed password and retirement of
   `console_bootstrap_password`.
3. A non-loopback HTTP request is rejected unless `trusted_tls_terminator` is
   configured with a non-empty allowlist of upstream IPv4 `/32` addresses.
4. Raijin enforces the allowlist against the TCP peer; the identical list must
   also be applied to the VM firewall and OCI NSG/security list.
5. Host configuration is changed only by a root-owned request processor; the
   web container can submit an atomic request but cannot edit `/etc` or invoke
   systemd.
6. Host validates address, port, TLS material, local interface and HTTP
   upstream allowlist before
   writing `web-bind.env`, then restarts the platform and records a result.

## Delivery steps

- [ ] Extend `web-bind.env` with transport mode, host certificate paths and
      `WEB_TRUSTED_UPSTREAM_IPS` (comma-separated IPv4 `/32` allowlist).
- [ ] Generate persistent self-signed certificates on the host with IP SAN.
- [ ] Launch Uvicorn with TLS when selected; retain internal HTTP health probes.
- [ ] Add the root-owned bind request processor and systemd timer.
- [ ] Add ADMIN APIs and Settings UI, including pending/result state.
- [ ] Test bootstrap lock, HTTP policy, TLS launch and request processor
      rejection paths.
- [ ] Update deployment and operations documentation.
