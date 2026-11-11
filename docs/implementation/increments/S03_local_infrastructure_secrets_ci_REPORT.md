# S03 — Local infrastructure (Docker Compose), secrets и CI baseline: Increment Report

**Дата:** 2026-11-11 · **Промпт:** `increments/prompts/S03_local_infrastructure_secrets_ci.md` · **Итоговый статус:** **VERIFIED (локально и GitHub Actions Linux)**; ранее TESTED (локальное runtime evidence на macOS/Docker Desktop). VERIFIED присвоен после повторного независимого review (см. §16): workflows не запускались на удалённом Linux-CI (G-27 — принятый остаточный риск до первого прогона), часть пунктов CI-scope открыта (G-20, интеграционный job). Для остальных частей `IMPLEMENTATION NOT VERIFIED` не требуется: стек поднимался и проверялся живьём.

## 1. Что реализовано
Реализовано (scope §5): Compose-стек из 11 сервисов (Caddy, api, postgres 16 + provision job, temporal + schema job + namespace job, temporal-ui, minio + init job, otel-collector) с профилями dev/test; сети ingress/app/data/admin/egress (app/data/admin — `internal`), наружу только `127.0.0.1:8443`; все сторонние образы по tag+digest, `latest` и непиннутые образы отклоняет скрипт; Compose secrets из SOPS/age (`make secrets-dev`), без default credentials, `.env.example` без секретов; Dockerfile backend (non-root, базы по digest, без pip) и `.dockerignore`; hardening контейнеров (non-root, `read_only`, `cap_drop: ALL`, `no-new-privileges`, лимиты) проверяется статически и по inspect; PostgreSQL: TLS + SCRAM, `pg_hba` по ролям и БД, схема `langgraph` и роль `ai_res_checkpointer` (USAGE без DDL) создаются provisioning-job (ADR-036); SBOM (Syft) и скан (Trivy); CI workflows (pin по SHA); формат Release Manifest со скриптом генерации; Renovate-конфиг; runbook.
Не сделано / открыто: Testcontainers-интеграция в CI (тестов нет до S04), oasdiff cross-check (G-20), подпись образов (G-26), ограничение исходящего трафика Caddy (G-34), аутентификация Temporal (G-36), полноценный ограничитель сети Manager/Worker → Temporal (G-38), подключение OTel (G-22). Не входит в S03: Prometheus/Loki/Tempo/Grafana (S13), backup (S32/S38), Bifrost (S16).

## 2. Нормативная база и проверка Registry
Проверено наличие canonical файлов Registry v4.1: DOC-015 (WORKING, `…Infrastructure_Deployment_Operations_v1.7.md`), DOC-019 (BASELINED), DOC-016, DOC-024, Implementation Spec v1.22, а также Threat Model v1.1 (THR-005/013/017). Discrepancy report не требуется. Интерпретации, требующие внимания владельца: третья БД `temporal_visibility_db` (G-39, ADR-044); «секреты в Git зашифрованы SOPS» (DOC-015 §17.17) применено к общим секретам, а dev-файл per-machine и не коммитится (ADR-045); MinIO собирается из исходников (ADR-042, решение владельца в сессии).

## 3. Созданные и изменённые файлы
Новые: `infra/` (compose.yaml, compose.dev.yaml, compose.test.yaml, config/{caddy,otel,postgres,temporal,minio}, images/{caddy,minio}/Dockerfile, scripts/{check_compose,secrets_dev,scan_secrets,supply_chain.sh,verify_digests,wait_stack,vuln_exceptions,release_manifest,install_tools.sh}, security/vulnerability-exceptions.yaml, releases/release-manifest.schema.json, tests/ (статические + runtime), pyproject.toml, uv.lock, .env.example); `backend/Dockerfile`, `backend/.dockerignore`, `backend/src/ai_res/api/serve.py`, `backend/tests/unit/test_serve.py`; `.github/workflows/ci.yml`; `renovate.json`; `docs/runbooks/local-stack.md`; `docs/implementation/reviews/S03_*.md` (5 файлов).
Изменены: `Makefile`, `.gitignore`, `.github/workflows/contracts.yml` (pin по SHA, убраны TODO S03), `docs/implementation/{ARCHITECTURE_DECISION_LOG,KNOWN_GAPS,ECC_USAGE,IMPLEMENTATION_STATUS,REQUIREMENTS_TRACEABILITY,CONTEXT_HANDOFF,LOCAL_DEVELOPMENT,RELEASE_AND_VERSIONING}.md`. Нормативные документы `docs/architecture/` не менялись.

