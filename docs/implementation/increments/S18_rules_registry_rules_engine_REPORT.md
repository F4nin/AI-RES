# S18 — Rules Registry и Rules Engine: Increment Report

**Дата:** 2026-11-17 · **Промпт:** [S18](prompts/S18_rules_registry_rules_engine.md) · **Статус:** TESTED; локальные gates/review завершены, Linux CI/delivery продолжаются.

## 1. Что реализовано

Отдельные Rules Registry/Engine/Policy; immutable typed DSL без eval, IO и LLM; SYSTEM/ORGANIZATION/PROJECT hierarchy; safe UNKNOWN и пять canonical outcomes; human exact-version lifecycle с отдельными approval/publication, schedule, suspend/resume/retire; finite exact-scope exceptions только при действующем вышестоящем allowance. Derived trusted facts берутся из авторизованного sealed S19 ContextPackageVersion. Полный registry, facts, time, exceptions и результат сохраняются для детерминированного исторического replay. Audit и HMAC idempotency атомарны с результатом; CAS защищает версии.

Manager draft persistence с rationale поддерживается storage; runtime Manager intake не подключён до upstream authorized binding. Human service не принимает ServiceIdentity для утверждения/активации. Активный production catalogue и grants не добавлены. UI относится к S36.

## 2. Нормативная база и проверка Registry

Registry v4.1 и его canonical файлы проверены при старте G01; missing canonical0. S18: Agent Architecture Concept v4.6 §15, MVP Matrix v3.3 Addenda v0.7/v0.8 RULE-MVP01..14, IAM v1.5 §2/§8, Spec v1.22/current addenda, Persistence Blueprint v1.0 и Migration Strategy v1.1. Повторно проверены S06/S07 DONE. Детали технического выбора — [ADR126](../decisions/ADR-126-rules-language-and-lifecycle.md). Полное прочтение каждого исторического повторения canonical corpus не заявляется.

## 3. Созданные и изменённые файлы

| Файлы | Изменение |
|---|---|
| `backend/src/ai_res/modules/rules/{types,language,engine,validation}.py` | immutable types/DSL, pure calculation, duplicate/conflict validation |
| `modules/rules/{repository,registry}.py` | owned persistence и complete approved registry |
| `application/rules.py`, `modules/context/service.py` | trusted orchestration, same-UoW context revalidation, lifecycle, evaluation, exceptions, retrieval/replay |
| `policy/enforcer.py` | optional project scope в subject lock для org commands; Policy semantics прежние |
| migration0019, `ops/postgres/schema_snapshot.sql` | counter + append-only facts, tenant constraints/RLS/grants |
| two unit and three PostgreSQL test files | types, hierarchy, DSL, lifecycle, current authorization, history/concurrency/security |
| `backend/pyproject.toml` | domain classification и pure engine import boundary |
| implementation docs/report/reviews/passport | evidence, traceability, gaps, handoff |

Исходные12 governance изменений владельца сохраняются вне stage commit; scope не включает изменение AGENTS/архитектуры/контрактного зеркала/глобальной конфигурации.

## 4. Изменения API / контрактов / событий

Public routes/OpenAPI/AsyncAPI/JSON schemas, Worker/Temporal contracts не менялись. Нового domain event нет: internal derived/lifecycle records и mandatory audit записываются атомарно; внешний async consumer отсутствует. Декларативные schema1.0 snapshots — внутренний технический формат ADR126, неизвестные версии отклоняются. Evaluation PASS не является разрешением domain action.

## 5. Миграции и совместимость

Expand0019 revision `b621f4d8a905`, previous `a41c8f92d603`. Существующие revisions immutable. `governance.rules.last_version_number` инициализируется один раз существующим max, runtime allocation только locked counter/CAS. Существующие версии не переписываются. Новые append-only validation/evaluation/exception/runtime-control/revocation tables имеют ENABLE+FORCE RLS, owner migration policy, минимальные SELECT/INSERT grants, tenant FKs/guard и no-truncate. SYSTEM runtime mutations запрещены. Нет active rule/permission seed, destructive cleanup или changes Temporal/LangGraph schemas.

