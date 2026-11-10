# AI RES — Контракты непрерывного улучшения и управления автономностью

**Версия:** 1.1  
**Статус:** BASELINED для post-MVP governed CI contracts; runtime и CI endpoints/events не входят в MVP  
**Блок:** 16A  
**Связанные требования:** CI-001…CI-040  

## 1. Назначение и границы

Документ переводит архитектуру Continuous Improvement в проверяемые доменные контракты. Он не объявляет runtime реализованным. Машиночитаемая структура находится в `AI_RES_Continuous_Improvement_Contracts_Schema_v1.0.json`. Перед реализацией DTO и endpoint должны быть согласованы с основными API/Domain Model/AsyncAPI документами; этот документ не разрешает создавать параллельную модель данных.

## 2. Владение данными

| Объект | Владелец | Примечание |
|---|---|---|
| Improvement Proposal / versions | Domain service: Improvement Governance | Доменный объект AI RES; версии неизменяемы |
| Evidence Reference | Improvement Evidence service + первичный доменный владелец | Сохранять ссылку и ACL; не копировать сырой payload без основания |
| Evaluation Manifest / Result | Evaluation service | Неизменяемый manifest конкретного прогона |
| Governance Decision | Approval service / Audit | Append-only решение; исправление — новым событием/решением |
| Autonomy Grant | Policy & Permission Engine | Только активное grant участвует в авторизации; проверка при каждом действии |
| Glossary Entry | Artifact/Glossary domain service | Версионируемый канонический артефакт |

## 3. Improvement Proposal

Обязательные поля: ID, номер версии, статус, проблема, гипотеза, класс изменения, затронутые capability/action classes/components/environment/scope, evidence references, ожидаемые метрики и guardrails, риск, owner, план оценки и план отката. Proposal не является разрешением на изменение.

### 3.1. Статусы и переходы

`DRAFT → SUBMITTED → TRIAGE → EVALUATION_PENDING → (EVALUATION_FAILED | READY_FOR_APPROVAL) → (REJECTED | APPROVED) → SCHEDULED → (SHADOW → CANARY → ACTIVE | ACTIVE) → (ROLLED_BACK | CLOSED)`

Допустимые дополнительные переходы: `DRAFT → TRIAGE`, `SUBMITTED → DRAFT` только по возврату на уточнение; `EVALUATION_FAILED → EVALUATION_PENDING` после новой версии candidate/evaluation plan; `APPROVED → SCHEDULED`; `SHADOW/CANARY → ROLLED_BACK`; `ACTIVE → ROLLED_BACK/CLOSED`. Любой переход фиксирует actor, timestamp, rationale, prior/new version и correlation ID. Запрещено переходить в `APPROVED` без успешной оценки и обязательных approvals. `ACTIVE` требует pinned versions и rollout gate.

## 4. Evaluation Manifest

Каждый прогон фиксирует: Proposal ID/version, dataset and version, rubric and version, evaluator version, application build, model/provider profile, prompt versions, tool versions, workflow version, seed (если применим), sample count, результаты метрик, hard-guardrail violations, report reference и временные метки. Результат `INCONCLUSIVE` не считается PASS. Повторяемость требует фиксировать все влияющие версии и параметры.

Изменение dataset/rubric/evaluator — самостоятельный change class с review; нельзя «улучшить» score незаметным изменением тестов.

## 5. Autonomy Grant

Grant связывает capability, action class, environment, scope, уровень A0–A4, список разрешённых операций, явные запреты, лимиты, preconditions, escalation conditions, approval reference, evidence, policy version, effective period, expiry/review date и rollback procedure.

### 5.1. Правила авторизации

1. Grant проверяется Policy & Permission Engine на каждом защищённом действии, а не только при старте Worker Run.
2. Проверяются также пользовательские/сервисные полномочия, ACL, системные и организационные правила, состояние grant, scope, environment, expiry и budget.
3. Запрет имеет приоритет над разрешением; отсутствующее или неоднозначное разрешение трактуется как deny.
4. Grant не наследуется шире исходного scope и не может быть создан, расширен или продлён самим агентом.
5. Отзыв/expiry немедленно блокирует новые защищённые действия; уже начатые внешние эффекты требуют reconciliation.
6. A3/A4 не включаются по умолчанию. Предлагаемая шкала A0–A4 требует утверждения; до этого применяется наиболее ограничительный режим и обычная модель permissions.

