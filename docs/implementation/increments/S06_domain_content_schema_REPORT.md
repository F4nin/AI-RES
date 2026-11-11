# S06 — Domain content schema: Increment Report

**Дата:** 2026-11-11 · **Промпт:** `increments/prompts/S06_domain_content_schema.md` · **Итоговый статус:** TESTED (локально; не VERIFIED — см. §12, §14). GitHub Actions на Linux для этой ветки ещё не запускался.

## 1. Что реализовано
- **Схема (ревизии 0007–0011, 18 схем S04):** requirements (types, requirements, requirement_versions, requirement_epics), `work.task_requirements`, sources (sources, uploads, source_versions), knowledge.extraction_records, artifacts (types, version_statuses, artifacts, artifact_versions, validation_reports, publications), governance (reviews, approvals, change_requests, baselines, baseline_items, rules, rule_versions), context (packages, immutable versions, items), decisions (decisions, assumptions, risks, issues, unknowns, hypotheses, conflicts), traceability (object/link types, правила пар, traceability_links), `platform.display_number_counters`, пять таблиц event history, `audit.aggregate_types` +5.
- **Инварианты в БД:** неизменяемые версии и указатель текущей версии (deferred FK), непрерывные номера версий, lifecycle-guard-ы **и на INSERT**, APPROVED/PUBLISHED/IN_BASELINE только при существующем факте, baseline = полный снимок + approval человека + цепочка номеров, версия источника только из проверенного upload, неизвестный тип требования → UNKNOWN с declared-текстом, реестры типов связей/объектов с проверкой существования концов в tenant, SYSTEM-правила read-only для tenant.
- **Репозитории:** `modules/requirements`, `modules/sources` (CAS, нет тихих no-op, идемпотентная финализация).
- **Не сделано (по scope/плану):** репозитории для остальных агрегатов (G-69), эмиссия событий в outbox (G-70, ждёт OD-13), таблицы G-74.

## 2. Нормативная база и проверка Registry
Registry v4.1 и canonical-файлы из §3 промпта присутствуют; `docs/architecture/` не изменялся. Discrepancy: словарь статусов артефакта (G-71, OD-14).

## 3. Созданные и изменённые файлы
- **Миграции:** `db/migrations/versions/0007_requirements_sources_knowledge.py`, `0008_artifacts_governance.py`, `0009_rules_context_decisions_traceability.py`, `0010_domain_event_history.py`, `0011_domain_content_hardening.py`.
- **Код:** `modules/requirements/repository.py`, `modules/sources/repository.py`.
- **Ops:** `ops/postgres/rls_coverage.sql` (исключения для 6 reference-реестров с причинами), `ops/postgres/schema_snapshot.sql` (перегенерирован; построчно проверено, что удалённые строки — только перестановка).
- **Тесты:** `tests/integration/postgres/test_domain_content_schema.py` (новый), `test_s06_repositories.py` (новый); обновлены ожидания S05-тестов (`test_audit_platform_schema`, `test_operations_work_schema`, `test_migration_safety`, `test_roles_and_grants`).
- **Документы (ненормативные):** `tools/adrs.py` + `ARCHITECTURE_DECISION_LOG.md` (ADR-056…060), `KNOWN_GAPS.md` (G-69…G-74), `DECISIONS_PENDING.md` (OD-14), `ECC_USAGE.md`, `REQUIREMENTS_TRACEABILITY.md`, `reviews/S06_REVIEWS.md`, `IMPLEMENTATION_STATUS.md`, `CONTEXT_HANDOFF.md`.

## 4. Изменения API / контрактов / событий
HTTP-поверхность и `contracts/` не менялись. Событийная: добавлены таблицы истории и типы агрегатов; outbox для них намеренно отвергается (fail closed) до OD-13.

## 5. Миграции и совместимость
Greenfield (ADR-011): 0007–0011 аддитивны; `downgrade` — `NotImplementedError` (forward-fix/PITR). Нет DROP/TRUNCATE (offline-SQL тест это проверяет). Upgrade from empty и from previous (`f3a96b1c8e47` с данными → head) — тесты. Ревизии 0007–0011 не выпускались, поэтому правка 0007/0009 по итогам review допустима; после слияния — неизменяемы.

## 6. Решения, принятые самостоятельно
ADR-056 (шаблон версий, требования, нумерация), ADR-057 (sources/uploads), ADR-058 (traceability, rules, context, decisions), ADR-059 (event history, aggregate_types), ADR-060 (artifacts/governance/baseline и hardening). Правила размещены в схеме `governance` (схемы `rules` в ADR-014 нет).

