# CONTEXT_HANDOFF — состояние для продолжения работы (обновлять в конце каждого этапа и сессии)

**Обновлено:** 2026-11-11 (конец S03) · Автоподстановка в сессию: `.claude/hooks/session-brief.mjs` (SessionStart: startup/resume/clear/compact). Первые 60 строк файла попадают в контекст — держи файл коротким.

## Где мы
- Подготовительная фаза завершена. S00 IMPLEMENTED, **S01 и S02 VERIFIED/DONE**, **S03 VERIFIED/DONE** (локально и CI на GitHub Actions Linux; G-27 закрыт): локальный стек Compose с TLS Postgres, SOPS/age, SBOM/скан; 81 runtime-тест + 76 статических + backend 58 + contracts 19. Отчёт: `increments/S03_local_infrastructure_secrets_ci_REPORT.md`; review: `reviews/S03_*.md`, disposition — `reviews/S03_REVIEW_DISPOSITION.md`.
- S03 повторно проверен независимо (`reviews/S03_security_rereview.md`, `reviews/S03_silent_failure_rereview.md`): 0 открытых HIGH/CRITICAL. CI на Linux зелёный (ветка `ci/s03-first-run`, коммит `5272c69`). Остаётся: решение владельца по остаточным рискам (G-34…G-39, MEDIUM из re-review). **Следующий этап S04 не начат** — запуск только по указанию владельца; зависимость S03 DONE выполнена.
- Стек сейчас может быть поднят (`make up`); остановить: `make down` (тома сохраняются), удалить данные: `make reset CONFIRM=yes`. Секреты: `~/.config/ai-res/age/keys.txt` (резервная копия вне репозитория!), `infra/secrets/encrypted/local.enc.yaml` per-machine, git-ignored.
- Git commit не выполнялся (OD-06) — коммит только по просьбе пользователя. Всё S03 лежит в рабочем дереве (infra/, backend/Dockerfile, .github/workflows, docs).

## Порядок действий в новой сессии
1. `CLAUDE.md` → `IMPLEMENTATION_CHARTER.md` → этот файл → `IMPLEMENTATION_STATUS.md`.
2. Следующий этап: `increments/prompts/<ID>_*.md` (самодостаточный). Старт только если зависимости DONE (ADR-032).
3. Инструменты: `tooling/README.md` (Context7, Serena, session-brief, handoff).

## Ключевые решения (полный список — ARCHITECTURE_DECISION_LOG.md, ADR-001…041)
- Стек: Python 3.13, uv, FastAPI async, SQLAlchemy 2 + psycopg 3 + Alembic, React+TS+Vite, Caddy, Testcontainers.
- Контракты: `contracts/` — зеркало canonical (ADR-009); недостающие endpoint — overlay WORKING (ADR-038); breaking-diff собственный (ADR-039).
- Checkpointer — через broker в API (ADR-036); P0-этапы S03/S05/S07/S37 — независимая проверка ADR-037; createTask — внутри активной Operation (ADR-012, NCP-08).

## Команды
`make contracts-check` · `make contracts-test` · `make backend-check` · `make backend-test` · `make up` · `make down` · `make reset CONFIRM=yes` · `make infra-check` · `make infra-test` · `make infra-test-runtime` · `make infra-verify-digests` · `make backend-audit` · `infra/scripts/supply_chain.sh` · `python3 docs/implementation/tools/gen.py .` · `…/check_prompts.py`. STATUS не перегенерируется (ведётся вручную); промпты/ROADMAP/ADL — из `tools/stages.py`, `adrs.py`.

## Открытое (владелец)
OD-01 провайдер LLM/egress (S16) · OD-02 SLO/пороги/retention (S33, S38) · OD-03 wire names, Bifrost security review · OD-04 NCP-01…08 · OD-05 risk calibration · OD-06 git commit. Подробно: `DECISIONS_PENDING.md`.

## Известные ограничения среды
Docker работает; Node 26 (проект целится в 22); oasdiff не установлен (G-20/G-21); sops/age/actionlint/hadolint установлены через brew; Linux-CI не проверялся (G-27). Serena (uvx из GitHub) — запуск вне MCP заблокирован классификатором, проверка через `/mcp`.

## Правила, которые легко потерять
Не менять `docs/architecture/`; не изобретать WORKING-значения; Readiness Gate перед каждым WorkerRun; Worker без DB credentials; не отправлять код/идентификаторы AI RES во внешние сервисы (Context7 — только имена библиотек и общие вопросы).
