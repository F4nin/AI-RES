# AI RES — Реестр проектной документации

**Версия:** 4.1  
**Дата актуализации:** 2026-11-10  
**Назначение:** единая точка определения актуальных документов, статусов и связей. Реестр описывает фактические файлы, а не просто планируемые артефакты.

## 1. Правила управления документами

1. Для каждого логического документа существует одна актуальная версия, указанная в этом реестре.
2. Предыдущие версии не удаляются: они сохраняются как история, но не используются как нормативная основа реализации.
3. Новая версия создаётся после проверки актуального файла, связанных документов и реестра.
4. Изменение архитектурного решения отражается во всех затронутых документах; реестр обновляется в том же изменении.
5. Статусы: `WORKING` — рабочий; `PROPOSED` — предложение; `DECIDED` — решение подтверждено пользователем; `BASELINED` — утверждённая версия; `SUPERSEDED` — заменён; `REFERENCE` — исходный методический материал.
6. Отсутствие файла в каталоге не компенсируется упоминанием в другом документе: он должен быть создан либо явно отмечен как не требуемый.
7. Файлы `*_for_New_Chat`, временные тесты и ZIP-пакеты не являются источником актуальных требований.

## 2. Текущие документы — актуальные версии

| ID | Область | Актуальный файл | Статус | Примечание |
|---|---|---|---|---|
| DOC-001 | Продукт и архитектура | `AI_RES_Agent_Architecture_Concept_v4.6.md` | BASELINED | Main architecture concept; current normative map in v4.6 addendum |
| DOC-002 | Процесс и алгоритмы | `AI_RES_Process_Design_and_Algorithms_v1.9.md` | BASELINED | Process, lifecycle and transaction algorithms; implementation pending |
| DOC-003 | Жизненный цикл требований | `AI_RES_Requirements_Lifecycle_v2.7.md` | BASELINED | Requirements lifecycle normative model; implementation pending |
| DOC-004 | UX | `AI_RES_UX_Concept_v1.2.md` | BASELINED | Web Project Workspace and Manager interaction modes |
| DOC-005 | Модель данных | `AI_RES_Domain_Model_and_Data_Architecture_v1.9.md` | BASELINED | Domain model and persistence boundaries; runtime validation pending |
| DOC-006 | API и взаимодействия | `AI_RES_API_and_Interaction_Contracts_v1.10.md` | BASELINED | Current API and interaction contract; implementation pending |
| DOC-007 | Worker contracts | `AI_RES_Worker_Contracts_v1.1.schema.json` | WORKING | JSON Schema |
| DOC-008 | Domain events | `AI_RES_Domain_Events_AsyncAPI_v1.6.yaml` | BASELINED | Current AsyncAPI event schema; runtime delivery not verified |
| DOC-009 | MVP scope | `AI_RES_MVP_Capability_Matrix_v3.3.md` | BASELINED | Canonical MVP/post-MVP scope; supersedes v3.2 |
| DOC-010 | Источники и контекст | `AI_RES_Source_and_Context_Lifecycle_v1.3.md` | BASELINED | Source/context and retrieval invariants; connector-specific limits remain WORKING |
| DOC-011 | Инструменты | `AI_RES_Tool_Registry_and_Tool_Management_MVP_v1.0.md` | BASELINED | Tool Gateway, typed contracts, MCP allowlist and per-call authorization |
| DOC-012 | Трассируемость | `AI_RES_Traceability_Dependencies_Impact_Analysis_v1.0.md` | WORKING | Traceability/impact |
| DOC-013 | Артефакты | `AI_RES_Documentation_Artifacts_Lifecycle_v1.0.md` | WORKING | Artifact lifecycle |
| DOC-014 | Внешние интеграции | `AI_RES_External_Integrations_and_Project_Context_v1.2.md` | BASELINED | MVP connector scope; provider-specific contracts remain WORKING |
| DOC-015 | Инфраструктура | `AI_RES_Infrastructure_Deployment_Operations_v1.7.md` | WORKING | Docker Compose, Temporal, PostgreSQL migration jobs, secrets and DB role isolation |
| DOC-016 | Security architecture | `AI_RES_Security_Architecture_v1.2.md` | BASELINED | Security architecture design baseline; runtime security acceptance pending |
| DOC-017 | Threat model | `AI_RES_Threat_Model_v1.1.md` | BASELINED | Threat treatment baseline; deployment-specific reassessment required |
| DOC-018 | Identity/access | `AI_RES_Identity_Access_Control_v1.5.md` | BASELINED | IAM/ACL/Policy Engine and DB access baseline; runtime acceptance pending |
| DOC-019 | Secrets/keys | `AI_RES_Secrets_and_Key_Management_v1.1.md` | BASELINED | SOPS/age + Compose secrets baseline; runtime rotation tests pending |
| DOC-020 | Security requirements | `AI_RES_Security_Controls_and_Requirements_v1.2.md` | BASELINED | SEC controls baseline; P0 tests are release blockers |
| DOC-021 | Методология | `AI_RES_Methodology_and_Source_Traceability_Matrix_v1.2.md` | BASELINED | Methodology traceability to chapters 2–10 and current design decisions |
| DOC-022 | Реестр документов | `AI_RES_Document_Registry_v4.1.md` | BASELINED | Canonical current registry v4.1 |
| DOC-023 | Аутентификация и сессии | `AI_RES_Authentication_and_Session_Management_v1.1.md` | BASELINED | Local Auth MVP, server-side sessions, CSRF and privileged MFA |
| DOC-024 | Архитектура наблюдаемости | `AI_RES_Observability_Architecture_v1.2.md` | BASELINED | Observability design; SLO/retention/sizing remain deployment gates |
| DOC-025 | Требования к мониторингу и alerting | `AI_RES_Monitoring_and_Alerting_Requirements_v1.0.md` | WORKING | OBS-MON/SEC/ALR requirements |
| DOC-026 | Наблюдаемость и оценка агентов | `AI_RES_Agent_Observability_and_Evaluation_v1.2.md` | BASELINED | Agent telemetry/evaluation design; thresholds require calibration |
| DOC-027 | Эксплуатационные runbooks | `AI_RES_Operational_Runbooks_v1.0.md` | WORKING | Проектные процедуры, требуют runtime drills |
| DOC-028 | Проверка этапа 14 | `AI_RES_Stage_14_Verification_v1.0.md` | WORKING | Статическая проверка пакета; runtime не проверен |
| DOC-029 | План пользовательской документации, глоссария и непрерывного улучшения | `AI_RES_Post_Implementation_Productization_Plan_v1.3.md` | WORKING | User documentation deliverables explicitly post-UI acceptance |
| DOC-030 | Архитектура производительности, масштабирования и отказоустойчивости | `AI_RES_Performance_Scalability_Resilience_Architecture_v1.0.md` | WORKING | Этап 15 |
| DOC-031 | Требования к производительности и масштабированию | `AI_RES_Performance_Scalability_Resilience_Requirements_v1.0.md` | WORKING | PERF-001..026 |
| DOC-032 | Требования к отказоустойчивости и восстановлению | `AI_RES_Resilience_and_Recovery_Requirements_v1.0.md` | WORKING | REL-001..028 |
| DOC-033 | План capacity assessment и нагрузочного тестирования | `AI_RES_Capacity_and_Load_Test_Plan_v1.0.md` | WORKING | Тесты после реализации |
| DOC-034 | Проверка этапа 15 | `AI_RES_Stage_15_Verification_v1.0.md` | WORKING | Статическая проверка; нагрузочные тесты не выполнялись |
| DOC-035 | Канонический глоссарий AI RES | `AI_RES_Glossary_v1.1.md` | BASELINED | 59 canonical terms; controlled changes through review and impact analysis |
| DOC-036 | Машинно-читаемый глоссарий | `AI_RES_Glossary_v1.1.json` | BASELINED | Machine-readable glossary, 59 APPROVED terms |
| DOC-037 | JSON Schema записи глоссария | `AI_RES_Glossary_Entry_Schema_v1.1.json` | WORKING | Валидация отдельной Glossary Entry |
| DOC-038 | Архитектура непрерывного улучшения и автономности | `AI_RES_Continuous_Improvement_and_Autonomy_Architecture_v1.3.md` | BASELINED | MVP governance A0-A2; A3/A4 and post-MVP governance remain WORKING |
| DOC-039 | Требования к непрерывному улучшению и автономности | `AI_RES_Continuous_Improvement_Requirements_v1.3.md` | BASELINED | CI-001..CI-045 normative; runtime delivered by staged capability scope |
| DOC-040 | Проверка проектной части блока 16 | `AI_RES_Block_16_Design_Verification_v1.1.md` | WORKING | Статические проверки; runtime не реализован |
| DOC-041 | Спецификация реализации для Claude Code | `AI_RES_Claude_Code_Implementation_Spec_v1.22.md` | BASELINED | Implementation instructions; repository/runtime evidence required |
| DOC-042 | Предварительный аудит готовности к реализации | `AI_RES_Pre_Implementation_Readiness_Audit_v2.2.md` | BASELINED | Static readiness audit; production gates remain |
| DOC-043 | Контракты непрерывного улучшения и автономности | `AI_RES_Continuous_Improvement_Contracts_v1.1.md` | BASELINED | CI contracts baseline for post-MVP governed runtime |
| DOC-044 | JSON Schema контрактов CI и autonomy | `AI_RES_Continuous_Improvement_Contracts_Schema_v1.0.json` | WORKING | Proposal, Evaluation Manifest, Autonomy Grant, Governance Decision |
| DOC-045 | JSON Schema документа глоссария | `AI_RES_Glossary_Document_Schema_v1.0.json` | WORKING | Валидация envelope и массива терминов |
| DOC-046 | Информационная архитектура пользовательской документации | `AI_RES_User_Documentation_Information_Architecture_v1.1.md` | WORKING | Guides are future deliverables after UI acceptance |
| DOC-050 | Public OpenAPI contract | `AI_RES_Public_API_v1.3.yaml` | WORKING | Initial normative vertical slice; cookie session + CSRF; not the full endpoint catalogue |
| DOC-051 | Решения, допущения, риски и неопределённость | `AI_RES_Decisions_Assumptions_Risks_Uncertainty_v1.2.md` | BASELINED | Typed uncertainty/governance model; quantitative calibration remains WORKING |
| DOC-054 | Сквозной аудит согласованности | `AI_RES_Cross_Document_Consistency_Audit_v2.2.md` | BASELINED | Current reconciliation audit v2.2 |
| DOC-055 | Архитектурное решение Operation и Readiness Gate | `AI_RES_Operation_and_Readiness_Gate_Architecture_Decision_v1.6.md` | BASELINED | Operation/WorkerRun, Event Model, PostgreSQL persistence and access design decisions |
| DOC-056 | JSON Schema Operation и ReadinessEvaluation | `AI_RES_Operation_and_Readiness_Gate_Schema_v1.0.json` | WORKING | Машинные контракты доменных записей |
| DOC-057 | State machines Operation, WorkerRun и Gate | `AI_RES_Operation_and_Readiness_Gate_State_Machine_v1.2.json` | WORKING | Полные статусы, переходы, derivation и aggregation rules |
| DOC-060 | Проверка Operation и WorkerRun Lifecycle | `AI_RES_Operation_WorkerRun_Lifecycle_Verification_v1.0.md` | WORKING | Статические проверки; runtime не реализован и не проверен |
| DOC-061 | Operation/WorkerRun Event Model | `AI_RES_Operation_WorkerRun_Event_Model_v1.4.md` | BASELINED | Current event model and source map; runtime delivery not verified |
| DOC-062 | Проверка Event Model | `AI_RES_Operation_WorkerRun_Event_Model_Verification_v1.0.md` | WORKING | Статическая проверка контрактов; runtime не проверен |
| DOC-063 | Пакет Operation/WorkerRun Event Model | `AI_RES_Operation_WorkerRun_Event_Model_Package_v1.0.zip` | WORKING | Архив документации и контрактов; не самостоятельный источник требований |
| DOC-064 | Физическая модель PostgreSQL и транзакционные алгоритмы | `AI_RES_PostgreSQL_Physical_Model_and_Transactions_v1.2.md` | BASELINED | Physical execution persistence slice, TX-01..TX-09, migration/access references |
| DOC-065 | PostgreSQL design DDL | `AI_RES_PostgreSQL_Physical_Model_v1.0.sql` | WORKING | Design DDL snapshot; convert to Alembic revisions before deployment |
| DOC-066 | Проверка физической модели PostgreSQL | `AI_RES_PostgreSQL_Physical_Model_Verification_v1.0.md` | WORKING | Статическая проверка; PostgreSQL runtime не запускался |
| DOC-067 | Пакет PostgreSQL Physical Model | `AI_RES_PostgreSQL_Physical_Model_Package_v1.0.zip` | WORKING | Архив design docs/DDL/verification; не самостоятельный источник требований |
| DOC-068 | Стратегия миграций и модель доступа PostgreSQL | `AI_RES_PostgreSQL_Migration_and_Access_Strategy_v1.1.md` | BASELINED | Alembic, expand/backfill/validate/contract, role separation, RLS and runbook |
| DOC-069 | PostgreSQL Roles/RLS SQL reference | `AI_RES_PostgreSQL_Roles_RLS_v1.0.sql` | WORKING | Шаблон ролей/GRANT/RLS; требует адаптации и runtime security tests |
| DOC-070 | Проверка PostgreSQL migration/access design | `AI_RES_PostgreSQL_Migration_Access_Verification_v1.0.md` | WORKING | Статическая проверка; PostgreSQL runtime не запускался |
| DOC-071 | Пакет PostgreSQL Migration & Access | `AI_RES_PostgreSQL_Migration_Access_Package_v1.0.zip` | WORKING | Архив нормативного design, SQL reference и verification |
| DOC-072 | Persistence Implementation Blueprint | `AI_RES_Persistence_Implementation_Blueprint_v1.0.md` | BASELINED | Alembic/SQLAlchemy, repository layout, migrations, backfill, Unit of Work, RLS, CI acceptance and DoD |
| DOC-073 | Проверка Persistence Implementation Blueprint | `AI_RES_Persistence_Implementation_Blueprint_Verification_v1.0.md` | WORKING | Static/package verification; live PostgreSQL not tested |
| DOC-074 | Пакет Persistence Implementation Blueprint | `AI_RES_Persistence_Implementation_Blueprint_Package_v1.0.zip` | WORKING | Blueprint, scaffold, operational SQL and updated normative documents |
| DOC-075 | Завершение архитектурных блоков и baseline решений | `AI_RES_Architecture_Completion_and_Baseline_Decisions_v1.0.md` | BASELINED | Каноническая карта закрытых решений и границ MVP/post-MVP |
| DOC-076 | LLM Gateway и Model Registry | `AI_RES_Model_Gateway_and_Model_Registry_v1.0.md` | BASELINED | LLMGatewayPort, Bifrost preferred behind adapter, model routing and PoC gate |
| DOC-077 | Knowledge, Memory и Retrieval Architecture | `AI_RES_Knowledge_Memory_Retrieval_Architecture_v1.0.md` | BASELINED | PostgreSQL FTS + pgvector, MinIO, immutable context, ACL-aware retrieval |
| DOC-078 | Evaluation Framework и Release Gates | `AI_RES_Evaluation_and_Release_Gates_v1.0.md` | BASELINED | Task-class evaluation sets, deterministic/security gates and release manifest |
| DOC-079 | Learning & Experience Lifecycle | `AI_RES_Learning_Experience_Lifecycle_v1.0.md` | BASELINED | Non-parametric MVP, governed improvement, A0-A2 only |
| DOC-082 | Baseline manifest | `AI_RES_Architecture_Baseline_Manifest_v1.2.json` | BASELINED | SHA-256 manifest for Registry v4.1 canonical files |
| DOC-083 | Проверка завершения архитектурных блоков | `AI_RES_Architecture_Completion_Verification_v1.2.md` | WORKING | Static verification report; no runtime certification |

