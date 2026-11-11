# S03 independent security review (local Docker Compose infrastructure)

Reviewer: security-reviewer (read-only, static). Date: 2026-11-11.
Scope: infra/compose*.yaml, infra/config/**, infra/images/**, infra/scripts/**, backend/Dockerfile, backend/src/ai_res/api/serve.py,
.github/workflows/*.yml, Makefile, renovate.json, .gitignore.
Not done: no Docker command was run and no container was started. Everything below is from reading files, plus one offline regex probe of
scan_secrets.py. Nothing here is runtime evidence (IMPLEMENTATION NOT VERIFIED for any "would fail" claim about a live stack).
Constraint honoured: docs/implementation/increments and docs/implementation/reviews were not read.
Normative sources read: Infrastructure v1.7 (sections 9, 11.4-11.5, 12.2, 14, add. 1.6), Threat Model THR-005/013/017, .claude/rules/security.md, database-and-migrations.md.

Result: 0 CRITICAL, 4 HIGH, 8 MEDIUM, 10 LOW. No hardcoded secret, no docker.sock mount, no privileged container, no published port other than
127.0.0.1:8443, and no CI shell injection were found. The weaknesses are in the policy gates (checks that can pass vacuously) and in
PostgreSQL/Temporal transport and auth.

---------------------------------------------------------------------------------------------------------------------------------------
## HIGH

### H-1  check_compose.py can be bypassed, so the Manager/Worker-to-PostgreSQL and egress guarantees are not actually enforced
File: infra/scripts/check_compose.py (lines 100-102, 120-134, 137-157, 160-165); Makefile:35-39.
Evidence and scenarios:
1. Compose profiles. `docker compose config` omits services whose `profiles:` are not active, and load_model (line 161) passes no `--profile`.
   A service such as `worker-runtime: {profiles: [debug], networks: [data], secrets: [postgres_superuser_password], ...}` never appears in
   model["services"], so every check passes (hardening, data-network allowlist, ports, root user, docker.sock). `COMPOSE_PROFILES=debug docker compose up` then starts it.
   Fix: render with `--profile '*'` (Compose >= 2.20) and add a test with a profiled service.
2. Network namespace sharing. Only `network_mode: host` is rejected (line 100-102). `network_mode: "service:postgres"` or `"container:<id>"` puts a
   Manager/Worker in PostgreSQL's namespace, so it passes `_networks_of` (no `networks` key, but the "must declare networks" rule is satisfied by adding any
   internal network) and never trips the data allowlist. `network_mode: bridge` or `default` gives the default bridge with full internet egress (THR-005).
   Fix: reject any `network_mode` other than unset, and `pid`/`ipc` values other than empty or private (`service:`/`container:` too).
3. No secret-to-service allowlist. Nothing stops `manager-runtime`/`worker-runtime` from mounting `postgres_superuser_password`, `temporal_db_password`,
   `checkpointer_db_password` or `minio_root_*`, even though security.md says Manager/Worker get no DB credentials. The `*_FILE` exemption (line 115)
   also hides this. Fix: explicit map secret -> allowed services (postgres, postgres-provision, temporal*, minio*, api for cursor key only), fail on anything else.
4. The `egress` network is never checked (INTERNAL_NETWORKS excludes it, and no rule limits membership). The comment says "no members until S15/S16/S28" but a
   Worker joining `egress` passes. Infra v1.7 11.5 item 5 explicitly lists egress as a required security check. Fix: assert the member set of `egress`
   (currently empty) and forbid Manager/Worker on it.
5. NO_DATA_PREFIXES (line 20) matches only names starting `manager-runtime`/`worker-runtime`; the real protection is the DATA_ALLOWED allowlist, which is
   fine, but the same prefixes are not used for the ingress, admin, secret, or egress rules above. Prefix-matching on service names is not a security boundary;
   label services by role instead.
6. Volume check (line 103-106) only matches paths ending `docker.sock`. Bind mounts of `/var/run`, `/run`, `/`, `/var/lib/docker`, `/proc`, `containerd.sock`
   and `podman.sock` pass. Missing: `security_opt: seccomp=unconfined` / `apparmor=unconfined`, `devices`, `sysctls`, `extra_hosts`, `DOCKER_HOST` env,
   `cgroup: host`.
Also: services with `restart: "no"` skip the healthcheck rule (line 111), so any long-running service can opt out of the healthcheck requirement.

### H-2  PostgreSQL has no TLS and accepts remote superuser logins from every container on the data network
Files: infra/config/postgres/entrypoint.sh:11-13; infra/compose.yaml:85, 138-146.
- `host all all all scram-sha-256` plus `listen_addresses='*'` allows `postgres` (SUPERUSER) to authenticate over the network from `api`, `temporal`, `minio`
  and their one-shot jobs. SCRAM with a 64-char random password makes brute force infeasible today, but the superuser has no reason to be remotely
  usable, and once S05 adds `ai_res_api` the same open rule applies to every role in every database.
- `ssl` is never enabled: all PostgreSQL traffic, including the cleartext password inside `ALTER ROLE ... PASSWORD` (provision.sh:19-20), is unencrypted, and
  SCRAM channel binding is impossible. Infra v1.7 add. 1.6 ("TLS + SCRAM-SHA-256 обязательны для сетевых соединений", "pg_hba.conf ограничивает подключения") and
  security.md ("TLS/SCRAM обязательны для PostgreSQL соединений") are not met. If the owner accepted a local-profile exception I could not see it in the
  files I was allowed to read; treat as a deviation that needs an explicit recorded decision.
- Infra v1.7 9.2: "доверие только на основании Docker network запрещено". The data network is the only barrier for several services (see M-3, M-4).
Fix: explicit hba lines per (db, role, source) with `hostssl`; `local`/127.0.0.1 only for `postgres`; `reject` for the rest; enable `ssl=on` with a
dev CA from tmpfs/secret and `sslmode=verify-full` in clients (temporal-sql-tool, Temporal config, provision.sh).

### H-3  wait_stack.py can report success when the stack never came up
File: infra/scripts/wait_stack.py:22-34 (consumed by Makefile:58 and therefore CI `make up`).
`pending` is computed only from services that appear in `docker compose ps -a`. If the stack is partially or not created, `st` has fewer than 11 entries,
`pending` is empty, the loop spins until the 300 s deadline, breaks, and `return 1 if failed or pending else 0` returns 0. Examples: `up` crashed before
creating containers but `ps` returns `[]`; a service silently removed from compose.yaml; the hardcoded `>= 11` (line 27) is only a loop-exit condition, not
part of the return value. Also `ExitCode` defaults to 0 when the key is absent (line 17), so a one-shot job with a missing field counts as success.
Fix: derive the expected set from `docker compose config --services`, treat missing services as pending/failed, return non-zero on timeout.

### H-4  Secrets scanner has structural blind spots; "0 findings" is weak evidence
File: infra/scripts/scan_secrets.py:12-25, 43-52. Probed offline with the module's own RULES:
- JSON `{"db_password": "Xk9fQ2mZp8Lw3VnR7tYa1B"}`: NOT detected (the closing quote of the key sits between the name and `[:=]`).
- `password: "Xk9!fQ2#mZp8$Lw3VnR7tYa1B"` (special characters): NOT detected; value class excludes `!@#$%^&*`.
- `password: CorrectHorseBatteryStaple` (no digit): NOT detected by design.
- AWS key `AKIA...`, GitHub `ghp_...`, `Authorization: Bearer ...`: NOT detected; there is no vendor-token rule.
- Detected: YAML/ENV `key: value` with a digit and >= 16 chars, URL with `user:pass@`, PEM blocks, age keys.
Scope gaps: SCOPE (line 22) skips `.claude/`, `docs/architecture`, `renovate.json`, `.gitignore`, repo-root files other than Makefile/CLAUDE.md; unreadable or non-UTF-8
files are silently skipped (line 47); files over any size are read fully. In CI the runtime-values check (line 33-35, 52) is vacuous because the placeholder
secrets are empty files (ci.yml:35). History is never scanned.
Impact: this is the repo's only deterministic control for Secrets-and-Key-Management sec. 8; a committed token in JSON, a `.claude/` file or a binary would pass.
Fix: add gitleaks (digest-pinned) in CI over the full history plus this scanner as a second layer; fix the JSON-key case (`["']?\s*[:=]`), add vendor-token rules, fail on unreadable files.

---------------------------------------------------------------------------------------------------------------------------------------
## MEDIUM

### M-1  Supply-chain gate is narrower than it reads
File: infra/scripts/supply_chain.sh:16-17, 26-28, 7-8; infra/scripts/vuln_exceptions.py:51-53.
- `--ignore-unfixed` removes every HIGH/CRITICAL without a published fix from the blocking gate, including for own images.
- The exception file becomes a global Trivy ignore list (CVE id only). The `component` field is never matched, so an exception granted for a Go module in
  `ai-res/minio` silently also suppresses that CVE in `ai-res/api`, `ai-res/caddy` and every third-party image.
- `--scanners vuln` only: no secret or misconfig scan of image layers/filesystems (Trivy `secret` scanner is off). The task statement asks for image-layer secret exposure; nothing checks it.
- Third-party images (postgres, temporal*, otel) are report-only (lines 26-28); the exit status ignores them. Infra v1.7 14.2 asks for scan before release with
  results/exceptions recorded, so report-only is defensible, but note ci.yml:66 says "own images blocking" while the images with the largest attack surface are not.
- No cosign verification or signing (v1.7 14.3) and no provenance; release_manifest.py hard-codes `signature_verified: False`. Declared as a known limitation, not closed.
- Trivy v0.58.1 and Syft v1.18.1 are old relative to today; a stale scanner/DB schema under-reports. Renovate (renovate.json) has no regex manager for these pins, for
  install_tools.sh versions, or for the Dockerfile ARG dependency bumps, so they never get update PRs.
Fix: per-image ignore (trivy `--ignorefile` per image or `.trivyignore.yaml` with `paths`/`purls`), add `--scanners vuln,secret,misconfig`, drop
`--ignore-unfixed` for own images (or require an exception entry per finding), add Renovate regex managers.

### M-2  Self-built MinIO fork with unreviewed dependency bumps
File: infra/images/minio/Dockerfile:3-25.
The tag-to-commit check (lines 16, 18) is good. But `go get` of 9 hand-picked versions (lines 11-12, 20, 23) produces a binary no one upstream has tested; the repo
tracks no go.mod/go.sum diff, so the final dependency set is whatever the module proxy returns at build time (sumdb verification applies, but nothing records
the result beyond the SBOM, which is gitignored: .gitignore:62). Two CVEs for prometheus are already excepted. There is no upstream security-advisory feed
for this fork. Fix: record the resulting go.mod/go.sum hash in the release manifest, build with `-mod=readonly` after a committed patch file, set an owner
decision on supporting this fork or moving to an alternative S3 store.

### M-3  Temporal frontend and Web UI have no authentication or authorization; UI write actions enabled
Files: infra/compose.yaml:130-191; infra/config/temporal/dynamic.yaml (empty).
No mTLS, no authorizer/claim mapper. Anyone on `data` (api, minio, postgres, jobs) or `admin` can start, signal, terminate, or delete namespaces. temporal-ui has
no `TEMPORAL_DISABLE_WRITE_ACTIONS` so the UI permits workflow terminate/cancel/signal without login. Contradicts v1.7 9.2 (service-to-service must authenticate;
Docker network membership is not trust). Topology gap for later increments: Manager/Worker Runtime must reach Temporal but are forbidden from `data`
(check_compose.py:19-20), and Temporal is on `data`+`admin` only. Whoever solves that by attaching Temporal to `app` extends this unauthenticated surface to the runtimes
(a Worker could signal/terminate other workflows, which is a self-grant path). Fix: decide the Temporal-access network and authz model before S11/S23; set
`TEMPORAL_DISABLE_WRITE_ACTIONS=true` on the UI; add mTLS or an authorizer.

### M-4  MinIO console and API reachable from `api` and `temporal` on the data network
File: infra/compose.yaml:199-200 (`--console-address :9001` on a service joined to `data` and `admin`).
The console listens on all interfaces, so the "admin only" claim (check_compose.py:22 and the vuln exception compensating controls) is false at the network
level: `api`, `temporal` and the one-shot jobs on `data` can reach 9001 and 9000. Also minio-init and any future consumer use the root user (init.sh:7), which is
full admin; no scoped service account is created. Fix: bind the console to an address only on the admin interface or put MinIO's console behind a separate
proxy container on `admin`; create per-service MinIO users/policies; adjust the exception text.

### M-5  Secret file mode strategy breaks on Linux and the fallback is a global switch
Files: infra/scripts/secrets_dev.py:25-28, 54-73; .github/workflows/ci.yml:62; infra/compose.yaml (all `secrets:` use `file:`).
Compose file secrets are bind mounts keeping host ownership. Files are 0600 owned by the developer, while services run as uids 999/1000/10001/10002, which works on
Docker Desktop only. The fallback `AI_RES_SECRETS_WORLD_READABLE=1` writes every secret 0644 in a 0755 directory and is controlled solely by an environment
variable: set on a shared Linux host it exposes the PostgreSQL superuser password and MinIO root credentials to every local user, and nothing refuses it outside CI.
Fix: refuse the switch unless `CI=true` (and `GITHUB_ACTIONS`), or chown per-service via a group (`chmod 0640`, dedicated secrets group + `group_add`) instead of world-readable.
Also, write_runtime rewrites in place (O_TRUNC), which is non-atomic: a crash leaves empty secret files that satisfy `docker compose config` and may start a service with an empty password path.

### M-6  Provisioning sends role passwords as cleartext SQL over an unencrypted connection
File: infra/config/postgres/provision.sh:13-20.
`ALTER ROLE ... PASSWORD :'temporal_pw'` carries the cleartext password in the statement. Mitigated by `log_min_error_statement = panic` and the data network, but the
statement is visible in `pg_stat_activity` while running, any `log_statement`/`auto_explain`/`pg_stat_statements` setting later enabled records it, and there is no TLS (H-2).
Fix: compute a SCRAM-SHA-256 verifier client-side (python hashlib/psycopg `encrypt_password`) and `ALTER ROLE ... PASSWORD 'SCRAM-SHA-256$...'`, or use `\password` semantics.

### M-7  Reverse proxy health check proves nothing; no request limits or timeouts
Files: infra/compose.yaml:51-55; infra/config/caddy/Caddyfile.
`caddy validate --config ...` only parses the file in a fresh process; the check stays green when the listener is wedged. The api container health is similarly
"any HTTP answer" (compose.yaml:74), so `reverse-proxy depends_on api: service_healthy` gives little assurance. Caddy sets no `request_body { max_size }`,
timeouts, or header-size limits in front of an API that will later accept uploads (security.md section on upload size), and the `Forwarded` (RFC 7239) header from
clients is passed through untouched while only `X-Forwarded-For` is rewritten. Fix: probe the listener (`wget --no-check-certificate`/bash tcp) and set
`request_body max_size`, `servers { timeouts }` and strip `Forwarded`.

### M-8  CI runs unprivileged-but-untrusted PR code with Docker, and gate coverage in CI is partial
File: .github/workflows/ci.yml.
Positive: actions are SHA-pinned, `permissions: contents: read`, `persist-credentials: false`, no `pull_request_target`, no `${{ }}` of attacker-controlled data in `run:`
(only `runner.temp`/`env.UV_VERSION`). Remaining issues: (a) `infra-runtime` builds and runs PR-supplied Dockerfiles/compose on every fork PR with no
approval gate: fine for secrets (none) but gives a PR author arbitrary code on the runner and cache write; (b) no `timeout-minutes` on any job; (c) setup-uv
cache is left at its default (cache poisoning surface across jobs); (d) `make up` (Makefile:56-58) never runs `infra-check` first, so the policy gate and the
runtime stack are independent jobs; ordering means `infra-runtime` needs `infra-static`, which is OK in CI but not locally; (e) the log-dump step redacts only
tokens >= 40 chars via sed, which is heuristic. Fix: require approval for first-time contributors on `pull_request`, add timeouts, set `enable-cache: false`
for runtime job, run `check_compose.py` in `make up`.

---------------------------------------------------------------------------------------------------------------------------------------
## LOW

- L-1  infra/scripts/install_tools.sh:7-8 - the age SHA-256 is "pinned from the first verified download" (trust on first use); no signature or second-source
  check. sops hash is upstream-published (good). Only used on CI.
- L-2  infra/scripts/verify_digests.py:10 - SOURCES omit .github/workflows and supply_chain.sh, so the hadolint, actionlint, Syft and Trivy digests are never re-verified.
  Digest equality shows the tag did not move; it does not show the first-pinned digest was the right one.
- L-3  infra/compose.yaml:62 `ai-res/api:dev` and infra/releases (release-manifest.json is gitignored, .gitignore:65): the release evidence and SBOMs are not committed, so
  v1.7 12.3/14 (SBOM kept with the Release Manifest, provenance) cannot be audited from the repository.
- L-4  infra/compose.yaml:45 + `ingress` network (compose.yaml:18): `ingress` is not internal, so reverse-proxy has unrestricted outbound internet (and is also on `app`).
  A compromised proxy is both an egress channel and a pivot. Acceptable for a local stack, but contradicts the 9.4 "egress policy" statement. Consider internal ingress + published port via a separate
  frontend-only mechanism, or document the exception.
- L-5  backend/src/ai_res/api/serve.py:10: binds 0.0.0.0 on a container that is also on `data`, so Temporal/MinIO/Postgres containers can call the API
  directly, bypassing Caddy's header rewriting. The application must therefore validate the peer address before trusting X-Forwarded-For (ADR-020 says it does; not
  verified here). No uvicorn limits (`limit_concurrency`, `timeout_keep_alive`, `h11_max_incomplete_event_size`) are set.
- L-6  infra/config/postgres/provision.sh:25 - `REVOKE ... FROM PUBLIC` is applied to the three created databases only; the default `CONNECT` on `postgres` and `template1`
  stays with PUBLIC, so `temporal` and `ai_res_checkpointer` can log in there and enumerate roles/databases.
- L-7  infra/config/minio/init.sh:7 - root credentials are placed into `MC_HOST_local` (environment of the mc process). Not in argv/compose env, but mc error output may echo the
  alias URL; not verified. The `docker compose logs` upload in CI relies on sed redaction.
- L-8  infra/config/temporal/start.sh:6-7 and setup-schema.sh:4-5 export the DB password in the server process environment (readable via /proc by the same uid, and by
  anything with `docker exec`). Acceptable for Temporal's template mechanism; note it.
- L-9  infra/config/otel/config.yaml:5 - OTLP gRPC receiver on 0.0.0.0:4317 with no auth/TLS, on `app`; any app container can inject telemetry. Fine until S13 but v1.7 9.2 applies.
- L-10 Makefile:61-62 - `make down` runs `down --volumes` with no confirmation and CI calls it unconditionally; locally it destroys the PostgreSQL and MinIO volumes (CLAUDE.md section 8
  requires owner decision for destructive steps on persistent data; this is local-only, so low).
- L-11 infra/scripts/secrets_dev.py - the only encrypted file (infra/secrets/encrypted/local.enc.yaml) is encrypted to one developer's age key. If committed, a clean
  clone or CI cannot decrypt it and `make up` fails; if not committed, CI regenerates secrets each run (ci.yml:61). Decide which; there is also no `rotate` command although the docstring references one.
- L-12 Hardening gaps not enforced by check_compose.py: no `cpus`/ulimits, no `logging` size caps (disk fill DoS), no seccomp profile pinned, no `userns` mapping.
  mem_limit/pids_limit are present on all services (checked).

---------------------------------------------------------------------------------------------------------------------------------------
## Checked and found OK (brief, for coverage)
- No secrets in compose env, argv, Dockerfile layers or committed files; `*_FILE` pattern used; Postgres entrypoint avoids the stock POSTGRES_PASSWORD export; psql reads passwords via backtick inside psql.
- infra/secrets/runtime is git-ignored (.gitignore:24), 0600/0700; scripts use stdin for sops input.
- All third-party and base images pinned by tag and digest; GitHub Actions pinned by SHA; sops/age downloads checksum-verified; uv install is `--locked`.
- All services non-root, read_only, cap_drop ALL, no-new-privileges, pids/mem limits; no docker.sock mount in any service or script (supply_chain.sh uses `docker save`, not a socket mount).
- Only reverse-proxy publishes a port, bound to 127.0.0.1; app/data/admin networks are `internal: true`; Manager/Worker services do not exist yet; api has no DB credentials.
- contracts.yml passes `github.base_ref` through `env:`, not inline; no `${{ }}` injection into `run:` found.

## Recommended order of fixes
1. H-1 and H-3 (gates that pass vacuously) before anything else depends on them; add negative tests for each listed bypass.
2. H-2 and M-6 together (pg_hba + TLS + SCRAM verifier provisioning), or record an explicit owner decision for the local profile.
3. H-4, M-1 (secret and vulnerability scanning depth).
4. M-3/M-4 before S11/S23, since the Temporal-access network design decides whether Workers can reach an unauthenticated Temporal.
