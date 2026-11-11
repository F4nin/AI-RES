# S03 independent security re-review (local infrastructure, secrets, CI)

Reviewer: security-reviewer (read-only). Date: 2026-11-11. Method: blind-first (S03_*_REPORT.md and S03_REVIEW_DISPOSITION.md NOT read).
Read: infra/compose*.yaml, infra/config/**, infra/scripts/**, infra/tests/**, backend/Dockerfile, backend/.dockerignore, serve.py,
.github/workflows/*.yml, Makefile, .gitignore, renovate.json. Compared with the four earlier S03 reviews.

Evidence performed (no file in the repo was modified; no up/down/reset):
- `infra/.venv/bin/pytest tests --ignore=tests/runtime`: 72 passed. `check_compose.py -f compose.yaml -f compose.dev.yaml`: 11 services, 0 violations. `scan_secrets.py`: 0 findings.
- Live stack (running, all 7 long-running healthy, 4 one-shots exited 0): read-only `docker inspect` / `docker exec` probes, pg_hba and pg_stat_ssl queries, connection probes from the api container.
- Mutation probes in a scratch copy (scratchpad/w, not the repo) of compose + check_compose.py; offline regex probes of scan_secrets.RULES.
- The runtime pytest suite was NOT run (it executes `compose run --rm` jobs); its code was read and judged able to fail.

## VERDICT: no open CRITICAL, no open HIGH. 6 MEDIUM, 9 LOW remain.
All HIGH findings of the four earlier reviews are closed in code, and the ones I could exercise were confirmed by running them (table below).
The MEDIUM items are partly carried over and partly new residuals/bypasses of the fixes; none is exploitable today by an external actor.

## Closure of earlier HIGH findings

| Finding | Status | Evidence |
|---|---|---|
| SEC H-1 check_compose bypass (profiles) | CLOSED | `load_model` uses `docker compose --profile "*"` (check_compose.py:213). Scratch probe: a `worker-runtime` with `profiles: [debug]` on `data` now yields a violation. |
| SEC H-1 network_mode / pid / ipc sharing | CLOSED | Any `network_mode` is rejected (:126); `pid/ipc/userns/uts` host, `service:`, `container:` rejected (:128). Probe: `pid: container:abc` flagged. Tests at test_check_compose.py:134-135. |
| SEC H-1 no secret->service allowlist | CLOSED (see M-1 for a bypass) | `SECRET_ALLOWED` (:28). Probe: `worker-runtime` mounting `postgres_superuser_password` flagged. |
| SEC H-1 egress network unchecked | CLOSED | `EGRESS_ALLOWED` (:20, :172), Manager/Worker limited to app/workflow (:178). Test :224. |
| SEC H-1 socket/volume check | CLOSED for the stated cases | Bind mounts outside `infra/` rejected (:136-139); probes with `/var/run`, `/proc`, containerd.sock flagged. |
| SEC H-1 healthcheck opt-out via `restart: "no"` | CLOSED | Exemption limited to the named ONE_SHOT set (:147). |
| SEC H-2 PostgreSQL no TLS / open hba | CLOSED, runtime-verified | pg_hba_file_rules (live): `local scram`, `hostssl` per db/role, `host all all all reject`. `ssl=on`, min TLSv1.2. pg_stat_ssl: all 70 Temporal sessions `ssl=t, TLSv1.3`. Temporal rendered config: `tls.enabled true`, `enableHostVerification true`, `serverName postgres`. Provision job uses `PGSSLMODE=verify-full`. |
| SEC H-3 wait_stack false success | CLOSED | Expected set is fixed; missing = pending; timeout = exit 1 (wait_stack.py:23-56). Tests (empty state, missing service, timeout) would fail on the old logic. |
| SEC H-4 scanner blind spots | CLOSED for the listed cases | Probe: JSON-quoted key, special-char value, letters-only value, AKIA, ghp_, Bearer, URL creds, PEM all detected; unreadable files reported; non-UTF-8 scanned. Residual gaps are M-4. |
| ARCH H1 langgraph CREATE for checkpointer | CLOSED | provision.sh grants USAGE only; runtime test asserts CREATE=f, DDL denied, DML positive control, no ownership. |
| ARCH H2 SCRAM-only test vacuous | CLOSED | Test now asserts the set of hba methods is `<= {scram-sha-256, reject}`, no non-reject `host` rule, no non-SCRAM verifier in pg_authid; a `trust` or plain `host` rule would fail it. |
| CODE H1 local.enc.yaml committable | CLOSED | `git check-ignore` matches `.gitignore:26`; `secrets_dev.py` fails with an explicit message on decrypt failure and never regenerates silently. |

Also checked and fine: no secret in compose env/argv/inspect (`docker inspect` of postgres shows no password env); all services non-root, read_only, cap_drop ALL, no-new-privileges; only 127.0.0.1:8443 published; networks app/data/admin internal (live `docker network inspect`); `AI_RES_SECRETS_WORLD_READABLE=1` is refused outside CI (secrets_dev.py:31); CI actions SHA-pinned, `permissions: contents: read`, timeouts set, `persist-credentials: false`, no `${{ }}` with attacker data in `run:`; `make up` now depends on `infra-check`; `make down` keeps volumes and `make reset` requires `CONFIRM=yes`; `.env`, keys and runtime secrets are git-ignored; placeholder secret files in CI are enough for `docker compose config` (verified: the TLS secrets need not exist for rendering).

## MEDIUM

### M-1  A bind mount of `./secrets/runtime` inside the project dir bypasses SECRET_ALLOWED (new, residual of the H-1 fix)
check_compose.py:131-139 (bind-mount check) vs :159-161. The bind check only rejects sources OUTSIDE `infra/`. Verified by probe: `api: volumes: ["./secrets/runtime:/leak:ro"]` gives 0 violations, so any future Manager/Worker (or api) can read every secret including the PostgreSQL superuser password, defeating security.md "Manager/Worker get no DB credentials". Same for `./secrets/encrypted`.
Fix: reject any bind source under `secrets/` (or allow only an explicit config-file list), and cover it with a test.

### M-2  Networks other than the five known ones are not checked (new)
check_compose.py:18, 198-200, 170-176. A service on a custom non-internal network (`networks: {leak: {}}`, top-level `leak: {}`) passes: probe `api2` -> 0 violations. That is full internet egress (THR-005), and the `egress` allowlist is sidestepped. The name-prefix rule for Manager/Worker (:22, :178) only protects services literally named `manager-runtime*`/`worker-runtime*`; a service called `worker` or `agent-runtime` gets only the data allowlist.
Fix: allowlist the set of declared networks (fail on any unknown name and on any non-internal network except ingress/egress); identify Manager/Worker by a label rather than name prefix.

### M-3  Temporal frontend unauthenticated and MinIO console reachable from the application network (carried over, live-verified)
From the `api` container: `temporal:7233`, `minio:9000` and `minio:9001` (console) are OPEN; `temporal-ui` has no `TEMPORAL_DISABLE_WRITE_ACTIONS`. compose.yaml `minio` command `--console-address :9001` on `data`+`admin`; Temporal on `data`+`admin`, no authorizer/mTLS. Compromise of api or any `data` member can start/terminate workflows and reach the MinIO console login. The "admin only" comment (check_compose.py:26) is true for the UI containers, not for the console. Decide the Temporal-access network and authz model before S11/S23; set `TEMPORAL_DISABLE_WRITE_ACTIONS=true`; bind the console to an admin-only path.

### M-4  Secret scanner coverage is narrower than "0 findings" suggests
scan_secrets.py:12 and :13. (a) `EXCLUDED_PREFIXES` skips the whole `.claude/` (444 tracked files: settings.json, hooks, mcp-configs, scripts and the project's own `.claude/rules/*.md`, not only ECC prose) and the whole `docs/implementation/reviews/`; a real token committed there passes. With exclusions off the scanner reports 31 hits, all of which I checked to be placeholders or deliberate examples, so the exclusion is currently harmless but permanent. (b) KEY pattern misses `access_key`, `*_pwd`, `credential`, bare `PASS`, `hmac_key`, `encryption_key`, `auth` (probe: not detected); values < 16 chars and JWT-shaped strings are not detected. (c) SKIP_SUFFIX skips `.lock/.sum/.pdf/images`. History is not scanned; no second scanner (gitleaks) in CI.
Fix: exclude only `.claude/rules/ecc/` and `.claude/skills|agents` vendor trees (scan settings/hooks/mcp-configs), widen KEY, add gitleaks over history.

### M-5  Supply-chain gate still narrower than its name (carried over, unchanged)
supply_chain.sh:23-24, 36-38; vuln_exceptions.py:51-53. `--ignore-unfixed` also for own images; `--scanners vuln` only (no image secret/misconfig scan; the runtime layer-canary test partly compensates for the compose secrets); the exception file becomes a global ignore list by CVE id (the `component` field is never matched); third-party images report-only; no cosign/provenance; old Trivy 0.58.1/Syft 1.18.1 with no Renovate manager for them. Acceptable as a recorded limitation only if the owner has accepted it.

### M-6  CI: forks and cache surface
ci.yml: `infra-runtime` builds and runs PR-supplied Dockerfiles/compose on every PR including forks (no approval gate configured in the repo; GitHub setting required), setup-uv default cache is shared with the runtime job, and the failure-log redaction is a heuristic `sed` (40+ alnum chars; PEM lines with `+/=` are not covered). No secrets are exposed to the job (none exist), so impact is runner abuse/cache poisoning only.
Fix: require approval for outside contributors, `enable-cache: false` in `infra-runtime`.

## LOW

- L-1  check_compose.py misses: `security_opt` `seccomp=unconfined`/`apparmor=unconfined`, `devices`, `cgroup: host`, `sysctls`, `extra_hosts`, `DOCKER_HOST` env (probe: all pass; only the docker.sock mount in the same probe was flagged). Top-level `secrets:` `file:` pointing outside the project is not checked; `*_FILE` env check accepts `/run/secrets/../../x` (:154). Env name `MINIO_CREDS` is not matched by SECRET_NAME.
- L-2  Test gap: no unit test pins `--profile "*"` in `load_model`; deleting it (re-opening the profile bypass) keeps all 72 tests green. Add a test on the command line or a rendered fixture with a profiled service.
- L-3  PostgreSQL superuser is allowed over the network (`hostssl all postgres all`, entrypoint.sh:20) from every `data` member (api, minio, temporal). Needed by the provision job; mitigated by TLS+SCRAM, 64-char random password and secret allowlist (only postgres and postgres-provision mount it). Prefer a source CIDR for the data subnet pinned in compose, or a dedicated provisioning role.
- L-4  provision.sh:17-18 still sends role passwords as cleartext in `ALTER ROLE ... PASSWORD` (now over verified TLS; error statements suppressed by `log_min_error_statement=panic`; visible briefly in pg_stat_activity). A client-computed SCRAM verifier would remove it.
- L-5  wait_stack.py:10-11 hardcodes the expected service set: a new service is never awaited, and `ExitCode` defaults to 0 if absent (:20). Derive from `docker compose config --services` (the policy gate already uses the rendered model).
- L-6  `ingress` is not internal: reverse-proxy has unrestricted outbound access (documented as G-34, pinned by a non-assertion test). Caddyfile has no `request_body max_size`, timeouts, or removal of client `Forwarded` header; api listens on 0.0.0.0 on `data` too, so peers can bypass Caddy's `X-Forwarded-For` rewrite (the app must not trust it from non-proxy peers; `proxy_headers=False` is set).
- L-7  Temporal password stays in the server process environment (start.sh:7; excluded from the process-env runtime test by design). OTLP receiver 0.0.0.0:4317 unauthenticated (reachable from api: OPEN).
- L-8  `template1` keeps default PUBLIC CONNECT (provision.sh revokes only `postgres` and the three created DBs); roles `temporal`/`ai_res_checkpointer` cannot log in anywhere else because of hba, so impact is nil today.
- L-9  secrets_dev.py:85-103 writes secret files in place (O_TRUNC): a crash can leave an empty file that still satisfies `docker compose config`. Rationale (bind-mount inode) is documented; add a non-empty check in `up`/wait.
- L-10 install_tools.sh age SHA-256 is trust-on-first-use; verify_digests.py does not cover workflow/supply_chain image digests (hadolint, actionlint, Syft, Trivy).

## Recommended order
1. M-1 and M-2 (cheap, make the new gate unbypassable for the Manager/Worker increments) with tests.
2. L-2 (pin the profile fix with a test).
3. M-3 before S11/S23 (decision on Temporal access network/authz); M-4 widening of scanner scope.
4. M-5/M-6 as owner-accepted limitations or follow-up.

IMPLEMENTATION NOT VERIFIED items: the `infra/tests/runtime` suite was not executed by this review; claims about it come from reading the code and from the equivalent manual probes listed above.
