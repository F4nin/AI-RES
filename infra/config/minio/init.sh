#!/bin/bash
# One-shot, idempotent bucket creation (names are provisional, DOC-015 §5.3). Credentials are read from Compose secrets into
# mc's config in tmpfs only.
set -euo pipefail
umask 077
export MC_CONFIG_DIR=/tmp/mc
MC_HOST_local="http://$(cat /run/secrets/minio_root_user):$(cat /run/secrets/minio_root_password)@minio:9000"
export MC_HOST_local
for b in ai-res-sources ai-res-artifacts ai-res-worker-results ai-res-exports ai-res-temporary; do
  mc mb --ignore-existing "local/$b"
  mc version enable "local/$b"
done
echo "buckets ready"