## 3. Исходные методические материалы

| Источник | Файл | Статус |
|---|---|---|
| Глава 2 | `Глава 2. Проектирование агентских систем.md` | REFERENCE |
| Глава 3 | `Глава 3. UX-дизайн для агентных систем.md` | REFERENCE |
| Глава 4 | `Глава 4. Инструменты.md` | REFERENCE |
| Глава 5 | `Глава 5. Оркестрация ИИ-агентов.md` | REFERENCE |
| Глава 6 | `Глава 6. Знания и память ИИ-агентов.md` | REFERENCE |
| Глава 7 | `Глава 7. Обучение в агентных системах.md` | REFERENCE |
| Глава 8 | `Глава 8. От одного агента ко многим.md` | REFERENCE |
| Глава 9 | `Глава 9. Проверки и измерения ИИ-агентов.md` | REFERENCE |
| Глава 10 | `Глава 10. Мониторинг на стадии эксплуатации ИИ-агентов.md` | REFERENCE |

## 4. Документы, которые не следует использовать как актуальные

- Все версии архитектурной концепции до v4.0.
- Все версии Requirements Lifecycle до v2.5.
- Все версии MVP Capability Matrix до v2.7 после обновления.
- Все версии Infrastructure Deployment Operations до v1.2 после обновления.
- `AI_RES_Agent_Architecture_Concept_for_New_Chat.md` — контекстный экспорт, не нормативный документ.
- ZIP-пакеты — транспортные снимки; актуальность определяется версиями файлов внутри и этим реестром.

