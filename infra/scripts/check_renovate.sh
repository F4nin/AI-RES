#!/usr/bin/env bash
# DEP-01: the validator and behavioral checks share a digest-pinned, offline tool.
# Mount ONLY curated configuration inputs, never the checkout, .git, tokens or secrets.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RENOVATE_IMAGE=ghcr.io/renovatebot/renovate:44.249.0@sha256:595b3b1bd60514d1943d84a60c0ec57bbb2663ce1b5a981dccfe206283ca386c
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
inputs=(renovate.json infra/images/minio/Dockerfile infra/images/caddy/Dockerfile
  infra/compose.yaml infra/scripts/supply_chain.sh infra/scripts/check_renovate.sh
  infra/tests/runtime/test_stack.py .github/workflows/ci.yml .github/workflows/contracts.yml
  infra/tests/renovate/check.mjs)
for file in "${inputs[@]}"; do
  mkdir -p "$work/$(dirname "$file")"
  cp "$ROOT/$file" "$work/$file"
done
chmod -R a+rX "$work"
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  --tmpfs /tmp:rw,nosuid,nodev,size=256m \
  --mount "type=bind,source=$work,target=/work,readonly" \
  --entrypoint /bin/bash "$RENOVATE_IMAGE" -c \
  '/usr/local/renovate/node /usr/local/renovate/dist/config-validator.js --no-global --strict /work/renovate.json && /usr/local/renovate/node /work/infra/tests/renovate/check.mjs'
