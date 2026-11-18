# G02 / G-156 — независимые review первого отключённого среза

## Дельта ADR131 / контракт0.2 — 2026-11-17

Root — автор дельты; review выполнены двумя отдельными прежними non-author reviewers, blind-first по actualcode/schema/tests без нового авторского отчёта. Fingerprint VALUE required для expectation; candidate facts сохраняют ABSENT/NULL; historicalschema0.1 не меняется, activeparser её отвергает. Выбор состава делегирован владельцем, фактические live values/profile/Bifrost approvals ещё нужны.

- `g02_python_contract_review`: Python/code/test/type read-only; schema/parser/directconstructor, сравнение и несовместимая внутренняя pre-1.0 ревизия проверены. **APPROVE, openfindings0**. Собственных запусков нет.
- `g02_scope_security_review`: независимый read-only code/security; fail-closed/absence/value mismatch/no authority/wiring bypass. **APPROVE, openfindings0** для кода. Собственный inline `PYTHONPATH=backend/src backend/.venv/bin/python -B` exit0: schema/positive match и7negativecases (отсутствие/null expectations, missing-value mismatch, old0.1 records refused, noexpectation refused), без файлов/HTTP. Последующий отдельный docs delta review ADR131/DP/plan/passport/HANDOFF/STATUS без авторского отчёта также **APPROVE, C/H/M/L0**: закрыт только выбор состава, live values/profile и внешние зависимости не приняты автоматически.

Проверки интегратора дельты: TDDRED5failed→GREEN121passed; fast957passed/4warnings,ruff/mypy0,15contractsKEPT; contracts6/6+22passed. Это локальное evidence отключённого validator, без durable admission/DB/paid calls или actual profile approval. [ADR131](../decisions/ADR-131-flash-required-fingerprint.md); текущие команды/окончательные hashes — [report](../increments/G02_flash_admission_preparation_REPORT.md).

Ниже сохранены исходные review0.1 и его hashes/counts; они не переутверждают новую версию.

**База:** `db8d4af34b0933aa2562adcf072b717eb0e3e3e9` + текущий незакоммиченный diff. **Дата:** 2026-11-17. Scope: новые observed_identity.py, test_llm_observed_identity.py, internal schema0.1; паспорт/план/ADR130 и implementation context. Исходный NCP16/OD19 diff не переутверждается. Автор кода — отдельный g02_prerequisite_plan; reviewers не авторы проверяемого среза.

## 1. Blind-first, общий и security scope

`g02_scope_security_review`: явно прочитанные AGENTS/rules, code-reviewer/security-reviewer; read-only. До авторского отчёта проверены DOC076v1.1/ADR128/129/115, G02 order и фактические factory/transport/registry/Compose guards. Docs initial **APPROVE, findings0**: G156→SLICE01→S17 и OD19/G107 до S20; $10 cumulative,8attempts, unknown reservation и отсутствие product approval сохранены. Арифметика независимо вычислена Decimal:0.6003072×8=4.8024576USD. Это не code verdict; финальный кодовый проход выполняется отдельно после freeze.

## 2. Python / contract / test review

`g02_python_contract_review`: явно прочитанные Python/code/test/type инструкции, read-only/blind-first, без авторского отчёта. Проверены реальные parser/schema/tests: immutable nested DTOs, type bounds/unknown versions/duplicate fields, metadata extraction, fingerprint presence/value, no source content, generation and managed binding comparison и отсутствие authority в expectation.

Findings:

| Severity | Evidence | Исправление |
|---|---|---|
| MEDIUM | План/DOC076 требуют safe provider request ref, initial schema/IdentityObservation разрешали null; extraction missing id→None | Сделан обязательным nonnull в DTO/schema; missing/invalid id и standalone null покрыты negative tests |
| LOW | Схема не объясняла, что structural integral semantics JSON Schema допускает1.0, тогда как parser требует strict int; duplicate/secret checks также semantic layer | Уточнены schema description/план: использовать schema **и** semantic parser, tests проверяют strict behavior |

Промежуточный повтор после первого исправления: remaining code/type/immutability/security findings0; LOW documentation ожидал уточнения. Final delta recheck: план §2 уточняет structural/semantic layers и обязательный nonnull ref; **APPROVE, open CRITICAL/HIGH/MEDIUM/LOW0**. Статическое read-only review, собственных тестовых запусков этим reviewer не было.

Последняя schema-description-only дельта также отдельно перечитана тем же независимым Python/contract reviewer: structural+semantic требования точны, полномочия не расширены, регрессий нет; **APPROVE/open0**. Повтор автора108tests exit0 учитывается отдельно от статического review. Code/test hashes и финальный schema hash — в отчёте.

## Финальный code/security verdict

После freeze `g02_scope_security_review` перечитал полный модуль, schema/tests/ADR130 и актуальные context additions, без авторского отчёта: **APPROVE, CRITICAL/HIGH/MEDIUM/LOW0**. Собственный read-only smoke через `PYTHONPATH=backend/src backend/.venv/bin/python -B` (inline, без записи файлов):3positive/roundtrip +8negative cases,exit0; schema проверена текущим jsonschema/FormatChecker. Подтверждены обязательный safe provider ref, explicit trusted request_model_id, exact fingerprint states и отсутствие I/O/approval/wiring. Verdict не относится к отсутствующему durable admission или live model.

## 3. Ограничения и проверки автора/интегратора

Review только offline parser/comparison и точность плана. Не доказаны PostgreSQL durability/restart/concurrency, service authority/approval provenance, budget ledger, live provider metadata, Bifrost compatibility и включение. Review не заменяет human metadata acceptance, approval Bifrost/profile, финальный pre-pr/LinuxCI группы. Source/schema/tests synthetic, runtime/model calls0.

Автор: targeted245passed (108 новых cases + existing Bifrost/gateway), scopedruff/mypy exit0. Основной интегратор: `make pre-push-fast` exit0,ruff0,mypy174sourcefiles0issues,15importcontractsKEPT,944passed/4warnings/0failed/skipped; contracts-check6/6,contracts-test22passed. Точные команды/окончательная дельта — [отчёт](../increments/G02_flash_admission_preparation_REPORT.md). Reviewers читают actual files; авторский PASS им не приписывается.
