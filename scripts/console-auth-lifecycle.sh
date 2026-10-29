#!/usr/bin/env bash
# shellcheck shell=bash

# The initial console administrator is deliberately a local-host ceremony.
# This helper reads only durable authentication state from PostgreSQL; it never
# reads a password or emits an identity other than the lifecycle state.
raijin_console_auth_lifecycle_state() {
  local state
  state="$(podman exec s3-oci-postgres psql -U migration -d migration -tAc "
    SELECT CASE
      WHEN to_regclass('public.console_users') IS NULL THEN 'BOOTSTRAP_REQUIRED'
      WHEN EXISTS (
        SELECT 1 FROM console_users
        WHERE role = 'ADMIN' AND enabled IS TRUE AND must_change_password IS FALSE
      ) THEN 'READY'
      ELSE 'BOOTSTRAP_REQUIRED'
    END
  " 2>/dev/null | tr -d '[:space:]' || true)"
  case "$state" in
    READY|BOOTSTRAP_REQUIRED) printf '%s\n' "$state" ;;
    *) printf '%s\n' BOOTSTRAP_REQUIRED ;;
  esac
}

raijin_force_loopback_web_bind() {
  local port="$1"
  RAIJIN_WEB_BIND_HOST=127.0.0.1
  RAIJIN_WEB_BIND_PORT="$port"
  RAIJIN_WEB_BIND_PUBLISH="127.0.0.1:$port:8080"
  RAIJIN_WEB_BIND_PROBE_URL="http://127.0.0.1:$port"
  export RAIJIN_WEB_BIND_HOST RAIJIN_WEB_BIND_PORT RAIJIN_WEB_BIND_PUBLISH RAIJIN_WEB_BIND_PROBE_URL
}
