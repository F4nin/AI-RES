# AI RES — Архитектура безопасности

**Версия:** 1.2  
**Этап:** 13 — Архитектура безопасности и модель доступа  
**Статус:** BASELINED — архитектурный дизайн; runtime security acceptance не выполнена.  
**Основа:** ранее согласованные решения AI RES по Manager–Workers, Temporal, LangGraph, Docker Compose, PostgreSQL, MinIO, Tool Registry, Context Builder и LLM Gateway. Рекомендации, не подтверждённые пользователем, явно обозначены.

## 1. Цель и границы

Документ определяет целевую модель защиты AI RES для MVP локального On-premises deployment через Docker Compose и принципы, позволяющие позднее поддержать корпоративный On-premises и SaaS без изменения доменной модели безопасности.

Защищаются: пользовательские и корпоративные данные; требования, решения и Baseline; исходные документы и репозитории; контекст и память агентов; модели и ключи провайдеров; инструменты и интеграции; Workflow/Worker Runs; артефакты; audit trail; конфигурация, правила и программная цепочка поставки.

Не является целью MVP: сертификация по конкретному стандарту, полноценный multi-tenant SaaS, Kubernetes security deployment, произвольное выполнение кода агентами, автоматическая запись во внешние системы.

## 2. Архитектурные инварианты

1. **Zero implicit trust:** доверие не выводится только из Docker network, роли Worker, происхождения запроса или наличия технического соединения.
2. **Least privilege:** пользователь, сервис, Manager, Worker Run, инструмент и connector получают минимальные права на минимальный срок и область.
3. **Policy before execution:** каждое чувствительное действие проверяется Policy & Permission Engine непосредственно перед исполнением в enforcement point.
4. **Fail closed:** при недоступности или неоднозначности авторизации критическая операция запрещается; безопасные read-only действия могут продолжаться только по явно заданной политике.
5. **Separation of duties:** идентификация, принятие семантического решения, проверка полномочий, исполнение и аудит разделены.
6. **Untrusted data:** документы, репозитории, веб-страницы, tool outputs, MCP metadata и содержимое prompt не могут менять system rules, policy или grants.
7. **No secret in model context:** ключи и credentials остаются в host-side adapters/credential broker и не передаются LLM, Worker output, обычные logs/traces или Temporal history.
8. **Human authority preserved:** AI не утверждает бизнес-решения, Baseline, критические исключения и необратимые действия без предусмотренного полномочия.
9. **Immutable evidence:** значимые действия, policy decisions, версии контекста и артефактов оставляют проверяемый audit trail.
10. **Defense in depth:** сетевые ограничения дополняют, но не заменяют service authentication, object-level authorization и operation-level policy.

## 3. Границы доверия и компоненты

| Зона | Компоненты | Основная граница |
|---|---|---|
| User Ingress | Reverse Proxy, Frontend, API | Недоверенный пользовательский трафик; TLS, сессии, rate limits, CSRF/CORS по типу клиента |
| Application | Domain/Application Services, Manager Runtime, Worker Runtime | Сервисная идентичность, авторизация каждого запроса, ограниченные внутренние API |
| Workflow | Temporal Server/Workers, Activities | Temporal не является источником бизнес-полномочий; Signals/Updates авторизуются Backend до отправки |
| Data | PostgreSQL, MinIO, Redis (optional) | Не публикуются наружу; отдельные роли, ACL, резервные копии, шифрование диска/backup |
| Controlled Egress | LLM Gateway, Connector Gateway/Adapters | Разрешённые назначения, протоколы, классификация данных, лимиты и аудит |
| Admin | Temporal UI, MinIO Console, админские функции | Только ограниченный администраторский доступ, отдельная аутентификация и аудит |
| Untrusted execution | Будущий sandbox для кода | Изолирован от обычных Runtime и Data; выключен в MVP |

Схема является логической. В Docker Compose сети реализуют сегментацию, но контейнеры и host остаются частью общей поверхности риска.

## 4. Идентичности и полномочия

Различаются:
- **Human identity:** пользователь/администратор, аутентифицированный через Identity Provider или локальный механизм MVP.
- **Service identity:** API, Manager Runtime, Worker Runtime, Temporal Activity, LLM Gateway Adapter, Connector Adapter, backup/monitoring.
- **Agent role:** логическая специализация Manager/Worker; сама по себе не является субъектом безопасности.
- **Worker Run identity/context:** конкретный запуск с отдельными grants, бюджетами, контекстом и сроком действия.

Права пользователя не наследуются Worker автоматически. Manager может запросить временное расширение инструментария/прав, но Policy & Permission Engine независимо разрешает или отклоняет его. Worker не может выдать себе полномочия, перенести их на другой Run или обратиться к другому Worker Runtime напрямую.

## 5. Модель авторизации

