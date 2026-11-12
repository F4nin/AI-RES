# REQUIREMENTS_TRACEABILITY

Требования нормативных документов → этапы реализации → статус. Индекс сгенерирован из canonical документов Registry v4.1 (DOC-003, -009, -017, -020, -023, -025, -031, -032, -033, -039, -068, -072); 764 уникальных ID. Сопоставление выполнено на уровне семейств (G-14): при старте этапа исполнитель уточняет конкретные ID, указывает тесты и меняет статус (NOT_STARTED → IMPLEMENTED → TESTED → VERIFIED). TX-01…TX-09 (DOC-064 §8) — S05, S09, S12.

## 1. Семейства → этапы

| Семейство | Кол-во | Этапы |
|---|---|---|
| API-MVP | 36 | S01, S02, S08, S09, S12 |
| AUTH-MVP | 11 | S07 |
| AUTH | 13 | S07; S37 |
| SEC-MVP | 15 | S07; S37 |
| SEC | 32 | S02–S37 (по области); S37 верификация |
| DATA-MVP | 24 | S05, S06 |
| INF-MVP | 41 | S03; S11; S13; S32 |
| INT-MVP | 25 | S29 |
| PROC-MVP | 35 | S12, S20–S32 |
| RULE-MVP | 14 | S18 |
| DEP-MVP | 14 | S23, S30 |
| WS-MVP | 22 | S35 |
| UX-START | 12 | S20, S35 |
| UX-MVP | 15 | S35, S36 |
| UX-PLAN | 19 | S21, S36 |
| UX-RESULT | 25 | S25, S36 |
| UX-REQ | 35 | S26, S36 |
| UX-DUR | 32 | S26, S36 |
| UX-SRC | 28 | S27, S36 |
| UX-TRC | 36 | S30, S36 |
| UX-ART | 42 | S31, S36 |
| PERSIST | 24 | S04, S05 |
| DBM | 17 | S04, S05, S32 |
| PERF | 26 | S38 |
| REL | 28 | S32, S38 |
| LT | 12 | S38 |
| OBS-MON | 29 | S13 |
| OBS-SEC | 11 | S13 |
| OBS-ALR | 7 | S13 |
| CI | 45 | S34 (MVP A0–A2); остальное post-MVP |
| THR | 20 | S03, S05, S07, S16, S17, S23, S37 (по области угрозы) |
| LC-DEC | 19 | S26 |

## 2. Индекс требований

