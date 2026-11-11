# S03 code review (independent, read-only)

Scope: backend/Dockerfile, backend/.dockerignore, backend/src/ai_res/api/serve.py, backend/tests/unit/test_serve.py, Makefile, .gitignore, .github/workflows/*, renovate.json, infra/** (without .venv/.cache), docs/runbooks/local-stack.md.
Checks run: `infra: ruff` OK, `pytest --ignore=tests/runtime` 44 passed; `backend: ruff` OK, `mypy` OK. No docker commands run, so the runtime claims below come from reading the code and were not executed.

## HIGH

### H1. `infra/secrets/encrypted/local.enc.yaml` is committable but is encrypted to one developer's personal age key
- `.gitignore:24-25` (`infra/secrets/*` then `!infra/secrets/encrypted/`) leaves `local.enc.yaml` un-ignored (`git check-ignore` returns nothing). `git add infra` will commit it.
- `infra/scripts/secrets_dev.py:87-98`: when `ENCRYPTED` exists, `init()` keeps it and calls `decrypt()`. The recipient is the age key generated on the first machine.
- Failure: a clean clone (the CI job `infra-runtime`, `.github/workflows/ci.yml:59-63`, or another developer) generates a new age key, finds the file, and `sops --decrypt` fails with CalledProcessError (no matching identity). `make up` is broken for everyone except the author. This contradicts the runbook phrase "из чистого клона".
- Fix: treat the file as per-machine and git-ignore it (also drop the `!infra/secrets/encrypted/` exception). Alternatively commit it deliberately with a fixed `.sops.yaml` and a documented shared CI key as a secret. In both cases, make `init()` catch a decrypt failure and print a clear message (do not regenerate silently).

## MEDIUM

### M1. `git fetch` after `persist-credentials: false` breaks PR runs on a private repo
`.github/workflows/contracts.yml:9-20`: checkout drops the token, then `git fetch --depth=1 origin "$BASE_REF"` needs auth. It works only if the repo is public. `fetch-depth: 0` already fetched `origin/<base>`, so the extra fetch is redundant. Fix: `git diff --exit-code "origin/$BASE_REF" -- contracts/baseline` with no fetch (or `git diff origin/$BASE_REF...HEAD`).

### M2. `infra-runtime` can pass green with every test skipped
`infra/tests/runtime/conftest.py:12-18`: the autouse fixture calls `pytest.skip` when the stack is not detected. `Makefile infra-test-runtime` and CI only use `-rs`, and pytest exits 0 when all tests are skipped. This violates the project rule that a skip is not evidence (testing-and-verification.md). Fix: in CI (`CI=true` or `AI_RES_REQUIRE_STACK=1`) call `pytest.fail` instead of `skip`. Also fail when 0 tests ran (`-p no:cacheprovider --strict-markers` plus a `--maxfail` guard, or check the exit code 5 / skipped count).

### M3. `test_secret_values_are_not_in_image_layers` can pass vacuously
`infra/tests/runtime/test_stack.py:~183-200`: layers are searched only if they are NOT gzip (`data[:2] != b"\x1f\x8b"`). With the containerd image store (the Docker 29 default) `docker save` writes compressed layer blobs, so only compressed bytes are searched and a plaintext secret would never match. There is no positive control. Fix: open layers with `tarfile.open(fileobj=..., mode="r:*")` (handles gz/zstd-less), and add a control that plants a known marker (for example check that a known file path such as `/app/.venv/bin/python` is found in the walk).

### M4. `test_egress_denied_from_data_services[temporal]` is probably vacuous
`test_stack.py:~99-101` runs `bash -c "exec 3<>/dev/tcp/..."` inside `temporal`. The temporalio/server image is Alpine-based and has no bash (the compose file itself launches `start.sh` with `/bin/sh`, `compose.yaml:136`). The command then prints nothing and `assert "CONNECTED" not in out` passes. Fix: assert `"FAILED" in out` (positive proof that the probe ran), and use `nc -z -w2` or `python` where bash is absent.

### M5. `make down` is destructive and named like a safe command
`Makefile:61-63`: `down --volumes` deletes Postgres and MinIO data. It is documented, but `down` is conventionally non-destructive, and CI reuses it. Fix: `down` without `--volumes`, plus a separate `make reset` (volumes) and have CI call `reset`.

### M6. Runbook inaccuracies (docs/runbooks/local-stack.md)
- l.28: `exec temporal-ui sh` only gives a shell in a container on the admin network. It does not give access to the UI or console from the host, so the text promises something it cannot deliver. Describe the actual procedure (a temporary published port in a git-ignored override file) or state that no host access exists.
- l.30-31: `make infra-check` is listed under "без запуска контейнеров", but it needs Docker and the six `infra/secrets/runtime/*` files to exist (CI creates empty placeholders, ci.yml:31-36). A fresh clone without `make secrets-dev` fails. Document the placeholder step or make `infra-check` create them.
- l.36: "`make secrets-dev` ... не заменяет файлы" contradicts `write_runtime` (rewrites changed files in place) and the rotation paragraph (l.24). Reword.
- l.3 says the Linux CI run was not verified locally; keep, but the claim "проверено" for the exec/diagnostic commands is not backed by any test.

### M7. Weak assertion in `test_release_manifest.py`
`infra/tests/test_release_manifest.py:19-23` is named "matches_schema" but only compares key sets; the JSON Schema (types, patterns, `const`) is never evaluated, so e.g. a non-hex digest passes. Add `jsonschema` as a dev dependency and `jsonschema.validate(m, SCHEMA)`.

## LOW

- L1 `.github/workflows/contracts.yml` and `ci.yml` duplicate `uv` version "0.11.31", and `backend/Dockerfile:2` pins uv 0.11.0. Renovate cannot update the workflow inputs or the `docker run` image refs in `ci.yml:44,46` and `supply_chain.sh:7-8` (no customManager). Drift is likely; add `customManagers` regex rules or a single source.
- L2 `infra/scripts/wait_stack.py:27` hardcodes `len(st) >= 11`; the service sets are also duplicated in `check_compose.py:19`, `tests/runtime/helpers.py:11-12`, `wait_stack.py:10-11` and `test_stack.py` (`allowed`). Derive them from `docker compose config --services` / the model.
- L3 `infra/scripts/check_compose.py:30` `set(nets if isinstance(nets, dict) else nets)` has two identical branches; line 48 `[v for v in ...]` is a no-op comprehension. Environment checks cover `environment` only, not `command`/`entrypoint`/`labels`.
- L4 `infra/scripts/release_manifest.py:58`: `rendered_sha256` hashes the rendered model, which contains absolute host paths (build contexts, secret file sources), so it is not reproducible across machines. The script is not wired into Makefile or CI (dead until a release process uses it).
- L5 `infra/scripts/secrets_dev.py:27-28`: `AI_RES_SECRETS_WORLD_READABLE=1` silently makes secrets 0644 anywhere; add a guard (`CI=true` or `GITHUB_ACTIONS`). `write_runtime` truncates files in place (non atomic): a running container may read an empty secret; `stale.unlink()` fails if a directory is present.
- L6 `infra/scripts/supply_chain.sh:26-27` scans every third-party image twice (count and report); write the JSON once and count from the file. Exceptions in `vulnerability-exceptions.yaml` apply to all images by CVE id, not per component. `install_tools.sh:3`: age hash pinned from "first download" is trust-on-first-use.
- L7 `backend/tests/unit/test_serve.py` mirrors the implementation kwargs but does not check `host`/`port` and does not verify that the factory target resolves (`ai_res.api.app:create_app_from_env` exists today, app.py:28; a rename would only fail at container start). Add `importlib.import_module` + `getattr` on the target and assert `port == 8000`.
- L8 `test_stack.py` `test_internal_ports_not_reachable_on_host` includes 7233/8080/9000, which collide with common local dev servers (the author already removed 5432 for this reason); the `192.168.65.254` and `host.docker.internal` targets are Docker Desktop specific and trivially "FAILED" on Linux CI.
- L9 `ci.yml:2` `on: [push, pull_request]` runs everything twice for branches with an open PR; restrict `push` to `main`.
- L10 `backend/Dockerfile:18` `--chown=0:0` is the default and redundant.

## Not verified
Docker, Compose, SOPS and the runtime suite were not executed. The action SHA pins (`checkout`, `setup-node`, `setup-uv`) could not be validated (no `gh`/network check); verify them once before merge, as a mistyped SHA fails every job.

## Summary
| Severity | Count |
|----------|-------|
| HIGH | 1 |
| MEDIUM | 7 |
| LOW | 10 |

Verdict: WARNING. H1 blocks the claim "make up works from a clean clone"; M2-M4 weaken the runtime evidence.