### 5.2. Семантические инварианты Grant

JSON Schema проверяет форму, но следующие правила требуют доменной валидации:
- `expiresAt` MUST быть позже `effectiveFrom`; `reviewAt` MUST находиться в допустимом интервале и не быть позже `expiresAt`.
- Для `scopeType=PROJECT` требуется непустой `projectIds`; каждый Project должен принадлежать указанной Organization. Для `ORGANIZATION` требуется `organizationId`; `GLOBAL` доступен только специальной governance policy и не должен выводиться из отсутствия scope.
- `allowedOperations` и `explicitDenials` не должны содержать одну операцию; при конфликте deny имеет приоритет и активация блокируется до исправления Grant.
- `A0` не предоставляет права на выполнение изменяющих операций; `A1` — только рекомендация; `A2` — подготовка draft, но не активация; A3/A4 требуют явного отдельного approval.
- `maxDurationSeconds`, `maxConcurrency` и заданные budgets обязательны и не могут превышать лимиты policy/organization. Отсутствующий лимит не означает unlimited.
- Grant не может быть шире actor's own authorization, policy ceiling или project scope.
- Revocation и expiry запрещают новые protected actions; ongoing external effects переводятся в reconciliation.

## 6. Governance Decision

Решение хранится отдельно от Proposal/Grant: тип объекта, ID, APPROVE/REJECT/REQUEST_CHANGES/SUSPEND/REVOKE, approver, rationale, evidence references и timestamp. Проверка права approver выполняется сервером. Нельзя считать текстовое сообщение в Manager chat approval, если не вызван соответствующий авторизованный workflow.

## 7. Предлагаемые API операции

Базовый prefix `/api/v1`. Точные request/response DTO должны использовать JSON Schema из companion schema и общие API правила AI RES.

| Method | Path | Назначение | Основные ограничения |
|---|---|---|---|
| GET/POST | `/improvement-proposals` | Список / создание Proposal | Create — draft; evidence ACL проверяется |
| GET/PATCH | `/improvement-proposals/{proposalId}` | Чтение / изменение draft | PATCH создаёт новую версию; нельзя менять immutable history |
| POST | `/improvement-proposals/{proposalId}/submit` | Отправка на triage | Проверить owner, scope, evidence, required fields |
| POST | `/improvement-proposals/{proposalId}/evaluations` | Запуск оценки | Durable Temporal workflow; версия Proposal фиксируется |
| GET | `/improvement-proposals/{proposalId}/evaluations` | История прогонов | ACL и project scope |
| POST | `/improvement-proposals/{proposalId}/decisions` | Governance decision | Только назначенный approver; immutable decision |
| POST | `/improvement-proposals/{proposalId}/release` | Запуск approved release | Только APPROVED; pinned artifacts; release gates |
| POST | `/improvement-proposals/{proposalId}/rollback` | Остановка/откат | Authorized operator; reconciliation для side effects |
| GET/POST | `/autonomy-grants` | Список / draft grant | Создание не активирует grant |
| GET | `/autonomy-grants/{grantId}` | Просмотр grant и истории | ACL; скрывать внутренние policy details по роли |
| POST | `/autonomy-grants/{grantId}/decisions` | Approval/rejection | Human approver; A3/A4 дополнительные gates |
| POST | `/autonomy-grants/{grantId}/revoke` | Срочный отзыв | Authorized security/operator; немедленный deny |
| GET | `/glossary/terms` | Поиск канонических терминов | Только опубликованные в данном scope статусы по умолчанию |
| GET | `/glossary/terms/{termId}/versions` | История терминов | Неизменяемая история |
| POST | `/glossary/terms` | Предложить термин | Создаёт PROPOSED, не активирует |
| POST | `/glossary/terms/{termId}/decisions` | Утверждение термина | Glossary Owner / delegated approver |

