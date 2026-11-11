# ECC_USAGE — использование Everything Claude Code

ECC 2.2.3 (manual project-local install) — dev-time инструментарий (ADR-007; оценка — `reviews/ECC_TRUST_ASSESSMENT.md`). Иерархия: Registry/нормативные документы → `CLAUDE.md` и `.claude/rules/*.md` → ECC (`.claude/rules/ecc-precedence.md`). ECC agents — инструменты разработки, не Runtime Workers AI RES; не заменяют QA Worker и human approval.

Инвентарь (проверено 2026-11-10): 71 agents, 59 skills, 98 commands в `.claude/`; `.claude/rules/ecc/` (development-workflow, git-workflow, python-patterns); hooks не включены; MCP не подключены; нативных плагинов нет. Проектные `.claude/agents/` или `skills/` AI RES не создавались — потребности нет (существующие покрывают компетенции; пробелы ниже компенсируются процессом).

## 1. Карта компетенций → фактические имена

| Компетенция | Agents | Skills | Commands | Ограничения AI RES |
|---|---|---|---|---|
| Архитектура и планирование | `architect`, `planner`, `code-architect`, `code-explorer` | — | `/plan` | Нормативные решения — только владелец |
| Python / backend | `python-reviewer`, `fastapi-reviewer` (ADR-008), `type-design-analyzer` | `python-patterns`, `error-handling` | `/python-review`, `/fastapi-review`, `/build-fix` | — |
| PostgreSQL / миграции | `database-reviewer` | `postgres-patterns`, `database-migrations` | — | Только Alembic; RLS — transaction-local context, не Supabase |
| API / контракты | — (нет агента) | `contract-first`, `api-design` | — | Cursor pagination, RFC 9457; review — `code-reviewer` + `type-design-analyzer` |
| Temporal / LangGraph | — (нет агента) | `eval-harness` (агентные критерии) | — | Компенсация: `architect` + `silent-failure-hunter` + `python-reviewer` |
| Безопасность | `security-reviewer` | — | `/security-review` (встроенная), `/security-scan` (только с согласия: npm) | Внешние сервисы — с согласия владельца |
| Docker / CI / DevOps | — (нет агента); `build-error-resolver` для сборки | `production-audit`, `verification-loop` | `/quality-gate` | Компенсация: `security-reviewer` + `architect` |
| Тестирование / QA | `tdd-guide`, `pr-test-analyzer`, `e2e-runner` | `python-testing`, `tdd-workflow`, `e2e-testing`, `ai-regression-testing` | `/test-coverage`, `/react-test` | DoD — testing-and-verification.md, не 80% coverage |
| Независимое review | `code-reviewer`, `silent-failure-hunter`, `comment-analyzer` | — | `/code-review` (локально) | PR-режим — только с разрешения |
| Frontend | `typescript-reviewer`, `react-reviewer`, `a11y-architect` | `e2e-testing` | `/react-review`, `/react-build`, `/react-test` | `browser-qa` требует browser MCP — не используется |
| Retrieval / evaluation | `rag-pipeline-reviewer`, `mle-reviewer` | `eval-harness` | — | Пороги — OD-02 |
| Performance | `performance-optimizer` | — | — | SLO — OD-02 |
| Документация | `doc-updater` | — | — | Не менять `docs/architecture/` |
| Запрещено без решения владельца | — | `architecture-decision-records` (docs/adr), `continuous-learning*`, `ck`, `delivery-gate`, `plankton-code-quality`, `loop` | `/auto-update`, `/loop-start`, `/evolve`, `/learn*`, `/instinct-*` | ecc-precedence.md |

Обязательный набор на каждый этап задан в промпте этапа (раздел 8).

## 2. Журнал использования

