#!/usr/bin/env bash
set -euo pipefail

# Sparse deterministic zero-filled payloads consume almost no local disk while
# preserving the full logical size sent to S3.
root_dir="${1:?usage: populate.sh <local-directory>}"
mkdir -p "$root_dir"

create_series() {
  local prefix="$1" count="$2" bytes="$3" group="$4"
  local index path
  mkdir -p "$root_dir/$prefix/$group"
  for ((index=1; index<=count; index++)); do
    path="$root_dir/$prefix/$group/$(printf '%06d' "$index").bin"
    truncate -s "$bytes" "$path"
  done
}

# Smoke: ~2.06 GiB / 2,000 objects.
create_series Smoke_test 1800 $((64 * 1024)) small
create_series Smoke_test 180 $((4 * 1024 * 1024)) medium
create_series Smoke_test 20 $((64 * 1024 * 1024)) large

# Operational: ~30.3 GiB / 19,060 objects.
create_series Operational_test 16000 $((64 * 1024)) small
create_series Operational_test 3000 $((4 * 1024 * 1024)) medium
create_series Operational_test 60 $((300 * 1024 * 1024)) large

# Resilience: two independent 4 GiB multipart candidates.
create_series Resilience_test 2 $((4 * 1024 * 1024 * 1024)) multipart

printf 'Created %s files under %s\n' "$(find "$root_dir" -type f | wc -l | tr -d ' ')" "$root_dir"
