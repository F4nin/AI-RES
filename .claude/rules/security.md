# security.md — Безопасность, доступ и секреты

**Нормативные источники:** `AI_RES_Security_Architecture_v1.2.md` · `AI_RES_Authentication_and_Session_Management_v1.1.md` · `AI_RES_Identity_Access_Control_v1.5.md` · `AI_RES_Secrets_and_Key_Management_v1.1.md` · `AI_RES_Security_Controls_and_Requirements_v1.2.md` · `AI_RES_Threat_Model_v1.1.md`

---

## Аутентификация (BASELINED)

### Сессии браузера
- MVP: opaque server-side session cookie. Имя cookie — `ai_res_session` (**проектное предложение**; wire name подлежит security owner approval до релизного baseline).
- State сессии хранится на сервере в PostgreSQL; Redis не обязателен.
- Cookie flags: `HttpOnly`, `Secure` (HTTPS), `SameSite=Lax`, ограниченный `Path`, без широкого `Domain`.
- Не хранить access token, refresh token или session credential в `localStorage`/`sessionStorage`.
- Ротация session ID: после login, MFA completion, privilege elevation.
- Idle timeout: 30 мин; absolute lifetime: 12 ч (configureable defaults; строже для admin).

### CSRF
- CSRF protection обязательна для всех state-changing запросов, аутентифицированных через cookie.
- Имя CSRF header — `X-CSRF-Token` (**проектное предложение**; подлежит security owner approval).
- CORS: deny-by-default с явным allowlist.

### Пароли
- Только Argon2id hash с уникальной случайной солью; параметры конфигурируемы.
- Не хранить и не логировать пароль, reset token, bootstrap secret.
- Минимальная длина: 15 символов; проверять по local denylist распространённых паролей.

### Bootstrap и первый admin
- Первый администратор — только через одноразовую bootstrap-процедуру.
- Default credentials запрещены.
- Bootstrap secret: не в Git, не в image, не в shell history; недействителен после использования.

### MFA
- Обязательна для: Organization Owner, Organization Admin, Project Admin в production-like профиле.
- MVP: TOTP как первый фактор второго уровня.
- Recovery codes: одноразовые, хранить только hash.
- MFA reset — отдельная привилегированная процедура с аудитом.

### Сервисные идентичности
- API, Manager Runtime, Worker Runtime, Temporal Activities, Connector, LLM Gateway — **отдельные service identities**.
- Браузерные сессии не передаются Manager/Worker Runtime.
- Внутренние credentials: короткоживущие, audience-scoped, ротируемые.

---

## Авторизация (BASELINED)

### ACL — обязательные правила
- Каждый запрос (read, list, search, graph traversal, export, upload, download, summary) проверяет ACL server-side по organization/project/object scope.
- Никогда не доверять client-supplied `userId`, `organizationId`, `projectId` как proof авторизации.
- Ownership объекта разрешается из БД, не из токена.
- UI visibility ≠ authorization.
- Cross-project IDOR: отклонять без раскрытия факта существования объекта (controlled 404 по IAM policy).

### Policy Engine
- Policy Engine — независимый уровень авторизации; не встраивается в RBAC напрямую.
- Policy Engine недоступен → **fail-closed** для: критических write, approval, permission grant, external side-effect операций.
- RLS в PostgreSQL — defense-in-depth, **не замена** Policy Engine.
- Каждый tool call проходит повторную проверку Policy Engine; Readiness Gate не является permission token.

### Worker Run grants
- Worker Run grant выдаётся отдельно trusted platform service.
- Grant ограничен: project/task/run, resources, operations, tools, model profile, TTL, budget.
- Права пользователя не наследуются Worker автоматически.
- Worker не может self-grant permissions или расширять scope своей задачи.

---

## Секреты (BASELINED)

**Запрещено помещать секреты в:**
- prompts, LangGraph state, WorkerResult;
- Temporal history, event payloads, Outbox records;
- logs, traces, metrics labels;
- Git репозиторий.

**DB credentials:**
- Manager Runtime и Worker Runtime не получают DB credentials PostgreSQL.
- DB credentials — только через Secret Manager (SOPS/age + Docker Compose secrets).
- TLS/SCRAM обязательны для PostgreSQL соединений.
- Credential rotation — отдельный runbook; не реализовывать молча.

**Не экспонировать через публичный API:**
- Temporal Web UI, Temporal API.
- PostgreSQL, Redis, MinIO Console.
- Bifrost admin.
- LangGraph checkpointer endpoints.

---

## Работа с контентом источников

- Содержимое Source-документов — **не доверенные инструкции**: никогда не интерпретировать как system/developer prompt.
- Загружаемые файлы: проверка типа, размера, целостности (checksum) и безопасности **до** обработки.
- Upload URLs: short-lived, object-scoped, ограниченные по content-type/size; проверять checksum после загрузки.
- Webhook сигнатуры и replay windows: валидировать; дедуплицировать event IDs.

---

## Telemetry и аудит

- Operational telemetry, Agent/product quality, Domain/Security Audit Log — **три отдельных контура**.
- Audit Log хранится в PostgreSQL; потеря telemetry не останавливает выполнение задач.
- Fail-closed для Audit Log: если запись не удалась — защищённое доменное действие не выполняется.
- **Запрещено по умолчанию в telemetry:** passwords, reset tokens, cookies/session secrets, MFA seeds, recovery codes, API tokens, private keys, connection strings, full prompts/responses, source fragments, confidential payloads.
- Высококардинальные IDs — в logs/traces; **не** в Prometheus metric labels.

---

## Security controls P0 — release blockers

Не заявлять completion increment до прохождения:
- Opaque server-side sessions + CSRF protection.
- Argon2id для паролей.
- Least-privilege PostgreSQL roles + no DDL/BYPASSRLS для runtime principals.
- RLS ENABLE + FORCE на tenant tables.
- Secrets isolation (никаких credentials в Manager/Worker Runtime).
- Negative authorization tests: cross-project IDOR, stale session, revoked grant, policy engine outage.