## 5. Контроль целостности

Перед передачей документации в реализацию необходимо:
- проверить наличие каждого canonical file path из раздела 2;
- проверить уникальность DOC ID и canonical file path (ровно одна запись на логический документ);
- проверить, что ссылки между документами ведут на актуальные версии;
- сверить требования с MVP Capability Matrix;
- проверить отсутствие противоречий между Architecture, Infrastructure, Security, Tool Registry, Domain Model и API Contracts;
- проверить схемы/спецификации техническими валидаторами;
- зафиксировать утверждённый baseline комплекта документов.

## 6. История

- v1.0 — создан реестр актуальных документов, исходных глав и правил управления версиями.

- v1.1 — добавлена спецификация аутентификации и сессий; актуализированы архитектура, IAM, инфраструктура, security controls и MVP matrix.


- v1.2 — этап 14: добавлены observability architecture, monitoring/alerting requirements, agent observability/evaluation и operational runbooks; актуализированы Infrastructure v1.4, MVP Capability Matrix v2.9 и Methodology Matrix v1.1. Архитектурные решения спроектированы; runtime implementation/drills не заявляются как выполненные.

- v1.2 — в реестр добавлен отчёт статической проверки этапа 14 (DOC-028).

- v1.3 — зарегистрирован завершающий блок Product Documentation, Glossary & Continuous Improvement; предусмотрены пользовательские руководства, единый управляемый глоссарий и capability-based autonomy maturity.

