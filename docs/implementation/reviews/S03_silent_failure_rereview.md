# S03 silent-failure RE-review (infra, supply chain, CI)

Method: blind-first (S03_*_REPORT.md and S03_REVIEW_DISPOSITION.md NOT read). Read code, ran `infra` unit tests (72 passed), `tests/runtime` against the live stack (81 passed, 0 skipped, exit 0), `scan_secrets.py` (0 findings), `check_compose.py` (11 services, 0 violations), `verify_digests.py` (10 pins, 0 mismatch), backend `test_serve.py` (2 passed). Mutation probes ran on copies in the scratchpad only. Nothing in the repo was modified except this file.

## Verdict

No open CRITICAL or HIGH. All five HIGH items of the first review (S03_silent_failure_review.md #1-#5) are fixed in code and re-verified. Remaining: 2 MEDIUM (new/residual), several LOW.

## Verification of previous findings

| # | Previous | Status | Evidence |
|---|---|---|---|
| 1 | supply_chain.sh scans nothing | FIXED | supply_chain.sh:10 plain assignment (set -e aborts); :12-16 expected own images + >=9 total; :30 SBOM must have packages. Third-party Trivy failure aborts via pipefail inside `$(...)` assignment (:36). |
| 2 | runtime suite skips | FIXED for CI; local still skips | conftest.py:15-20 `pytest.fail` when AI_RES_REQUIRE_STACK=1; ci.yml:74-77 sets it. Probe: copy with a fake service "ghost" -> skipped (84) without the flag, ERROR with it. See N2. |
| 3 | SCRAM test vacuous | FIXED | test_stack.py:271-280 asserts methods subset of {scram-sha-256, reject}, non-empty, no non-reject `host` rule. |
| 4 | wait_stack returns 0 on nothing | FIXED | wait_stack.py:23-41 expected-set, missing = pending, exited long-running = failed; test_wait_stack.py covers empty/partial/timeout. |
| 5a Dockerfile missing | FIXED | check_compose.py:65-66. |
| 5b COPY --from | FIXED (`RUN --mount=from=` still open, N3) | :76-78. |
| 5c network membership | MOSTLY FIXED | ingress/egress allowlists :170-175. Residual N3. |
| 5d healthcheck/restart | PARTIAL | `disable` rejected, restart exemption limited to ONE_SHOT (:144-148); `test: ["NONE"]` still accepted (N3). |
| 5e env secrets | FIXED for `environment`; `command`/`entrypoint` not scanned (N3). |
| 5f volumes/network_mode | PARTIAL | network_mode any value rejected, bind outside project dir rejected (verified `/var/run`); devices/volumes_from/sysctls unchecked (N3). |
| 5g empty model, 5h profiles | FIXED | :204-205, :213 `--profile '*'`. |
| 6 scan_secrets | MOSTLY FIXED | JSON-quoted keys, non-UTF-8 (decoded with replace), nested SOPS plaintext, whole repo scope, trailing newline: all verified detected in a temp repo. New gap N1. |
| 7 CI scan with empty secrets | FIXED | ci.yml:78-79 runs the scan after `make up` with real values. No assertion that values were loaded (N9). |
| 8-10 egress/image-layer/plain-HTTP tests | FIXED | positive controls at test_stack.py:93-106, canary test :196-205, plain HTTP asserts 400 or close :147. |
| 11 setup-schema `|| true` | FIXED | setup-schema.sh:13-18 tolerates only "already exists". Note: no read-back of resulting schema version (L). |
| 12 vuln exceptions | PARTIAL | header strict, trailing comments stripped; still CVE-global across all images (N8). |
| 13 supply-chain policy | UNCHANGED by design | third-party report-only (ADR-043), `--ignore-unfixed` also for own images (N8). |
| 14 release_manifest fail-open | UNCHANGED | release_manifest.py:49-50 `git()` check=False -> dirty=false / commit null, rc 0 (L: not a CI gate). |
| 15 healthchecks | FIXED/IMPROVED | proxy now `nc -z 127.0.0.1 8443`, minio matches status line only. otel-collector still only "running". |
| 16 temporal env test omission | UNCHANGED (L, N7) |
| 17 host-port test | FIXED | uses HostConfig.PortBindings (test_stack.py:36-43). |
| 18 misc | start.sh empty-broadcast guard added; namespace.sh now distinguishes not-found; verify_digests refuses < 10 pins. |

## Transient `test_internal_ports_not_reachable_on_host[8000]`

Assessment: most likely a foreign host process, not a stack defect; cannot be proven after the fact.
- Test (test_stack.py:47-51) does `connect_ex(("127.0.0.1", 8000))` on the host. It cannot tell a Docker-published port from any local process (dev server, uvicorn, a manual `docker run -p 8000:8000 ai-res/api:dev` smoke test of the new Dockerfile, a lingering Docker Desktop forwarder). The file itself already acknowledges this for 5432.
- Evidence against a stack defect: `docker ps` shows `api` as `8000/tcp` (exposed, not published); `test_only_reverse_proxy_publishes_host_ports` (HostConfig.PortBindings) passes in the same runs; `compose.yaml` has no `ports:` except the proxy; check_compose enforces that. `lsof` now shows only 127.0.0.1:8443 (Docker) and an unrelated host PostgreSQL on 5432; port 8000 is closed.
- Docker event history was too short to identify the opener.
- Consequence: the probe is flaky on any developer machine (8000/8080/9000 are common dev ports) and gives no diagnostic. See N4.

## Findings

### N1. MEDIUM - scan_secrets skips lowercase/hex-looking values (false negative)
infra/scripts/scan_secrets.py:24 (`(?!(?-i:[a-z_][a-z0-9_.]*)...)` identifier exclusion).
Scenario (executed): `api_key = "a1b2c3d4e5f60718293a4b5c6d7e8f90"` -> not detected (the same value starting with a digit IS detected); `secret: abcdefghijklmnopqrstuvwxyz`, `password: correcthorsebattery`, `DB_PASSWORD=correcthorsebatterystaple` -> not detected. About 37% of random lowercase hex tokens (start with a-f) and all lowercase passphrases pass the gate. The "current dev secret value" rule only covers this machine's dev values, not real ones.
Fix: apply the identifier exemption only when the value is a plausible identifier without digits and contains `_` or `.` (or is an allowlisted word list), or require entropy/length >= 20 with digits for exemption; add tests for hex and lowercase passphrases.

### N2. MEDIUM - `make infra-test-runtime` can exit 0 with every test skipped outside CI
Makefile:74-75 does not set AI_RES_REQUIRE_STACK; conftest.py:20 skips locally. The delivery report path (local `make infra-test-runtime`) can therefore show "84 skipped, exit 0" (reproduced with an unreachable service). Only `-rs` output reveals it.
Fix: Makefile target `AI_RES_REQUIRE_STACK=1 uv run ... pytest tests/runtime`; keep skip only behind an explicit opt-out variable.

### N3. LOW - check_compose residual holes (all executed, all return no violation)
check_compose.py:144-148, :150-157, :198-200, :131-139.
- `healthcheck: {test: ["NONE"]}`.
- A new non-internal network (`foo: {}`) and a service joined to it; deleted `data`/`app` network; `check_networks` only inspects names in INTERNAL_NETWORKS.
- `devices`, `volumes_from`, `sysctls`, `RUN --mount=from=<unpinned image>` in Dockerfiles, secrets in `command`/`entrypoint`.
- Expected service set is not asserted (removing a service passes).
Fix: reject NONE; require every network except ingress/egress to be internal; extend deny-list; assert expected services.

### N4. LOW - host-port probe is environment-dependent and undiagnosable
test_stack.py:47-51. See section above. Fix: on failure, also run `docker ps --filter publish=<port>` / `lsof` and report whether the stack publishes it; or drop 8000/8080/9000 host probes, leaving the inspect-based test as the authority.

### N5. LOW - proxy-egress pin test cannot fail
test_stack.py:109-113: `assert out in ("OPEN", "CLOSED")` is always true when `nc` exists. Documented as a pin, but it does not detect a change. Fix: assert the current value (or xfail strict against G-34).

### N6. LOW - image-layer scan blind spots
helpers.py:50-59: zstd layers are not decompressed; `suppress(OSError, EOFError)` and `except tarfile.TarError: pass` hide parse failures. The canary control only proves the gzip path of the local daemon format. Fix: count and assert scanned layer files per image, fail on parse errors.

### N7. LOW - temporal excluded from process-env secret test
test_stack.py:178 omits temporal although config/temporal/start.sh exports `POSTGRES_PWD` into the server environment. Fix: record as an accepted exception in KNOWN_GAPS and pin with `xfail(strict=True)`.

### N8. MEDIUM-to-LOW (policy, documented) - supply-chain gate scope
supply_chain.sh:23-24,34-38; vuln_exceptions.py. Exceptions apply to every image by CVE id only; `--ignore-unfixed` also applies to own images (an unfixed HIGH in `ai-res/api` is neither blocking nor listed); third-party findings are never compared with a baseline. Step name "own images blocking" is accurate; a green run says nothing about third-party risk. Not a hidden failure, but keep tracked in KNOWN_GAPS.

### N9. LOW - secret scan meta-coverage
scan_secrets.py:12,28,80-84: no count of scanned files and no assertion that runtime secret values were loaded (ci.yml:78 relies on it); `docs/implementation/reviews/` is excluded wholesale (real leaks in reports are invisible), plus ALLOW of two files. Fix: print scanned-file count, add `--require-values` in the runtime job.

### N10 (LOW) - small items
- release_manifest.py:49-50 fails open on git errors.
- otel-collector has no health probe; wait_stack and tests accept "running" (a crash-looping container sampled while up passes).
- setup-schema.sh does not read back the schema version; ci.yml hadolint threshold `error` and caddy/minio coverage as before.
- verify_digests SOURCES omit pins in supply_chain.sh/ci.yml.

## Summary table

| ID | Sev | Location |
|---|---|---|
| N1 | M | infra/scripts/scan_secrets.py:24 |
| N2 | M | Makefile:74-75, infra/tests/runtime/conftest.py:20 |
| N3 | L | infra/scripts/check_compose.py:131-157,198-200 |
| N4 | L | infra/tests/runtime/test_stack.py:47-51 |
| N5 | L | infra/tests/runtime/test_stack.py:109-113 |
| N6 | L | infra/tests/runtime/helpers.py:50-59 |
| N7 | L | infra/tests/runtime/test_stack.py:178 |
| N8 | M/L (policy) | infra/scripts/supply_chain.sh:23-38 |
| N9 | L | infra/scripts/scan_secrets.py:12,28,80 |
| N10 | L | misc |

Open HIGH/CRITICAL: none. The runtime evidence above was collected against the stack that was already up; IMPLEMENTATION VERIFIED only for what the executed commands show (no CI run, no supply_chain.sh run, no Trivy/Syft execution in this review).
