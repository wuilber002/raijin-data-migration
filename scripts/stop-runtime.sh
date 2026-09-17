#!/usr/bin/env bash
set -euo pipefail
for container in s3-oci-local-ui-gateway s3-oci-fujin-local-materializer s3-oci-fujin-local s3-oci-fujin-local-dns s3-oci-governance-worker s3-oci-transfer-worker s3-oci-app s3-oci-simulator s3-oci-postgres; do
  podman stop -t 30 --ignore "$container"
  podman rm -f --ignore "$container"
done