`make db-snapshot`: exit0 с ожидаемым1SKIPPED (генерация, не проверка); reviewed diff340 additions. Проверка без regeneration входит в backend suite. Previous→head test сохраняет legacy versions и выделяет следующую3; empty migration/grants/RLS/drift проверяются реальным PostgreSQL16.

## 6. Решения, принятые самостоятельно

| ADR | Решение | Статус |
|---|---|---|
| [126](../decisions/ADR-126-rules-language-and-lifecycle.md) | typed bounded DSL, lifecycle mapping, trusted metadata provider, exact waiver, immutable replay | ACCEPTED, Implementation Lead |

## 7. Устранённые несогласованности / NCP

Canonical impact scale I0 NO_IMPACT → I4 CRITICAL имеет приоритет над устаревшим `.claude/rules/testing-and-verification.md` «critical I0». Три прежние processing categories не приравнивались к impact. Отдельные approval facts на PROPOSED позволяют scheduled activation без преждевременного retire текущей версии. Global sensitive-key detector не ослаблен: строго typed Boolean metadata допускается только по точному пути fact values; произвольные чувствительные поля/содержимое запрещены. Нормативные документы и NCP не менялись.

## 8. ECC: фактически использованные agents, skills, commands

Planner/TDD/type analysis — отдельный ограниченный author типов, DSL и security acceptance; architect — отдельный author pure engine/validation и проверка canonical scope; database specialist — отдельный author migration/storage. Root интегрирует application и тесты. Инструкции python-patterns/python-testing/tdd-workflow/verification-loop применяются как прочитанные checklists; это не native запуск Claude slash commands/hooks. RED→GREEN воспроизведён для типов/engine, service collection, validate API; exceptions первоначально дополнительно выявили нарушение fixture initial-state, исправлено lifecycle updates без обхода guard.

Independent blind-first reviewers не являются авторами S18: code/Python/types/test-analysis/architecture, security/silent-failure, отдельный database reviewer. Результаты — [review](../reviews/S18_IMPLEMENTATION_REVIEWS.md). Development MCP не понадобились; обычное чтение и локальные инструменты компенсируют отсутствие native Claude механизма. Числовое coverage не заявляется: pytest-cov отсутствует в текущем lock; поведенческое покрытие привязано к cases, новая зависимость только ради процента не вводилась.

## 9. Тесты и проверки

База `d5342ac915303a1de3d15f3a911b11243d656dc3`, branch `feat/s18-rules-registry-engine`, рабочий stage diff. Python3.13.5, PostgreSQL16.15 Testcontainers, Docker29.2.0, uv0.11.31; make uses existing Node22.23.5/OpenSSL3.6.3 в command-local PATH. Результаты ниже обновляются по завершении gates; исторические PASS S19 не засчитываются S18.

| Gate | Команда | Результат |
|---|---|---|
| G1/G2 | `make pre-push-fast` | exit0,836passed/4warnings,15 import contracts kept/0broken в финальном прогоне |
| G2/G3/G5 | `cd backend && uv run --locked pytest -q tests/integration/postgres/test_rules_application.py tests/integration/postgres/test_rules_application_security.py tests/integration/postgres/test_rules_storage.py tests/unit/test_rules_engine.py tests/unit/test_rules_types_language.py --tb=short` | exit0,186passed/0failed/0skipped (141unit+45PG),26.19s; finaldiff после двух MEDIUM fixes |
| Supply chain | `make backend-audit`; `make infra-verify-digests` | exit0;0knownbackend vulnerabilities;21pinned/0mismatch |
| G6 | `make db-snapshot` | exit0,1expected generation skip; это не runtime PASS |
| G1–G6/G9 | `PATH=/tmp/arch-01-tools/node-v22.23.5-darwin-arm64/bin:/opt/homebrew/opt/openssl@3/bin:$PATH make -j1 pre-pr` | exit0; backend1749/541warnings,infra369,runtime148,contracts22,Renovate10,PoC19; failed/errors/skipped0 |
| G7 | independent review | 3APPROVE/openfindings0, final hashes в review |
| G8 | cached diff/check + local Markdown links | exit0;80links/0missing; original12 owner changes excluded |
| Linux + supply chain | exact source SHA push/PR | ещё не запускались до source commit |

