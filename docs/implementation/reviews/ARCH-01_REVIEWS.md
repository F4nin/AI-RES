# ARCH-01 — независимое исследование и review

**Дата:** 2026-11-17. База `4bdd9043680bdd1622bed65c7506a1726172df23`, ветка `feat/arch-01-domain-import-contracts`. Проверяемая дельта реализации: два новых контракта в `backend/pyproject.toml`, новый `backend/tests/architecture/test_domain_import_rules.py`, промпт ARCH-01 и ADR-120. Последующие implementation evidence/status записи не меняют эти контракты/тесты.

## 1. Исследование до реализации

Отдельный Codex-агент `arch_analysis` применил прочитанную роль `.claude/agents/architect.md` read-only. Граф построен `python -B` / `grimp.build_graph(..., cache_dir=None)`; cache не читается/не пишется. Прочитаны Registry §2, Spec §3, относящиеся к модульности разделы Architecture Concept/Domain Model, ADR-114, pyproject, lock и исходники установленных import-linter 2.16 / grimp 3.19.

Факт: 14 модулей, 17 межмодульных import edges, 9 направлений, циклов нет:

| Направление | Edges |
|---|---:|
| epics → events | 1 |
| iam → audit | 4 |
| operations → audit | 1 |
| operations → events | 5 |
| projects → events | 1 |
| requirements → events | 1 |
| sources → events | 2 |
| sources → operations | 1 |
| worker_runs → events | 1 |

Существующий `sources.completion → operations.repository → events.aggregate_events` сохраняется; между девятью верхними модулями нет запрещённых путей. Уточнение «15 → 14» и состав 9/3/2 оформлены ADR-120. `:` внутри shared-слоёв не вводит неоговорённой независимости; отдельный independence защищает верхний слой. `exhaustive` блокирует незаявленных непосредственных потомков. Рекомендации приняты без изменения продуктового кода.

## 2. Blind-first общее review

Отдельный агент `general_review`, роль `.claude/agents/code-reviewer.md`, независимо прочитал diff и окружающий код, AGENTS, ADR-114/120 и локальные исходники import-linter/grimp. Отчёт автора, результаты других review не предоставлялись. Read-only граф построен без cache. Pytest/Docker/pre-pr этим reviewer не запускались.

Вердикт **APPROVE**. CRITICAL 0 / HIGH 0 / MEDIUM 0 / LOW 0. Все 12 прежних контрактов сохранены; точный состав соответствует 14 существующим модулям; семантика прямых/непрямых путей и exhaustive подтверждена; scope сохранён.

## 3. Blind-first профильное review тестов

Другой агент `test_review`, роль `.claude/agents/pr-test-analyzer.md`, независимо проверил production-конфигурацию, новые тесты и ADR-114 без отчёта автора/других review. Эксперименты только во временных каталогах, repo не изменялся; полный pytest/pre-pr/Docker не запускались.

CRITICAL 0 / HIGH 0 / MEDIUM 0 / LOW 0. Тесты используют production-опции, проверяют разрешённый путь, обратные слои, оба направления peer-импортов, непрямые пути, новый модуль. Exit 1 + имя сломанного контракта + точные counts исключают ошибочный PASS только из-за сбоя конфигурации. Все **3/3 мутации обнаружены**:

1. `exhaustive = false`.
2. Исключение `projects.service → epics`.
3. Обратный порядок слоёв.

## 4. Границы результата

Review относится к dev-time архитектурному gate, не подтверждает runtime isolation/authorization, SQL/table access, динамические импорты или event semantics. Security/database reviewer не требуются: соответствующие механизмы не изменялись. Независимое review фактически проведено отдельными Codex-агентами; Claude slash commands/agents автоматически подключёнными не объявляются. Исправлений по findings не потребовалось. Полный pre-pr/CI и статус — в отчёте этапа.

Отдельный повторный проход `general_review` по implementation-документации (report/reviews/status/handoff/traceability/ECC/roadmap/index; основные контракты/тесты с первого review не менялись): конкретных findings нет. Этот проход уже допускает чтение отчёта автора для проверки evidence и не выдаётся за blind-first повтор основного review. Статус IN_PROGRESS, ещё ожидаемые pre-pr/CI и ограничения scope подтверждены.