Эти endpoint — проектный каталог, не утверждённая редакция основного OpenAPI. Перед кодом их необходимо внести в `AI_RES_API_and_Interaction_Contracts` и `AI_RES_Public_API_v1.1.yaml`, затем проверить совместимость.

## 8. Доменные события

Рекомендуемые события (CloudEvents 1.0 envelope; typed `data`):

- `aires.improvement.proposal.created.v1`
- `aires.improvement.proposal.submitted.v1`
- `aires.improvement.evaluation.completed.v1`
- `aires.improvement.decision.recorded.v1`
- `aires.improvement.release.started.v1`
- `aires.improvement.release.activated.v1`
- `aires.improvement.rollback.completed.v1`
- `aires.autonomy.grant.created.v1`
- `aires.autonomy.grant.activated.v1`
- `aires.autonomy.grant.revoked.v1`
- `aires.glossary.term.proposed.v1`
- `aires.glossary.term.approved.v1`

События публикуются через transactional outbox после commit доменной транзакции. Consumer обязан быть идемпотентным; события содержат IDs/versions/references, а не сырые документы, prompts, secrets или полный evaluation payload. Полные схемы событий должны быть добавлены в AsyncAPI до реализации event consumers.

## 9. Идемпотентность, конкуренция и безопасность

- Все mutating endpoints требуют idempotency key там, где повтор запроса может создать дубликат или side effect.
- PATCH использует optimistic concurrency (`ETag`/`If-Match` либо version field); конфликт возвращает 409.
- Approvals, grant activation/revocation, release and rollback — отдельные аудируемые команды, не generic PATCH.
- Доступ проверяется по Organization/Project ACL на каждом read/write, включая Evidence refs, evaluations и glossary scope.
- Не передавать сырые prompts, source fragments и секреты в события/метрики по умолчанию.
- Manager и Workers могут предлагать Proposal/Grant/Glossary changes, но не утверждать и не активировать их.

## 10. Связь требований и тестирования

| Требования | Контракт / тест |
|---|---|
| CI-001…008 | Proposal schema, evidence ACL, no-self-approval negative tests |
| CI-009…012, CI-033, CI-036 | Evaluation Manifest schema, reproducibility and guardrail tests |
| CI-013…020, CI-034…039 | State-transition, approval, release, rollback and Temporal recovery tests |
| CI-021…030, CI-040 | Autonomy Grant schema, policy-per-action, scope/expiry/revocation tests |
| CI-031…032 | Glossary schema, referential integrity, deprecated-term and approval tests |

## 11. Открытые решения перед baseline

1. Согласовать сущности и поля с Domain Model v1.2; определить, какие сущности уже существуют и должны быть расширены, а какие новые.
2. Согласовать endpoint и DTO с API Contracts v1.2 и Public API v1.0.
3. Добавить typed event schemas в AsyncAPI v1.2.
4. Утвердить матрицу owner/reviewer/approver по организациям и типам изменений.
5. Утвердить A0–A4 либо заменить шкалу; не активировать A3/A4 до решения.
6. Утвердить статистические методы, пороги, sample sufficiency и measurement windows на реальных baseline.
7. Утвердить retention, deletion, rights and consent rules для Evidence/Evaluation data.

## 12. Статус

Это детализированный проектный контракт для блока 16A. Он достаточен для предметного review и подготовки следующего contract-integration increment, но не является доказательством реализованных API, событий, таблиц или workflow.


## Дополнение v1.1 — уточнение ссылок и статуса интеграции

Ссылка на Public API уточнена до `AI_RES_Public_API_v1.1.yaml`. Этот OpenAPI файл описывает только initial vertical slice; CI endpoints из данного документа в него не включены и не считаются утверждёнными. CI endpoint/event catalogue остаётся PROPOSED до закрытия PRE-010 и согласования с `AI_RES_Domain_Model_and_Data_Architecture_v1.2.md`, `AI_RES_API_and_Interaction_Contracts_v1.3.md` и `AI_RES_Domain_Events_AsyncAPI_v1.2.yaml`. Никакие миграции, endpoint или events не должны выводиться из этого предложения автоматически.
