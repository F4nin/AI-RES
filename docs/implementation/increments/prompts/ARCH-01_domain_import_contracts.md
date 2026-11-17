# ARCH-01 — Контракты импортов между доменными модулями

**Основание:** ADR-114, поручение владельца 2026-11-17 по AGENTS.md §10. Мини-этап после DONE CI-01, до S17; не запускает S16/SLICE-01.

## 1. Цель и scope

Зафиксировать текущий ациклический граф `ai_res.modules` контрактами import-linter: верхние слои могут импортировать нижние; обратное запрещено. Равноправные доменные модули независимы, включая непрямые импорты. Новые модули требуют явной классификации. Состав уточнить по актуальному графу и записать техническим ADR (ADR-120).

Разрешённые файлы: `backend/pyproject.toml`, `backend/tests/architecture/`, implementation-промпт, ADR, status/handoff, traceability, ECC и отчёт/review. Продуктовый код, API/события, миграции, зависимости, Compose/CI, canonical и конфигурация инструментов не меняются.

## 2. Источники и зависимости

- AGENTS.md целиком, tooling/CONTEXT_RETENTION.md, CLAUDE.md, Registry v4.1; canonical paths проверяются по Registry.
- Spec v1.22 §3, §8 и addenda v1.22/v1.22.1; Architecture Concept v4.6 (modular Backend); Domain Model v1.9 §3 и application service interfaces/domain events.
- IMPLEMENTATION_CHARTER, ROADMAP, STATUS, HANDOFF, DECISIONS_PENDING, KNOWN_GAPS, QUALITY_GATES, TEST_STRATEGY, ECC_USAGE; ADR-114.
- CI-01 VERIFIED/DONE. Проверить актуальные Git refs, чистоту дерева, 12 существующих контрактов и установленную lock-версию import-linter.

## 3. План

1. Read-only архитектурное исследование текущего графа и семантики установленного import-linter; зафиксировать точный состав слоёв, расхождения и ограничения.
2. Добавить `layers` с `containers`/`exhaustive` и отдельный `independence` для верхнего слоя. Сохранить существующие контракты и исключения.
3. Проверить реальные production-опции на синтетических пакетах: разрешённый граф, прямые/непрямые нарушения, новый незаявленный модуль, полнота списка peer-модулей.
4. Локальные проверки, отдельное blind-first review, исправления; обновить evidence/контекст.
5. Commit → push → PR → Linux CI по точному SHA → merge → проверить состояние и остановиться.

## 4. ECC

| Тип | Имя | Применение |
|---|---|---|
| agent | `architect` | Отдельное read-only исследование перед реализацией: граф, слои, границы и точный scope |
| agent | `code-reviewer` | Независимое blind-first review реализации, сохранности исходных контрактов и scope |
| agent | `pr-test-analyzer` | Независимое blind-first review обнаружения нарушений и отсутствия ложного PASS |
| skill | `verification-loop` | Явно прочитанный checklist основного исполнителя: Makefile/CI, проверки, diff, секреты и evidence |

Нативные Claude agents/slash commands не объявляются запущенными. Роли применяются через отдельных Codex-агентов; checklist — вручную. Общее и профильное review полезны для предотвращения ложного зелёного результата архитектурного gate и обязательны для DoD этого мини-этапа. Security/database review не требуются: runtime authorization, SQL/RLS, криптография и миграции не меняются.

## 5. Проверки и DoD

- 12 прежних контрактов сохранены; все 14 контрактов проходят на текущем коде без новых исключений.
- Синтетические пакеты используют точные опции новых production-контрактов. Запрещённые импорты ломают ожидаемый контракт с exit 1, разрешённые проходят с exit 0; проверяются оба направления peer-импортов и непрямые пути.
- Незаявленный дочерний модуль ломает exhaustive; каждый модуль верхнего слоя включён в independence.
- `make pre-push-fast`, полный `make -j1 pre-pr`, скан секретов и `git diff --check` проходят. Локальный стек строго dev/test, volumes сохраняются; отложенные backup/два инфраструктурных сценария не запускаются.
- Linux `ci` и `contracts`, включая дополнительные audit/digest/supply-chain gates, проходят на опубликованном SHA. Findings CRITICAL/HIGH устранены; G8/G9 обновлены.
- G1/G2/G5/G7/G8/G9 применимы. Новые G3/G4/G6 cases не нужны: нет изменений runtime/API/persistence. Регрессионные проверки этих областей сохраняются в полном pre-pr/CI; статические контракты не объявляются доказательством runtime isolation.
- Отчёт: `increments/ARCH-01_domain_import_contracts_REPORT.md` по INCREMENT_REPORT_TEMPLATE; review: `reviews/ARCH-01_REVIEWS.md`. Статус VERIFIED относится только к этому dev-time gate, не к продукту в целом.

## 6. Ограничения и следующий шаг

Статические импорты не доказывают изоляцию SQL/таблиц, динамических импортов, событий или runtime permissions. При добавлении модулей S17+ состав пересматривается осмысленно, без обхода exhaustive. Не вводить отдельные сервисы/БД и не менять BASELINED. После ARCH-01 не начинать другой инкремент без новой команды; очередь S16/SLICE-01/S17 и прочие блокеры сохраняются. Порядок DEP-01/PROF-01 и других READY-этапов проверить с владельцем, если не установлен.