## 4. Изменения API / контрактов / событий
Нет. Эндпоинты и события не добавлялись (health/readiness api — без контракта запрещён, G-23). Контейнерная точка входа `ai_res.api.serve` — запуск uvicorn с `log_config=None`.

## 5. Миграции и совместимость
Alembic-миграций нет (S04). Provisioning вне Alembic: БД `ai_res_db`, `temporal_db`, `temporal_visibility_db`, роли `ai_res_owner` (NOLOGIN), `temporal`, `ai_res_checkpointer`, схема `langgraph` — идемпотентный one-shot job; Temporal schema — `temporal-sql-tool` (повторный запуск проверен тестом). Доменные роли, RLS и grants — S05.

## 6. Решения, принятые самостоятельно
| ADR | Решение | Статус |
|---|---|---|
| ADR-042 | MinIO и mc из закреплённых исходников (+ обновление зависимостей) | ACCEPTED (выбор владельца) |
| ADR-043 | SBOM, скан образов: own блокирует, third-party report-only; исключения со сроком | ACCEPTED |
| ADR-044 | Состав и hardening стека; TLS/`pg_hba`; пароль Temporal в env процесса; liveness-healthcheck | ACCEPTED |
| ADR-045 | Dev-секреты: SOPS+age, per-machine, идемпотентная материализация | ACCEPTED |

## 7. Устранённые несогласованности / NCP
Выявлено: официальный образ MinIO недоступен (решено ADR-042); health-эндпоинт отсутствует в контракте (G-23); третья БД Temporal (G-39). NCP не готовились: baseline не менялся.

## 8. ECC: фактически использованные agents, skills, commands
| Инструмент | Зачем | Результат |
|---|---|---|
| `security-reviewer` | Независимое security review (blind-first) | 0 CRITICAL, 4 HIGH, 8 MEDIUM, 12 LOW; все HIGH исправлены |
| `architect` | Соответствие архитектуре | 2 HIGH, 9 MEDIUM, 11 LOW; HIGH исправлены, остаток — gaps |
| `silent-failure-hunter` | Холостые проверки, fail-open | 5 HIGH, множество MEDIUM; исправлены |
| `code-reviewer` | Общее review | 1 HIGH, 7 MEDIUM, 10 LOW; исправлены |
Не использованы: `planner`/`/plan` (план по срезам согласован с владельцем в диалоге), `build-error-resolver`, `production-audit`, `verification-loop`, `/quality-gate`, `/security-review`. DevOps-агента в ECC нет — компенсация: `security-reviewer` + `architect` + детерминированные проверки.

## 9. Тесты и проверки
| Gate | Команда | Результат (точно) |
|---|---|---|
| G1 Static | `make backend-check` | ruff чисто, mypy `no issues found in 18 source files`, import-linter `4 kept, 0 broken` |
| G1 Static | `make infra-check` | ruff чисто; `check_compose.py`: 11 services, 0 violation(s) для compose.yaml, +dev, +test |
| G2 Unit | `make backend-test` | `58 passed` |
| G2/G5 Unit infra | `cd infra && uv run --locked pytest -q --ignore=tests/runtime` | `72 passed` (политики compose 52, сканер секретов 16, wait_stack 8, исключения 8, manifest 5 — пересекающиеся модули, суммарно 72) |
| G3 Integration (live stack) | `AI_RES_REQUIRE_STACK=1 make infra-test-runtime` (после `make reset CONFIRM=yes` и `make up`) | `81 passed`, 0 skipped |
| G4 Contract | `make contracts-check` / `make contracts-test` | `[ok] lint-openapi`, `[ok] breaking`; `19 passed` |
| G5 Security | `make backend-audit` | `No known vulnerabilities found` |
| G5 Security | `cd infra && uv run --locked python scripts/scan_secrets.py` | `0 finding(s)` (в том числе со значениями живых dev-секретов) |
| G5 Supply chain | `infra/scripts/supply_chain.sh` | exit 0: собственные образы api/caddy/minio/mc — `HIGH: 0, CRITICAL: 0` с 3 исключениями (prometheus ×2, x/net в Caddy); сторонние — report-only: otel 61, postgres 26, admin-tools 291, temporal server 146, UI 117 |
| G4/G5 | `make infra-verify-digests` | `10 pinned images, 0 mismatch(es)` |
| Идемпотентность | второй `make up` | exit 0, секреты не перезаписаны |
| G6 Migration | — | N/A: миграций нет (S04). RLS/grants audit — S05 |
| G7 Independent review | см. §11 | слой 2 выполнен, HIGH исправлены; повторный проход не выполнялся |
| G8/G9 | этот отчёт, STATUS, ADL, KNOWN_GAPS, TRACEABILITY | обновлены |