| Этап | Инструмент | Зачем | Результат |
|---|---|---|---|
| S00 | — (собственная работа) | Сверка Registry/SHA-256 и валидация контрактов — подходящего ECC инструмента нет | S00 report |
| S00 | `architect` | Независимое review пакета S00 | 15 замечаний (3 HIGH), все учтены (S00 report §7) |
| PREP | инвентаризация `.claude/` (agents/skills/commands/settings/install-state) | Проверка фактической доступности и trust assessment | `reviews/ECC_TRUST_ASSESSMENT.md` |
| PREP | `architect` | Независимое review roadmap, ADR и промптов | 14 замечаний (4 HIGH), `reviews/PREP_PHASE_REVIEW.md` |
| PREP | `database-reviewer` | Review persistence-решений (ADR-011…016, ADR-024) и промптов S04–S06 | см. `reviews/PREP_PHASE_REVIEW.md` |
| PREP | `security-reviewer` | Review security-решений (ADR-015, 017, 020, 022, 031) и промптов S03, S07, S16 | см. `reviews/PREP_PHASE_REVIEW.md` |
| S01 | `code-reviewer`, `silent-failure-hunter` | Независимое review contracts toolchain | 5 HIGH + 8 MEDIUM, исправлено; `reviews/S01_REVIEW.md`. `planner`, `architect`, `verification-loop` не использованы (отклонение, S01 report §8) |

## 3. Дополнительные инструменты (ADR-040)
SessionStart hook `session-brief`, `CONTEXT_HANDOFF.md`, Context7 MCP (через ECC `docs-lookup`), Serena MCP (совместно с `code-explorer`, `code-reviewer`). Промпты и ограничения — `tooling/`. ECC `ck` и `strategic-compact` hook не включались (глобальные записи / скрипт не установлен).
| S02 | `fastapi-reviewer`, `security-reviewer`, `type-design-analyzer` | Независимое review platform primitives | HIGH исправлены, `reviews/S02_REVIEW.md`; повторное review не проводилось |
| S03 | `security-reviewer`, `architect`, `silent-failure-hunter`, `code-reviewer` | Независимое blind-first review инфраструктуры (ADR-037 слой 2); DevOps-агента в ECC нет — компенсация: `security-reviewer` + `architect` | результаты и устранение — `reviews/S03_*.md` |
| S03 | `planner`, `verification-loop`, `production-audit` | `planner`/`/plan` заменены планом по срезам, согласованным с владельцем; `verification-loop`, `production-audit` не запускались | отмечено в S03 report |
| S04 | `code-reviewer`, `database-reviewer`, `security-reviewer`, `silent-failure-hunter` | Независимое параллельное read-only review (ADR-035); `database-reviewer` — с учётом ecc-precedence (без Supabase-RLS) | CRITICAL/HIGH — 0; MEDIUM/LOW исправлены или записаны в gaps, `reviews/S04_REVIEWS.md`; повторного прохода агентов после исправлений не было |
| S04 | `planner`, `architect`, `python-reviewer`, `tdd-guide`, `pr-test-analyzer`; skills `python-patterns`, `python-testing`, `tdd-workflow`, `postgres-patterns`, `database-migrations`, `verification-loop`; commands `/plan`, `/code-review`, `/quality-gate`, `/python-review`, `/test-coverage`, `/security-review` | **Не запускались** (требовались промптом §8). Компенсация: план по вертикальным срезам согласован внутри сессии; тесты писались вместе с кодом и проверены мутациями; профильные проверки Python — ruff/mypy --strict/import-linter; полнота тестов — `silent-failure-hunter` (вакуозные тесты) вместо `pr-test-analyzer`; соответствие архитектуре — прямая сверка с DOC-068/072 и ADR в review `database-reviewer`; `/security-review` заменён `security-reviewer`. Отклонение от порядка применения промпта фиксируется здесь и в отчёте | отмечено |
| S06 | `database-reviewer`, `silent-failure-hunter`; навыки `postgres-patterns`, `database-migrations` — как ориентир, без запуска skill-инструментов | Независимое read-only review (ADR-035); `database-reviewer` с учётом ecc-precedence (без Supabase-RLS). `planner`, `architect`, `code-reviewer`, `python-reviewer`, `tdd-guide`, `pr-test-analyzer`, `type-design-analyzer`, `/plan`, `/quality-gate`, `/test-coverage`, `verification-loop` в этой сессии НЕ запускались: компенсация — тесты вместе с кодом, `make pre-pr`; пробел отмечен в reviews/S06_REVIEWS.md §3 | database-reviewer: 1 CRITICAL, 4 HIGH, 6 MEDIUM, 6 LOW — CRITICAL/HIGH устранены или вынесены в G-72/OD-14 (reviews/S06_REVIEWS.md) |