Логи текущей сессии `/tmp/g01-s18-{fast,static,application,application-extra,exceptions,pre-pr,snapshot}.log` вспомогательные; существенные counts переносятся сюда. Generation skip отличается от acceptance skips. Temporal replay/new activity/webhook/upload/SSE/new CSRF transport неприменимы: этого кода в scope нет; общий regression сохраняется.

## 10. Security / authorization cases

SYSTEM effect не ослабляется lower-level; require/forbid conflict failclosed; DRAFT/expired/suspended rules не действуют; missing facts дают UNKNOWN; exception требует human approval+current MFA/Policy, exact target/effect/version, finite expiry, matching higher rule и exact context scope; expired/revoked/wrong permission не применяются. Replay использует старые snapshots без выдачи полномочий. Production unknown management actions DENY; separation defaultNone denies activation. Real fixture-only PolicyEngine grants обеспечивают acceptance, не production permissions. Проверены current session revoke/expiry/MFA, selfseparation, project→org denial, cross-project retrieval, CAS races, retries, audit rollback, Policy outage и context reauthorization. Секреты/полные документы/raw locations не входят в facts/audit/telemetry; recognized secret-shaped codes rejected, regex detector не объявляется абсолютной гарантией.

## 11. Независимое review

[Review evidence](../reviews/S18_IMPLEMENTATION_REVIEWS.md) — три финальных APPROVE/openfindings0. Security MEDIUM storage scope↔context binding и DB MEDIUM org-report/project-grant namespace исправлены explicit checks и negative cases; namespace regression RED1failed→GREEN1passed. Live evaluation сериализована тем же registry lock, что publication/suspension/revocation, исключая mixed READ COMMITTED snapshots. Первоначальный HIGH общего reviewer о пропущенном allowance check отозван после повторного чтения текущего файла; исправление отсутствующего дефекта не заявляется.

## 12. Не выполненные проверки, ограничения, риски

G158: production transport/service grant bindings для rule management/Manager proposals, owner OD14 separation policy, approved active catalogue и admission/pool-pressure при реальной интеграции остаются открыты. Ничто из этого не выдаётся за утверждённые параметры или действующий production workflow. Manager/Worker не получают ORM/credentials; нет model calls. UI не реализован (S36). Current facts ограничены техническими manifest metadata. General G24 third-party CVE report-only и G147 regex limits остаются открыты. Полный продукт не VERIFIED.

## 13. Обновлённые документы и статусы

ADR126, ADL, STATUS/HANDOFF, G01 passport, REQUIREMENTS_TRACEABILITY, CONTRACT_TRACEABILITY_MAP, KNOWN_GAPS/G158, ECC_USAGE, prompt index, stage report/review. DECISIONS_PENDING собственных новых решений не требует; его исходные dirty изменения сохраняются. Docs architecture/Registry/contracts не меняются.

## 14. Статус DoD

Code/миграции/mandatory four behavioral cases TESTED;3independentAPPROVE,localpre-pr exit0. Linux CI/delivery ещё не завершены. **S18/G01 не DONE**, текущий checkpoint не является VERIFIED.

## 15. Можно ли начинать следующий этап

Нет: сначала завершить S18 gates/delivery и G01 evidence. После DONE G01 остановиться до нового поручения; другая группа автоматически не запускается.

## 16. Точный локальный checkpoint перед PR

Fullpre-pr backend начал сбор tests до final namespace fix и двух дополнительных PG cases (telemetry/orgreport), поэтому1749 не подменяется1751. После final2linefix полный затронутый targeted suite186passed/0failed/0skipped, включая14application+22storage+9security+141unit; fast836/15importcontracts exit0. Runtime image в этом pre-pr собирался уже из final source. Whitespace-only EOF cleanup после review не менял semantics; cached diffcheck0. Linux exact final SHA обязан проверить весь итоговый backend заново. Snapshot generation1expectedskip не засчитывается как acceptance; subsequent fullbackend drift/empty/previous/grants/RLS прошли без skipped. Secretfiles24preserved/0written, volumes сохранены, provider calls0.
