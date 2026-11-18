"""Bounded namespace evidence for the separate ADR137 candidate, never approval.

Only a trusted development host may execute the fixed observation command. The
reviewed image's health handler checks file/live/logical SQLite invariants; raw
configuration and credential bytes never leave that running mount namespace.
"""
import hashlib
import json
import re
from dataclasses import dataclass

from ai_res.modules.model_registry.candidate_runner import CandidateRunDenied

INTEGRITY_VERSION = "ai-res-candidate-integrity/0.1"
MARKER_PATH = "/app/data/candidate-integrity.json"
NAMESPACE_FILES = (
    "/poc/start-bifrost.sh", "/etc/bifrost/config.template.json", "/etc/bifrost/pricing.json",
    "/etc/bifrost/model-parameters.json", "/etc/bifrost/mcp-library.json",
    "/run/secrets/bifrost_admin_password", "/run/secrets/bifrost_virtual_key", "/run/secrets/llm_relay_auth",
    "/app/data/config.json", MARKER_PATH,
)

# No interpolated input, credential argv/env, shell expansion from a caller or
# outbound route. The host bounds subprocess lifetime/stdout and checks exit.
NAMESPACE_COMMAND = r'''set -efu
PATH=/usr/bin:/bin
export PATH
printf 'FILES\n'
for item in /poc/start-bifrost.sh /etc/bifrost/config.template.json /etc/bifrost/pricing.json \
  /etc/bifrost/model-parameters.json /etc/bifrost/mcp-library.json /run/secrets/bifrost_admin_password \
  /run/secrets/bifrost_virtual_key /run/secrets/llm_relay_auth /app/data/config.json /app/data/candidate-integrity.json; do
  test -f "$item" && test ! -L "$item"
  size=$(stat -c %s "$item")
  test "$size" -gt 0 && test "$size" -le 1048576
  printf '%s\n' "$item"
  stat -c '%a %s' "$item"
  sha256sum "$item"
done
test "$(stat -c %s /app/data/candidate-integrity.json)" -le 1024
printf 'MARKER\n'
cat /app/data/candidate-integrity.json
printf '\n'
wget -q -O /dev/null -T 3 http://127.0.0.1:8080/health
printf 'HEALTHY\n'
'''


def _deny(condition: bool) -> None:
    if not condition:
        raise CandidateRunDenied("HOST_UNCONFIGURED")


@dataclass(frozen=True, slots=True, repr=False)
class CandidateIntegrityObservation:
    namespace_sha256: str
    boot_nonce: str
    files: tuple[tuple[str, int, str], ...]

    def __post_init__(self) -> None:
        _deny(isinstance(self.namespace_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", self.namespace_sha256) is not None
              and isinstance(self.boot_nonce, str) and re.fullmatch(r"[0-9a-f]{32}", self.boot_nonce) is not None)
        _deny(isinstance(self.files, tuple) and len(self.files) == len(NAMESPACE_FILES))
        for expected, value in zip(NAMESPACE_FILES, self.files, strict=True):
            _deny(isinstance(value, tuple) and len(value) == 3 and value[0] == expected
                  and type(value[1]) is int and 0 <= value[1] <= 0o777 and not value[1] & 0o022
                  and isinstance(value[2], str) and re.fullmatch(r"[0-9a-f]{64}", value[2]) is not None)
        _deny(dict((path, mode) for path, mode, _ in self.files)[MARKER_PATH] == 0o600
              and dict((path, mode) for path, mode, _ in self.files)["/app/data/config.json"] == 0o600)


def namespace_observation(raw: bytes) -> CandidateIntegrityObservation:
    """Strict fixed-output grammar; keep secret-derived digests inside the gate."""
    try:
        _deny(type(raw) is bytes and 0 < len(raw) <= 16_384)
        lines = raw.decode("ascii").splitlines()
        _deny(len(lines) == 3 * len(NAMESPACE_FILES) + 4 and lines[0] == "FILES" and lines[-1] == "HEALTHY"
              and lines[-3] == "MARKER")
        facts = []
        for index, path in enumerate(NAMESPACE_FILES):
            start = index * 3 + 1
            _deny(lines[start] == path)
            stat = re.fullmatch(r"([0-7]{3}) ([0-9]{1,7})", lines[start + 1])
            checksum = re.fullmatch(r"([0-9a-f]{64})  " + re.escape(path), lines[start + 2])
            _deny(stat is not None and checksum is not None)
            assert stat is not None and checksum is not None
            _deny(0 < int(stat[2]) <= 1_048_576)
            facts.append((path, int(stat[1], 8), checksum[1]))

        def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in values:
                _deny(key not in result)
                result[key] = value
            return result

        marker = json.loads(lines[-2], object_pairs_hook=pairs)
        _deny(isinstance(marker, dict) and set(marker) == {"version", "bootNonce", "configSha256"}
              and marker["version"] == INTEGRITY_VERSION and isinstance(marker["bootNonce"], str)
              and re.fullmatch(r"[0-9a-f]{32}", marker["bootNonce"]) is not None
              and marker["configSha256"] == dict((path, sha) for path, _, sha in facts)["/app/data/config.json"])
        _deny(hashlib.sha256(lines[-2].encode()).hexdigest() == facts[-1][2])
        normalized = json.dumps({"marker": marker, "files": facts}, sort_keys=True, separators=(",", ":")).encode()
        return CandidateIntegrityObservation(hashlib.sha256(b"candidate-namespace/0.1\0" + normalized).hexdigest(), marker["bootNonce"], tuple(facts))
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise CandidateRunDenied("HOST_UNCONFIGURED") from None
