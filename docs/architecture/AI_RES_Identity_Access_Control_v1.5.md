# AI RES — Идентификация и модель управления доступом

**Версия:** 1.5  
**Статус:** BASELINED design contract для MVP; точные deployment bindings, secret provisioning и runtime enforcement проверяются на этапе реализации.

## 1. Цель

Определить, кто может войти в AI RES, от чьего имени действуют сервисы и агенты, какие объекты и операции доступны и как полномочия ограничиваются на протяжении Worker Run.

## 2. Слои контроля

1. Authentication — подтверждение личности пользователя/сервиса.
2. Identity propagation — передача проверенного субъекта и контекста без передачи секретов в LLM.
3. RBAC — базовые роли и административные полномочия.
4. ABAC/ACL — ограничения по ресурсу, проекту, Epic, задаче, классификации, состоянию и контексту.
5. Policy & Permission Engine — окончательное решение allow/deny/approval-required.
6. Enforcement point — API, retrieval service, Tool/Connector Gateway, Artifact Service и export service.
7. Audit — запись субъекта, решения и результата.

Аутентификация не означает авторизацию. UI скрытие элемента не заменяет серверную проверку.

## 3. Типы субъектов

| Субъект | Примеры | Принцип |
|---|---|---|
| Human user | Analyst, Reviewer, Admin | Личная учётная запись; права назначаются в организации/проекте |
| Service | API, Manager Runtime, Worker Runtime, Connector, LLM Adapter | Отдельная машинная identity; не использовать общий универсальный credential |
| Agent role | Manager, Requirements Worker, QA Worker | Компетенция, не самостоятельная identity и не grant |
| Worker Run | конкретный запуск Worker | Временный scope и ограниченные grants; expiry/revoke |
| External principal | Git provider, LLM provider, MCP service | Только через адаптеры и разрешённые операции |

## 4. Предварительная ролевая модель (RBAC)

| Роль | Организационный уровень | Проектный уровень | Типичные полномочия |
|---|---|---|---|
| Organization Owner | Да | Наследуемые в пределах политики | Управление организацией, админами, правилами верхнего уровня |
| Organization Admin | Да | По назначению | Пользователи, интеграции, настройки и аудит организации |
| Project Admin | Нет | Да | Участники, проектные настройки, источники и разрешённые правила |
| Analyst | Нет | Да | Работа с Epic, требованиями, задачами, источниками и артефактами в пределах scope |
| Reviewer/Approver | Нет | Да | Просмотр и решения только по назначенным review/approval объектам |
| Read-only Viewer | Нет | Да | Чтение разрешённых объектов |
| Auditor | По назначению | По назначению | Чтение audit/security evidence без изменения бизнес-объектов |

Это стартовый словарь ролей, а не окончательная матрица. Запрещено предполагать, что Analyst автоматически может утверждать собственные результаты или Baseline.

## 5. ABAC атрибуты

**Subject:** user_id/service_id, organization_id, memberships, role, authentication_strength, status.  
**Resource:** resource_type/id, organization_id, project_id, epic_id, owner, classification, lifecycle_status, version, ACL.  
**Action:** read/list/search/retrieve/create/update/delete/approve/publish/export/execute/communicate/administer.  
**Context:** task_id, worker_run_id, purpose, environment, time, source, policy_version, risk, approval reference.  
**Obligations:** redaction, watermark, read-only, rate limit, expiry, approval, audit level.

## 6. Worker Run grants

Каждый Run получает неизменяемый набор grants, привязанный к:
- конкретной service identity и Worker Definition;
- project/Epic/Task/Run;
- допустимым ресурсам и операциям;
- разрешённым инструментам и model profiles;
- классификации данных и egress policy;
- бюджету/лимиту и сроку действия.

Grant создаётся trusted platform service после решения Manager и независимой проверки Policy Engine. Grant не наследуется новым Run, консультацией, handoff или delegated subtask; для нового Run выполняется новая проверка и выдача нового grant. Отзыв и expiry должны немедленно блокировать последующие операции.