- v1.4 — этап 15: добавлены архитектура производительности/масштабирования/отказоустойчивости, требования PERF/REL и план нагрузочного тестирования; актуализированы Architecture Concept v4.2, Infrastructure v1.5 и MVP Capability Matrix v3.0.

- v1.5 — добавлен отчёт статической проверки этапа 15 (DOC-034).

- v1.6 — начато выполнение проектной части блока 16: создан начальный глоссарий и JSON Schema, спроектированы Continuous Improvement и capability-scoped autonomy; обновлены Architecture Concept v4.3, MVP Matrix v3.1 и Productization Plan v1.1.

- v1.7 — добавлен отчёт проверки проектной части блока 16 (DOC-040).

- v1.8 — обновлена спецификация реализации для Claude Code до v1.3 с актуальным baseline этапов 13–16; добавлен предварительный аудит готовности к реализации.
- v1.9 — блок 16 детализирован: глоссарий v1.0 (59 терминов) обогащён примерами и связями; добавлены document/entry schemas, CI domain contracts и JSON Schema, user documentation information architecture; обновлены Architecture Concept v4.4, MVP Matrix v3.2, Productization Plan v1.2 и Claude Code Implementation Spec v1.4. Реализация runtime и пользовательские руководства по фактическому UI не заявляются.