## 7. Устранённые несогласованности / NCP
Расхождение словарей статусов артефакта зафиксировано (G-71, OD-14), NCP не потребовался (нормативные документы не менялись). Новых NCP нет.

## 8. ECC: фактически использованные agents, skills, commands
`database-reviewer`, `silent-failure-hunter`, `code-reviewer` (см. `ECC_USAGE.md`). Не запускались: `planner`, `architect`, `python-reviewer`, `tdd-guide`, `pr-test-analyzer`, `type-design-analyzer`, команды `/plan`, `/quality-gate`, `/test-coverage`, `verification-loop`; компенсация — тесты вместе с кодом и `make pre-pr`.

## 9. Тесты и проверки
Команды и результаты (локально, PostgreSQL 16 Testcontainers): `cd backend && uv run pytest -q` → **331 passed** (после исправлений по трём review); `make backend-check` (ruff, mypy, import-linter 5 kept) — зелёный; `make contracts-check` — зелёный. `make pre-pr` (включая `make up` с миграциями на локальную БД, infra static, runtime) — финальный прогон 2026-11-11: exit 0 (contracts 19, backend 331, infra static 172, runtime 95; точные числа — в логе scratchpad `prepr3.log`). Обязательные тесты §9 промпта: immutable versions — `test_requirement_version_content_is_immutable_and_never_deleted`, `test_baseline_is_an_immutable_complete_snapshot…`; UNKNOWN — `test_unknown_requirement_type…`; registry link/object — `test_traceability_types_come_from_registries…`; RLS всех новых tenant-таблиц — `test_rls_isolation_for_every_new_tenant_table` (+ аудит `rls_coverage.sql`); baseline items — тот же baseline-тест; upgrade from previous revision — `test_upgrade_from_previous_revision_keeps_data` и PERSIST-002.

## 10. Security / authorization cases
Cross-tenant и cross-project IDOR (чтение 0 строк, UPDATE затрагивает 0 строк, запись в чужой tenant отвергается), default-deny без контекста, SYSTEM-правила не изменяемы tenant-ом, чужое rule-version не попадает в контекст, approver — пользователь организации, статусы нельзя «родить» утверждёнными, upload без совпадения checksum/размера/срока не верифицируется, версия источника только из verified upload, append-only истории, outbox для новых агрегатов отвергается. **Не проверено:** Stale session/Policy outage/revoked grant (S07), Worker self-grant (нет runtime), prompt injection, webhook — вне scope.

## 11. Независимое review
См. `reviews/S06_REVIEWS.md`: `database-reviewer` (1 CRITICAL, 4 HIGH, 6 MEDIUM, 6 LOW), `silent-failure-hunter` (4 HIGH, 5 MEDIUM, 3 LOW), `code-reviewer` (результат — в том же файле). CRITICAL/HIGH исправлены либо явно вынесены в G-72/OD-14 как доменные решения; исправления после review тестами подтверждены, **отдельным агентом дельта исправлений не пересматривалась**.

## 12. Не выполненные проверки, ограничения, риски
Linux CI не запускался. Репозитории для 6 агрегатов отсутствуют (G-69). Нет эмиссии событий (G-70). Открытые доменные правила (G-71, G-72, OD-14). FK worker_runs→context_package_versions не добавлен (G-73). Нет Observability-инструментации новых компонентов (репозитории без OTel-спанов; общий слой — S02). Покрытие как метрика не измерялось. Параллельные сценарии покрыты для счётчика и финализации источника.

## 13. Обновлённые документы и статусы
Да — перечислены в §3. `docs/architecture/` и Registry не менялись.

## 14. Статус DoD
- Тесты зелёные, RLS coverage и drift = 0 (локально): да. Финальный `make pre-pr`: exit 0.
- Обязательные тесты §9: да. Негативные security-кейсы этапа: да (§10).
- Independent review с CRITICAL/HIGH устранены: да, дельта без повторного пересмотра.
- Заглушки: нет. Observability: нет (§12). Linux CI: нет.
Итог: **TESTED**, не VERIFIED.

## 15. Можно ли начинать следующий этап
Следующий этап по порядку — S07 (Identity, Local Auth, Policy Engine, Audit, Idempotency); зависимость S06 — достаточно TESTED? ADR-032 требует DONE: перед S07 нужны зелёный Linux CI и решение владельца о принятии статуса.