## 7. Авторизация операций

Обязательные проверки:
- объектная авторизация на каждый API endpoint (защита от BOLA/IDOR);
- ACL до поиска, retrieval, graph traversal, summarization, export и caching;
- проверка доступа к точной версии Source/Artifact/Context Package;
- повторная проверка Tool/Connector permission непосредственно перед side effect;
- backend authorization для Temporal Signal/Update и admin actions;
- запрет обхода Policy Engine прямым доступом к DB, MinIO или provider API.

## 8. Approval и separation of duties

Human approval — отдельная доменная операция с идентификатором approver, полномочием, объектом/версией, решением, временем и комментарием. Approval должен быть связан с exact version/hash. Смена объекта после approval аннулирует применимость решения.

Критические действия требуют разделения инициатора и утверждающего, если это возможно в составе организации. Самоутверждение запрещается для явно настроенных классов действий.

## 9. Authentication и сессии

Для MVP требуется безопасный механизм локальной аутентификации; поддержка внешнего OIDC/SAML IdP и MFA должна быть архитектурно предусмотрена. Конкретный IdP, MFA enforcement, session lifetime, refresh/revocation, password policy и break-glass account остаются открытыми до определения deployment-потребностей. Администраторские интерфейсы требуют усиленной аутентификации в рабочем профиле.

## 10. Тесты доступа

- Analyst проекта A не читает проект B через API, search, RAG, graph, cache, export или artifact URL.
- Worker Run не может прочитать объект вне своих grants даже если его service identity технически имеет доступ к сервису.
- Expired/revoked grant блокирует следующий tool call.
- Нельзя подделать project_id/worker_run_id в запросе для повышения прав.
- Temporal Signal/Update без backend authorization отклоняется.
- Reviewer не может менять reviewed artifact; approver не может утверждать версию, отличную от просмотренной.
- Denied request не раскрывает чувствительные метаданные объекта.


---

## Дополнение v1.1 — принятое решение по аутентификации и сессиям

Раздел 9 версии 1.0 уточняется и заменяется спецификацией `AI_RES_Authentication_and_Session_Management_v1.0.md`.

**Решение для MVP:** локальные учётные записи AI RES без обязательного внешнего IdP; архитектурный порт `IdentityProvider` позволяет позднее подключить OIDC. Первый внешний протокол — OIDC Authorization Code + PKCE. SAML напрямую не входит в MVP и может быть обеспечен корпоративным OIDC broker.

Нормативные правила:
- Local Authentication Provider является единственным включённым provider в MVP.
- OIDC Provider Adapter — предусмотренная расширяемость, но не обязательная MVP-функция.
- MFA обязательна для привилегированных ролей в production-like deployment; TOTP — первый поддерживаемый механизм.
- Browser sessions — opaque server-side sessions в HttpOnly/Secure/SameSite cookies; CSRF защита обязательна.
- Password hashing — Argon2id; bootstrap без default credentials.
- OIDC identity mapping — `(issuer, subject)`, не email.
- Внешние claims не назначают AI RES project roles автоматически.
- Human sessions, service identities и Worker Run grants — три разные сущности и не взаимозаменяемы.

Все значения и сценарии детализированы в документе Authentication and Session Management v1.0. Старое указание о невыбранных IdP/MFA/session design считается superseded.


---

## Дополнение 1.2 — PostgreSQL defense-in-depth

**Нормативное решение:** для `ai_res_db` применяется Alembic + SQLAlchemy 2.x; migration execution отделён от runtime. Используется expand → backfill/migrate → validate → contract. Alembic autogenerate создаёт только candidate migrations и всегда требует ручного review. Temporal и LangGraph persistence мигрируются отдельными владельцами.

