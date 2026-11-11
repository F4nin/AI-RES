#!/usr/bin/env bash
# Installs sops and age on a Linux amd64 CI runner from pinned releases with SHA-256 verification (THR-017). Local machines use brew.
# sops hash = upstream sops-v3.13.3.checksums.txt; age publishes no checksum file, so its hash is pinned from the first verified download.
set -euo pipefail
SOPS_URL=https://github.com/getsops/sops/releases/download/v3.13.3/sops-v3.13.3.linux.amd64
SOPS_SHA=e5bec3346a873ae91d871550f3e698c1aad962aff462a080e40f25fde17fef6b
AGE_URL=https://github.com/FiloSottile/age/releases/download/v1.3.2/age-v1.3.2-linux-amd64.tar.gz
AGE_SHA=cbe24006683f8eb669266162894b9a522a1af52f2665fbc63a4bb032ed26ac10
BIN="${1:-$HOME/.local/bin}"; mkdir -p "$BIN"; T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
curl -fsSL -o "$T/sops" "$SOPS_URL"; echo "$SOPS_SHA  $T/sops" | sha256sum -c -
curl -fsSL -o "$T/age.tgz" "$AGE_URL"; echo "$AGE_SHA  $T/age.tgz" | sha256sum -c -
tar -xzf "$T/age.tgz" -C "$T"; install -m 0755 "$T/sops" "$BIN/sops"; install -m 0755 "$T/age/age" "$T/age/age-keygen" "$BIN/"
echo "$BIN" >> "${GITHUB_PATH:-/dev/null}"