## 10. Security / authorization cases
Runtime (81): порты — публикует только Caddy на 127.0.0.1, внутренние порты недоступны с хоста; MinIO/Temporal UI/Temporal/Postgres недоступны из ingress-сети (с positive control); egress с api и data-сервисов к metadata/интернету/RFC1918/host gateway заблокирован (с positive control); заголовки Caddy (HSTS, CSP, nosniff, Referrer-Policy, без Server), cleartext → 400; hardening из inspect (non-root, `read_only`, `cap_drop ALL`, no-new-privileges, нет privileged/docker.sock/host namespaces, лимиты); секреты не в `docker inspect`, не в окружении процессов api/postgres/minio/proxy, не в логах, не в слоях 4 собственных образов (скан с canary positive control); секреты смонтированы только нужным сервисам; секреты случайны и различны; Postgres: роли без superuser/bypassrls, SCRAM-only (`pg_hba` ⊆ {scram, reject}), TLS обязателен для сети (cleartext отклонён), роли не видят чужие БД, `ai_res_checkpointer` — USAGE без CREATE/ownership, DML на provisioned-таблице работает; Temporal подключён по TLS (`pg_stat_ssl`); образ api без pip/setuptools; namespace `ai-res` и бакеты MinIO с versioning; one-shot jobs идемпотентны при повторном запуске. PERSIST-023: проверена только структурно и по сети для существующих сервисов (G-29); Manager/Worker — S11/S23.
Статические (72): каждое нарушение политики (latest, нет digest, root, не read_only, cap_add, privileged, docker.sock, network_mode, секреты в env, чужие секреты, сети, bind вне проекта и др.) приводит к отказу; пустая модель не проходит.

## 11. Независимое review
Отчёты и disposition: `reviews/S03_security_review.md`, `S03_architecture_review.md`, `S03_silent_failure_review.md`, `S03_code_review.md`, `S03_REVIEW_DISPOSITION.md`. CRITICAL: 0. Все HIGH закрыты изменениями кода и тестами; найденные MEDIUM/LOW частично исправлены, остальные — gaps G-34…G-39 или ACCEPTED. Исправления проверены детерминированно (тесты, runtime), но **повторное независимое review не проводилось** — это основание не присваивать VERIFIED.

## 12. Не выполненные проверки, ограничения, риски
- CI не запускался на GitHub/Linux (G-27): права bind-mount секретов, установка sops/age, сборка MinIO там не проверены.
- Нет интеграционного job (до S04) и oasdiff (G-20); нет подписи образов (G-26).
- Сторонние образы имеют много HIGH/CRITICAL с доступным исправлением (G-24).
- OTel не подключён, redaction отсутствует (G-22/S13); healthcheck api — liveness (G-23).
- Egress Caddy не ограничен (G-34); Temporal без authn/authz (G-36); консоль MinIO достижима с `data` (G-37); сеть Manager/Worker → Temporal не решена (G-38).
- Лимиты ресурсов, retention namespace (72h), срок dev-сертификата и даты исключений — WORKING (G-33).
- Runtime evidence получено на macOS/Docker Desktop (виртуализированные bind mount); поведение на Linux может отличаться.

## 13. Обновлённые документы и статусы
STATUS, ADL (ADR-042…045), KNOWN_GAPS (G-23…G-39), ECC_USAGE, REQUIREMENTS_TRACEABILITY (INF-MVP, SEC-MVP-011/012), CONTEXT_HANDOFF, LOCAL_DEVELOPMENT, RELEASE_AND_VERSIONING, `docs/runbooks/local-stack.md`. CONTRACT_TRACEABILITY_MAP — без изменений (контракты не затрагивались). DECISIONS_PENDING — без изменений (блокирующих вопросов нет; G-39 подтверждается владельцем при NCP).