- v2.0 — сквозная проверка: добавлены OpenAPI public contract и Decision/Assumption/Risk document в реестр; API Contracts v1.3 и Implementation Spec v1.5; исправлены ссылки на актуальные версии в authoritative implementation brief; зафиксированы блокирующие вопросы Operation/ReadinessGate persistence, state machine completeness и CI reconciliation.

- v2.1 — исправлена ссылка в CI Contracts на OpenAPI Public API v1.1; CI contracts остаются PROPOSED до закрытия PRE-010.

- v2.2 — актуализированы CI Contracts v1.1, Implementation Spec v1.6 и Cross-Document Audit v1.1.

- v2.3 — Implementation Spec v1.7 указывает на Registry v2.2; для исключения циклической ссылки реестр v2.3 фиксирует актуальный spec v1.7 и является текущим реестром. Spec v1.7 указывает реестр v2.2 как snapshot для baseline; при запуске реализации сначала сверить этот файл с текущим Registry v2.3.

- v2.4 — обновлён Implementation Spec до v1.8; он определяет динамический выбор самого нового реестра по SemVer, устраняя жёсткую циклическую ссылку.

- v2.5 — включён финальный отчёт аудита v1.2; implementation brief v1.8 и контрактные исправления зафиксированы как текущие документы.

