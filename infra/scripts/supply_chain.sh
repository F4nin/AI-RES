#!/usr/bin/env bash
# SBOM (Syft) + vulnerability scan (Trivy) for the Compose stack or the separately built G02 native image (DOC-015 §14.1-2, THR-017). Tools run from digest-pinned
# images and read `docker save` archives, so no docker.sock is mounted anywhere. Exit 1 on unexcepted HIGH/CRITICAL findings.
# Exceptions live in infra/security/vulnerability-exceptions.yaml (CVE, component, rationale, compensating controls, owner, expiry).
set -euo pipefail
cd "$(dirname "$0")/.."
SYFT=anchore/syft:v1.18.1@sha256:b8c170b8e51bfc4779ec3ef4399942c57290f5ce76a9c3af564c9d00d4946a6b
TRIVY=aquasec/trivy:0.58.1@sha256:ab70a02200597efa04748f210f793936eb647cbcdb0ea69cc30b226d6f5a22c7
case "$#:${1:-}" in
  1:--g02-native-only)
    IMAGES=(ai-res/temporal-native:g02-local)
    ;;
  0:)
    # Capture first so a Compose failure cannot yield a vacuous scan.
    COMPOSE_INPUTS=(-p ai-res -f compose.yaml)
    if [ "${AI_RES_SCAN_LLM_POC:-0}" = "1" ]; then
      COMPOSE_INPUTS+=(-f compose.llm-poc.yaml --profile llm-poc)
    fi
    IMAGE_LIST="$(docker compose "${COMPOSE_INPUTS[@]}" config --images)"
    IMAGES=()
    while IFS= read -r line; do [ -n "$line" ] && IMAGES+=("$line"); done < <(printf '%s\n' "$IMAGE_LIST" | sort -u)
    EXPECTED_OWN=(ai-res/api:dev ai-res/caddy:2.11.9 ai-res/minio:RELEASE.2025-10-15T17-29-55Z ai-res/minio-mc:RELEASE.2025-08-13T08-35-41Z)
    for want in "${EXPECTED_OWN[@]}"; do
      printf '%s\n' "${IMAGES[@]}" | grep -Fqx -- "$want" || { echo "FATAL: expected own image $want is not in the compose model" >&2; exit 2; }
    done
    [ "${#IMAGES[@]}" -ge 9 ] || { echo "FATAL: only ${#IMAGES[@]} images found, expected >= 9" >&2; exit 2; }
    ;;
  *)
    echo 'usage: supply_chain.sh [--g02-native-only]' >&2
    exit 2
    ;;
esac
OUT=releases/sbom; REPORTS=releases/scan; WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
mkdir -p "$OUT" "$REPORTS" .cache/trivy
if [ "${1:-}" = "--g02-native-only" ]; then
  : > "$WORK/trivyignore"
else
  python3 scripts/vuln_exceptions.py ids > "$WORK/trivyignore"      # fails on expired/incomplete exceptions
fi
# Policy (ADR-043): own images (ai-res/*) are a blocking gate; third-party images are pinned inputs whose findings are reported in
# releases/scan/ and tracked in KNOWN_GAPS.md until upstream ships fixes (we cannot patch them).
status=0
trivy() { docker run --rm -v "$WORK:/in:ro" -v "$PWD/.cache/trivy:/root/.cache" "$TRIVY" image --input "/in/$1.tar" --severity HIGH,CRITICAL --ignore-unfixed \
  --ignorefile /in/trivyignore --scanners vuln --quiet "${@:2}"; }
for img in "${IMAGES[@]}"; do
  name="$(echo "${img%%@*}" | tr '/:' '__')"
  docker save -o "$WORK/$name.tar" "$img"
  docker run --rm -v "$WORK:/in:ro" "$SYFT" "docker-archive:/in/$name.tar" -o "spdx-json" -q > "$OUT/$name.spdx.json"
  # An empty/failed SBOM must not pass silently: it must be valid JSON that lists packages.
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d.get("packages") else 1)' "$OUT/$name.spdx.json" \
    || { echo "FATAL: SBOM for $img is empty or invalid" >&2; exit 2; }
  if [[ "$img" == ai-res/* ]]; then
    echo "== OWN   $img (blocking)"
    if [ "${1:-}" = "--g02-native-only" ]; then
      report="$REPORTS/$name.json"
      trivy "$name" --exit-code 1 --format json --list-all-pkgs > "$report" || status=1
      python3 - "$report" <<'PY'
import json
import sys

with open(sys.argv[1]) as report:
    results = json.load(report).get("Results") or []
native = [result for result in results if result.get("Target") == "temporal-native" and result.get("Type") == "gobinary"]
if len(native) != 1:
    raise SystemExit("FATAL: Trivy did not identify the native Temporal Go binary")
packages = {package["Name"] for package in native[0].get("Packages") or []}
if not {"stdlib", "google.golang.org/grpc", "golang.org/x/net"} <= packages:
    raise SystemExit("FATAL: Trivy missed the linked Go inventory")
findings = sum(len(result.get("Vulnerabilities") or []) for result in results)
print(f"Native Temporal: {len(packages)} linked packages, {findings} HIGH/CRITICAL fixable finding(s), {sys.argv[1]}")
if findings:
    raise SystemExit(1)
PY
    else
      trivy "$name" --exit-code 1 || status=1
    fi
  else
    # One scan per image (CI-01): the count is read back from the very report that is written, so an empty/invalid report still fails (set -e).
    trivy "$name" --format json > "$REPORTS/$name.json"
    n="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(sum(len(r.get("Vulnerabilities") or []) for r in d.get("Results", [])))' "$REPORTS/$name.json")"
    echo "== THIRD $img: $n HIGH/CRITICAL fixable finding(s) (report-only, $REPORTS/$name.json)"
  fi
done
exit $status
