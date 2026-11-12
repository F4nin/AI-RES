# CONTEXT_HANDOFF — состояние для продолжения работы (обновлять в конце каждого этапа и сессии)

**Обновлено:** 2026-11-12 (S10 VERIFIED) · Автоподстановка в сессию: `.claude/hooks/session-brief.mjs` (SessionStart: startup/resume/clear/compact). Первые 60 строк файла попадают в контекст — держи файл коротким.

## Где мы
- S00 IMPLEMENTED, **S01–S04 VERIFIED/DONE**. S03 — локальный Compose-стек (TLS Postgres, SOPS/age, CI). **S04 (2026-11-11)** — Alembic env + PDB-0001 (18 схем, роли, USAGE-гранты), provisioning ролей (`infra/config/postgres/provision_roles.sql`), одноразовая служба `migrate`, `db/` (engine, Unit of Work, tenant context), audit SQL + `audit.sh` gate, reviewed `backend/ops/postgres/schema_snapshot.sql`. Тесты: backend 159 (PostgreSQL 16.15 Testcontainers), runtime 95, infra static 77, contracts 19. Отчёт: `increments/S04_persistence_foundation_REPORT.md`; review: `reviews/S04_REVIEWS.md` (0 HIGH/CRITICAL); ADR-046…049.
- **S05 DONE/VERIFIED и влит в `main`** (PR #3, merge 3221578, 2026-11-11): ревизии `0002`–`0006`, ADR-050…055, `db/cas.py`, `modules/{events,operations,tasks,worker_runs,readiness,idempotency}/`; backend 297 passed, runtime 95, GitHub Actions на Linux зелёный; три раунда review (`reviews/S05_REVIEWS.md`), отчёт `increments/S05_core_tenant_execution_schema_rls_REPORT.md`. Открытые gaps после S05: G-48…G-68 (`KNOWN_GAPS.md`); для S06 важны G-59 (индексы под FK), G-60/G-61 (Gate/переходы), правило «каждая новая tenant-таблица: RLS ENABLE+FORCE + политика + owner-политика `p_<table>_owner_migration` (иначе падает `rls_coverage.sql`)». **Решение владельца (2026-11-11):** OD-13 (формы `dataschema`/`source`) и NCP-09…11 решаются перед этапами, на которые влияют (событийные: не позднее S10), не сейчас — S06 их не блокирует. **Следующий этап: S06** (Domain content schema): ветку `feat/s06-domain-content-schema` создать от актуального `main` (после слияния PR с этим handoff). Перед PR — `make pre-pr`.
- **S06 VERIFIED по решению владельца и влит в `main` (PR #5, 2026-11-11):** ревизии `0007`–`0011` (requirements, sources, knowledge.extraction_records, artifacts, governance, context, decisions, traceability, event history), репозитории `modules/{requirements,sources}`, ADR-056…060, G-69…G-74, OD-14; три review (`reviews/S06_REVIEWS.md`; дельта последнего не пересматривалась); Linux CI зелёный (runs 43074829225, 43074859429); backend 331, runtime 95. Открыто: репозитории остальных агрегатов (G-69), outbox новых агрегатов (G-70, OD-13 не позднее S10), словарь статусов артефакта (OD-14). **Следующий этап: S07** (Identity, Local Auth, Policy Engine, Audit, Idempotency); ветку создать от актуального `main`; перед PR — `make pre-pr`.
- Стек может быть поднят (`make up` теперь запускает и `migrate`); `make down` сохраняет тома, `make reset CONFIRM=yes` удаляет. Если правите `entrypoint.sh` (pg_hba) — `docker compose … restart postgres`. Секреты: `~/.config/ai-res/age/keys.txt` (резервная копия вне репозитория!), `infra/secrets/encrypted/local.enc.yaml` per-machine; `make secrets-dev` добавляет только недостающие секреты.
- Git commit не выполнялся (OD-06): весь S03-репозиторий закоммичен и смержен ранее; S04 лежит в рабочем дереве (ветку/коммит делать только по просьбе пользователя).
- Правила S05: каждая новая таблица — RLS ENABLE+FORCE + политика + запись в `rls_coverage.sql` `exempt` только с причиной; `make db-snapshot` и разбор diff; sabotage-тест на каждое новое нарушение; PERSIST-002 (previous revision) и PERSIST-005..014 на доменных таблицах.

- **S07 VERIFIED по решению владельца и влит в `main` (PR #6, 2026-11-12):** identity/local auth/MFA/bootstrap/Policy Engine/audit/idempotency/service tokens, миграции 0012–0013, ADR-061…073, OD-16. Два прохода независимого review (`reviews/S07_REVIEWS.md` §5–§6): CRITICAL/HIGH нет; Linux CI зелёный (runs 43111752244, 43111759690). Открыто: NCP-12 (PROPOSED), OD-15 (матрица политик WORKING до проверки на S08+), G-75…G-83, подсеть app 172.28.20.0/24 (WORKING). **Следующий этап: S08**; ветку создать от актуального `main`. Порядок на будущее (решение владельца): реализация → ревью → исправления → ОДИН `make pre-pr` и CI.

- **S08 VERIFIED (2026-11-12), PR #7 (`feat/s08-read-only-api-slices`), Linux CI зелёный (ci 43186306478/43186313460, contracts 43186306145/43186313578); влить в `main` по решению владельца:** 12 GET, ADR-074…077, политика read 2026-11-12.1 (только члены проекта + org AUDITOR, WORKING), `make pre-pr` ok (backend 872). Review: `reviews/S08_REVIEWS.md`. Pin `caddy:2.11.9` обновлён (Docker Hub переопубликовал индекс; Linux-манифесты идентичны). Следующий этап: **S09** (ветку создать от актуального `main` после слияния PR #7). Открыто: G-84…G-90, OD-17.

- **S09 VERIFIED (2026-11-12), PR #8, Linux CI зелёный (ci 43203466196/43203684744, contracts 43203466171/43203684738), влит в `main`:** 6 команд записи, миграция 0014, ADR-078…083, G-91…G-97, OD-18, политика 2026-11-12.2 (WORKING), секрет `idempotency_keyring`. `make pre-pr` ok (backend 924, infra 186, runtime 99), review без CRITICAL/HIGH (`reviews/S09_REVIEWS.md`). `createTask` — S21. Следующий этап: S10 (сначала OD-13). Загрузки в стеке отвечают 503 до S27 (G-92).

- **S10 VERIFIED (2026-11-12), PR #9 (`feat/s10-outbox-dispatcher-inbox-cloudevents`), Linux CI зелёный (ci 43220712053/43220722294, contracts 43220712147/43220722299); влить в `main` по решению владельца:** OD-13 решён (ADR-084), миграция 0015, dispatcher/consumer/contract/CLI, ADR-085/086, G-98…G-103, NCP-13, runbook `docs/runbooks/outbox.md`; `make pre-pr` ok (backend 964, infra 186, runtime 99, contracts 22); review без CRITICAL/HIGH. Dispatcher не в Compose (G-98) — закроется первым consumer'ом (S12). Следующий этап: S11 (ветку создать от актуального `main` после слияния PR #9). Нестабильный тест S08 исправлен (PR #10, смержен, `derandomize` + `crc32`).

## Порядок действий в новой сессии
1. `CLAUDE.md` → `IMPLEMENTATION_CHARTER.md` → этот файл → `IMPLEMENTATION_STATUS.md`.
2. Следующий этап: `increments/prompts/<ID>_*.md` (самодостаточный). Старт только если зависимости DONE (ADR-032).
3. Инструменты: `tooling/README.md` (Context7, Serena, session-brief, handoff).

## Ключевые решения (полный список — ARCHITECTURE_DECISION_LOG.md, ADR-001…041)
- Стек: Python 3.13, uv, FastAPI async, SQLAlchemy 2 + psycopg 3 + Alembic, React+TS+Vite, Caddy, Testcontainers.
- Контракты: `contracts/` — зеркало canonical (ADR-009); недостающие endpoint — overlay WORKING (ADR-038); breaking-diff собственный (ADR-039).
- Checkpointer — через broker в API (ADR-036); P0-этапы S03/S05/S07/S37 — независимая проверка ADR-037; createTask — внутри активной Operation (ADR-012, NCP-08).

## Команды
`make contracts-check` · `make contracts-test` · `make backend-check` · `make backend-test` · `make up` · `make down` · `make reset CONFIRM=yes` · `make migrate` · `make test-integration` · `make backend-test-unit` · `make db-snapshot` · `make infra-check` · `make infra-test` · `make infra-test-runtime` · `make infra-verify-digests` · `make backend-audit` · `infra/scripts/supply_chain.sh` · `python3 docs/implementation/tools/gen.py .` · `…/check_prompts.py`. STATUS не перегенерируется (ведётся вручную); промпты/ROADMAP/ADL — из `tools/stages.py`, `adrs.py`.

## Открытое (владелец)
OD-01 провайдер LLM/egress (S16) · OD-02 SLO/пороги/retention (S33, S38) · OD-03 wire names, Bifrost security review · OD-04 NCP-01…08 · OD-05 risk calibration · OD-06 git commit. Подробно: `DECISIONS_PENDING.md`.

## Перед PR (урок S05)
`make pre-pr` — всё, что запускает CI (contracts, backend, infra static, `make up` с миграциями на ЛОКАЛЬНУЮ dev-БД, runtime-набор). Изменение миграций/схемы/контрактов влияет на проверки вне `backend/` (в S05 runtime-тест зашил head S04 и упал только в CI). Не зашивать в тесты номера ревизий/версий: вычислять из источника. Сбои внешних сервисов при сборке образов (sum.golang.org, git clone) — повторяются внутри Dockerfile (`retry`), проверка пинов и GOSUMDB остаются включёнными.

## Известные ограничения среды
Docker работает; Node 26 (проект целится в 22); oasdiff не установлен (G-20/G-21); sops/age/actionlint/hadolint установлены через brew; Linux-CI для S04 зелёный (G-43; Testcontainers без TLS остаётся). Serena (uvx из GitHub) — запуск вне MCP заблокирован классификатором, проверка через `/mcp`.

## Правила, которые легко потерять
Не менять `docs/architecture/`; не изобретать WORKING-значения; Readiness Gate перед каждым WorkerRun; Worker без DB credentials; не отправлять код/идентификаторы AI RES во внешние сервисы (Context7 — только имена библиотек и общие вопросы).