| ID | Документ | Требование (кратко) | Приоритет/scope | Этапы | Статус |
|---|---|---|---|---|---|
| API-MVP-001 | DOC-009 | Contract-first и CI validation | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-002 | DOC-009 | Разделение API planes | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-003 | DOC-009 | REST public API v1 | MVP | S01, S02, S08, S09, S12 | PARTIAL (S08: 12 GET реализованы и проверены schemathesis; записи — S09) |
| API-MVP-004 | DOC-009 | OpenAPI baseline | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-005 | DOC-009 | JSON Schema 2020-12 | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-006 | DOC-009 | RFC 9457 errors | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-007 | DOC-009 | Cursor pagination | MVP | S01, S02, S08, S09, S12 | PARTIAL (S08: keyset-курсоры на всех списках, ADR-074; нет offset) |
| API-MVP-008 | DOC-009 | ETag/If-Match | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-009 | DOC-009 | Idempotency-Key | MVP | S01, S02, S08, S09, S12 | PARTIAL (S09/S12: write-команды, включая cancel и completeUpload; TESTED локально) |
| API-MVP-010 | DOC-009 | Async Operation resource | MVP | S01, S02, S08, S09, S12 | PARTIAL (S12 TESTED локально: getOperation, cancel 202, completeUpload 202 + Location; Linux CI ожидается) |
| API-MVP-011 | DOC-009 | SSE events | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-012 | DOC-009 | Lifecycle transition validation | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-013 | DOC-009 | Local Authentication + pluggable IdentityProvider; OIDC Code+PKCE adapter is future extension | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-014 | DOC-009 | Service identities | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-015 | DOC-009 | Object-level ACL | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-016 | DOC-009 | Policy fail-closed | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-017 | DOC-009 | Scoped Worker grants | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-018 | DOC-009 | Safe MinIO file transfer | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-019 | DOC-009 | WorkerRunEnvelope | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-020 | DOC-009 | WorkerResult | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-021 | DOC-009 | Distinct acceptance states | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-022 | DOC-009 | No direct Worker DB writes | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-023 | DOC-009 | Controlled Worker handoff | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-024 | DOC-009 | Temporal contracts | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-025 | DOC-009 | Temporal compatibility | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-026 | DOC-009 | LangGraph contract | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-027 | DOC-009 | LLM Gateway Adapter | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-028 | DOC-009 | CloudEvents envelope | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-029 | DOC-009 | Transactional Outbox | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-030 | DOC-009 | Event ordering/replay | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-031 | DOC-009 | AsyncAPI catalogue | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-032 | DOC-009 | Correlation propagation | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-033 | DOC-009 | Connector contract | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-034 | DOC-009 | Contract compatibility | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-035 | DOC-009 | Contract test suite | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| API-MVP-036 | DOC-009 | Claude Code implementation discipline | MVP | S01, S02, S08, S09, S12 | NOT_STARTED |
| AUTH-001 | DOC-020 | Local Authentication работает без внешнего IdP | MUST / MVP | S07; S37 | TESTED (S07: локальные аккаунты, PostgreSQL 16) |
| AUTH-002 | DOC-020 | Authentication Provider отделён интерфейсом | MUST / MVP | S07; S37 | PARTIAL (S07: AuthService не вынесен за порт IdentityProvider; ServiceIdentityPort есть; OIDC-адаптер — post-MVP) |
| AUTH-003 | DOC-020 | Пароли хранятся как Argon2id hashes | MUST / MVP | S07; S37 | TESTED (S07: Argon2id, соль, rehash; параметры WORKING — G-75) |
| AUTH-004 | DOC-020 | Bootstrap admin без default credentials, одноразовый bootstrap secret | MUST / MVP | S07; S37 | TESTED (S07: одноразовый bootstrap, секрет из файла, атомарный claim) |
| AUTH-005 | DOC-020 | Защита login от brute force и account enumeration | MUST / MVP | S07; S37 | TESTED (S07: единый 401, decoy-хеш, progressive delay; throttle process-local — G-76) |
| AUTH-006 | DOC-020 | MFA обязательна для привилегированных ролей | MUST / MVP | S07; S37 | PARTIAL (S07: Policy требует MFA для привилегированных действий iam.*; TOTP+recovery протестированы; обязательность MFA для будущих действий — по мере их появления) |
| AUTH-007 | DOC-020 | Opaque server-side browser sessions и CSRF protection | MUST / MVP | S07; S37 | TESTED (S07: opaque sessions, cookie-атрибуты, CSRF, Origin, CORS deny; HTTP + live stack) |
| AUTH-008 | DOC-020 | Logout/reset/disable/revocation отзывают sessions | MUST / MVP | S07; S37 | TESTED (S07: logout, смена пароля, disable, revoke membership, MFA reset) |
| AUTH-009 | DOC-020 | OIDC Authorization Code + PKCE S256 | SHOULD / Future | S07; S37 | NOT_STARTED |
| AUTH-010 | DOC-020 | OIDC identity mapping `(issuer, subject)` | SHOULD / Future | S07; S37 | NOT_STARTED |
| AUTH-011 | DOC-020 | OIDC claims не назначают AI RES permissions автоматически | MUST / Future | S07; S37 | NOT_STARTED |
| AUTH-012 | DOC-020 | Human, service и Worker Run identities разделены | MUST / MVP | S07; S37 | PARTIAL (S07: сервис-токены Ed25519 и разделение с сессиями протестированы; Worker Run grants — S23) |
| AUTH-013 | DOC-020 | Authentication security events аудируются без секретов | MUST / MVP | S07; S37 | TESTED (S07: аудит login/logout/пароль/MFA/bootstrap/политика; golden-тест без секретов) |
| AUTH-MVP-001 | DOC-009 | Local user accounts; no mandatory external IdP | MUST | S07 | TESTED (S07) |
| AUTH-MVP-002 | DOC-009 | Replaceable IdentityProvider abstraction | MUST | S07 | PARTIAL (S07: см. AUTH-002) |
| AUTH-MVP-003 | DOC-009 | Argon2id password hashing and secure bootstrap | MUST | S07 | TESTED (S07) |
| AUTH-MVP-004 | DOC-009 | Login rate limiting, progressive delay, anti-enumeration | MUST | S07 | TESTED (S07) |
| AUTH-MVP-005 | DOC-009 | TOTP MFA for privileged roles | MUST | S07 | PARTIAL (S07: см. AUTH-006) |
| AUTH-MVP-006 | DOC-009 | Opaque server-side sessions, secure cookies, CSRF | MUST | S07 | TESTED (S07) |
| AUTH-MVP-007 | DOC-009 | Session revocation on logout/reset/disable/role change | MUST | S07 | TESTED (S07) |
| AUTH-MVP-008 | DOC-009 | Human/service/Worker Run identity separation | MUST | S07 | PARTIAL (S07: см. AUTH-012) |
| AUTH-MVP-009 | DOC-009 | Authentication audit events without secrets | MUST | S07 | TESTED (S07) |
| AUTH-MVP-010 | DOC-009 | OIDC Authorization Code + PKCE S256 adapter | FUTURE | S07 | DEFERRED (post-MVP) |
| AUTH-MVP-011 | DOC-009 | OIDC mapping by issuer + subject; no automatic role grants | FUTURE | S07 | DEFERRED (post-MVP) |
| CI-001 | DOC-039 | Evidence-backed proposal | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-002 | DOC-039 | Immutable proposal versions | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-003 | DOC-039 | Signal provenance | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-004 | DOC-039 | Data minimization | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-005 | DOC-039 | No default training | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-006 | DOC-039 | Sanitized evaluation data | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-007 | DOC-039 | Separation of knowledge and behavior | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-008 | DOC-039 | No self-approval | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-009 | DOC-039 | Versioned evaluation | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-010 | DOC-039 | Regression evaluation | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-011 | DOC-039 | Independent review | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-012 | DOC-039 | Guardrail veto | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-013 | DOC-039 | Approval matrix | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-014 | DOC-039 | Controlled lifecycle | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-015 | DOC-039 | Release version pinning | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-016 | DOC-039 | Shadow mode isolation | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-017 | DOC-039 | Canary and staged release | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-018 | DOC-039 | Post-release measurement | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-019 | DOC-039 | Rollback decision | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-020 | DOC-039 | Rollback limitations | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-021 | DOC-039 | Capability-scoped autonomy | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-022 | DOC-039 | Explicit autonomy grant | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-023 | DOC-039 | Policy enforcement per action | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-024 | DOC-039 | No inherited expansion | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-025 | DOC-039 | No self-escalation | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-026 | DOC-039 | Reserved human decisions | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-027 | DOC-039 | Autonomy promotion evidence | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-028 | DOC-039 | No single-score promotion | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-029 | DOC-039 | Auditability | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-030 | DOC-039 | Tenant/project isolation | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-031 | DOC-039 | Glossary governance | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-032 | DOC-039 | Glossary validation | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-033 | DOC-039 | Evaluation integrity | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-034 | DOC-039 | Improvement workflow durability | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-035 | DOC-039 | Human-readable rationale | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-036 | DOC-039 | Insufficient evidence | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-037 | DOC-039 | Monitoring after promotion | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-038 | DOC-039 | Emergency disable | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-039 | DOC-039 | Improvement outcome segmentation | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-040 | DOC-039 | Learning does not grant permission | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-041 | DOC-039 | Glossary referential integrity | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-042 | DOC-039 | Documentation release binding | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-043 | DOC-039 | Documentation evidence | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-044 | DOC-039 | Documentation change impact | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| CI-045 | DOC-039 | Accessibility and localization review | — | S34 (MVP A0–A2); остальное post-MVP | NOT_STARTED |
| DATA-MVP-001 | DOC-009 | Модульный Backend и единая доменная БД PostgreSQL | MVP | S05, S06 | NOT_STARTED |
| DATA-MVP-002 | DOC-009 | Организационная и проектная модель | MVP | S05, S06 | NOT_STARTED |
| DATA-MVP-003 | DOC-009 | Независимость Task и Requirement | MVP | S05, S06 | IMPLEMENTED (S06: БД-инварианты и тесты; HTTP-слой — S09) |
| DATA-MVP-004 | DOC-009 | Версионирование требований | MVP | S05, S06 | IMPLEMENTED (S06: БД-инварианты и тесты; HTTP-слой — S09) |
| DATA-MVP-005 | DOC-009 | Версионирование источников и provenance | MVP | S05, S06 | NOT_STARTED |
| DATA-MVP-006 | DOC-009 | Типизированные Decision/Assumption/Risk/Issue/Unknown/Hypothesis/Conflict | MVP | S05, S06 | NOT_STARTED |
| DATA-MVP-007 | DOC-009 | Версионируемый Plan | MVP | S05, S06 | NOT_STARTED |
| DATA-MVP-008 | DOC-009 | Единый Artifact Registry с версиями | MVP | S05, S06 | NOT_STARTED |
| DATA-MVP-009 | DOC-009 | Точное версионирование Approval и Baseline | MVP | S05, S06 | NOT_STARTED |
| DATA-MVP-010 | DOC-009 | Разделение Worker Definition, Runtime и Run | MVP | S05, S06 | NOT_STARTED |
| DATA-MVP-011 | DOC-009 | Неизменяемая версия Context Package | MVP | S05, S06 | NOT_STARTED |
| DATA-MVP-012 | DOC-009 | Типизированная Traceability | MVP | S05, S06 | NOT_STARTED |
| DATA-MVP-013 | DOC-009 | Разделение видов зависимостей | MVP | S05, S06 | NOT_STARTED |
| DATA-MVP-014 | DOC-009 | Transactional Outbox | MVP | S05, S06 | NOT_STARTED |
| DATA-MVP-015 | DOC-009 | Доменный аудит | MVP | S05, S06 | NOT_STARTED |
| DATA-MVP-016 | DOC-009 | UUID и бизнес-идентификаторы | MVP | S05, S06 | NOT_STARTED |
| DATA-MVP-017 | DOC-009 | Реляционная целостность | MVP | S05, S06 | NOT_STARTED |
| DATA-MVP-018 | DOC-009 | Управляемое удаление и архивирование | MVP | S05, S06 | NOT_STARTED |
| DATA-MVP-019 | DOC-009 | ACL для всех способов доступа | MVP | S05, S06 | NOT_STARTED |
| DATA-MVP-020 | DOC-009 | Независимые миграции | MVP | S05, S06 | NOT_STARTED |
| DATA-MVP-021 | DOC-009 | Восстановление и reconciliation | MVP | S05, S06 | NOT_STARTED |
| DATA-MVP-022 | DOC-009 | Проверка циклов TaskDependency | MVP | S05, S06 | NOT_STARTED |
| DATA-MVP-023 | DOC-009 | Контролируемое применение JSONB | MVP | S05, S06 | NOT_STARTED |
| DATA-MVP-024 | DOC-009 | Контроль внешних идентификаторов | MVP | S05, S06 | NOT_STARTED |
| DBM-001 | DOC-068 | Все domain migrations управляются Alembic | Fresh DB upgrade и upgrade f | S04, S05, S32 | PARTIAL (S04: upgrade from empty; previous — S05) |
| DBM-002 | DOC-068 | Temporal/LangGraph schemas не управляются Alembic AI RES | Migration allowlist test | S04, S05, S32 | TESTED (S04: allowlist, autogenerate не видит langgraph/temporal) |
| DBM-003 | DOC-068 | Migration scripts immutable, reviewed, named constraints | CI lint + code review | S04, S05, S32 | PARTIAL (S04: naming convention, single head, review; CI lint ревизий — S05) |
| DBM-004 | DOC-068 | Несовместимые изменения проходят expand/backfill/validate/contract | Migration plan и compatibili | S04, S05, S32 | NOT_STARTED |
| DBM-005 | DOC-068 | Backfill resumable и bounded | Повторный запуск, interrupti | S04, S05, S32 | NOT_STARTED |
| DBM-006 | DOC-068 | Runtime identities не имеют DDL/owner/BYPASSRLS | `pg_roles`, `has_table_privi | S04, S05, S32 | TESTED (S04) |
| DBM-007 | DOC-068 | Manager/Worker Runtime не имеют DB credentials | Deployment secret inventory  | S04, S05, S32 | PARTIAL (S04: нет DB credentials/секретов у api и прочих; Manager/Worker не существуют) |
| DBM-008 | DOC-068 | RLS FORCE + default-deny на tenant tables | Tests под runtime login role | S04, S05, S32 | PARTIAL (S04: probe-таблица ENABLE+FORCE, под ролью ai_res_api; доменные — S05) |
| DBM-009 | DOC-068 | Tenant context transaction-local | Pool reuse test: tenant A th | S04, S05, S32 | TESTED (S04: pool reuse; доменные — S05) |
| DBM-010 | DOC-068 | Отсутствующий context возвращает 0 rows/denies writes | Negative tests | S04, S05, S32 | PARTIAL (S04: probe-таблица; доменные — S05) |
| DBM-011 | DOC-068 | Policy Engine остаётся authoritative для ACL | BOLA/IDOR/search/RAG/export  | S04, S05, S32 | NOT_STARTED |
| DBM-012 | DOC-068 | `public` CREATE отозван; search_path безопасен | Privilege/search_path audit | S04, S05, S32 | TESTED (S04: PUBLIC CREATE отозван, search_path pg_catalog, audit gate) |
| DBM-013 | DOC-068 | DB credentials externalized and rotatable | Rotation drill | S04, S05, S32 | NOT_STARTED |
| DBM-014 | DOC-068 | TLS/SCRAM/network restrictions enforced | pg_hba inspection + connecti | S04, S05, S32 | PARTIAL (S04: TLS/SCRAM/hba на живом стеке; Testcontainers без TLS) |
| DBM-015 | DOC-068 | Production migration имеет backup/PITR/restore evidence | Release gate | S04, S05, S32 | NOT_STARTED |
| DBM-016 | DOC-068 | Schema owner and migrator are separate from runtime | Role membership audit | S04, S05, S32 | TESTED (S04: owner/migrator/runtime разделены) |
| DBM-017 | DOC-068 | New tenant-scoped tables cannot omit RLS silently | CI RLS coverage check | S04, S05, S32 | TESTED (S04: RLS coverage default-fail + positive controls; таблиц пока нет) |
| DEP-MVP-01 | DOC-009 | Неизменяемость результатов | Обязательно | S23, S30 | NOT_STARTED |
| DEP-MVP-02 | DOC-009 | Provenance | Обязательно | S23, S30 | NOT_STARTED |
| DEP-MVP-03 | DOC-009 | Граф зависимостей | Обязательно | S23, S30 | NOT_STARTED |
| DEP-MVP-04 | DOC-009 | Раздельные статусы Обязательно | Freshness, verification и | S23, S30 | NOT_STARTED |
| DEP-MVP-05 | DOC-009 | Оценка влияния | Обязательно | S23, S30 | NOT_STARTED |
| DEP-MVP-06 | DOC-009 | Категории влияния | Обязательно | S23, S30 | NOT_STARTED |
| DEP-MVP-07 | DOC-009 | Критическая переоценка | Обязательно | S23, S30 | NOT_STARTED |
| DEP-MVP-08 | DOC-009 | Gate использования Обязательно | Readiness Gate не | S23, S30 | NOT_STARTED |
| DEP-MVP-09 | DOC-009 | Downstream impact | Обязательно | S23, S30 | NOT_STARTED |
| DEP-MVP-10 | DOC-009 | Неопределённость зависимостей | Обязательно | S23, S30 | NOT_STARTED |
| DEP-MVP-11 | DOC-009 | Snapshot активного Обязательно Run | Worker Run продолжает | S23, S30 | NOT_STARTED |
| DEP-MVP-12 | DOC-009 | Повторная проверка Обязательно | Новая проверка связана с | S23, S30 | NOT_STARTED |
| DEP-MVP-13 | DOC-009 | Аудит переходов | Обязательно | S23, S30 | NOT_STARTED |
| DEP-MVP-14 | DOC-009 | Замещение | Обязательно | S23, S30 | NOT_STARTED |
| INF-MVP-001 | DOC-009 | Развёртывать MVP локально через Docker Compose | MVP | S03; S11; S13; S32 | TESTED (S03) |
| INF-MVP-002 | DOC-009 | Разделить API, Manager Runtime и общий Worker Runtime | MVP | S03; S11; S13; S32 | IN_PROGRESS (S11 VERIFIED: процессы и очереди разделены, WorkerRun — S23) |
| INF-MVP-003 | DOC-009 | Использовать Temporal как durable Workflow Engine, LangGraph — для агентной логики | MVP | S03; S11; S13; S32 | NOT_STARTED |
| INF-MVP-004 | DOC-009 | Разделить `ai_res_db` и `temporal_db` в одном PostgreSQL instance | MVP | S03; S11; S13; S32 | TESTED (S03; + temporal_visibility_db, G-39) |
| INF-MVP-005 | DOC-009 | Использовать PostgreSQL Checkpointer LangGraph с отделением от доменных таблиц | MVP | S03; S11; S13; S32 | PARTIAL (S03: schema+роль provisioned, TESTED; брокер — S23) |
| INF-MVP-006 | DOC-009 | Использовать MinIO для файловых объектов | MVP | S03; S11; S13; S32 | TESTED (S03) |
| INF-MVP-007 | DOC-009 | Сделать Redis необязательным | MVP | S03; S11; S13; S32 | TESTED (S03: Redis не включён) |
| INF-MVP-008 | DOC-009 | Реализовать PostgreSQL backup через pgBackRest + WAL Archiving | MVP | S03; S11; S13; S32 | NOT_STARTED |
| INF-MVP-009 | DOC-009 | Резервировать MinIO objects отдельно | MVP | S03; S11; S13; S32 | NOT_STARTED |
| INF-MVP-010 | DOC-009 | Поддержать целевые RPO ≤ 1 часа и RTO ≤ 4 часов | Цель MVP | S03; S11; S13; S32 | NOT_STARTED |
| INF-MVP-011 | DOC-009 | Изолировать внешние вызовы через LLM Gateway/Connector Platform | MVP | S03; S11; S13; S32 | NOT_STARTED |
| INF-MVP-012 | DOC-009 | Использовать готовый LLM Gateway, не разрабатывать свой | MVP | S03; S11; S13; S32 | NOT_STARTED |
| INF-MVP-013 | DOC-009 | Провести Bifrost PoC и security review до production-подобного использования | Gate | S03; S11; S13; S32 | NOT_STARTED |
| INF-MVP-014 | DOC-009 | Поддержать внешний и локальный модельный provider через Gateway architecture | MVP architecture | S03; S11; S13; S32 | NOT_STARTED |
| INF-MVP-015 | DOC-009 | Не передавать секреты в LLM context, logs, traces, Temporal History и Worker results | MVP | S03; S11; S13; S32 | PARTIAL (S03: инфраструктура; S11/S13 — Temporal/telemetry) |
| INF-MVP-016 | DOC-009 | Применять least privilege и scoped Worker permissions | MVP | S03; S11; S13; S32 | NOT_STARTED |
| INF-MVP-017 | DOC-009 | Ограничить контейнеры и выполнение | MVP | S03; S11; S13; S32 | TESTED (S03) |
| INF-MVP-018 | DOC-009 | Инструментировать компоненты через OpenTelemetry | MVP | S03; S11; S13; S32 | NOT_STARTED |
| INF-MVP-019 | DOC-009 | Развернуть Prometheus, Grafana, Loki, Tempo и Alertmanager | MVP | S03; S11; S13; S32 | NOT_STARTED |
| INF-MVP-020 | DOC-009 | Хранить доменный Audit Log отдельно в PostgreSQL | MVP | S03; S11; S13; S32 | NOT_STARTED |
| INF-MVP-021 | DOC-009 | Ограничить доступ и изменение Audit Log | MVP | S03; S11; S13; S32 | NOT_STARTED |
| INF-MVP-022 | DOC-009 | Редактировать secrets и чувствительные данные перед telemetry export | MVP | S03; S11; S13; S32 | NOT_STARTED |
| INF-MVP-023 | DOC-009 | Разделить retention для logs, traces, metrics, LLM traces и audit | MVP | S03; S11; S13; S32 | NOT_STARTED |
| INF-MVP-024 | DOC-009 | Не блокировать выполнение при потере обычной telemetry | MVP | S03; S11; S13; S32 | NOT_STARTED |
| INF-MVP-025 | DOC-009 | Обеспечить надёжную запись критических audit events | MVP | S03; S11; S13; S32 | NOT_STARTED |
| INF-MVP-026 | DOC-009 | Управлять конфигурацией как кодом в Git | MVP | S03; S11; S13; S32 | PARTIAL (S03) |
| INF-MVP-027 | DOC-009 | Разделить конфигурацию инфраструктуры, окружения, приложения, Rules/Policy и secrets | MVP | S03; S11; S13; S32 | PARTIAL (S03) |
| INF-MVP-028 | DOC-009 | Валидировать конфигурацию до запуска | MVP | S03; S11; S13; S32 | PARTIAL (S03: policy-проверки Compose; typed settings — S02) |
| INF-MVP-029 | DOC-009 | Хранить секреты только зашифрованными в Git | MVP | S03; S11; S13; S32 | PARTIAL (S03: нет общих секретов; dev per-machine, ADR-045) |
| INF-MVP-030 | DOC-009 | Передавать runtime secrets через Compose secrets | MVP | S03; S11; S13; S32 | TESTED (S03) |
| INF-MVP-031 | DOC-009 | Фиксировать container images по digest | MVP | S03; S11; S13; S32 | TESTED (S03) |
| INF-MVP-032 | DOC-009 | Формировать Release Manifest | MVP | S03; S11; S13; S32 | PARTIAL (S03: формат+генератор) |
| INF-MVP-033 | DOC-009 | Использовать Renovate для предложений обновлений | MVP | S03; S11; S13; S32 | PARTIAL (S03: конфиг не проверен приложением Renovate, G-31) |
| INF-MVP-034 | DOC-009 | Проверять обновления до развёртывания | MVP | S03; S11; S13; S32 | NOT_STARTED |
| INF-MVP-035 | DOC-009 | Разделять процедуры миграций | MVP | S03; S11; S13; S32 | NOT_STARTED |
| INF-MVP-036 | DOC-009 | Поддержать безопасный rollback/forward-fix | MVP | S03; S11; S13; S32 | NOT_STARTED |
| INF-MVP-037 | DOC-009 | Формировать SBOM для release images | MVP | S03; S11; S13; S32 | TESTED (S03: SBOM локально) |
| INF-MVP-038 | DOC-009 | Сканировать образы и зависимости | MVP | S03; S11; S13; S32 | TESTED (S03: own blocking, third-party report-only) |
| INF-MVP-039 | DOC-009 | Подписывать собственные release images | MVP | S03; S11; S13; S32 | NOT_STARTED |
| INF-MVP-040 | DOC-009 | Вести Runbooks эксплуатации | MVP | S03; S11; S13; S32 | PARTIAL (S03: local-stack) |
| INF-MVP-041 | DOC-009 | Связывать Release Manifest с Recovery Manifest | MVP | S03; S11; S13; S32 | NOT_STARTED |
| INT-MVP-001 | DOC-009 | Система должна вести реестр подключений и версий адаптеров | MVP | S29 | NOT_STARTED |
| INT-MVP-002 | DOC-009 | Адаптеры должны реализовывать общий типизированный контракт | MVP | S29 | NOT_STARTED |
| INT-MVP-003 | DOC-009 | В MVP внешние интеграции должны быть read-only | MVP | S29 | NOT_STARTED |
| INT-MVP-004 | DOC-009 | Поддержать read-only подключение выбранных GitHub/GitLab repositories | MVP | S29 | NOT_STARTED |
| INT-MVP-005 | DOC-009 | Поддержать импорт OpenAPI/Swagger как контролируемого источника | MVP | S29 | NOT_STARTED |
| INT-MVP-006 | DOC-009 | Для каждого внешнего объекта хранить стабильный external ID и mapping | MVP | S29 | NOT_STARTED |
| INT-MVP-007 | DOC-009 | Проверять права на каждый connector operation и retrieval | MVP | S29 | NOT_STARTED |
| INT-MVP-008 | DOC-009 | Хранить credentials вне LLM-контекста и логов | MVP | S29 | NOT_STARTED |
| INT-MVP-009 | DOC-009 | Поддержать ручное обновление и ограниченный polling | MVP | S29 | NOT_STARTED |
| INT-MVP-010 | DOC-009 | Сохранять sync checkpoint и внешние version markers | MVP | S29 | NOT_STARTED |
| INT-MVP-011 | DOC-009 | Обеспечить идемпотентность повторных событий/запросов | MVP | S29 | NOT_STARTED |
| INT-MVP-012 | DOC-009 | Реализовать ограниченные retries/backoff и классификацию ошибок | MVP | S29 | NOT_STARTED |
| INT-MVP-013 | DOC-009 | Маркировать partial sync отдельно от success | MVP | S29 | NOT_STARTED |
| INT-MVP-014 | DOC-009 | Формировать Source Version/Change Set при изменении внешнего источника | MVP | S29 | NOT_STARTED |
| INT-MVP-015 | DOC-009 | Запускать Impact Assessment при содержательном изменении | MVP | S29 | NOT_STARTED |
| INT-MVP-016 | DOC-009 | Не менять Context Package активного Worker Run | MVP | S29 | NOT_STARTED |
| INT-MVP-017 | DOC-009 | Отображать статус подключения, свежесть и понятные ошибки | MVP | S29 | NOT_STARTED |
| INT-MVP-018 | DOC-009 | Вести аудит существенных операций интеграции | MVP | S29 | NOT_STARTED |
| INT-MVP-019 | DOC-009 | Поддержать отключение интеграции без молчаливого удаления истории | MVP | S29 | NOT_STARTED |
| INT-MVP-020 | DOC-009 | Фильтровать поиск и контекст по ACL/tenant/project | MVP | S29 | NOT_STARTED |
| INT-MVP-021 | DOC-009 | Сопоставлять неизвестные внешние статусы без догадки | MVP | S29 | NOT_STARTED |
| INT-MVP-022 | DOC-009 | Не использовать last-write-wins без явно утверждённой политики | MVP | S29 | NOT_STARTED |
| INT-MVP-023 | DOC-009 | Использовать webhook как сигнал, а не доверенный snapshot | MVP ограниченно | S29 | NOT_STARTED |
| INT-MVP-024 | DOC-009 | Выполнять reconciliation для обнаружения пропущенных событий | MVP ограниченно | S29 | NOT_STARTED |
| INT-MVP-025 | DOC-009 | Не выполнять внешние write/delete без отдельной политики и подтверждения | MVP | S29 | NOT_STARTED |
| LC-DEC-01 | DOC-003 | Использовать гибридный подход регистрации: автоматически создавать предварительные записи кандидатов и предост | Подтверждено | S26 | NOT_STARTED |
| LC-DEC-02 | DOC-003 | Разделять исходное утверждение источника, кандидата, требование проекта и утверждённое требование. | Предлагается принять | S26 | NOT_STARTED |
| LC-DEC-03 | DOC-003 | Подтверждение корректности извлечения не означает бизнес-утверждения требования. | Предлагается принять | S26 | NOT_STARTED |
| LC-DEC-04 | DOC-003 | Поддерживать каталог типов требований, но не требовать от пользователя заранее предоставлять требования всех т | Подтверждено | S26 | NOT_STARTED |
| LC-DEC-05 | DOC-003 | Использовать диалог с аналитиком и стейкхолдером как основной механизм постепенного выявления и уточнения треб | Подтверждено | S26 | NOT_STARTED |
| LC-DEC-06 | DOC-003 | Применять комбинированную модель elicitation: аналитик предоставляет максимально полный доступный контекст и м | Подтверждено | S26 | NOT_STARTED |
| LC-DEC-07 | DOC-003 | Аналитик инициирует создание задачи и начинает взаимодействие с AI RES; автоматическая коммуникация со стейкхо | Подтверждено | S26 | NOT_STARTED |
| LC-DEC-08 | DOC-003 | Поддерживать два способа создания задач: аналитик создаёт их самостоятельно, Manager выявляет и предлагает зад | Подтверждено | S26 | NOT_STARTED |
| LC-DEC-09 | DOC-003 | Manager должен декомпозировать потребности и сложные требования, а также выявлять необходимые задачи для дальн | Подтверждено | S26 | NOT_STARTED |
| LC-DEC-10 | DOC-003 | Предложения задач Manager должны оставаться контролируемыми аналитиком; предложение задачи само по себе не озн | Предлагается принять | S26 | NOT_STARTED |
| LC-DEC-11 | DOC-003 | Manager самостоятельно определяет необходимые направления аналитической работы, формирует и адаптирует план за | Подтверждено | S26 | NOT_STARTED |
| LC-DEC-12 | DOC-003 | Использовать интеллектуальную оркестрацию: Manager определяет пользователем зависимости и последовательное/пар | Подтверждено | S26 | NOT_STARTED |
| LC-DEC-13 | DOC-003 | Manager не выполняет специализированные задачи самостоятельно: он распределяет их между специализированными Wo | Подтверждено | S26 | NOT_STARTED |
| LC-DEC-14 | DOC-003 | Поддерживать контролируемое взаимодействие Worker-to-Worker пользователем в рамках целей, полномочий и огранич | Подтверждено | S26 | NOT_STARTED |
| LC-DEC-15 | DOC-003 | Использовать комбинированную проверку результатов Workers: Manager проверяет каждый результат; независимая про | Подтверждено | S26 | NOT_STARTED |
| LC-DEC-16 | DOC-003 | При несогласии независимого проверяющего Worker с исходным результатом Manager не выбирает автоматически одну  | Подтверждено | S26 | NOT_STARTED |
| LC-DEC-17 | DOC-003 | При невозможности выполнения задачи Manager выбирает стратегию восстановления по причине неудачи: повторная по | Подтверждено | S26 | NOT_STARTED |
| LC-DEC-18 | DOC-003 | Worker вправе сигнализировать Manager о нехватке данных, противоречиях, рисках и блокировках, запрашивать разр | Подтверждено | S26 | NOT_STARTED |
| LC-DEC-19 | DOC-003 | Manager обязан проводить и фиксировать проверку готовности пользователем каждой задачи до запуска Worker. Пров | Подтверждено | S26 | NOT_STARTED |
| LT-01 | DOC-033 | Interactive workspace | — | S38 | NOT_STARTED |
| LT-02 | DOC-033 | Plan creation | — | S38 | NOT_STARTED |
| LT-03 | DOC-033 | Worker pool mixed capabilities | — | S38 | NOT_STARTED |
| LT-04 | DOC-033 | Ingestion burst | — | S38 | NOT_STARTED |
| LT-05 | DOC-033 | Artifact generation/export | — | S38 | NOT_STARTED |
| LT-06 | DOC-033 | Change impact | — | S38 | NOT_STARTED |
| LT-07 | DOC-033 | QA and evaluation batch | — | S38 | NOT_STARTED |
| LT-08 | DOC-033 | Provider degradation | — | S38 | NOT_STARTED |
| LT-09 | DOC-033 | Worker restart | — | S38 | NOT_STARTED |
| LT-10 | DOC-033 | Temporal outage/restart | — | S38 | NOT_STARTED |
| LT-11 | DOC-033 | PostgreSQL/MinIO pressure | — | S38 | NOT_STARTED |
| LT-12 | DOC-033 | Mixed peak + optional component outage | — | S38 | NOT_STARTED |
| OBS-ALR-001 | DOC-025 | Alert rule содержит name, severity, scope, condition, evaluation window/for, owner, runbook, user impact, auto | — | S13 | NOT_STARTED |
| OBS-ALR-002 | DOC-025 | Alerts дедуплицируются и подавляют flapping; paging только для пользовательского impact, integrity или securit | — | S13 | NOT_STARTED |
| OBS-ALR-003 | DOC-025 | Alert отделяет обнаруженный факт от гипотезы причины. | — | S13 | NOT_STARTED |
| OBS-ALR-004 | DOC-025 | Alert не может автоматически approve requirements, publish artifacts, expand permissions, change model/provide | — | S13 | NOT_STARTED |
| OBS-ALR-005 | DOC-025 | Автоматическое восстановление только заранее разрешёнными, ограниченными, обратимыми действиями с audit/trace. | — | S13 | NOT_STARTED |
| OBS-ALR-006 | DOC-025 | До production-like запуска назначить owner и escalation route каждому критичному alert. | — | S13 | NOT_STARTED |
| OBS-ALR-007 | DOC-025 | Низкоуровневые alerts нормализуются для Workspace; не создавать пользователю поток инфраструктурного шума. | — | S13 | NOT_STARTED |
| OBS-MON-001 | DOC-025 | MUST | Собирать health/availability | S13 | NOT_STARTED |
| OBS-MON-002 | DOC-025 | MUST | Собирать distributed traces  | S13 | NOT_STARTED |
| OBS-MON-003 | DOC-025 | MUST | Структурированные логи содер | S13 | NOT_STARTED |
| OBS-MON-004 | DOC-025 | MUST | Измерять длительность, outco | S13 | NOT_STARTED |
| OBS-MON-005 | DOC-025 | MUST | Измерять latency/errors/time | S13 | NOT_STARTED |
| OBS-MON-006 | DOC-025 | MUST | Собирать provider/model, LLM | S13 | NOT_STARTED |
| OBS-MON-007 | DOC-025 | MUST | Отражать Temporal backlog, s | S13 | NOT_STARTED |
| OBS-MON-008 | DOC-025 | MUST | Отражать Readiness Gate, Man | S13 | NOT_STARTED |
| OBS-MON-009 | DOC-025 | MUST | Коррелировать события с rele | S13 | NOT_STARTED |
| OBS-MON-010 | DOC-025 | MUST | Предоставить dashboards Plat | S13 | NOT_STARTED |
| OBS-MON-011 | DOC-025 | MUST | Для критичных отказов иметь  | S13 | NOT_STARTED |
| OBS-MON-012 | DOC-025 | MUST | Логи, metrics и traces испол | S13 | NOT_STARTED |
| OBS-MON-013 | DOC-025 | MUST | Обнаруживать деградацию tele | S13 | NOT_STARTED |
| OBS-MON-014 | DOC-025 | MUST | Недоступность telemetry back | S13 | NOT_STARTED |
| OBS-MON-015 | DOC-025 | MUST | Буферы и retries telemetry о | S13 | NOT_STARTED |
| OBS-MON-016 | DOC-025 | MUST | Поддерживать P50/P95/P99 для | S13 | NOT_STARTED |
| OBS-MON-017 | DOC-025 | SHOULD | Сравнивать поведение по верс | S13 | NOT_STARTED |
| OBS-MON-018 | DOC-025 | SHOULD | Сохранять sanitized producti | S13 | NOT_STARTED |
| OBS-MON-019 | DOC-025 | SHOULD | Собирать явную и ограниченны | S13 | NOT_STARTED |
| OBS-MON-020 | DOC-025 | POST-MVP | Drift analysis по выбранным  | S13 | NOT_STARTED |
| OBS-MON-021 | DOC-025 | POST-MVP | Shadow comparison новой моде | S13 | NOT_STARTED |
| OBS-MON-022 | DOC-025 | POST-MVP | Canary rollout только при tr | S13 | NOT_STARTED |
| OBS-MON-030 | DOC-025 | Для каждой критичной метрики определить смысл, единицу, источник, окно, владельца, baseline и action. | — | S13 | NOT_STARTED |
| OBS-MON-031 | DOC-025 | Технический успех должен отличаться от семантического качества и принятия результата. | — | S13 | NOT_STARTED |
| OBS-MON-032 | DOC-025 | `ACCEPTED_FOR_ORCHESTRATION`, `VERIFIED`, `VERIFIED_WITH_LIMITATIONS`, `DISPUTED`, `UNVERIFIED`, QA и human ap | — | S13 | NOT_STARTED |
| OBS-MON-033 | DOC-025 | Средние значения не использовать без распределения/percentile и sample size там, где важны хвостовые задержки. | — | S13 | NOT_STARTED |
| OBS-MON-034 | DOC-025 | `project_id`, `task_id`, `worker_run_id`, `trace_id` и прочие high-cardinality IDs запрещены в Prometheus labe | — | S13 | NOT_STARTED |
| OBS-MON-035 | DOC-025 | LLM cost маркировать `estimated`, если расчёт сделан по локальному pricing, а не provider billing. | — | S13 | NOT_STARTED |
| OBS-MON-036 | DOC-025 | Отсутствующая оценка качества не означает нулевое качество или успешность. | — | S13 | NOT_STARTED |
| OBS-SEC-001 | DOC-025 | MUST | Запретить в telemetry passwo | S13 | NOT_STARTED |
| OBS-SEC-002 | DOC-025 | MUST | По умолчанию не записывать f | S13 | NOT_STARTED |
| OBS-SEC-003 | DOC-025 | MUST | Redaction выполнять до telem | S13 | NOT_STARTED |
| OBS-SEC-004 | DOC-025 | MUST | Scrub stack traces и error m | S13 | NOT_STARTED |
| OBS-SEC-005 | DOC-025 | MUST | Ограничить dashboards/logs/t | S13 | NOT_STARTED |
| OBS-SEC-006 | DOC-025 | MUST | Отделить Domain/Security Aud | S13 | NOT_STARTED |
| OBS-SEC-007 | DOC-025 | MUST | Установить отдельные retenti | S13 | NOT_STARTED |
| OBS-SEC-008 | DOC-025 | MUST | Ограничить просмотр/экспорт  | S13 | NOT_STARTED |
| OBS-SEC-009 | DOC-025 | MUST | Temporal Web UI и observabil | S13 | NOT_STARTED |
| OBS-SEC-010 | DOC-025 | MUST | LLM content capture только п | S13 | NOT_STARTED |
| OBS-SEC-011 | DOC-025 | MUST | Telemetry не используется дл | S13 | NOT_STARTED |
| PERF-001 | DOC-031 | Классификация нагрузки | — | S38 | NOT_STARTED |
| PERF-002 | DOC-031 | Разделение API и длительных задач | — | S38 | NOT_STARTED |
| PERF-003 | DOC-031 | Изоляция control plane | — | S38 | NOT_STARTED |
| PERF-004 | DOC-031 | Worker concurrency | — | S38 | NOT_STARTED |
| PERF-005 | DOC-031 | Queue backpressure | — | S38 | NOT_STARTED |
| PERF-006 | DOC-031 | Fairness | — | S38 | NOT_STARTED |
| PERF-007 | DOC-031 | Приоритеты и starvation | — | S38 | NOT_STARTED |
| PERF-008 | DOC-031 | Resource budgets | — | S38 | NOT_STARTED |
| PERF-009 | DOC-031 | API performance telemetry | — | S38 | NOT_STARTED |
| PERF-010 | DOC-031 | Workflow performance telemetry | — | S38 | NOT_STARTED |
| PERF-011 | DOC-031 | Database efficiency | — | S38 | NOT_STARTED |
| PERF-012 | DOC-031 | Connection budget | — | S38 | NOT_STARTED |
| PERF-013 | DOC-031 | Async bulk processing | — | S38 | NOT_STARTED |
| PERF-014 | DOC-031 | Object/document processing | — | S38 | NOT_STARTED |
| PERF-015 | DOC-031 | Context efficiency | — | S38 | NOT_STARTED |
| PERF-016 | DOC-031 | LLM efficiency | — | S38 | NOT_STARTED |
| PERF-017 | DOC-031 | Cache correctness | — | S38 | NOT_STARTED |
| PERF-018 | DOC-031 | Capacity envelope | — | S38 | NOT_STARTED |
| PERF-019 | DOC-031 | SLO definitions | — | S38 | NOT_STARTED |
| PERF-020 | DOC-031 | Percentile reporting | — | S38 | NOT_STARTED |
| PERF-021 | DOC-031 | Capacity headroom | — | S38 | NOT_STARTED |
| PERF-022 | DOC-031 | Scale-out compatibility | — | S38 | NOT_STARTED |
| PERF-023 | DOC-031 | State consistency | — | S38 | NOT_STARTED |
| PERF-024 | DOC-031 | Resource saturation behavior | — | S38 | NOT_STARTED |
| PERF-025 | DOC-031 | Load test coverage | — | S38 | NOT_STARTED |
| PERF-026 | DOC-031 | No invented SLO | — | S38 | NOT_STARTED |
| PERSIST-001 | DOC-072 | Alembic upgrade empty DB | Reaches expected head | S04, S05 | TESTED (S04: Testcontainers PG16.15; live stack) |
| PERSIST-002 | DOC-072 | Upgrade previous supported revision | Data preserved, no drift | S04, S05 | PARTIAL (S04: одна ревизия; полноценно — S05) |
| PERSIST-003 | DOC-072 | One head / revision graph | No accidental branches | S04, S05 | TESTED (S04) |
| PERSIST-004 | DOC-072 | Offline SQL review | SQL matches reviewed revisio | S04, S05 | TESTED (S04: offline --sql + autocommit_block/CONCURRENTLY, test-only ревизия) |
| PERSIST-005 | DOC-072 | Runtime role DDL attempt | Permission denied | S04, S05 | PARTIAL (S04: DDL denied под login-ролями; на доменных таблицах — S05) |
| PERSIST-006 | DOC-072 | Runtime role TRUNCATE/DELETE protected rows | Permission denied | S04, S05 | PARTIAL (S04: TRUNCATE/DELETE/SELECT на объекте owner denied; доменные таблицы — S05) |
| PERSIST-007 | DOC-072 | Owner/BYPASSRLS flags | Runtime has neither | S04, S05 | TESTED (S04: catalog + audit gate) |
| PERSIST-008 | DOC-072 | Tenant A reads Tenant B | Zero rows / denied | S04, S05 | PARTIAL (S04: probe-таблица; доменные — S05) |
| PERSIST-009 | DOC-072 | Missing tenant context | Default deny | S04, S05 | PARTIAL (S04: probe-таблица; доменные — S05) |
| PERSIST-010 | DOC-072 | Connection pool context reuse | No tenant leakage | S04, S05 | PARTIAL (S04: pool reuse на одном соединении; доменные — S05) |
| PERSIST-011 | DOC-072 | Cross-project forged IDs | Denied by Policy + RLS | S04, S05 | NOT_STARTED |
| PERSIST-012 | DOC-072 | Event sequence concurrent updates | Unique contiguous sequence p | S04, S05 | NOT_STARTED |
| PERSIST-013 | DOC-072 | Idempotency same key/fingerprint concurrency | One resource, same response | S04, S05 | NOT_STARTED |
| PERSIST-014 | DOC-072 | Same key, different fingerprint | `IDEMPOTENCY_KEY_REUSED` | S04, S05 | NOT_STARTED |
| PERSIST-015 | DOC-072 | Outbox crash after publish before mark | Duplicate delivery safely de | S04, S05, S10 | TESTED (test_event_delivery) |
| PERSIST-016 | DOC-072 | Inbox crash before commit | No partial local effect | S04, S05, S10 | TESTED (test_event_delivery) |
| PERSIST-017 | DOC-072 | Backfill stop/restart | Safe resume, no duplicate ma | S04, S05 | NOT_STARTED |
| PERSIST-018 | DOC-072 | FK NOT VALID then VALIDATE | Validation detects orphan | S04, S05 | NOT_STARTED |
| PERSIST-019 | DOC-072 | Concurrent index interrupted | Invalid index detected and r | S04, S05 | NOT_STARTED |
| PERSIST-020 | DOC-072 | Alembic lock timeout | Deployment fails safely, no  | S04, S05 | NOT_STARTED |
| PERSIST-021 | DOC-072 | Backup restore rehearsal | Recovery manifest reconciled | S04, S05 | NOT_STARTED |
| PERSIST-022 | DOC-072 | Secret rotation | New credentials work; old re | S04, S05 | NOT_STARTED |
| PERSIST-023 | DOC-072 | Manager/Worker Runtime DB access | No secret and no network pat | S04, S05 | PARTIAL (S04: у api/прочих нет DB credentials; сетевой путь Manager/Worker — S11/S23) |
| PERSIST-024 | DOC-072 | Schema drift | CI fails | S04, S05 | TESTED (S04: reviewed snapshot + drift test) |
| PROC-MVP-001 | DOC-009 | Project initiation | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-002 | DOC-009 | Evidence-aware elicitation | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-003 | DOC-009 | Candidate requirement lifecycle | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-004 | DOC-009 | Adaptive Manager planning | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-005 | DOC-009 | Immutable PlanVersion | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-006 | DOC-009 | Dependency graph validation | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-007 | DOC-009 | Controlled plan approval | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-008 | DOC-009 | Impact-based replanning | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-009 | DOC-009 | Mandatory Readiness Gate | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-010 | DOC-009 | Gate staleness protection | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-011 | DOC-009 | Immutable WorkerRun context | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-012 | DOC-009 | Controlled Worker handoff | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-013 | DOC-009 | Worker result validation | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-014 | DOC-009 | Separate verification levels | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-015 | DOC-009 | Risk-based independent QA | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-016 | DOC-009 | Source ingestion pipeline | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-017 | DOC-009 | Separate change assessment | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-018 | DOC-009 | Hybrid impact analysis | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-019 | DOC-009 | Artifact lifecycle orchestration | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-020 | DOC-009 | Change Request and Baseline | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-021 | DOC-009 | Classified recovery | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-022 | DOC-009 | Safe pause/cancel/resume | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-023 | DOC-009 | Parallelism and join rules | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-024 | DOC-009 | Manager next-action policy | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-025 | DOC-009 | Process domain events | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-026 | DOC-009 | Process observability | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-027 | DOC-009 | Process evaluation sets | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-028 | DOC-009 | Process deployment gates | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-029 | DOC-009 | Typed Worker Coordination Request | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-030 | DOC-009 | Mediated Worker-to-Worker coordination | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-031 | DOC-009 | Per-Run scope and readiness | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-032 | DOC-009 | Manager adjudication by risk tier | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-033 | DOC-009 | Separate orchestration acceptance and verification | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-034 | DOC-009 | Independent QA blind-first | MVP | S12, S20–S32 | NOT_STARTED |
| PROC-MVP-035 | DOC-009 | Platform-mediated Blackboard | MVP | S12, S20–S32 | NOT_STARTED |
| REL-001 | DOC-032 | Durable workflow | — | S32, S38 | NOT_STARTED |
| REL-002 | DOC-032 | Разделение источников истины | — | S32, S38 | NOT_STARTED |
| REL-003 | DOC-032 | Bounded retries | — | S32, S38 | NOT_STARTED |
| REL-004 | DOC-032 | Cancellation propagation | — | S32, S38 | NOT_STARTED |
| REL-005 | DOC-032 | Idempotent Activities | — | S32, S38 | NOT_STARTED |
| REL-006 | DOC-032 | External side effects | — | S32, S38 | NOT_STARTED |
| REL-007 | DOC-032 | Transactional event consistency | — | S32, S38 | NOT_STARTED |
| REL-008 | DOC-032 | Circuit breaker | — | S32, S38 | NOT_STARTED |
| REL-009 | DOC-032 | Bulkheads | — | S32, S38 | NOT_STARTED |
| REL-010 | DOC-032 | Graceful degradation | — | S32, S38 | NOT_STARTED |
| REL-011 | DOC-032 | Audit fail-closed | — | S32, S38 | NOT_STARTED |
| REL-012 | DOC-032 | Storage dependency | — | S32, S38 | NOT_STARTED |
| REL-013 | DOC-032 | Temporal outage | — | S32, S38 | NOT_STARTED |
| REL-014 | DOC-032 | Provider outage | — | S32, S38 | NOT_STARTED |
| REL-015 | DOC-032 | Retry amplification control | — | S32, S38 | NOT_STARTED |
| REL-016 | DOC-032 | Health/readiness | — | S32, S38 | NOT_STARTED |
| REL-017 | DOC-032 | Recovery manifest | — | S32, S38 | NOT_STARTED |
| REL-018 | DOC-032 | Independent backup domains | — | S32, S38 | NOT_STARTED |
| REL-019 | DOC-032 | RPO/RTO targets | — | S32, S38 | NOT_STARTED |
| REL-020 | DOC-032 | Recovery reconciliation | — | S32, S38 | NOT_STARTED |
| REL-021 | DOC-032 | DR drills | — | S32, S38 | NOT_STARTED |
| REL-022 | DOC-032 | Single-node limitation | — | S32, S38 | NOT_STARTED |
| REL-023 | DOC-032 | Rollback safety | — | S32, S38 | NOT_STARTED |
| REL-024 | DOC-032 | Partial failure tests | — | S32, S38 | NOT_STARTED |
| REL-025 | DOC-032 | Data integrity | — | S32, S38 | NOT_STARTED |
| REL-026 | DOC-032 | Recovery audit | — | S32, S38 | NOT_STARTED |
| REL-027 | DOC-032 | Degraded mode visibility | — | S32, S38 | NOT_STARTED |
| REL-028 | DOC-032 | Security boundary | — | S32, S38 | NOT_STARTED |
| RULE-MVP-01 | DOC-009 | Разделение ответственности | Обязательно | S18 | NOT_STARTED |
| RULE-MVP-02 | DOC-009 | Реестр правил | Обязательно | S18 | NOT_STARTED |
| RULE-MVP-03 | DOC-009 | Иерархия правил | Обязательно | S18 | NOT_STARTED |
| RULE-MVP-04 | DOC-009 | Жизненный цикл | Обязательно | S18 | NOT_STARTED |
| RULE-MVP-05 | DOC-009 | Предложение Manager Обязательно | Manager создаёт | S18 | NOT_STARTED |
| RULE-MVP-06 | DOC-009 | Автоматическая валидация | Обязательно, | S18 | NOT_STARTED |
| RULE-MVP-07 | DOC-009 | Детерминированное исполнение | Обязательно | S18 | NOT_STARTED |
| RULE-MVP-08 | DOC-009 | Конфликт правил | Обязательно | S18 | NOT_STARTED |
| RULE-MVP-09 | DOC-009 | Безопасный формат | Обязательно | S18 | NOT_STARTED |
| RULE-MVP-10 | DOC-009 | Исключения | Обязательно | S18 | NOT_STARTED |
| RULE-MVP-11 | DOC-009 | Аудит и воспроизводимость | Обязательно | S18 | NOT_STARTED |
| RULE-MVP-12 | DOC-009 | Независимая авторизация | Обязательно | S18 | NOT_STARTED |
| RULE-MVP-13 | DOC-009 | Simulation/dry run | Желательно для | S18 | NOT_STARTED |
| RULE-MVP-14 | DOC-009 | Визуальный конструктор правил | Позже | S18 | NOT_STARTED |
| SEC-001 | DOC-020 | Каждый API endpoint, работающий с объектом, MUST выполнять object-level authorization | P0 | S02–S37 (по области); S37 верификация | PARTIAL (S07: Policy Engine + enforcer + conceal-404 протестированы; применение к доменным endpoint — S08+); S08: object-level ACL на всех 12 GET, IDOR → один 404 (ADR-075) |
| SEC-002 | DOC-020 | ACL MUST применяться до retrieval, graph traversal, cache response, summarization и export | P0 | S02–S37 (по области); S37 верификация | NOT_STARTED; S08: object-level ACL на всех 12 GET, IDOR → один 404 (ADR-075) |
| SEC-003 | DOC-020 | Каждая Worker Run MUST иметь scoped grants с expiry; права не наследуются автоматически | P0 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-004 | DOC-020 | Каждый tool/connector side effect MUST проходить независимую policy authorization перед исполнением | P0 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-005 | DOC-020 | Worker/Manager MUST NOT иметь прямой произвольный доступ к provider credentials | P0 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-006 | DOC-020 | Secrets MUST NOT appear in prompts, Context Packages, Worker Results, Temporal History, logs or traces | P0 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-007 | DOC-020 | LLM requests MUST route through AI RES LLM Gateway Adapter and approved Gateway | P0 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-008 | DOC-020 | Provider/model routing MUST enforce data classification and egress policy | P0 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-009 | DOC-020 | Fallback MUST use only explicitly allowed provider/model profiles and MUST re-evaluate data policy | P0 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-010 | DOC-020 | External writes MUST be deny-by-default in MVP unless separately approved and scoped | P0 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-011 | DOC-020 | Untrusted source/tool output MUST NOT modify system/org/project rules or grants | P0 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-012 | DOC-020 | MCP servers and tools MUST be registered, versioned, allowlisted and policy-checked | P1 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-013 | DOC-020 | Services MUST use separate service identities and least-privilege credentials | P0 | S02–S37 (по области); S37 верификация | PARTIAL (S07: отдельные ключи и токены сервисов, библиотека; сервисы-потребители — S11/S23) |
| SEC-014 | DOC-020 | PostgreSQL, Temporal, MinIO and Redis MUST NOT be publicly exposed | P0 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-015 | DOC-020 | Only Reverse Proxy MUST expose user-facing ingress in MVP | P0 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-016 | DOC-020 | Runtime containers MUST be non-root, non-privileged and MUST NOT mount Docker Socket | P0 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-017 | DOC-020 | Runtime resources, file sizes, execution time, concurrency and retries MUST be bounded | P0 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-018 | DOC-020 | URL fetchers/connectors MUST prevent SSRF, private IP access and unsafe redirects | P0 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-019 | DOC-020 | Domain audit MUST record actor, action, resource, scope, policy decision and correlation IDs | P0 | S02–S37 (по области); S37 верификация | PARTIAL (S07: audit writer в одной транзакции, policy_version, fail-closed; покрытие остальных доменных действий — по этапам) |
| SEC-020 | DOC-020 | Audit data MUST be protected from ordinary application update/delete paths | P1 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-021 | DOC-020 | Telemetry MUST redact secrets and sensitive payloads by default | P0 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-022 | DOC-020 | Admin interfaces MUST be restricted to authorized administrators | P0 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-023 | DOC-020 | Temporal Signals/Updates MUST be authorized by Backend before dispatch | P0 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-024 | DOC-020 | Generated HTML/Markdown/SQL/OpenAPI/diagrams MUST be validated/safely rendered before use | P1 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-025 | DOC-020 | Container images MUST be pinned by digest for reproducible deployment | P1 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-026 | DOC-020 | Release images SHOULD have SBOM, vulnerability scan and provenance/signature evidence | P1 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-027 | DOC-020 | Secret rotation/revocation MUST have documented owner and runbook | P1 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-028 | DOC-020 | Backups containing sensitive data MUST be encrypted and access-controlled | P0 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-029 | DOC-020 | Critical approval MUST bind to exact object version/hash | P0 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-030 | DOC-020 | Security-relevant events MUST be monitored and alertable | P1 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-031 | DOC-020 | Security incidents MUST have containment, credential revocation, evidence preservation and recovery runbooks | P1 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-032 | DOC-020 | AI evaluation suite MUST include prompt injection, data exfiltration, cross-project leakage and tool misuse ca | P0 | S02–S37 (по области); S37 верификация | NOT_STARTED |
| SEC-MVP-001 | DOC-009 | Object-level authorization на API и всех путях доступа к доменным объектам | MUST | S07; S37 | PARTIAL (S07: см. SEC-001) |
| SEC-MVP-002 | DOC-009 | ACL до retrieval/search/graph/cache/export | MUST | S07; S37 | NOT_STARTED |
| SEC-MVP-003 | DOC-009 | Scoped, expiring Worker Run grants | MUST | S07; S37 | NOT_STARTED |
| SEC-MVP-004 | DOC-009 | Per-operation authorization для tool/connector calls | MUST | S07; S37 | NOT_STARTED |
| SEC-MVP-005 | DOC-009 | LLM Gateway Adapter; отсутствие прямых provider calls из Runtime | MUST | S07; S37 | NOT_STARTED |
| SEC-MVP-006 | DOC-009 | Data classification и egress/model routing policy | MUST | S07; S37 | NOT_STARTED |
| SEC-MVP-007 | DOC-009 | Secret isolation from prompts, context, Temporal and telemetry | MUST | S07; S37 | NOT_STARTED |
| SEC-MVP-008 | DOC-009 | Deny-by-default external writes in MVP | MUST | S07; S37 | NOT_STARTED |
| SEC-MVP-009 | DOC-009 | Prompt injection and tool misuse evaluation cases | MUST | S07; S37 | NOT_STARTED |
| SEC-MVP-010 | DOC-009 | SSRF protection for URL/document/connectors | MUST | S07; S37 | NOT_STARTED |
| SEC-MVP-011 | DOC-009 | Non-root containers, no privileged, no Docker Socket | MUST | S07; S37 | TESTED (S03) |
| SEC-MVP-012 | DOC-009 | Internal data services not publicly exposed | MUST | S07; S37 | TESTED (S03) |
| SEC-MVP-013 | DOC-009 | Security audit events and correlation | MUST | S07; S37 | PARTIAL (S07: см. SEC-019) |
| SEC-MVP-014 | DOC-009 | Authorized Temporal Signals/Updates | MUST | S07; S37 | NOT_STARTED |
| SEC-MVP-015 | DOC-009 | Encrypted, access-controlled backups | MUST | S07; S37 | NOT_STARTED |
| THR-001 | DOC-017 | Indirect prompt injection в PDF/Markdown/репозитории заставляет агента раскрыть данные или вызвать инструмент | Утечка/несанкционированное д | S03, S05, S07, S16, S17, S23, S37 (по области угрозы) | NOT_STARTED |
| THR-002 | DOC-017 | Worker использует права сервисной учётной записи шире Task/Run scope | Межпроектный доступ/изменени | S03, S05, S07, S16, S17, S23, S37 (по области угрозы) | NOT_STARTED |
| THR-003 | DOC-017 | Ошибка ACL в RAG/графе/кеше возвращает чужие фрагменты или summary | Утечка данных | S03, S05, S07, S16, S17, S23, S37 (по области угрозы) | NOT_STARTED |
| THR-004 | DOC-017 | Prompt/tool output содержит секрет и он попадает в LLM, Temporal, logs или result | Компрометация credentials | S03, S05, S07, S16, S17, S23, S37 (по области угрозы) | NOT_STARTED |
| THR-005 | DOC-017 | SSRF через URL/document parser/connector вызывает доступ к metadata/internal services | Захват внутренних сервисов/д | S03, S05, S07, S16, S17, S23, S37 (по области угрозы) | NOT_STARTED |
| THR-006 | DOC-017 | Подмена MCP server/tool schema или supply-chain package | Произвольные действия/утечка | S03, S05, S07, S16, S17, S23, S37 (по области угрозы) | NOT_STARTED |
| THR-007 | DOC-017 | BOLA/IDOR в API позволяет обратиться к чужому Project/Epic/Artifact | Утечка/изменение | S03, S05, S07, S16, S17, S23, S37 (по области угрозы) | NOT_STARTED |
| THR-008 | DOC-017 | Подделка Temporal Signal/Update или прямой доступ к Temporal UI | Несанкционированное изменени | S03, S05, S07, S16, S17, S23, S37 (по области угрозы) | NOT_STARTED |
| THR-009 | DOC-017 | Злоумышленник использует egress/LLM для exfiltration через модельные prompts | Утечка корпоративных данных | S03, S05, S07, S16, S17, S23, S37 (по области угрозы) | NOT_STARTED |
| THR-010 | DOC-017 | Слишком широкие tool permissions и excessive agency | Внешнее/необратимое действие | S03, S05, S07, S16, S17, S23, S37 (по области угрозы) | NOT_STARTED |
| THR-011 | DOC-017 | Poisoning memory/exemplar/evaluation data | Систематическое ухудшение ре | S03, S05, S07, S16, S17, S23, S37 (по области угрозы) | NOT_STARTED |
| THR-012 | DOC-017 | Недоверенный generated SQL/HTML/Markdown/diagram/code исполняется или рендерится небезопасно | XSS/инъекция/компрометация | S03, S05, S07, S16, S17, S23, S37 (по области угрозы) | NOT_STARTED |
| THR-013 | DOC-017 | Компрометация Docker host или чрезмерные privileges контейнера | Полный компромисс среды | S03, S05, S07, S16, S17, S23, S37 (по области угрозы) | NOT_STARTED |
| THR-014 | DOC-017 | Секреты попадают в backup/config repository | Длительная компрометация | S03, S05, S07, S16, S17, S23, S37 (по области угрозы) | NOT_STARTED |
| THR-015 | DOC-017 | Audit Log изменён/удалён администратором или атакующим | Потеря доказательств | S03, S05, S07, S16, S17, S23, S37 (по области угрозы) | NOT_STARTED |
| THR-016 | DOC-017 | Resource exhaustion через циклы агентов, большие файлы, retries или tool calls | DoS/рост расходов | S03, S05, S07, S16, S17, S23, S37 (по области угрозы) | NOT_STARTED |
| THR-017 | DOC-017 | Подмена образа/зависимости/Compose config | Выполнение вредоносного кода | S03, S05, S07, S16, S17, S23, S37 (по области угрозы) | NOT_STARTED |
| THR-018 | DOC-017 | Утечка данных через Langfuse/observability dashboards | Раскрытие prompt/payload | S03, S05, S07, S16, S17, S23, S37 (по области угрозы) | NOT_STARTED |
| THR-019 | DOC-017 | Model fallback переключает запрос на неподходящий provider/location | Нарушение data residency/pol | S03, S05, S07, S16, S17, S23, S37 (по области угрозы) | NOT_STARTED |
| THR-020 | DOC-017 | Ошибка восстановления связывает Workflow с неверной версией контекста/артефакта | Некорректные действия/порча  | S03, S05, S07, S16, S17, S23, S37 (по области угрозы) | NOT_STARTED |
| UX-ART-01 | DOC-009 | Единый Artifact Registry | MVP | S31, S36 | NOT_STARTED |
| UX-ART-02 | DOC-009 | Стабильная идентичность | MVP | S31, S36 | NOT_STARTED |
| UX-ART-03 | DOC-009 | Тип артефакта | MVP | S31, S36 | NOT_STARTED |
| UX-ART-04 | DOC-009 | Назначение и аудитория | MVP | S31, S36 | NOT_STARTED |
| UX-ART-05 | DOC-009 | Source of Truth Mode | MVP | S31, S36 | NOT_STARTED |
| UX-ART-06 | DOC-009 | Неизменяемая версия | MVP | S31, S36 | NOT_STARTED |
| UX-ART-07 | DOC-009 | Представления | MVP | S31, S36 | NOT_STARTED |
| UX-ART-08 | DOC-009 | Provenance генерации | MVP | S31, S36 | NOT_STARTED |
| UX-ART-09 | DOC-009 | Шаблоны и версии | MVP | S31, S36 | NOT_STARTED |
| UX-ART-10 | DOC-009 | Generate | MVP | S31, S36 | NOT_STARTED |
| UX-ART-11 | DOC-009 | Update | MVP | S31, S36 | NOT_STARTED |
| UX-ART-12 | DOC-009 | Import | MVP | S31, S36 | NOT_STARTED |
| UX-ART-13 | DOC-009 | Compose/Export | MVP | S31, S36 | NOT_STARTED |
| UX-ART-14 | DOC-009 | Универсальная валидация | MVP | S31, S36 | NOT_STARTED |
| UX-ART-15 | DOC-009 | Типоспецифические валидаторы | MVP | S31, S36 | NOT_STARTED |
| UX-ART-16 | DOC-009 | Отдельный Validation Report | MVP | S31, S36 | NOT_STARTED |
| UX-ART-17 | DOC-009 | Review lifecycle | MVP | S31, S36 | NOT_STARTED |
| UX-ART-18 | DOC-009 | Approval lifecycle | MVP | S31, S36 | NOT_STARTED |
| UX-ART-19 | DOC-009 | Publication lifecycle | MVP | S31, S36 | NOT_STARTED |
| UX-ART-20 | DOC-009 | Ручное редактирование | MVP | S31, S36 | NOT_STARTED |
| UX-ART-21 | DOC-009 | Конфликты ручных и AI-изменений | MVP | S31, S36 | NOT_STARTED |
| UX-ART-22 | DOC-009 | Связь с трассируемостью | MVP | S31, S36 | NOT_STARTED |
| UX-ART-23 | DOC-009 | Impact Analysis | MVP | S31, S36 | NOT_STARTED |
| UX-ART-24 | DOC-009 | Локальная регенерация | MVP | S31, S36 | NOT_STARTED |
| UX-ART-25 | DOC-009 | Полная проверка | MVP | S31, S36 | NOT_STARTED |
| UX-ART-26 | DOC-009 | Baseline | MVP | S31, S36 | NOT_STARTED |
| UX-ART-27 | DOC-009 | Каталог UX | MVP | S31, S36 | NOT_STARTED |
| UX-ART-28 | DOC-009 | Карточка артефакта | MVP | S31, S36 | NOT_STARTED |
| UX-ART-29 | DOC-009 | Разделение ролей | MVP | S31, S36 | NOT_STARTED |
| UX-ART-30 | DOC-009 | Аудит | MVP | S31, S36 | NOT_STARTED |
| UX-ART-31 | DOC-009 | Markdown/DOCX/PDF | MVP | S31, S36 | NOT_STARTED |
| UX-ART-32 | DOC-009 | OpenAPI | MVP | S31, S36 | NOT_STARTED |
| UX-ART-33 | DOC-009 | Mermaid/PlantUML | MVP | S31, S36 | NOT_STARTED |
| UX-ART-34 | DOC-009 | BPMN-native | После MVP | S31, S36 | DEFERRED (post-MVP) |
| UX-ART-35 | DOC-009 | AsyncAPI/Protobuf/Avro | После MVP | S31, S36 | DEFERRED (post-MVP) |
| UX-ART-36 | DOC-009 | Внешняя синхронизация | После MVP | S31, S36 | DEFERRED (post-MVP) |
| UX-ART-37 | DOC-009 | Пакетная генерация | После MVP | S31, S36 | DEFERRED (post-MVP) |
| UX-ART-38 | DOC-009 | Локализация | После MVP | S31, S36 | DEFERRED (post-MVP) |
| UX-ART-39 | DOC-009 | Электронная подпись/retention | Открыто | S31, S36 | OPEN (не решено) |
| UX-ART-40 | DOC-009 | Матрица approval | Открыто | S31, S36 | OPEN (не решено) |
| UX-ART-41 | DOC-009 | Шаблоны организации | Открыто | S31, S36 | OPEN (не решено) |
| UX-ART-42 | DOC-009 | Редактор | Открыто | S31, S36 | OPEN (не решено) |
| UX-DUR-01 | DOC-009 | Типизированный реестр | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-02 | DOC-009 | Автоматическое выявление | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-03 | DOC-009 | Provenance | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-04 | DOC-009 | Разделение предложения и решения | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-05 | DOC-009 | Pending Decision | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-06 | DOC-009 | Управление допущениями | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-07 | DOC-009 | Пересмотр допущения | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-08 | DOC-009 | Risk vs Issue | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-09 | DOC-009 | Оценка риска | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-10 | DOC-009 | Остаточный риск | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-11 | DOC-009 | Неизвестные | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-12 | DOC-009 | Гипотезы | Желательно | S26, S36 | NOT_STARTED |
| UX-DUR-13 | DOC-009 | Конфликты | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-14 | DOC-009 | Decision Proposal | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-15 | DOC-009 | Decision Record / ADR | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-16 | DOC-009 | Пересмотр решения | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-17 | DOC-009 | Владельцы | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-18 | DOC-009 | Эскалация | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-19 | DOC-009 | Приоритизация | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-20 | DOC-009 | Честная неопределённость | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-21 | DOC-009 | Локальная блокировка | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-22 | DOC-009 | Меры риска | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-23 | DOC-009 | Статус по evidence Обязательно | Автоизменение статуса основа | S26, S36 | NOT_STARTED |
| UX-DUR-24 | DOC-009 | Полномочия | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-25 | DOC-009 | Контекст Worker | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-26 | DOC-009 | Оспаривание | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-27 | DOC-009 | Уведомления | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-28 | DOC-009 | Аудит | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-29 | DOC-009 | Проверяемость классификации | Обязательно | S26, S36 | NOT_STARTED |
| UX-DUR-30 | DOC-009 | Калибровка оценок | Желательно | S26, S36 | NOT_STARTED |
| UX-DUR-31 | DOC-009 | SLA реакции | Открыто | S26, S36 | OPEN (не решено) |
| UX-DUR-32 | DOC-009 | Внешние реестры | Открыто | S26, S36 | OPEN (не решено) |
| UX-MVP-01 | DOC-009 | Hybrid Workspace Обязательно | Структурированные | S35, S36 | NOT_STARTED |
| UX-MVP-02 | DOC-009 | Project Overview Обязательно | Пользователь видит | S35, S36 | NOT_STARTED |
| UX-MVP-03 | DOC-009 | Attention Center Обязательно | Блокировки, | S35, S36 | NOT_STARTED |
| UX-MVP-04 | DOC-009 | Manager Plan Transparency | Обязательно | S35, S36 | NOT_STARTED |
| UX-MVP-05 | DOC-009 | Worker Execution Обязательно Status | Видны стадия, | S35, S36 | NOT_STARTED |
| UX-MVP-06 | DOC-009 | Contextual Manager Panel | Обязательно | S35, S36 | NOT_STARTED |
| UX-MVP-07 | DOC-009 | Autonomy Transparency | Обязательно | S35, S36 | NOT_STARTED |
| UX-MVP-08 | DOC-009 | Approval Guardrails | Обязательно | S35, S36 | NOT_STARTED |
| UX-MVP-09 | DOC-009 | Async Continuity Обязательно | Длительная работа | S35, S36 | NOT_STARTED |
| UX-MVP-10 | DOC-009 | Useful Notifications | Желательно для | S35, S36 | NOT_STARTED |
| UX-MVP-11 | DOC-009 | Provenance & Uncertainty | Обязательно | S35, S36 | NOT_STARTED |
| UX-MVP-12 | DOC-009 | Failure Recovery Обязательно | Ошибка объясняется; | S35, S36 | NOT_STARTED |
| UX-MVP-13 | DOC-009 | Technical Diagnostics Separation | Желательно для | S35, S36 | NOT_STARTED |
| UX-MVP-14 | DOC-009 | Responsive Workspace | Обязательно | S35, S36 | NOT_STARTED |
| UX-MVP-15 | DOC-009 | User Continuity | Обязательно | S35, S36 | NOT_STARTED |
| UX-PLAN-01 | DOC-009 | Plan как самостоятельная сущность | Обязательно | S21, S36 | NOT_STARTED |
| UX-PLAN-02 | DOC-009 | Версионирование плана | Обязательно | S21, S36 | NOT_STARTED |
| UX-PLAN-03 | DOC-009 | Состав плана | Обязательно | S21, S36 | NOT_STARTED |
| UX-PLAN-04 | DOC-009 | Обоснование предложений | Обязательно | S21, S36 | NOT_STARTED |
| UX-PLAN-05 | DOC-009 | Разделение Plan Item и Task | Обязательно | S21, S36 | NOT_STARTED |
| UX-PLAN-06 | DOC-009 | Управление предложениями | Обязательно | S21, S36 | NOT_STARTED |
| UX-PLAN-07 | DOC-009 | Частичное подтверждение | Желательно для | S21, S36 | NOT_STARTED |
| UX-PLAN-08 | DOC-009 | Видимость зависимостей | Обязательно | S21, S36 | NOT_STARTED |
| UX-PLAN-09 | DOC-009 | Статусы плана/задачи/Run | Обязательно | S21, S36 | NOT_STARTED |
| UX-PLAN-10 | DOC-009 | Динамическое перепланирование | Обязательно | S21, S36 | NOT_STARTED |
| UX-PLAN-11 | DOC-009 | Классификация изменений плана | Обязательно | S21, S36 | NOT_STARTED |
| UX-PLAN-12 | DOC-009 | Человеческое подтверждение | Обязательно | S21, S36 | NOT_STARTED |
| UX-PLAN-13 | DOC-009 | Новые задачи от Manager | Обязательно | S21, S36 | NOT_STARTED |
| UX-PLAN-14 | DOC-009 | Параллельное выполнение | Обязательно | S21, S36 | NOT_STARTED |
| UX-PLAN-15 | DOC-009 | Контроль прогресса Обязательно | Показываются | S21, S36 | NOT_STARTED |
| UX-PLAN-16 | DOC-009 | Восстановление выполнения | Обязательно | S21, S36 | NOT_STARTED |
| UX-PLAN-17 | DOC-009 | Пауза и отмена | Обязательно | S21, S36 | NOT_STARTED |
| UX-PLAN-18 | DOC-009 | Уведомления о плане | Желательно для | S21, S36 | NOT_STARTED |
| UX-PLAN-19 | DOC-009 | Возобновление работы | Обязательно | S21, S36 | NOT_STARTED |
| UX-REQ-01 | DOC-009 | Единый раздел требований | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-02 | DOC-009 | Простое создание | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-03 | DOC-009 | Несколько источников создания | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-04 | DOC-009 | Предварительная регистрация | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-05 | DOC-009 | Автоматическая классификация | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-06 | DOC-009 | Автозаполнение метаданных | Желательно | S26, S36 | NOT_STARTED |
| UX-REQ-07 | DOC-009 | Карточка требования | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-08 | DOC-009 | Простое редактирование | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-09 | DOC-009 | AI-помощь в формулировке | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-10 | DOC-009 | Сохранение оригинала | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-11 | DOC-009 | Автономная нормализация | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-12 | DOC-009 | Защита утверждённых требований | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-13 | DOC-009 | Декомпозиция | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-14 | DOC-009 | Поиск дублей | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-15 | DOC-009 | Контролируемое объединение | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-16 | DOC-009 | Выявление противоречий | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-17 | DOC-009 | Автономное разрешение конфликтов | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-18 | DOC-009 | Предложение связей | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-19 | DOC-009 | Provenance связей Обязательно | Для автоматических содержате | S26, S36 | NOT_STARTED |
| UX-REQ-20 | DOC-009 | Контекстная проверка качества | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-21 | DOC-009 | Понятная готовность | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-22 | DOC-009 | Автоматическая подготовка согласования | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-23 | DOC-009 | Ролевое утверждение | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-24 | DOC-009 | Разделение принятия и Baseline | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-25 | DOC-009 | Массовые операции Желательно | Поддержаны безопасные группо | S26, S36 | NOT_STARTED |
| UX-REQ-26 | DOC-009 | Версии и история | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-27 | DOC-009 | Анализ влияния | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-28 | DOC-009 | Архивирование вместо потери | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-29 | DOC-009 | Упрощённый список Обязательно | Основной список показывает т | S26, S36 | NOT_STARTED |
| UX-REQ-30 | DOC-009 | Одно следующее действие | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-31 | DOC-009 | Автономная обработка рутины | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-32 | DOC-009 | Контроль автономности | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-33 | DOC-009 | Уведомления по значимым событиям | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-34 | DOC-009 | Поиск и фильтрация | Обязательно | S26, S36 | NOT_STARTED |
| UX-REQ-35 | DOC-009 | Восстановление версии | Желательно | S26, S36 | NOT_STARTED |
| UX-RESULT-01 | DOC-009 | Уведомление о готовности | Обязательно | S25, S36 | NOT_STARTED |
| UX-RESULT-02 | DOC-009 | Краткое представление | Обязательно | S25, S36 | NOT_STARTED |
| UX-RESULT-03 | DOC-009 | Единая карточка результата | Обязательно | S25, S36 | NOT_STARTED |
| UX-RESULT-04 | DOC-009 | Подробности по запросу | Обязательно | S25, S36 | NOT_STARTED |
| UX-RESULT-05 | DOC-009 | Происхождение выводов | Обязательно | S25, S36 | NOT_STARTED |
| UX-RESULT-06 | DOC-009 | Типы сведений | Обязательно | S25, S36 | NOT_STARTED |
| UX-RESULT-07 | DOC-009 | Неопределённость и ограничения | Обязательно | S25, S36 | NOT_STARTED |
| UX-RESULT-08 | DOC-009 | Комментарии к результату | Обязательно | S25, S36 | NOT_STARTED |
| UX-RESULT-09 | DOC-009 | Возврат на доработку Обязательно | Аналитик может запросить | S25, S36 | NOT_STARTED |
| UX-RESULT-10 | DOC-009 | Отклонение результата | Обязательно | S25, S36 | NOT_STARTED |
| UX-RESULT-11 | DOC-009 | Независимая QA-проверка | Обязательно | S25, S36 | NOT_STARTED |
| UX-RESULT-12 | DOC-009 | Прозрачный итог QA | Обязательно | S25, S36 | NOT_STARTED |
| UX-RESULT-13 | DOC-009 | Разделение принятия и утверждения | Обязательно | S25, S36 | NOT_STARTED |
| UX-RESULT-14 | DOC-009 | Ролевое бизнес-утверждение | Обязательно | S25, S36 | NOT_STARTED |
| UX-RESULT-15 | DOC-009 | Передача downstream | Обязательно | S25, S36 | NOT_STARTED |
| UX-RESULT-16 | DOC-009 | Предварительные результаты | Обязательно | S25, S36 | NOT_STARTED |
| UX-RESULT-17 | DOC-009 | Версионирование результата | Обязательно | S25, S36 | NOT_STARTED |
| UX-RESULT-18 | DOC-009 | Сравнение версий | Желательно для Пользователь  | S25, S36 | NOT_STARTED |
| UX-RESULT-19 | DOC-009 | Влияние изменений источника | Обязательно | S25, S36 | NOT_STARTED |
| UX-RESULT-20 | DOC-009 | Устаревание результата | Обязательно | S25, S36 | NOT_STARTED |
| UX-RESULT-21 | DOC-009 | Точечная перепроверка | Обязательно | S25, S36 | NOT_STARTED |
| UX-RESULT-22 | DOC-009 | Сдержанные уведомления | Обязательно | S25, S36 | NOT_STARTED |
| UX-RESULT-23 | DOC-009 | Простота статусов | Обязательно | S25, S36 | NOT_STARTED |
| UX-RESULT-24 | DOC-009 | Восстановление и история | Обязательно | S25, S36 | NOT_STARTED |
| UX-RESULT-25 | DOC-009 | Отсутствие перегрузки | Обязательно | S25, S36 | NOT_STARTED |
| UX-SRC-01 | DOC-009 | Единая точка добавления источника | Обязательно | S27, S36 | NOT_STARTED |
| UX-SRC-02 | DOC-009 | Автоматическое определение метаданных | Обязательно | S27, S36 | NOT_STARTED |
| UX-SRC-03 | DOC-009 | Сохранение оригинала | Обязательно | S27, S36 | NOT_STARTED |
| UX-SRC-04 | DOC-009 | Версионирование | Обязательно | S27, S36 | NOT_STARTED |
| UX-SRC-05 | DOC-009 | Надёжная идентификация | Обязательно | S27, S36 | NOT_STARTED |
| UX-SRC-06 | DOC-009 | Базовая автоматическая обработка | Обязательно | S27, S36 | NOT_STARTED |
| UX-SRC-07 | DOC-009 | Статус и ограничения | Обязательно | S27, S36 | NOT_STARTED |
| UX-SRC-08 | DOC-009 | Глубокий контекстный анализ | Обязательно | S27, S36 | NOT_STARTED |
| UX-SRC-09 | DOC-009 | Сравнение версий | Обязательно | S27, S36 | NOT_STARTED |
| UX-SRC-10 | DOC-009 | Типизированный diff Желательно | Для OpenAPI/схем доступны | S27, S36 | NOT_STARTED |
| UX-SRC-11 | DOC-009 | Извлечение новых утверждений | Обязательно | S27, S36 | NOT_STARTED |
| UX-SRC-12 | DOC-009 | Поиск затронутых объектов | Обязательно | S27, S36 | NOT_STARTED |
| UX-SRC-13 | DOC-009 | Объяснимость влияния | Обязательно | S27, S36 | NOT_STARTED |
| UX-SRC-14 | DOC-009 | Классификация impact | Обязательно | S27, S36 | NOT_STARTED |
| UX-SRC-15 | DOC-009 | Гибридная оценка impact | Обязательно | S27, S36 | NOT_STARTED |
| UX-SRC-16 | DOC-009 | Перепланирование Manager | Обязательно | S27, S36 | NOT_STARTED |
| UX-SRC-17 | DOC-009 | Точечная перепроверка | Обязательно | S27, S36 | NOT_STARTED |
| UX-SRC-18 | DOC-009 | QA критических изменений | Обязательно | S27, S36 | NOT_STARTED |
| UX-SRC-19 | DOC-009 | Неизменяемый контекст Worker Run | Обязательно | S27, S36 | NOT_STARTED |
| UX-SRC-20 | DOC-009 | Новая версия контекста | Обязательно | S27, S36 | NOT_STARTED |
| UX-SRC-21 | DOC-009 | Защита утверждённых Обязательно объектов | Источник не переписывает | S27, S36 | NOT_STARTED |
| UX-SRC-22 | DOC-009 | Human-in-the-loop по риску | Обязательно | S27, S36 | NOT_STARTED |
| UX-SRC-23 | DOC-009 | Независимые ветви | Обязательно | S27, S36 | NOT_STARTED |
| UX-SRC-24 | DOC-009 | Групповые уведомления | Обязательно | S27, S36 | NOT_STARTED |
| UX-SRC-25 | DOC-009 | Аудит | Обязательно | S27, S36 | NOT_STARTED |
| UX-SRC-26 | DOC-009 | Контроль доступа | Обязательно | S27, S36 | NOT_STARTED |
| UX-SRC-27 | DOC-009 | Brownfield: факт vs Обязательно намерение | Факт реализации не подменяет | S27, S36 | NOT_STARTED |
| UX-SRC-28 | DOC-009 | Восстановление после ошибок | Обязательно | S27, S36 | NOT_STARTED |
| UX-START-01 | DOC-009 | Минимальное создание проекта | Обязательно | S20, S35 | NOT_STARTED |
| UX-START-02 | DOC-009 | Тип проекта | Обязательно | S20, S35 | NOT_STARTED |
| UX-START-03 | DOC-009 | Необязательная загрузка источников | Обязательно | S20, S35 | NOT_STARTED |
| UX-START-04 | DOC-009 | Адаптивное уточнение контекста | Обязательно | S20, S35 | NOT_STARTED |
| UX-START-05 | DOC-009 | Последовательные вопросы | Обязательно | S20, S35 | NOT_STARTED |
| UX-START-06 | DOC-009 | Разделение фактов и неизвестного | Обязательно | S20, S35 | NOT_STARTED |
| UX-START-07 | DOC-009 | Предложение начального плана | Обязательно | S20, S35 | NOT_STARTED |
| UX-START-08 | DOC-009 | Подтверждение плана | Обязательно | S20, S35 | NOT_STARTED |
| UX-START-09 | DOC-009 | Readiness Gate | Обязательно | S20, S35 | NOT_STARTED |
| UX-START-10 | DOC-009 | Обработка ошибок старта | Обязательно | S20, S35 | NOT_STARTED |
| UX-START-11 | DOC-009 | Возобновление начальной работы | Обязательно | S20, S35 | NOT_STARTED |
| UX-START-12 | DOC-009 | Состояние первых задач | Обязательно | S20, S35 | NOT_STARTED |
| UX-TRC-01 | DOC-009 | Типизированный граф | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-02 | DOC-009 | Типы связей | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-03 | DOC-009 | Статус связи | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-04 | DOC-009 | Provenance связи | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-05 | DOC-009 | Версионная применимость | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-06 | DOC-009 | Различение зависимостей | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-07 | DOC-009 | Проверка типов связей | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-08 | DOC-009 | Обзор трассируемости | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-09 | DOC-009 | Карточка объекта | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-10 | DOC-009 | Путь влияния | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-11 | DOC-009 | Сравнение версий | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-12 | DOC-009 | Триггеры Impact Analysis | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-13 | DOC-009 | Детерминированный анализ | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-14 | DOC-009 | Семантическая оценка | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-15 | DOC-009 | Классификация влияния | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-16 | DOC-009 | Обоснование воздействия | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-17 | DOC-009 | Неполнота графа | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-18 | DOC-009 | Минимальная переработка | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-19 | DOC-009 | Независимые ветви | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-20 | DOC-009 | Контекст Worker Run | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-21 | DOC-009 | QA Impact Plan | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-22 | DOC-009 | Подтверждение связей | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-23 | DOC-009 | Оспаривание вывода | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-24 | DOC-009 | Baseline через CR | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-25 | DOC-009 | Аудит | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-26 | DOC-009 | ACL графового обхода | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-27 | DOC-009 | UX списка влияния | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-28 | DOC-009 | Тестирование качества | MVP | S30, S36 | NOT_STARTED |
| UX-TRC-29 | DOC-009 | Графовая СУБД | После MVP | S30, S36 | DEFERRED (post-MVP) |
| UX-TRC-30 | DOC-009 | GraphRAG | После MVP | S30, S36 | DEFERRED (post-MVP) |
| UX-TRC-31 | DOC-009 | Интерактивный граф | После MVP | S30, S36 | DEFERRED (post-MVP) |
| UX-TRC-32 | DOC-009 | Cross-project traceability | После MVP | S30, S36 | DEFERRED (post-MVP) |
| UX-TRC-33 | DOC-009 | Численные пороги качества | Открыто | S30, S36 | OPEN (не решено) |
| UX-TRC-34 | DOC-009 | Матрица полномочий | Открыто | S30, S36 | OPEN (не решено) |
| UX-TRC-35 | DOC-009 | Политика хранения связей | Открыто | S30, S36 | OPEN (не решено) |
| UX-TRC-36 | DOC-009 | SLA Impact Analysis | Открыто | S30, S36 | OPEN (не решено) |
| WS-MVP-01 | DOC-009 | Project-centric модель | Обязательно | S35 | NOT_STARTED |
| WS-MVP-02 | DOC-009 | Epic как область результата | Обязательно | S35 | NOT_STARTED |
| WS-MVP-03 | DOC-009 | Отдельная сущность Task | Обязательно | S35 | NOT_STARTED |
| WS-MVP-04 | DOC-009 | Отдельная сущность Requirement Обязательно | Требование имеет ID, | S35 | NOT_STARTED |
| WS-MVP-05 | DOC-009 | Many-to-many связи | Обязательно | S35 | NOT_STARTED |
| WS-MVP-06 | DOC-009 | Source Registry | Обязательно | S35 | NOT_STARTED |
| WS-MVP-07 | DOC-009 | Artifact Registry | Обязательно | S35 | NOT_STARTED |
| WS-MVP-08 | DOC-009 | Decisions / Assumptions / Risks | Обязательно | S35 | NOT_STARTED |
| WS-MVP-09 | DOC-009 | Reviews & Approvals | Обязательно | S35 | NOT_STARTED |
| WS-MVP-10 | DOC-009 | Agent Activity | Обязательно | S35 | NOT_STARTED |
| WS-MVP-11 | DOC-009 | Traceability | Обязательно | S35 | NOT_STARTED |
| WS-MVP-12 | DOC-009 | Change Impact | Обязательно | S35 | NOT_STARTED |
| WS-MVP-13 | DOC-009 | Audit History | Обязательно | S35 | NOT_STARTED |
| WS-MVP-14 | DOC-009 | Role-aware access | Обязательно | S35 | NOT_STARTED |
| WS-MVP-15 | DOC-009 | Unified Search | Желательно для Поиск по осно | S35 | NOT_STARTED |
| WS-MVP-16 | DOC-009 | Technical diagnostics view | Желательно для Уполномоченны | S35 | NOT_STARTED |
| WS-MVP-17 | DOC-009 | Portfolio / My Work | Желательно для Пользователь  | S35 | NOT_STARTED |
| WS-MVP-18 | DOC-009 | Extensible artifact types | Обязательно | S35 | NOT_STARTED |
| WS-MVP-19 | DOC-009 | Greenfield/Brownfield/Hybrid support | Обязательно | S35 | NOT_STARTED |
| WS-MVP-20 | DOC-009 | Event notifications | Желательно для Критические | S35 | NOT_STARTED |
| WS-MVP-21 | DOC-009 | UX continuity | После MVP / UX Пользователь  | S35 | DEFERRED (post-MVP) |
| WS-MVP-22 | DOC-009 | Configurable workspace views | После MVP | S35 | DEFERRED (post-MVP) |
