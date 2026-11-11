# S03 silent-failure review (infra, supply chain, CI)

Scope: infra/scripts/**, infra/config/**, infra/images/**/Dockerfile, backend/Dockerfile, infra/tests/** (static and runtime), Makefile, .github/workflows/*.yml.
Method: static reading plus local Python reproductions of the policy checkers (no docker run). Items marked "(not run)" are reasoning only and have not been executed against a stack: IMPLEMENTATION NOT VERIFIED for those.
Severity: H = a gate reports green while the property is unproven; M = narrower or conditional; L = hygiene.

## Summary

| # | Sev | Location | Silent failure |
|---|-----|----------|----------------|
| 1 | H | infra/scripts/supply_chain.sh:10 | `docker compose config` failure inside `< <(...)` is invisible, so zero images are scanned and the script exits 0 |
| 2 | H | infra/tests/runtime/conftest.py:12-16 | Runtime suite skips, and exits 0, on any compose/ps problem or one missing service; CI step "runtime evidence" goes green |
| 3 | H | infra/tests/runtime/test_stack.py:251-254 | SCRAM-only test filters `trust` rows out of its own query, then asserts there are none |
| 4 | H | infra/scripts/wait_stack.py:27,34 | Empty or partial stack returns rc 0 at deadline; `len(st) >= 11` is a magic number |
| 5 | H | infra/scripts/check_compose.py (several rules) | Checker passes models that violate the stated policy (details below) |
| 6 | M | infra/scripts/scan_secrets.py | Misses JSON-quoted keys, letter-only secrets, root files, non-UTF-8 files, partial-plaintext SOPS files |
| 7 | M | .github/workflows/ci.yml:33-36 | Secret scan runs against empty placeholder secrets, so the "current dev secret value" rule is inert in CI |
| 8 | M | infra/tests/runtime/test_stack.py:98-101 | Egress test from data services has no positive control and ignores rc/stderr |
| 9 | M | infra/tests/runtime/test_stack.py:180-203 | Image-layer secret scan skips gzip layers and has no positive control |
| 10 | M | infra/tests/runtime/test_stack.py:130-134 | "Plain HTTP not served" cannot fail, because the app answers 404, not 200 |
| 11 | M | infra/config/temporal/setup-schema.sh:10-11 | `\|\| true` on create-database and setup-schema hides the root cause and any partial init |
| 12 | M | infra/scripts/vuln_exceptions.py + supply_chain.sh | Exceptions are CVE-global, not scoped to a component or image; parser accepts a wrong header and trailing comments |
| 13 | M | infra/scripts/supply_chain.sh:22-27 | Third-party scan is report-only with no baseline or regression gate; `--ignore-unfixed` hides unfixed findings in own images |
| 14 | M | infra/scripts/release_manifest.py:49-61 | git failure yields `dirty=false`, `commit=null`, rc 0; SBOM absence is silent |
| 15 | M | infra/compose.yaml:50-56 (reverse-proxy healthcheck) | `caddy validate` proves only that the Caddyfile parses |
| 16 | L | infra/tests/runtime/test_stack.py:166 | temporal is excluded from the process-env secret test, hiding the deliberate `POSTGRES_PWD` env exposure |
| 17 | L | infra/tests/runtime/test_stack.py:37-44 | Host-port test inspects `NetworkSettings.Ports`, which is empty for exited one-shot containers |
| 18 | L | misc scripts | verify_digests with 0 pins, start.sh empty broadcast address, namespace.sh describe error swallowed, minio healthcheck grep, hadolint coverage, empty secrets |

---

## 1. supply_chain.sh scans nothing and exits 0 if `docker compose config` fails (H)

File: infra/scripts/supply_chain.sh:10
```
IMAGES=(); while IFS= read -r line; do IMAGES+=("$line"); done < <(docker compose -p ai-res -f compose.yaml config --images | sort -u)
```
How it fails: `set -e` and `pipefail` do not apply to the exit status of a process substitution. If `docker compose` fails (missing secret files, YAML error, docker unavailable), `IMAGES` is empty. The `for` loop never runs, `status` stays 0, and the script ends with `exit 0`. `python3 vuln_exceptions.py ids` still runs and succeeds. CI step "SBOM + vulnerability scan (own images blocking)" is green with no SBOM and no scan.
Demonstration: run it where `infra/secrets/runtime/*` is absent (as in the infra-static job). Compose errors on the missing secret files, stderr shows the error, and the script exits 0 with no `== OWN` lines. Equivalent: `docker compose` not on PATH.
Fix: capture first, then validate.
```
mapfile -t IMAGES < <(...)   # no: same problem
out="$(docker compose -p ai-res -f compose.yaml config --images)"   # set -e aborts on failure
mapfile -t IMAGES < <(printf '%s\n' "$out" | sort -u)
(( ${#IMAGES[@]} >= 1 )) || { echo "no images resolved" >&2; exit 1; }
```
Also assert that the set contains every expected `ai-res/*` image (api, caddy, minio, minio-mc) and exactly one SBOM per image; fail if any `$OUT/$name.spdx.json` is empty (`[[ -s ... ]]`).

## 2. Runtime suite skips instead of failing (H)

File: infra/tests/runtime/conftest.py:10-16, infra/tests/runtime/helpers.py:14-19, Makefile `infra-test-runtime`, ci.yml:63-64.
How it fails: autouse session fixture `stack_up` calls `compose("ps", ...)` with `check=False` and parses stdout only. Cases that all end in `pytest.skip` for the whole session, so pytest exits 0:
- docker/compose error: stdout is empty, `running` is empty.
- compose project name or file mismatch.
- one container crash-looping (state "restarting"). The otel-collector has no healthcheck, so this is the likeliest.
`pytest -rs` prints SKIPPED, but CI does not read it. The skip message even says "skip is NOT evidence", yet nothing enforces that.
Demonstration: `docker compose ... stop otel-collector && make infra-test-runtime` gives about 100 skipped, exit 0. Or `PATH` without docker gives FileNotFoundError, which is an error, but a failing `ps` yields skip.
Fix: in CI (`CI=true` or `AI_RES_REQUIRE_STACK=1`) call `pytest.fail` instead of `skip`; check `res.returncode`; also fail the Makefile target when the junit/summary shows `skipped > 0` (`pytest ... -p no:cacheprovider --junitxml` plus a check, or `-W error::pytest.PytestUnraisableExceptionWarning` is not enough). Do not let one missing service skip all tests.

## 3. `test_password_auth_is_scram_only` is vacuous (H)

File: infra/tests/runtime/test_stack.py:251-254
```
select distinct auth_method from pg_hba_file_rules where auth_method<>'trust' union all select current_setting('password_encryption')
...
assert "trust" not in r.stdout.lower()
assert "scram-sha-256" in r.stdout
```
How it fails: rows with `trust` are removed by the query, so `"trust" not in stdout` is always true. The second assertion is satisfied by `current_setting('password_encryption')` alone. No hba rule is actually examined.
Demonstration: put `host all all all trust` into pg_hba.conf (e.g. edit infra/config/postgres/entrypoint.sh:11 to `trust`). The test still passes.
Fix: `select auth_method from pg_hba_file_rules where auth_method not in ('scram-sha-256')` and assert the output is empty (also assert `select count(*) from pg_hba_file_rules` > 0 as a positive control), and also check `error is null`.

## 4. wait_stack.py returns success on nothing (H)

File: infra/scripts/wait_stack.py:24-34
How it fails: `pending` and `failed` only contain services that appear in `ps`. If `st == {}`, or contains only a subset that is healthy, the loop runs to the deadline and `return 1 if failed or pending else 0` returns 0. The `len(st) >= 11` guard only decides when to break early; it is not part of the return condition. A magic number replaces an expected-service set.
Demonstration (executed): with `state()` stubbed to `{}` then `{"postgres": ("running","healthy",0)}`, `main(timeout=0)` returns 0 in both cases.
Also: services in `ONE_SHOT` that are absent from `ps -a` (never created) count as neither failed nor pending; a long-running service in state `exited`/`dead` is only reported after the full 300 s.
Fix: define `EXPECTED = LONG_RUNNING | ONE_SHOT`; `missing = EXPECTED - st.keys()` counts as pending/failed; return non-zero when `missing` at deadline; treat `exited`/`dead`/`restarting` of a long-running service as immediate failure. Also share the service lists with tests/runtime/helpers.py (both define them separately today; they have drifted-by-copy risk).

## 5. check_compose.py: policy rules that pass violating models (H)

All demonstrated by running `check_model` on a synthetic model that returned `[]`.

a. Missing or unreadable Dockerfile passes (infra/scripts/check_compose.py:168-176). `gather_dockerfiles` returns `[]` when the file is absent. `name in dockerfiles` is then true, so "Dockerfile not provided" is never raised, and `check_dockerfile` iterates no lines. Input: `{"build": {"context": "."}}` with `dockerfiles={"b": []}` gives no violation. Same result for `dockerfile_inline` builds and a wrong `dockerfile:` path. Fix: treat an empty or missing Dockerfile as a violation; require at least one `FROM`.

b. `COPY --from=<image>` and `RUN --mount=from=<image>` bypass pinning (check_compose.py:47-59). Only `FROM` lines are parsed. `COPY --from=evil/tool:latest /x /x` yields no violation. Fix: scan `--from=` values that are not earlier stage names.

c. Network membership rules are incomplete (check_compose.py:120-134, 148-150). A non-proxy service may join `ingress` or `egress` (both non-internal, have a gateway and egress) together with `data`: `postgres: networks {data, ingress}` and `minio: {data, egress}` return no violation. The runtime test `test_egress_denied_from_data_services` is the only backstop (see 8). Also, `check_networks` only inspects networks that exist, so a renamed or removed `data` network and any additional non-internal network are not flagged. Fix: allowlist who may join `ingress` (only reverse-proxy) and `egress` (no member until S15/S16/S28); require every non-allowlisted network to be `internal: true`; require the internal networks to exist.

d. Healthcheck exemptions (check_compose.py:111): `healthcheck: {disable: true}` or `test: ["NONE"]` satisfies `svc.get("healthcheck")`; `restart: "no"` exempts any service, not only one-shot jobs (executed: services `api` with disabled healthcheck and `x` with restart no both pass). Fix: reject `disable`/`NONE`; restrict the restart exemption to an explicit ONE_SHOT allowlist (the same set as wait_stack).

e. Secrets-in-environment rule (check_compose.py:114-118): `POSTGRES_PASSWORD_FILE: hunter2hunter2` passes (any `_FILE` key is accepted without checking the value starts with `/run/secrets/`); names that do not match the regex (`AUTH: abc123`) pass; `command`/`entrypoint` arguments are not scanned. Fix: require `_FILE` values under `/run/secrets/`; also scan `command`, `entrypoint`.

f. Volumes/namespaces: only a path ending in `docker.sock` is rejected. `/var/run:/var/run` and `/:/host` pass; `network_mode: container:x` / `service:x` pass (only the literal `host` is rejected); `devices`, `sysctls`, `volumes_from`, `extra_hosts` unchecked. Fix: deny bind sources of `/`, `/var/run`, `/run`, `/proc`, `/sys`, `/etc`, and docker-socket parents; reject any `network_mode` other than unset.

g. Empty model passes (executed): `check_model({"services": {}, "networks": {}}, {})` returns `[]` and `main` prints "0 services checked, 0 violation(s)" rc 0. Fix: fail when no services, or when the expected service names are missing.

h. Profiles: the Makefile comment says "every profile combination", but neither Makefile nor `load_model` passes `--profile '*'`. Today compose.yaml has no `profiles:` (checked), so nothing is hidden yet; any future service with `profiles:` is silently absent from the rendered model and from check_compose and release_manifest. Fix: add `--profile '*'` in `load_model`.

i. Test gaps (infra/tests/test_check_compose.py): no tests for the cases above; `load_model`/`main` exit-code plumbing and the real compose files are not tested in pytest (only `make infra-check`); `has(v, "tag")` also matches the "latest ... tag" message, so `test_missing_tag_rejected` could pass for the wrong reason; fragments like "data"/"app"/"admin" are generic. Fix: assert the exact violation text or code and assert `len(v) == 1`.

## 6. scan_secrets.py false negatives (M)

Executed against temporary git repos (all returned `[]`):
- JSON/quoted key: `{"db_password": "Sup3rS3cretValue12345"}`. The regex `[\w-]*password[\w-]*\s*[:=]` cannot cross the closing quote of the key. (YAML `password: "Sup3r..."` is detected.) Python dict literals and quoted TOML/JSON keys are the same.
- Letter-only secret: `DB_PASSWORD=correcthorsebatterystaple`. The lookahead `(?=[A-Za-z/+_=.-]*\d)` requires a digit; values with `!@#%^&*` or fewer than 16 chars are also ignored.
- Root-level files: `.env`, `renovate.json`, etc. with a secret. `SCOPE` (scan_secrets.py:22-24) only includes listed prefixes, so `docs/architecture/**`, root dotfiles and anything new are never scanned. An untracked, unignored root `.env` is exactly the case this scan exists for.
- Non-UTF-8 file containing a private key block: `except (UnicodeDecodeError, OSError): continue` (scan_secrets.py:45-48) skips it silently (executed with bytes `-----BEGIN RSA PRIVATE KEY-----\n\xe9\xff` giving `[]`). Fix: read bytes and decode with `errors="replace"`; report undecodable files as findings or at least print a count of skipped files.
- Dev-secret-value rule uses `p.read_text()` unstripped (scan_secrets.py:35). A value file saved with a trailing newline will not match a file where the value is followed by a space (executed: `[]`). Fix: `.strip()`.
- SOPS check (scan_secrets.py:54-64): `_values_only` inspects only top-level `key: value` lines before `\nsops:`. A file with nested plaintext plus one `ENC[` value passes (executed: `db:\n  password: plainvalue\nk: ENC[AES256_GCM,data:a]\nsops:\n  age: []` returns `[]`). Fix: parse the YAML (PyYAML is not a dependency; use `sops --decrypt`-free structural check, or require every leaf string to start with `ENC[`).
- `ALLOW` exempts two test files wholesale; any real secret added there is invisible.
- Also zero scanned files returns rc 0: a wrong ROOT or an empty `git ls-files` yields "0 finding(s)". Fix: print and assert the number of scanned files (> 0).

## 7. CI runs the secret scan with empty secrets (M)

File: .github/workflows/ci.yml:33-42
The `infra-static` job creates empty placeholder files (`touch`) under `infra/secrets/runtime`. `runtime_values` skips files smaller than 12 bytes, so the "contains a current dev secret value" rule scans for nothing. The `infra-runtime` job (where real values exist) never runs `scan_secrets.py`. Unit tests cover the rule with a synthetic repo, but the repository-level gate does not exercise it.
Fix: run `scan_secrets.py` in `infra-runtime` after `make up` (secrets exist) and fail if no secret values were loaded there (`assert values` when `--require-values`).

## 8. Egress from data services: no positive control, rc and stderr ignored (M)

File: infra/tests/runtime/test_stack.py:98-101
```
out = exec_in(service, "bash", "-c", "exec 3<>/dev/tcp/1.1.1.1/443 && echo CONNECTED || echo FAILED").stdout
assert "CONNECTED" not in out
```
How it fails: asserts only the absence of a token in stdout. If `bash` is not present in the image (compose runs `/bin/sh` for the temporal server and its start.sh, which suggests the image may not ship bash; not verified), `exec_in` returns rc 127 with empty stdout and the test passes. Also a failed `docker exec` (container restarting) passes.
Demonstration: change `bash` to `nonexistent`; the test still passes.
Fix: require `"FAILED" in out` (and rc == 0), and add a positive control reaching `postgres:5432` through the same mechanism, per service. For images without bash use a different probe.

## 9. Image-layer secret scan can miss gzip layers and has no positive control (M)

File: infra/tests/runtime/test_stack.py:180-203
How it fails: `if data[:2] != b"\x1f\x8b" and m.size > 512:` only opens uncompressed layer tars. `docker save` from the containerd image store (Docker Desktop default, which is the developer platform here) produces an OCI layout whose layer blobs are gzip; they are searched only as raw compressed bytes, where a plaintext needle never matches. `except tarfile.TarError: pass` swallows other failures. No test plants a known string to prove the scan can find one.
Fix: open gzip blobs (`tarfile.open(fileobj=..., mode="r:*")`), count scanned files/layers and assert > 0, and add a positive control (build or tag a throw-away image containing a marker, or check that a known file from the base image, e.g. `etc/os-release`, was seen).

## 10. "Plain HTTP not served" cannot fail (M)

File: infra/tests/runtime/test_stack.py:130-134
`assert not data.startswith(b"HTTP/1.1 200")`. The proxy answers 404 for `/` (the previous test asserts exactly that), so a plaintext listener would return `HTTP/1.1 404` and pass. In practice the HTTPS test would then fail with a TLS error, so this is partly compensated, but the test itself carries no signal.
Fix: assert that the first line is not an application response: either connection closed/TLS alert, or `HTTP/1.x 400` from the TLS server, plus a positive control that the same socket with TLS succeeds.

## 11. setup-schema.sh `|| true` (M)

File: infra/config/temporal/setup-schema.sh:10-11
```
$tool create-database || true
$tool setup-schema -v 0.0 || true   # no-op when schema_version already exists
```
How it fails: masks every error, not only "already exists": wrong password, unreachable host, wrong plugin or flag, permission denied. `create-database` is redundant (provision.sh creates both databases), so it can only hide problems. If `setup-schema` fails for a real reason, the later `update-schema` fails with an unrelated message (loud, but root cause lost); a half-created version table (crash mid-setup) may make `update-schema` behave oddly. The final `echo "temporal schema is current"` is printed without checking the version. The idempotency runtime test cannot detect any of this because the rerun also succeeds through `|| true`.
Demonstration (not run): set `-u wrongrole`; the first two commands print errors and are ignored; if the version table already exists, `update-schema` also errors, but if run on an up-to-date DB with working credentials in only the later call, no difference is visible in the job result.
Fix: remove `create-database`; run `setup-schema` and tolerate only the documented "already exists" outcome (capture output, match the exact message, otherwise print and `exit 1`); after `update-schema` read back and assert the version equals the newest directory under `$SCHEMA_ROOT/$kind/versioned`. Add a runtime test that checks the schema version for both databases (psql `select max(curr_version) from schema_version`).

## 12. Vulnerability exceptions: scope and parser (M)

Files: infra/scripts/vuln_exceptions.py:13-25, infra/scripts/supply_chain.sh:14,18-24
- Exceptions are written to one Trivy ignorefile used for every image, own (blocking) and third-party. `component` is free text and is not enforced. An exception for the MinIO prometheus dependency also silences the same CVE in `ai-res/api` or Caddy. Fix: use per-image ignorefiles (Trivy `.trivyignore.yaml` supports `paths`/`purls`) or add an `images:` field and filter.
- The parser skips line 1 without checking it is `exceptions:` (executed: `exceptionz:` header accepted), accepts unknown keys, duplicate keys overwrite silently, and a trailing `# comment` makes `cve` equal `CVE-1  # x` (executed), which Trivy then reads as a different ID, so the exception is silently ineffective or the comment becomes part of an ID. Unknown mode arguments (`vuln_exceptions.py idz`) validate and print nothing, rc 0. Fix: use `tomllib`/JSON, or require header equality, validate `cve` with `^CVE-\d{4}-\d{4,}$`, and reject unknown modes and keys.
- Expiry is compared with the machine's local `date.today()`; use UTC.
- Test gaps (infra/tests/test_vuln_exceptions.py): no test for the real file, the header, or `main()` exit codes.

## 13. Supply-chain gate policy (M)

File: infra/scripts/supply_chain.sh:19-28
- Third-party images: findings are printed as a count and written to `releases/scan/*.json`, nothing compares them with a committed baseline, so a new CRITICAL in a pinned third-party image never fails CI (ADR-040 "report-only"; documented, but the step is named "own images blocking" and a green result says nothing about third-party risk). Fix: fail when the finding set is not a subset of the committed baseline (`releases/scan/*.json`), or when a CRITICAL appears.
- `--ignore-unfixed` applies to own images too: an unfixed HIGH/CRITICAL in `ai-res/api` (python base) is neither blocking nor listed. Fix: report unfixed own-image findings as non-blocking output at least.
- `trivy ... || status=1` correctly fails on Trivy errors too (exit 1), but the log cannot tell a finding from a DB-download failure. Fix: use `--exit-code 1` with a distinct error code (`--exit-on-eol`, or check the report file exists and parses).
- Trivy is run twice per third-party image (count and report); the two runs can disagree if the DB updates in between. Fix: scan once to JSON, derive the count.

## 14. release_manifest.py fails open (M)

File: infra/scripts/release_manifest.py:49-61
- `git()` uses `check=False` and returns `""` on error. A failing `git rev-parse` gives `commit=None` and `release_id="dev-unknown"`; a failing `git status --porcelain` gives `dirty=False`. The manifest then claims "clean tree" when git failed. rc 0.
- SBOM missing gives `sbom_sha256: null` silently (the schema allows null); `origin` is "third-party" only if a digest exists, so an unpinned third-party image is recorded as `built`.
- Tests (infra/tests/test_release_manifest.py) only call `build()`; the "matches schema" test checks `required` and property names but never validates types or values (no `jsonschema` validation).
Fix: `check=True` on git (or non-zero exit when the tree state is unknown), `--require-sbom` option used by release flows, run `check_compose` rules before writing, and validate the produced JSON against the schema in a test.

## 15. Health checks that do not prove readiness (M/L)

- reverse-proxy: `caddy validate --config /etc/caddy/Caddyfile` (infra/compose.yaml:50-54) only parses the config. It stays healthy if Caddy is hung or its listener is gone. The runtime tests partially back it (HTTPS GET), but wait_stack and `depends_on` rely on it. Fix: probe the listener, e.g. `caddy`-image `wget --no-check-certificate -q --spider https://127.0.0.1:8443/` accepting any HTTP status.
- api: any HTTP answer, including 500/502, is healthy (compose.yaml api healthcheck). Documented as liveness-only for S02; the test comment says so. Acceptable for now but it means `make up` cannot detect an app that answers 500 for everything.
- minio: `grep -q ' 200 '` on the whole response also matches any later line or body containing ` 200 `. Fix: `head -n1 | grep -q 'HTTP/1.[01] 200'`.
- otel-collector: no healthcheck; wait_stack asserts only `running`, and the runtime health test excludes it, so a collector with a bad config that restarts quickly can appear running at the sample moment. Fix: enable the collector `health_check` extension and probe it externally (planned S13), or assert RestartCount == 0 in a test.

## 16. Process-env secret test excludes temporal (L)

File: infra/tests/runtime/test_stack.py:165
The parametrization is `["api", "postgres", "minio", "reverse-proxy"]`. infra/config/temporal/start.sh:6-7 deliberately exports `POSTGRES_PWD` (the DB password) into the temporal-server environment, readable from `/proc/<pid>/environ`; temporal-schema exports `SQL_PASSWORD`. The test list silently omits the one case that would fail. Fix: record this as an explicit accepted exception in the decision log with a negative test (`xfail(strict=True)` with reason) rather than leaving it out.

## 17. Host-port test is empty for stopped containers (L)

File: infra/tests/runtime/test_stack.py:37-44
`NetworkSettings.Ports` is `{}`/null for exited containers, so for the four one-shot jobs "not published" holds trivially. Fix: also assert `HostConfig.PortBindings` is empty/None for non-proxy services.

## 18. Smaller items (L)

- infra/scripts/verify_digests.py:21-29: if `SOURCES` is empty or contains no pins (path moved, glob typo) the output is "0 pinned images, 0 mismatch(es)" and rc 0. Digest pins in supply_chain.sh (syft, trivy) and in ci.yml (hadolint, actionlint) are outside `SOURCES` and never re-verified; a typo fails loudly only at pull time. Fix: fail when pins < expected minimum; add those files.
- infra/config/temporal/start.sh:10: `TEMPORAL_BROADCAST_ADDRESS="$(getent hosts ... | awk '{print $1; exit}')"` can be empty with rc 0 (empty output from awk). Add `[ -n "$TEMPORAL_BROADCAST_ADDRESS" ] || exit 1`. The shebang is bash but compose runs it with `/bin/sh`, so `pipefail` support depends on the image's sh (works today per runtime evidence); keep shebang and invocation consistent.
- infra/config/temporal/namespace.sh:5: `describe ... >/dev/null 2>&1` treats any failure (server down, TLS, permission) as "does not exist" and hides the real stderr; an existing namespace with a different retention is reported as "exists". Fix: capture stderr, distinguish NotFound, and compare retention.
- infra/config/postgres/provision.sh:13-14: the backtick `cat` of a secret inside psql: a read failure is not guaranteed to stop under `ON_ERROR_STOP` (psql behaviour not verified here); an empty value would produce `ALTER ROLE ... PASSWORD ''` (password cleared; PostgreSQL treats it as no password), surfacing only later as a login failure in temporal-schema. Line 8 `printf ... "$(cat ...)"`: a failing `cat` inside an argument substitution is not caught by `set -e`. Also `CREATE DATABASE ... WHERE NOT EXISTS` never repairs owner drift on an existing database. Fix: `[ -s file ] || exit 1` for every secret at the top of each script; same guard in entrypoint.sh, start.sh, minio/init.sh (empty or truncated secret files are accepted everywhere; init.sh:7 assigns two `$(cat ...)` in one string and only the last substitution's status can trip `set -e`).
- infra/config/postgres/entrypoint.sh:8-12: `[ ! -s PG_VERSION ]` treats a data directory as initialised even if the process died between `initdb` and the `pg_hba.conf` append; later starts then lack the all-address rule (fails loudly in provision, not silently, but the root cause is hidden). Fix: write the hba rule via `initdb`'s auth flags only, or append idempotently on every start (`grep -qxF`).
- .github/workflows/ci.yml:51 (hadolint): caddy Dockerfile is not linted, minio only at `--failure-threshold error`. Default `run:` shell is `bash -e` without `pipefail`; currently no gating pipeline depends on it, but the "stack logs on failure" pipeline (`logs | sed`) would hide a failing `logs`. No `continue-on-error` or unreachable `if:` conditions were found in contracts.yml/ci.yml; `make down` runs under `if: always()` as intended. The `infra-runtime` job `needs: [backend, infra-static]`, so it is skipped if either fails (intended).
- Makefile `up`: `$(COMPOSE) up -d --build` then wait_stack; with finding 4 the second step cannot prove completeness. `infra-check` chains with `&&` correctly (no `;` masking); `contracts-baseline` chains correctly.
- infra/scripts/install_tools.sh: `set -euo pipefail` and `sha256sum -c -` gate both downloads correctly. Note that the age hash is trust-on-first-use (stated in the file); `curl` has no `--proto =https`/retry.
- infra/scripts/secrets_dev.py: `clean` uses `rmtree(ignore_errors=True)` and prints "runtime secrets removed" even if removal failed (root-owned files from a container); `write_runtime` deletes unknown files in the runtime dir with `unlink()`. `decrypt()` correctly fails on missing names. `AI_RES_SECRETS_WORLD_READABLE` makes secrets 0644 and is gated only by an env var; the CI job sets it, which is intended and documented.

## Items checked and found sound (no finding)

- minio/init.sh uses `set -euo pipefail`; `mc mb --ignore-existing` is a precise idempotency primitive.
- Runtime positive controls exist for: proxy host port, proxy to api, admin-network reachability, checkpointer in-schema DDL, process-env probe (`PATH=`).
- Dockerfile pin checks: backend/minio/caddy Dockerfiles use digest-pinned bases; minio build verifies commit SHAs under `set -eux`.
- vuln_exceptions expiry/missing-field/malformed-date logic fails closed (unit tested).
- verify_digests resolves `name:tag` (without digest), so tag moves are detected; unresolved refs count as mismatches.

## Suggested order of fixes

1 (supply_chain IMAGES), 2 (runtime skip enforcement), 3 (hba test), 4 (wait_stack expected set), 5a/5c/5d (checker holes), 11 (setup-schema), 6 and 7 (scan scope and CI ordering), then the rest.