Рекомендуется гибрид RBAC + ABAC:
- RBAC задаёт базовые роли организации/проекта (например, Organization Owner, Project Admin, Analyst, Reviewer, Read-only Viewer, Auditor).
- ABAC ограничивает доступ атрибутами субъекта, объекта, операции, проекта, Epic, Task, классификации данных, состояния объекта, среды, времени и контекста Run.
- Системные правила AI RES имеют высший приоритет; организационные и проектные правила могут только добавлять ограничения, но не ослаблять обязательные системные.
- ACL проверяется не только на UI/API, но и на retrieval, индексации, графовых путях, summaries, экспорте, tool calls и artifact access.

Решение авторизации включает subject, action, resource, scope, data classification, policy/rules versions, decision, reason code, obligations, expiry и correlation IDs. Отказ не раскрывает сведения о существовании недоступного объекта сверх разрешённого.

## 6. Контроль данных и LLM Gateway

**Принятое пользователем решение:** вариант C — единый LLM Gateway поддерживает внешние API и локальные модели; Manager/Workers не обращаются к провайдерам напрямую.

**MVP:** один выбранный режим/провайдер, но интерфейс и policy contract допускают оба класса моделей. Конкретный провайдер и модель фиксируются после PoC.

Поток: Runtime → AI RES LLM Gateway Adapter → Policy/Rules checks → LLM Gateway → разрешённый provider/model. Перед отправкой проверяются: разрешённый профиль модели, классификация данных, допустимость egress, project/org policy, redaction/minimization, лимиты и наличие согласия/основания, если оно требуется политикой.

Gateway выполняет техническую маршрутизацию, provider auth, retries/fallback и usage metering. Он не заменяет AI RES Policy Engine и не решает, допустимо ли раскрытие данных. Локальная модель не означает автоматически безопасный или разрешённый контур: доступ к локальному endpoint и данным также контролируется.

Кандидат Bifrost остаётся **кандидатом**, а не утверждённой production-зависимостью, до PoC и security review. Проверить как минимум auth, tenancy/isolation, secret handling, request/response logging, provider routing, model allowlist, egress, limits, structured output/tool calling, streaming, failure modes, CVE/advisories и конфигурацию контейнера.

## 7. Инструменты и интеграции

Все вызовы проходят через Tool/Connector Gateway или эквивалентный enforcement point. Инструмент имеет узкий типизированный контракт; запрещены универсальные произвольные SQL/shell/HTTP операции без отдельного обоснования и изоляции.

Перед исполнением проверяются субъект, scope, операция, объект, классификация данных, побочные эффекты, обратимость, idempotency, rate limit и необходимость human approval. Для внешней записи в MVP действует deny-by-default; текущие GitHub/GitLab подключения read-only.

MCP серверы считаются внешними компонентами и требуют инвентаризации, проверки происхождения/версии, allowlist tools, отдельной идентичности и ограниченного сетевого доступа. Описание инструмента и tool output являются недоверенными данными.

## 8. Секреты и криптография

Для MVP сохраняется уже описанная конфигурационная модель SOPS/age для секретов в репозитории и Docker Compose secrets для передачи сервису. Это не полноценный runtime vault.

Требования:
- plaintext secrets не хранятся в Git, образах, prompt, Context Package, Worker result, Temporal History, telemetry или audit payload;
- отдельные service credentials, минимальные scope, ротация, отзыв и учёт использования;
- secret bootstrap и age private key находятся вне репозитория и защищаются отдельно;
- credentials провайдеров хранятся в Gateway/host-side broker; Runtime получает только разрешённую операцию, а не сам ключ;
- шифрование диска/backup и TLS ingress обязательны для рабочей поставки; service-to-service TLS уточняется профилем угроз и PoC.

## 9. Сеть и runtime hardening

Рекомендуемая сегментация: Ingress, Application, Data, Controlled Egress и Admin. Data services не публикуются на host interfaces без необходимости; наружу доступен только Reverse Proxy. Egress allowlist ограничивает домены/IP/порты для LLM Gateway, connectors и обновлений. DNS и redirect handling контролируются для защиты от SSRF/DNS rebinding.

Контейнеры non-root, без privileged и Docker Socket; read-only filesystem где возможно; drop Linux capabilities; seccomp/AppArmor профили по совместимости; CPU/RAM/PID/time limits; отдельные временные каталоги; минимальные base images; pinned digests. Worker Runtime не исполняет недоверенный произвольный код. Sandbox — отдельная будущая capability и не является обязательной частью MVP.

## 10. AI-specific угрозы

- Direct/indirect prompt injection через документы, веб, репозитории, tool output и memory.
- Data exfiltration через prompt, tool arguments, model response, generated artifact и telemetry.
- Tool misuse/confused deputy: агент использует полномочия Runtime шире исходной задачи.
- Context/tenant leakage через retrieval, кеши, summaries, graph traversal и shared Worker pool.
- Poisoning источников, индекса, памяти, Evaluation Set или exemplar library.
- Insecure output handling: небезопасный SQL/Markdown/HTML/diagram/code/API spec.
- Model/provider compromise, malicious MCP server, dependency/supply-chain compromise.
- Excessive agency: автоматическое выполнение внешних/необратимых действий.

Защита строится не только на prompt instructions: ACL до retrieval, provenance, untrusted-content labeling, tool allowlist, schema validation, operation-level authorization, output validation, human approval, egress control, independent QA и audit.