- v2.6 — Process Design v1.2 синхронизирован с API Operation lifecycle; обновлены Implementation Spec v1.9 и Audit v1.3; уточнена граница семантической проверки.

- v2.7 — Implementation Spec v1.10 фиксирует актуальный process design v1.2; Audit v1.3 уточняет границы содержательной проверки.

- v2.8 — актуализированы Implementation Spec v1.11 и Audit v1.4; указано, что cookie/header wire names в OpenAPI являются проектными предложениями до security owner approval.

- v2.9 — исправлены заголовочные ссылки Implementation Spec v1.12; устранена дублирующая запись implementation spec в реестре; обновлён Audit v1.5.


- v3.0 — предложено каноническое persistence-решение для Operation и Readiness Gate; добавлены доменные схемы и state machine; синхронизированы Domain Model v1.3, Process Design v1.3, API Contracts v1.4, Public OpenAPI v1.2, AsyncAPI v1.3 и Implementation Spec v1.13. Решение остаётся PROPOSED до архитектурного подтверждения; runtime не реализован и не тестировался.

- v3.1 — зарегистрированы OpenAPI v1.2 и AsyncAPI v1.3; расширены machine-readable contracts для Operation и ReadinessEvaluation.

- v3.2 — добавлен отчёт статической проверки Operation/Readiness Gate; архив пакета проверен на целостность. Архитектурное решение остаётся PROPOSED.


- v3.3 — пользователь подтвердил архитектурное решение Operation и Readiness Gate 2026-11-10. DOC-055 обновлён до v1.1 и BASELINED; Implementation Spec обновлена до v1.14; verification report — v1.1. PRE-009/PRE-011 закрыты на уровне архитектурного выбора, но детализация физической реализации и runtime verification остаются открытыми.


- v3.4 — пользователь принял рекомендацию одной Operation на команду, fan-out через Tasks/WorkerRuns и дочерние Operation только для самостоятельных подкоманд; делегировал выбор деталей. Зафиксированы критерии Operation aggregation, полный WorkerRun lifecycle, Gate/WorkerRun separation, derived-run lineage, cancellation/reconciliation, event catalogue и обязательные тесты. Обновлены Architecture Decision v1.2, Domain Model v1.4, Process Design v1.4, API Contracts v1.5, State Machine JSON v1.1, OpenAPI v1.3, AsyncAPI v1.4, Implementation Spec v1.15. Runtime не реализован/не тестировался.


## Дополнение v3.5 — Operation/WorkerRun Event Model (2026-11-10)

- DOC-002 → `AI_RES_Process_Design_and_Algorithms_v1.8.md` — transactional event production, Outbox/Inbox, delivery/recovery.
- DOC-005 → `AI_RES_Domain_Model_and_Data_Architecture_v1.8.md` — append-only event history, sequence and Outbox/Inbox persistence.
- DOC-006 → `AI_RES_API_and_Interaction_Contracts_v1.9.md` — event identity, idempotency, ordering, safe event history API.
- DOC-008 → `AI_RES_Domain_Events_AsyncAPI_v1.5.yaml` — canonical CloudEvents catalog, at-least-once and per-aggregate ordering.
- DOC-041 → `AI_RES_Claude_Code_Implementation_Spec_v1.19.md` — mandatory implementation constraints and tests.
- DOC-055 → `AI_RES_Operation_and_Readiness_Gate_Architecture_Decision_v1.6.md` — BASELINED event model decision.
- DOC-057 → `AI_RES_Operation_and_Readiness_Gate_State_Machine_v1.2.json` — machine-readable event catalog and delivery guarantees.
- New DOC-061 → `AI_RES_Operation_WorkerRun_Event_Model_v1.3.md` — normative event model and operational semantics.
- New DOC-062 → `AI_RES_Operation_WorkerRun_Event_Model_Verification_v1.0.md` — static verification report.
- New DOC-063 → `AI_RES_Operation_WorkerRun_Event_Model_Package_v1.0.zip` — package archive.

The user delegated detailed choices; recommended event architecture is documented as BASELINED design. Runtime implementation, PostgreSQL concurrency, dispatcher/consumer crash tests and Temporal integration are not claimed.


