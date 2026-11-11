# ecc-precedence.md — Приоритет правил AI RES над Everything Claude Code (ECC)

**Нормативные источники:** `CLAUDE.md` · `.claude/rules/*.md` (AI RES)

ECC (агенты, команды, Skills, `.claude/rules/ecc/`, `.claude/AGENTS.md`) — вспомогательный инструментарий разработки. Он не является нормативным источником AI RES.

---

## Иерархия

1. `docs/architecture/AI_RES_Document_Registry_v4.1.md` и canonical документы из него.
2. `CLAUDE.md` и правила AI RES в `.claude/rules/*.md`.
3. ECC: `.claude/rules/ecc/`, Skills, агенты, команды, `.claude/AGENTS.md`.

При расхождении действует уровень с меньшим номером. Конфликт между ECC и AI RES не разрешать в пользу ECC; при неясности — зафиксировать и спросить владельца проекта.

---

## Известные расхождения ECC с правилами AI RES

| ECC | Правило AI RES |
|---|---|
| `api-design`: offset-пагинация, собственные error envelopes | Только cursor-based пагинация; ошибки — RFC 9457 Problem Details (`api-and-contracts.md`) |
| `postgres-patterns`, `database-reviewer`: Supabase RLS (`auth.uid()`) | Transaction-local tenant context, `ENABLE FORCE` RLS, default deny (`database-and-migrations.md`) |
| `database-migrations`: Prisma/Drizzle/Kysely/Django/golang-migrate | Только Alembic + SQLAlchemy 2.x |
| `fastapi-reviewer`, `/fastapi-review`, примеры FastAPI в `python-testing` | Web-фреймворк — WORKING; не выбирать FastAPI по примерам ECC без решения владельца |
| `architecture-decision-records`: `docs/adr/` | Решения фиксируются через владельца в `AI_RES_Decisions_Assumptions_Risks_Uncertainty_v1.2.md` и Registry; `docs/adr/` не создавать |
| `tdd-guide`, `AGENTS.md`: «80% coverage» как критерий готовности | Покрытие — дополнительная метрика; Definition of Done — `testing-and-verification.md` и Implementation Spec §8 |
| `development-workflow.md`: research через `gh search`/Exa/web | Не отправлять код, документы или идентификаторы AI RES во внешние сервисы без согласия владельца |
| `development-workflow.md`, `git-workflow.md`, `AGENTS.md`: commit/push/PR | Commit и push — только по явной просьбе пользователя |
| Описания агентов «MUST BE USED» / «PROACTIVELY» | Не обязательства проекта; агенты ECC не заменяют независимый QA Worker и человеческое approval |

---

## Механизмы, не включённые в проекте

Hooks ECC (install-state: hook consent отклонён), MCP-серверы из `.claude/mcp-configs/`, continuous learning, автономные loops и auto-update не включаются без отдельного решения владельца. Skills, требующие этих механизмов (`continuous-learning*`, `ck`, `delivery-gate`, `plankton-code-quality`, `loop`), используются только после такого решения.

---

## Когда запускать агентов-ревьюеров (решение владельца, 2026-11-11)

Агенты-ревьюеры ECC (`security-reviewer`, `database-reviewer`, `code-reviewer`, `python-reviewer`, `silent-failure-hunter`, `architect` и др.) запускаются **только на этапах, где независимая проверка действительно необходима**, и тогда запускаются без дополнительной просьбы пользователя:

1. **Обязательно:** P0-этапы по ADR-037 (S03, S05, S07, S37) и любой этап, чей промпт (раздел «ECC: обязательные agents» / Definition of Done) требует независимого review. Без него этап не выше TESTED.
2. **По решению исполнителя, с указанием причины в отчёте:** этап вносит изменение в границы безопасности, RLS/роли, миграции с данными, криптографию, контракты с обратной совместимостью или fail-closed поведение, даже если он не P0.
3. **Не запускать:** для документационных, scaffold- и малых изменений без таких рисков; достаточно слоёв 1–2 ADR-037 (детерминированные проверки и тесты). Причину пропуска записать в отчёт этапа (раздел «Независимое review»).

Состав и порядок: blind-first (агент не читает отчёт автора), профильный агент по области (БД — `database-reviewer`, безопасность — `security-reviewer`, скрытые отказы — `silent-failure-hunter`). Агенты read-only, их находки и расположение отчётов — в `docs/implementation/reviews/<ID>_*.md`; CRITICAL/HIGH исправляются до VERIFIED. Агенты не заменяют человеческое approval и независимый QA Worker.
