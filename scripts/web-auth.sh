#!/usr/bin/env bash
# shellcheck shell=bash

# Load the non-secret web authentication policy.  Keep this separate from
# oci-runtime.json: the latter contains Secret references only, whereas this
# file controls host exposure and session policy.
raijin_load_web_auth() {
  local config_file="${RAIJIN_WEB_AUTH_CONFIG:-/etc/s3-oci-migration/web-auth.env}"
  local key value line
  local mode="disabled"
  local external_https="false"
  local trusted_proxy_cidrs=""
  local idle_minutes="30"
  local absolute_minutes="720"

  if [[ -e "$config_file" ]]; then
    [[ -f "$config_file" && -r "$config_file" ]] || {
      echo "Web authentication configuration is not a readable file: $config_file" >&2
      return 2
    }
    while IFS= read -r line || [[ -n "$line" ]]; do
      [[ -z "$line" || "$line" == \#* ]] && continue
      [[ "$line" == *=* ]] || {
        echo "Invalid web authentication configuration line in $config_file" >&2
        return 2
      }
      key="${line%%=*}"
      value="${line#*=}"
      case "$key" in
        RAIJIN_WEB_AUTH_MODE) mode="$value" ;;
        RAIJIN_WEB_EXTERNAL_HTTPS) external_https="$value" ;;
        RAIJIN_WEB_AUTH_TRUSTED_PROXY_CIDRS) trusted_proxy_cidrs="$value" ;;
        RAIJIN_WEB_AUTH_SESSION_IDLE_MINUTES) idle_minutes="$value" ;;
        RAIJIN_WEB_AUTH_SESSION_ABSOLUTE_MINUTES) absolute_minutes="$value" ;;
        *)
          echo "Unsupported web authentication configuration key in $config_file: $key" >&2
          return 2
          ;;
      esac
    done <"$config_file"
  fi

  export RAIJIN_WEB_AUTH_MODE="$mode"
  export RAIJIN_WEB_EXTERNAL_HTTPS="$external_https"
  export RAIJIN_WEB_AUTH_TRUSTED_PROXY_CIDRS="$trusted_proxy_cidrs"
  export RAIJIN_WEB_AUTH_SESSION_IDLE_MINUTES="$idle_minutes"
  export RAIJIN_WEB_AUTH_SESSION_ABSOLUTE_MINUTES="$absolute_minutes"
}
