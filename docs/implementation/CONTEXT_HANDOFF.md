# CONTEXT_HANDOFF — состояние для продолжения работы (обновлять в конце каждого этапа и сессии)

**Обновлено:** 2026-11-11 (конец S04) · Автоподстановка в сессию: `.claude/hooks/session-brief.mjs` (SessionStart: startup/resume/clear/compact). Первые 60 строк файла попадают в контекст — держи файл коротким.

## Где мы
- S00 IMPLEMENTED, **S01–S04 VERIFIED/DONE**. S03 — локальный Compose-стек (TLS Postgres, SOPS/age, CI). **S04 (2026-11-11)** — Alembic env + PDB-0001 (18 схем, роли, USAGE-гранты), provisioning ролей (`infra/config/postgres/provision_roles.sql`), одноразовая служба `migrate`, `db/` (engine, Unit of Work, tenant context), audit SQL + `audit.sh` gate, reviewed `backend/ops/postgres/schema_snapshot.sql`. Тесты: backend 159 (PostgreSQL 16.15 Testcontainers), runtime 95, infra static 77, contracts 19. Отчёт: `increments/S04_persistence_foundation_REPORT.md`; review: `reviews/S04_REVIEWS.md` (0 HIGH/CRITICAL); ADR-046…049.
- **Следующий этап S05 (Core tenant и execution schema + RLS) не начат** — по указанию владельца; зависимость S04 DONE. Перед S05: прогнать ветку в GitHub Actions (G-43), решить G-46 (ADR вне `tools/adrs.py`: **не запускать `tools/gen.py`** — перезапишет журнал).
- Стек может быть поднят (`make up` теперь запускает и `migrate`); `make down` сохраняет тома, `make reset CONFIRM=yes` удаляет. Если правите `entrypoint.sh` (pg_hba) — `docker compose … restart postgres`. Секреты: `~/.config/ai-res/age/keys.txt` (резервная копия вне репозитория!), `infra/secrets/encrypted/local.enc.yaml` per-machine; `make secrets-dev` добавляет только недостающие секреты.
- Git commit не выполнялся (OD-06): весь S03-репозиторий закоммичен и смержен ранее; S04 лежит в рабочем дереве (ветку/коммит делать только по просьбе пользователя).
- Правила S05: каждая новая таблица — RLS ENABLE+FORCE + политика + запись в `rls_coverage.sql` `exempt` только с причиной; `make db-snapshot` и разбор diff; sabotage-тест на каждое новое нарушение; PERSIST-002 (previous revision) и PERSIST-005..014 на доменных таблицах.

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

## Известные ограничения среды
Docker работает; Node 26 (проект целится в 22); oasdiff не установлен (G-20/G-21); sops/age/actionlint/hadolint установлены через brew; Linux-CI для S04 не проверялся (G-43). Serena (uvx из GitHub) — запуск вне MCP заблокирован классификатором, проверка через `/mcp`.

## Правила, которые легко потерять
Не менять `docs/architecture/`; не изобретать WORKING-значения; Readiness Gate перед каждым WorkerRun; Worker без DB credentials; не отправлять код/идентификаторы AI RES во внешние сервисы (Context7 — только имена библиотек и общие вопросы).