- v3.6 — Event Model дополнена физическим storage/delivery mapping (v1.1); создана и зафиксирована физическая модель PostgreSQL для execution persistence slice, DDL design migration, TX-01..TX-09 и verification report. Обновлены Architecture Decision v1.4, Domain Model v1.6, Process Design v1.6, Implementation Spec v1.17. PostgreSQL runtime/concurrency/Temporal tests не выполнялись.

- Дополнение v3.6 — API Contracts v1.7 уточняет idempotency/persistence semantics; wire schema OpenAPI не менялась.


## Дополнение v3.7 — PostgreSQL migration strategy и access model (2026-11-10)

- DOC-002 → `AI_RES_Process_Design_and_Algorithms_v1.8.md`: migration deployment gates, resumable backfill, lock/timeout and expand-contract behavior.
- DOC-005 → `AI_RES_Domain_Model_and_Data_Architecture_v1.8.md`: DB ownership, RLS and tenant-context requirements.
- DOC-006 → `AI_RES_API_and_Interaction_Contracts_v1.9.md`: API/Application Service DB boundary; no direct Runtime SQL.
- DOC-015 → `AI_RES_Infrastructure_Deployment_Operations_v1.7.md`: Alembic deployment job, DB network/TLS/secret rotation.
- DOC-018 → `AI_RES_Identity_Access_Control_v1.3.md`: PostgreSQL roles distinct from business roles; RLS defense-in-depth.
- DOC-041 → `AI_RES_Claude_Code_Implementation_Spec_v1.19.md`: mandatory migration and access implementation/acceptance requirements.
- DOC-055 → `AI_RES_Operation_and_Readiness_Gate_Architecture_Decision_v1.6.md`: approved PostgreSQL migration/access design.
- DOC-061 → `AI_RES_Operation_WorkerRun_Event_Model_v1.3.md`: DB role ownership and migration lifecycle references.
- DOC-064 → `AI_RES_PostgreSQL_Physical_Model_and_Transactions_v1.2.md`: migration/access strategy cross-reference.
- New DOC-068: Alembic + SQLAlchemy 2.x; expand/backfill/validate/contract; least-privilege roles; RLS + FORCE; transaction-local tenant context; explicit caveat that RLS does not replace Policy Engine.
- New DOC-069: SQL reference template for roles, grants and RLS policies.
- New DOC-070: static verification report.
- New DOC-071: design package archive.

Design decisions are BASELINED; actual Alembic environment, DB roles, RLS policies and runtime tests are NOT implemented/verified in a live PostgreSQL instance.


## Дополнение v3.8 — Persistence Implementation Blueprint (2026-11-10)

- DOC-002 → `AI_RES_Process_Design_and_Algorithms_v1.8.md`: migration deployment and persistence transaction workflow.
- DOC-005 → `AI_RES_Domain_Model_and_Data_Architecture_v1.8.md`: Unit of Work, DB ownership, backfill and transaction boundaries.
- DOC-006 → `AI_RES_API_and_Interaction_Contracts_v1.9.md`: Application Service persistence boundary; no Runtime direct SQL.
- DOC-015 → `AI_RES_Infrastructure_Deployment_Operations_v1.7.md`: one-shot migration job, preflight/postflight and release gates.
- DOC-018 → `AI_RES_Identity_Access_Control_v1.3.md`: technical DB identities and RLS enforcement.
- DOC-041 → `AI_RES_Claude_Code_Implementation_Spec_v1.19.md`: mandatory implementation sequence and Definition of Done.
- DOC-055 → `AI_RES_Operation_and_Readiness_Gate_Architecture_Decision_v1.6.md`: persistence blueprint reference.
- DOC-061 → `AI_RES_Operation_WorkerRun_Event_Model_v1.3.md`: event storage and transactional persistence.
- DOC-064 → `AI_RES_PostgreSQL_Physical_Model_and_Transactions_v1.2.md`: physical schema and transaction blueprint.
- DOC-068 → `AI_RES_PostgreSQL_Migration_and_Access_Strategy_v1.1.md`: migration and access implementation gates.
- New DOC-072 → `AI_RES_Persistence_Implementation_Blueprint_v1.0.md` — normative implementation blueprint.
- New DOC-073 → `AI_RES_Persistence_Implementation_Blueprint_Verification_v1.0.md` — static package verification.
- New DOC-074 → `AI_RES_Persistence_Implementation_Blueprint_Package_v1.0.zip` — implementation assets package.