## 14. Статус DoD
- ✅ `make up` из чистого клона локально (проверено после `make reset CONFIRM=yes` и удаления зашифрованного файла); `make down` останавливает, `make reset CONFIRM=yes` чистит тома.
- ✅ Негативные проверки сегментации и секретов проходят.
- ⚠️ CI исполняет проверки S01–S03 по описанию workflows (actionlint чисто), фактический прогон — нет (G-27); oasdiff и интеграционный job отсутствуют.
- ⚠️ ADR-037: слои 1 (детерминированные проверки) и 3 (adversarial/негативные тесты) выполнены, слой 2 выполнен, HIGH закрыты; повторного прохода нет; слой 4 — подпись security owner в S37.
- ✅ Результаты (`infra/**`, Dockerfile, CI workflow, runbook, S03 report) созданы; заглушек нет.
- ✅ Тесты проверяют поведение (в том числе positive controls), команды и результаты — в §9.
- N/A миграции; ⚠️ observability (OTel не подключён, G-22).
- ⚠️ Нет открытых CRITICAL/HIGH; открытые MEDIUM — в gaps.

## 15. Можно ли начинать следующий этап
Формально нет: по ADR-032 зависимости должны быть DONE (VERIFIED), а S03 — TESTED. Для VERIFIED нужны: повторное независимое review исправлений и/или прогон CI на удалённом Linux-runner; решение владельца, принимать ли G-27 как остаточный риск. Следующий безопасный этап после этого — **S04** (Persistence: Alembic env). Разблокирует S04 (и далее S05).


## 16. Повторная верификация (2026-11-11)

- Повторные независимые review (blind-first, свежий контекст): `reviews/S03_security_rereview.md`, `reviews/S03_silent_failure_rereview.md`. Результат: все 12 прежних HIGH закрыты и проверены; **0 открытых HIGH/CRITICAL**.
- Исправлено по итогам: `tests/runtime/conftest.py` (`pytest.skip` не принимает `pytrace` → ошибка вместо skip); `scan_secrets.py` (исключение «идентификатор» требует `_` или `.`, иначе пропускались hex/слова в нижнем регистре); `check_compose.py` (bind-mount каталога `secrets/` отклоняется; любая сеть кроме `ingress`/`egress` обязана быть internal); `Makefile` (`infra-test-runtime` ставит `AI_RES_REQUIRE_STACK=1`). Добавлены регрессионные тесты (в т.ч. `--profile '*'`).
- Итоговые прогоны: `AI_RES_REQUIRE_STACK=1 make infra-test` 157 passed (76 статических + 81 runtime); `make infra-test-runtime` 81 passed; `make backend-test` 58 passed; `make contracts-test` 19 passed; `make infra-check` 0 нарушений; `scan_secrets` 0 findings; `backend-audit` без известных уязвимостей.
- Один непонятный transient-провал `test_internal_ports_not_reachable_on_host[8000]` (порт открыт на хосте в двух подряд прогонах, затем закрыт; по `docker inspect` api порт не публикует) — вероятно, посторонний процесс на машине; причина не доказана. Тест не отличает опубликованный Docker порт от чужого процесса (см. N4 в re-review).
- Остаточные MEDIUM/LOW из re-review (не блокируют): M-3 Temporal/MinIO без authn от api (G-36, G-37), M-4 неполные имена ключей и исключения `scan_secrets`, M-5 узость supply-chain gate (G-35), M-6 fork-PR в CI (G-27), N5–N10, LOW по `check_compose`. Слой 4 ADR-037 (security owner) — S37.

## 17. Прогон на GitHub Actions (2026-11-11)

Ветка `ci/s03-first-run`, коммит `5272c69`. `contracts` (run 42980597940): success. `ci` (run 42980598813): `backend`, `infra-static`, `infra-runtime` — success, шаг runtime-тестов выполнялся с `AI_RES_REQUIRE_STACK=1` (пропуск = провал). G-27 и G-13 закрыты. G-20 (oasdiff в CI) и G-21 (`@asyncapi/parser` на Node 22) остаются открытыми: прогон не добавил эти проверки. Прогон на `main`/PR не выполнялся.
