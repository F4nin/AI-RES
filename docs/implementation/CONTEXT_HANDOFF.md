# CONTEXT_HANDOFF — состояние для продолжения работы (обновлять в конце каждого этапа и сессии)

**Обновлено:** 2026-11-11 · Автоподстановка в сессию: `.claude/hooks/session-brief.mjs` (SessionStart: startup/resume/clear/compact). Первые 60 строк файла попадают в контекст — держи файл коротким.

## Где мы
- Подготовительная фаза завершена (`reviews/PREP_PHASE_REPORT.md`). S00 IMPLEMENTED, **S01 VERIFIED/DONE**, **S02 VERIFIED/DONE** (56 тестов, 2 прохода review), **S03 READY** (следующий; P0 — ADR-037: slой 1–3 + sign-off в S37; Dockerfile должен запускать uvicorn с `log_config=None`). Блокированы: S16, S33, S38 и зависимые (OD-01, OD-02).
- Есть `contracts/` (toolchain) и `backend/` (platform primitives без БД, роутов нет). Context7 и Serena включены в settings.local.json — активны после перезапуска. Git commit не выполнялся (OD-06) — коммит только по просьбе пользователя.

## Порядок действий в новой сессии
1. `CLAUDE.md` → `IMPLEMENTATION_CHARTER.md` → этот файл → `IMPLEMENTATION_STATUS.md`.
2. Следующий этап: `increments/prompts/<ID>_*.md` (самодостаточный). Старт только если зависимости DONE (ADR-032).
3. Инструменты: `tooling/README.md` (Context7, Serena, session-brief, handoff).

## Ключевые решения (полный список — ARCHITECTURE_DECISION_LOG.md, ADR-001…041)
- Стек: Python 3.13, uv, FastAPI async, SQLAlchemy 2 + psycopg 3 + Alembic, React+TS+Vite, Caddy, Testcontainers.
- Контракты: `contracts/` — зеркало canonical (ADR-009); недостающие endpoint — overlay WORKING (ADR-038); breaking-diff собственный (ADR-039).
- Checkpointer — через broker в API (ADR-036); P0-этапы S03/S05/S07/S37 — независимая проверка ADR-037; createTask — внутри активной Operation (ADR-012, NCP-08).

## Команды
`make contracts-check` · `make contracts-test` · `make backend-check` · `make backend-test` · `python3 docs/implementation/tools/gen.py .` · `…/check_prompts.py`. STATUS не перегенерируется (ведётся вручную); промпты/ROADMAP/ADL — из `tools/stages.py`, `adrs.py`.

## Открытое (владелец)
OD-01 провайдер LLM/egress (S16) · OD-02 SLO/пороги/retention (S33, S38) · OD-03 wire names, Bifrost security review · OD-04 NCP-01…08 · OD-05 risk calibration · OD-06 git commit. Подробно: `DECISIONS_PENDING.md`.

## Известные ограничения среды
Docker daemon не запущен; Node 26 (проект целится в 22); oasdiff не установлен (G-20/G-21). Serena (uvx из GitHub) — запуск вне MCP заблокирован классификатором, проверка через `/mcp`.

## Правила, которые легко потерять
Не менять `docs/architecture/`; не изобретать WORKING-значения; Readiness Gate перед каждым WorkerRun; Worker без DB credentials; не отправлять код/идентификаторы AI RES во внешние сервисы (Context7 — только имена библиотек и общие вопросы).
