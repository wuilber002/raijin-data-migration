#!/usr/bin/env bash
set -euo pipefail
for container in raijin-governance-worker raijin-raikou-shin raijin-raikou-sei raijin-raikou-ko raijin-raikou-kai raijin-transfer-worker raijin-app raijin-postgres; do
  podman stop -t 30 --ignore "$container"
  podman rm -f --ignore "$container"
done