## 11. Аудит, телеметрия и инциденты

Доменный Audit Log отделён от технических logs/traces. Audit события append-only с контролем доступа и защитой от незаметной модификации. Фиксируются субъект/сервис, действие, объект, scope, результат, policy version, время, correlation IDs и ссылки на версии. Секреты и чувствительные payload не записываются.

Security monitoring включает auth failures, denied operations, unusual tool use, egress anomalies, retrieval ACL denials, secret access, admin actions, policy changes, model/provider changes, rate-limit spikes и anomalous Worker Runs. Нужны процедуры incident triage, containment, credential rotation, evidence preservation, recovery и post-incident review.

## 12. Статус решений

| Положение | Статус |
|---|---|
| LLM Gateway с внешними и локальными моделями (вариант C) | **Подтверждено пользователем** |
| MVP начинает с одного режима/провайдера | Рекомендация; уточнить конкретный выбор перед реализацией |
| Bifrost как основной кандидат | Кандидат для PoC/security review, не окончательный выбор |
| Docker Compose, локальный On-prem MVP | Ранее подтверждено |
| Temporal, LangGraph, PostgreSQL, MinIO и модульный Backend/Runtime | Ранее подтверждено |
| RBAC + ABAC, отдельные service identities, scoped Worker Run grants | Архитектурная рекомендация для утверждения |
| Сети Ingress/Application/Data/Controlled Egress/Admin | Архитектурная рекомендация для утверждения |
| SOPS/age + Compose secrets | Ранее описано как инфраструктурное решение; operational hardening требует проверки |
| MFA/SSO/IdP и точная ролевая матрица | Открыто |
| TLS между всеми сервисами, алгоритмы шифрования, retention, RTO для security incidents | Открыто |
| sandbox для произвольного кода | Не входит в MVP |

## 13. Критерии готовности security design

- [ ] Инвентаризированы активы, субъекты, потоки и границы доверия.
- [ ] Для каждой операции определены субъект, scope, policy check и enforcement point.
- [ ] ACL действует до retrieval и экспорта, включая graph paths и summaries.
- [ ] Worker Run grants ограничены по объектам, операциям и времени; автоматическое наследование запрещено.
- [ ] LLM egress контролируется по provider/model/data classification.
- [ ] Tool/Connector calls проходят повторную авторизацию непосредственно перед исполнением.
- [ ] Секреты исключены из модельного контекста, истории Workflow и телеметрии.
- [ ] Внешние/необратимые side effects требуют утверждённой политики и при необходимости human approval.
- [ ] Пройдены негативные тесты prompt injection, SSRF, IDOR/BOLA, cross-project leakage и privilege escalation.
- [ ] Проверены backup, audit integrity, credential rotation и incident runbooks.

## 14. Связанные документы

- `AI_RES_Threat_Model_v1.0.md`
- `AI_RES_Identity_Access_Control_v1.0.md`
- `AI_RES_Secrets_and_Key_Management_v1.0.md`
- `AI_RES_Security_Controls_and_Requirements_v1.0.md`
- `AI_RES_Infrastructure_Deployment_Operations_v1.2.md`
- `AI_RES_Tool_Registry_and_Tool_Management_MVP_v0.3.md`
- `AI_RES_Agent_Architecture_Concept_v4.0.md`


---

## Дополнение v1.1 — Authentication Provider и пользовательские сессии

Для MVP используется локальная аутентификация AI RES без обязательного внешнего IdP. Authentication Service работает через заменяемый `IdentityProvider` port. Local Identity Provider включён в MVP; OIDC Provider Adapter предусмотрен для последующего подключения корпоративного IdP.

OIDC — первый поддерживаемый протокол внешней федерации (Authorization Code + PKCE S256). SAML напрямую не реализуется; SAML-корпоративные каталоги при необходимости подключаются через OIDC broker. Внешний IdP не становится источником проектных ролей и ACL автоматически.

Пользовательские browser sessions — непрозрачные server-side sessions, передаваемые только в HttpOnly/Secure/SameSite cookie с CSRF protection. Пароли хешируются Argon2id. MFA обязательна для привилегированных административных ролей в production-like deployment. Сервисные identity и Worker Run grants остаются отдельными механизмами.

Полная спецификация: `AI_RES_Authentication_and_Session_Management_v1.0.md`. Модель ролей и object authorization: `AI_RES_Identity_Access_Control_v1.1.md`.


---

# Дополнение v1.2 — Security Architecture baseline

Статус: BASELINED (architecture design). Mandatory MVP boundaries: local auth + server-side sessions; object-level authorization; project/org isolation; Policy Engine independent from LLM; scoped WorkerRun grants; per-call tool/connector authorization; secrets outside prompts/Temporal/telemetry; file intake validation; prompt-injection treated as untrusted data; egress allowlist; non-root/no privileged/no Docker socket; PostgreSQL least privilege and RLS; durable audit for protected mutations; incident/revocation/recovery procedures.

Security design approval does not equal penetration-test or production certification. SEC acceptance tests and runtime evidence remain release blockers.