PostgreSQL access разделяется по process identity: `ai_res_owner` (NOLOGIN), отдельный `ai_res_migrator`, `ai_res_api`, `ai_res_outbox_dispatcher`, `ai_res_event_consumer`, `ai_res_auditor` и backup identity. Manager Runtime и Worker Runtime не получают прямые DB credentials. Runtime роли не имеют DDL, object ownership, SUPERUSER, BYPASSRLS или доступа к owner role.

RLS + FORCE применяется к tenant/project scoped таблицам; transaction-local `app.organization_id`/`app.project_id` устанавливаются только после серверной авторизации. Отсутствующий контекст — default deny. RLS является defense-in-depth и не заменяет Policy & Permission Engine; GUC-based policies не защищают от произвольного SQL под скомпрометированной общей API identity. Все query/retrieval/export/cache/event paths сохраняют объектную ACL-проверку.

Подробная стратегия, роли, политики, миграционный runbook и acceptance criteria — `AI_RES_PostgreSQL_Migration_and_Access_Strategy_v1.0.md`; SQL reference — `AI_RES_PostgreSQL_Roles_RLS_v1.0.sql`. Реальное внедрение и runtime tests не заявляются.

PostgreSQL roles — роли процессов, а не бизнес-роли. Analyst/Reviewer/Admin права продолжают вычисляться IAM/ABAC/ACL/Policy Engine. RLS ограничивает tenant/project context и снижает риск забытых фильтров, но не авторизует действия и не защищает от произвольного SQL под общей API DB identity. Worker Run grants остаются отдельными и проверяются на каждом tool/API side effect.


## Дополнение v1.3 — DB identities и persistence enforcement

PostgreSQL roles являются техническими process identities и не заменяют бизнес RBAC/ABAC. `ai_res_owner` — NOLOGIN; `ai_res_migrator` — отдельный DDL principal; API, Outbox Dispatcher, Event Consumer, Auditor и Backup используют отдельные минимальные grants. Runtime agent processes (Manager/Worker) не получают DB credentials или network route.

Tenant/project context формируется только сервером после Policy Engine authorization и устанавливается transaction-local. RLS + FORCE применяется к scoped tables; отсутствующий контекст default-deny. GUC не считается защитой от arbitrary SQL compromise общей API identity; поэтому сохраняются параметризованные запросы, минимальная поверхность SQL и Policy Engine. Acceptance tests определены в Persistence Blueprint.


---

# Дополнение v1.4 — утверждённая security/access baseline

Статус: BASELINED (design). Local authentication MVP; server-side opaque sessions; object-level RBAC+ABAC/ACL; Policy & Permission Engine; per-WorkerRun scoped grants; no implicit permission inheritance; RLS defense-in-depth; separate DB technical identities; Manager/Worker Runtime have no direct PostgreSQL credentials; tool/connector access through Gateway; deny by default for missing/unknown context. Business roles do not map directly to PostgreSQL roles. Full SaaS multi-tenancy remains out of MVP.


---

## Дополнение v1.5 — статус и границы baseline

Архитектурные решения Local Authentication MVP, server-side opaque sessions, CSRF, privileged MFA policy, separate human/service/agent identities, organization/project ACL, Policy & Permission Engine, per-WorkerRun scoped grants и PostgreSQL process identities приняты как design baseline. PostgreSQL technical roles не являются бизнес-ролями и не заменяют Policy Engine. Manager/Worker Runtime не получают DB credentials.

Остаются implementation/acceptance gates: provisioning и rotation credentials, проверка RLS под реальными ролями, tenant isolation, pooled connection context leakage, session revocation, MFA recovery, penetration/adversarial tests и deployment-specific threat reassessment. BASELINED не означает runtime security certification. Актуальные связанные документы: Security Architecture v1.2, Threat Model v1.1, Security Controls v1.2, Secrets & Key Management v1.1, Authentication & Session Management v1.1, PostgreSQL Migration & Access Strategy v1.1 и Registry v4.0.