The Persistence Implementation Blueprint is BASELINED as the implementation contract. Alembic revisions, repositories, RLS deployment, backfill and PostgreSQL runtime acceptance are NOT implemented or verified against a live repository/database by this documentation task.

- v3.9 — завершены оставшиеся архитектурные блоки по делегированию владельца проекта: создан Architecture Completion Baseline, Model Gateway/Registry, Knowledge/Memory/Retrieval, Evaluation/Release Gates и Learning Lifecycle; обновлены security/IAM/secrets/auth, tools, integrations, source/context, requirements, UX, MVP matrix, architecture concept и Implementation Spec v1.20; добавлен Cross-Document Audit v2.0. Все design decisions baseline, runtime evidence не заявляется.

- v3.9.1 — исправлены заголовочные версии и статусы новых addenda; создан канонический Glossary v1.1; актуализированы Methodology Matrix v1.2, UX IA v1.1 и Productization Plan v1.3; исправлена статистика missing references; добавлен baseline manifest DOC-082.

- v3.9.2 — добавлен отчёт статической проверки Architecture Completion; исправлен self-hash manifest (manifest не хеширует сам себя), реестр содержит 83 записи и 75 уникальных файлов.


## Дополнение v4.0 — reconciliation после Architecture Completion (2026-11-10)

- Реестр нормализован до одной canonical записи на логический документ: 74 canonical records / 74 unique paths; duplicate DOC IDs = 0; duplicate paths = 0; missing registered files = 0.
- DOC-009 переведён на MVP Capability Matrix v3.3; дублирующая DOC-049 удалена.
- Удалены дублирующие alias-записи на те же файлы: DOC-047, DOC-048, DOC-052, DOC-058, DOC-059, DOC-080, DOC-081. Канонические записи сохранены в DOC-001, DOC-006, DOC-008, DOC-029, DOC-042, DOC-050 и DOC-054.
- Актуализированы DOC-001, DOC-002, DOC-005, DOC-006, DOC-008, DOC-018, DOC-022, DOC-041, DOC-042, DOC-054, DOC-061, DOC-082 и DOC-083.
- Новые версии: Architecture Concept v4.6; Domain Model v1.9; Process Design v1.9; API Contracts v1.10; IAM v1.5; Event Model v1.4; AsyncAPI v1.6; Implementation Spec v1.21; Readiness Audit v2.1; Cross-Document Audit v2.1; Verification v1.1; Baseline Manifest v1.1.
- Исторические версии не удалены. Исторические ссылки остаются допустимыми в контексте описания прежних решений; нормативный выбор всегда выполняется по Registry v4.0 и current-source maps.
- Никакая программная реализация, runtime test, security certification или production readiness не заявляется.


---

## 6. Status reconciliation v4.1

В v4.1 устранены расхождения между статусами в заголовках восьми документов и статусами реестра. Статус `BASELINED` означает утверждённую нормативную модель/границу scope, а не наличие runtime implementation. Частичные baseline явно ограничивают post-MVP и deployment-specific параметры.

- DOC-003 Requirements Lifecycle: BASELINED; реализация и UI acceptance pending.
- DOC-010 Source & Context: BASELINED; connector-specific limits, formats, SLO and thresholds remain WORKING.
- DOC-014 External Integrations: BASELINED; MVP read-only connector scope; provider-specific passports remain WORKING.
- DOC-024 Observability: BASELINED design; numerical SLO, retention, sizing and alert destinations are deployment gates.
- DOC-026 Agent Observability/Evaluation: BASELINED design; thresholds and sample sizes require empirical calibration.
- DOC-038 Continuous Improvement Architecture: BASELINED MVP A0-A2; A3/A4 and post-MVP governance remain WORKING.
- DOC-039 Continuous Improvement Requirements: BASELINED normative requirements; capabilities are delivered by staged scope, not all in MVP.
- DOC-051 Decisions/Assumptions/Risks: BASELINED typed domain model; quantitative risk calibration and organization-specific authority matrix remain WORKING.

No document is marked runtime-verified by this status reconciliation.


## 7. Контроль статусов

`BASELINED` относится к утверждённому нормативному дизайну/требованиям, а не к факту программной реализации. Частичные baseline обязаны перечислять WORKING-параметры и post-MVP ограничения. Runtime, security, performance и production acceptance фиксируются отдельными verification artifacts и release gates.
