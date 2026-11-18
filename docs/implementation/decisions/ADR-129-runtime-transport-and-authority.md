# ADR-129 — OD-19: сервисная авторизация Temporal и Platform API

| Поле | Значение |
|---|---|
| Дата / статус | 2026-11-17 / ACCEPTED как техническое решение по делегированию владельца; реализация NOT_STARTED, protocol PoC NOT VERIFIED |
| Ответственный | Implementation Lead; владелец делегировал выбор механизма, независимые security/runtime gates сохраняются |
| Основание | На вопрос OD-19 владелец поручил: «Тут возьми ответственность на себя. Обязательно учитывай общую концепцию нашего разрабатываего агента, и специфику уже ранее разработанных узлов» |
| Требования / gaps | DOC-006 §7.2/9, DOC-018 service/Run identities, DOC-016/020, DOC-023 §8, DOC-068/072; G-104/106/111, OD-19; G-107 остаётся отдельной обязательной предпосылкой первого producer |
| Решение | Один Temporal namespace, две очереди, mTLS + native server authorization extension с durable task-issuance receipts; отдельный Platform API с private TLS, существующей Ed25519 основой, versioned request binding и trusted execution assignments |
| Scope | Выбор и документирование технического механизма/плана, без изменения runtime, DB, секретов, wire contracts, canonical и без запуска G02/SLICE |
| Совместимость | Публичный API/доменная модель полномочий не расширяются. Внутренние credential/Platform contracts версионируются до handler; ar1 и исторические migrations не переписываются |
| Риск / пересмотр | Receipt protocol, custom server composition и SDK compatibility — гипотезы до ограниченного PoC. Неудача PoC не разрешает weaker fallback; пересматривается механизм в тех же гарантиях |

## 1. Концепция и существующие узлы

AI RES — единая платформа инженерии требований: Manager координирует, Temporal хранит durable orchestration, LangGraph выполняет reasoning, Backend/PostgreSQL владеет доменным состоянием. Бизнес-решения, Baseline и grants остаются за предусмотренными человеком/Policy границами. Девять Worker специализаций — роли общего Worker Runtime pool, не девять сервисов/сертификатов/БД.

Сохраняются модули/процессы, очереди `ai-res-manager` и `ai-res-workers`, стабильный Workflow ID от Operation, Outbox/Inbox, CAS и атомарные Event+Outbox+Audit, SOPS/age → Compose secrets, Ed25519 service authentication, replay историй и текущая failure/cancel семантика. Manager/Worker не получают DB credentials или Docker socket, не self-grant и не запускают peer Worker. Перед каждым реальным WorkerRun остаётся актуальный Gate с final revalidation и отдельным Run grant.

Фактическое состояние:

- [client.py](../../../backend/src/ai_res/orchestration/client.py): Temporal connect без TLS/identity; [workers.py](../../../backend/src/ai_res/orchestration/workers.py) уже разделяет Manager workflows/Activities и activity-only Worker. Worker не получает workflow polling/completion права.
- [service_tokens.py](../../../backend/src/ai_res/modules/iam/service_tokens.py): ar1 содержит ровно iss/aud/iat/exp/jti, отдельные issuer Ed25519 keys; verified jti не возвращается вызывающему слою и не проверяется durable replay store.
- [internal_api.py](../../../backend/src/ai_res/api/internal_api.py): audience API и таблица capabilities только по сервису; это не execution-scoped authorization. [orchestration_service.py](../../../backend/src/ai_res/modules/operations/orchestration_service.py): tenant ref проверяется по строке/RLS, но ack ещё не требует trusted dispatch assignment.
- [compose.yaml](../../../infra/compose.yaml): platform-api в общей app/data, HTTP и общая ai_res_api роль; Worker только в workflow, без Platform API/signing key. Эти ограничения не снимаются преждевременно.
- [writer.py](../../../backend/src/ai_res/modules/audit/writer.py) требует проверенную organization; нельзя придумать tenant для аудита anonymous401/403.

## 2. Temporal: identity, RPC и очереди

### 2.1. Выбранный механизм

Сохранить Temporal1.29.7 и Python SDK1.36.0, один namespace и существующие две очереди. Сборка Temporal получает тонкую composition-extension через native ClaimMapper/Authorizer/frontend interceptor hooks; ядро Temporal не форкается. Это дополнительный поддерживаемый build artifact того же сервера, без нового proxy/IdP/broker/БД или прикладного фреймворка. Пин source/dependencies/toolchain, SBOM/audit, upgrades и restore/restart evidence включаются в реализацию; текущий образ не заменяется этой записью.

Frontend требует mTLS с проверкой цепочки/срока/разрешённой service identity из проверенного сертификата. Issuer map основан на явном verified SAN и текущем реестре identities/отзыва; не на request.identity, task queue prefix, произвольном CN или клиентском заголовке. CA/signing private keys остаются вне Manager/Worker, каждый Runtime получает только свою leaf identity; внутренние server/operator identities отделены от agent identities. Существующие секреты не ротируются как побочный эффект.

Default-deny Authorizer проверяет полный RPC method, namespace и фактический ресурс. Health/SDK-support RPC разрешаются только минимальным явным набором без данных. Unknown RPC/version/request shape и неразрешённые batch/multi-operation/eager/ById пути отклоняются. Не выдавать namespace Writer как замену нужной матрице.

| Principal | Разрешённая задача | Запрещённое |
|---|---|---|
| Outbox dispatcher | Идемпотентный Start только утверждённого workflow type/namespace/manager queue по durable dispatch intent | Poll/complete, domain mutation, generic Start/Signal/Update/admin |
| Manager Runtime | Workflow+Activity polling своей manager queue; token-bound replies; необходимые SDK calls | Worker queue polling, administrative API, права бизнес-/human approval |
| Worker Runtime | Activity-only polling worker queue; token-bound completion/failure/cancel/heartbeat своей выдачи | Workflow polling/completion, Start/Signal/Update, чужая выдача, ById, history/visibility/admin |
| Backend cancellation / future reconciler | Только авторизованный signal/read/describe для своего execution purpose | Poller права и обход доменной Policy; клиентский Signal напрямую |
| Bootstrap/operator/server-internal | Отдельные минимальные инфраструктурные capabilities | Передача admin credentials Runtime; публичный Temporal UI/API |

Матрица реализуется по реальным SDK/server RPC, не только по намерению Python wrapper. Manager orchestration не получает произвольный user-supplied Start; fan-out выполняется через разрешённые deterministic Workflow commands и Platform assignments после Policy/Gate.

### 2.2. Completion: проверка реальной выдачи task token

mTLS и Poll ACL недостаточны: native task token не подписывает identity/queue caller. Выбрано сохранять token bytes без изменения SDK protocol и регистрировать факт выдачи на доверенной frontend стороне:

1. После успешной выдачи server task, но **до доставки ответа клиенту**, frontend interceptor через узкий auth-control endpoint Platform API сохраняет digest точных opaque token bytes, проверенный runtime principal, namespace, normal queue, task kind и требуемую lifecycle/binding metadata. Физический контракт/индексы/size bounds определяются до PoC handler; здесь не вводятся публичные поля.
2. Backend хранит receipts в существующей ai_res_db под собственной узкой security-control ролью/портом. Temporal extension получает отдельную auth-control service identity: register/check issuance и narrow metadata-only authorization checks §3.2, без domain mutation grants и domain DB credentials. Новый сервис/БД не вводится.
3. На completion/heartbeat проверяются текущая identity/revocation, допустимый RPC и совпадение digest/binding с фактически выданной задачей. Missing/conflicting receipt, неверный principal/kind/queue, store outage — отказ до core handler. Затем native Temporal проверяет attempt/deadline/state: receipt не заменяет его проверки и не даёт бизнес-полномочий.
4. Register-before-deliver fail-closed: не удалось durable registration — ответ с usable token не выдаётся; восстановление через штатные timeout/retry. Повтор той же регистрации с тем же binding идемпотентен; конфликт нельзя молча перезаписать. Legitimate lost-poll/repoll/reassignment моделируются PoC; при неоднозначном ownership отказываем, не расширяем audience.
5. Task receipt **не расходуется одноразово**. Повтор completion/heartbeat после потерянного ACK должен дойти до native state/idempotency проверки. Это отличается от одноразового nonce HTTP service request (§3).
6. Raw task tokens/cert keys/service credentials не хранятся в receipt store, prompt, history, events, logs или telemetry; только минимальная binding metadata. Digest/IDs не metric labels. Retention/TTL/purge не выдумываются: до определённой безопасной lifecycle policy нет автоматического удаления; устаревшие tokens отвергает core/current identity. Потеря registry не восстанавливается разрешением всех token.

**Все пути выдачи** должны быть покрыты или запрещены сервером: PollActivity/PollWorkflow, sticky handling, inline next WorkflowTask в RespondWorkflowTaskCompletedResponse. Sticky ownership/normal queue устанавливаются доверенным assignment, не верой клиентскому normal_name/prefix. Eager activity и eager workflow start изначально отключить серверной policy; одного SDK flag недостаточно. Query/Nexus/async ById/completion APIs не открывать по умолчанию. Пропущенный путь выдачи должен дать отказ входящего unregistered token, а не обход проверки.

Auth-control receipt endpoint не выполняет Temporal RPC ни при register, ни при check: иначе возникнет цикл Temporal auth → Platform → Temporal. Только короткие DB transactions, ограниченный I/O вне чужих transactions. Store outage намеренно прекращает защищённое исполнение; bounded retries и G-107 восстанавливают процесс, не fail-open. Дополнительная API/DB нагрузка измеряется в PoC, новые SLO/числа не утверждаются.

### 2.3. Вложенные Workflow Commands — отдельная граница авторизации

Действительный task-token receipt доказывает получение задачи, но не право произвольных команд в RespondWorkflowTaskCompleted. До core handler сервер проверяет полный вложенный Commands набор: явный allowlist по утверждённой workflow contract version, exact type/namespace/queue и компактной typed input schema. Нельзя авторизовать только внешний RPC и пропустить вложенный fan-out.

ScheduleActivityTask для Worker разрешается лишь при backend-owned разрешённом Run assignment с exact Task/WorkerDefinition/ContextPackage, актуальным Gate/Run grant и допустимым activity type/worker queue. Эта metadata-only проверка не выполняет Temporal RPC; DB transaction не удерживается во время внешнего I/O. При stale/revoked/unknown assignment либо недоступном verifier команда не поступает core. При Activity entry выполняется current admission/revalidation; разрешение команды не заменяет финальную проверку перед WorkerRun.

StartChildWorkflowExecution, SignalExternalWorkflowExecution, ContinueAsNew и их namespace/type/queue/input изменения разрешаются только отдельным typed policy handler для конкретного утверждённого сценария; до его реализации DENY. То же относится к eager execution, version/routing overrides и неизвестным Commands/полям/codec payloads. Безвредные workflow primitives также имеют явный bounded контракт; неизвестное не получает неявный ALLOW. Разрешённые cancel/outcome commands привязаны к существующему execution assignment; generic external orchestration не открывается.

Проверка выполняется на реальном server request, а не только в коде Python SDK/LLM tool schema. Replay Workflow кода остаётся детерминированным: auth I/O на транспортной границе и в Activities. PoC обязан покрыть valid Manager identity+receipt с вредоносной ScheduleActivity/Child/Signal/ContinueAsNew командой, подменой queue/type/input/assignment, stale Gate и разрешённый positive control. До этих тестов утверждение «fan-out не обходит Gate» NOT VERIFIED.

### 2.4. Почему не выбран более простой на вид вариант

- mTLS + default Authorizer: аутентифицирует peer, но namespace Writer позволяет слишком широкий RPC набор и не обеспечивает нужный queue scope.
- Только client wrapper/Poll ACL: изменённый клиент или forged completion обходит намерение программы.
- Разделение namespace/кластеров: меняет durable orchestration и не решает методные права само по себе; для текущих двух queues лишняя миграция.
- Дополнительный сетевой proxy: ещё одна служба и тот же вопрос task-token binding. Native extension сохраняет имеющуюся топологию.
- Подписанный wrapper task token: дополнительная crypto/wire совместимость; internal validators парсят token до custom frontend interceptor. Для первого MVP не выбирается protobuf/MAC трюк с unknown fields.
- Privileged history/scheduled-event lookup на каждый completion: резервная альтернатива при провале receipt PoC, с рисками availability/recursive auth; не разрешён как автоматический fallback.

## 3. Platform API: существующая криптография, точные полномочия

### 3.1. Transport и service request authentication

Отдельная internal platform network вместо общей app для Platform API/Manager. Listener не публикуется на host/public proxy. На первом шаге прямой Uvicorn HTTPS и HTTPX с private CA, hostname/SAN verify, запретом HTTP downgrade/redirect и bounded body/header/concurrency до parsing/auth. Никаких verify=False/универсальных upstream proxies. Trusted frontend auth-control caller подключается к этому же узкому internal listener; Worker получает доступ только вместе с разрешёнными S23 ports/grants.

Platform identity доказывается существующей Ed25519 основой, а не отсутствующей в текущем ASGI доверенной peer-cert привязкой. Не заявлять mTLS certificate-to-issuer binding для Platform API до отдельного проверенного TLS termination seam. Temporal mTLS и private TLS+Ed25519 Platform — разные механизмы, оба явно контролируемы.

Выделить audience PLATFORM_API из общей API. Сохранить строгий ar1 для прежних потребителей; новый versioned internal request credential с отдельной domain separation связывает authenticated issuer, audience, action, method, canonical route, bounded body digest, execution assignment ref, nonce и срок. Точная сериализация/полезная нагрузка и key/instance mapping проходят contract+crypto review до реализации; нельзя молча добавить claims в ar1 или обещать текущему ServiceIdentity недоступный jti. Никаких roles/grants по заявлению модели.

Одноразовый request nonce проверяется durable PostgreSQL receipt с uniqueness при конкуренции/нескольких replicas и после restart; store outage — fail-closed. Принимается только после подписи/issuer/audience проверки, потребляется надёжно до защищённого эффекта и не возвращается в оборот rollback бизнес-команды. HTTP retry выпускает новый credential/nonce, сохраняя тот же semantic command/idempotency key. Нельзя подменять бизнес-идемпотентность nonce и ломать безопасный повтор после потерянного ответа.

### 3.2. Authority принадлежит backend

Подписанный самим Manager operationId, правильный tenant body или знание assignment ref — ещё не право. При принятии разрешённой команды backend атомарно с Operation+Outbox фиксирует server-owned dispatch assignment с exact Operation/tenant, workflow/type, разрешённым service principal и narrow actions. Runtime не может создать/расширить его своей подписью. При ack/outcome/cancel Platform проверяет этот assignment, текущие состояние/версии и actor; затем устанавливает transaction-local tenant и выполняет существующие RLS/CAS/domain rules.

Start ещё не имеет task receipt: до StartWorkflowExecution custom authorizer запрашивает отдельную typed read-only проверку trusted dispatch assignment (authenticated caller, namespace, точный workflowId/type, queue, contract version и digest компактного input). Ref/UUID от dispatcher без существующего server-owned intent не является proof. Отсутствие/несовпадение intent или недоступность проверки запрещает Start. Аналогично narrow cancel/read checks привязаны к backend-авторизованному purpose и execution, а не к одному method allowlist. Проверяющий endpoint читает только platform-owned metadata и не обращается обратно в Temporal; это не допуск прямого domain mutation для Temporal frontend.

Workflow/run binding получает provenance из trusted dispatch/reconciliation, а не только из переданного Runtime идентификатора; race между фактическим Start и сохранением его результата восстанавливается G-107. I/O Temporal/HTTP не выполняется внутри DB transaction; после внешнего чтения делается final revalidation под lock/CAS. Assignment reference в history — непривилегированный ref, bearer capability/credential туда не попадает.

Для S23 отдельно добавляются точные WorkerRun/Task/WorkerDefinition/runtime assignment, immutable ContextPackageVersion, финальный Gate и актуальный Run grant с TTL/tools/model/budget. Ключ/identity Runtime не заменяет grant. Host-side typed ports используют bound execution context, а не произвольные runId/grantId/worker role от LLM. Общий пул специализаций сохраняется; Worker не получает operation-control actions Manager или прямую запись доменных данных.

Auth-control identity Temporal extension имеет register/check task issuance и отдельные narrow read-only metadata authorization checks: разрешён ли конкретный Start по trusted dispatch intent, cancellation/read purpose и набор typed Workflow Commands по действующим assignments/grants. Она не может создавать/расширять доменные assignments, approve grants/results, менять Operation или читать source content. Endpoints metadata-only и не вызывают Temporal; это не generic execute/универсальный permission lookup с правом self-grant. Service request replay receipts и Temporal task-issuance receipts — разные логические сущности с разным lifecycle.

## 4. БД, audit, ошибки и существующая семантика

Platform API — собственная техническая login/group с явными schema/table/column grants. Не наследовать широкий ai_res_api_group, не давать owner/DDL/SUPERUSER/BYPASSRLS; FORCE RLS/default-deny и transaction-local scope сохраняются. Manager/Worker и Temporal auth extension доменных DB credentials не получают. Provisioning allowlists/CONNECT/secret mapping, role map и tests меняются согласованно; только новые forward Alembic migrations, без правки immutable revisions.

Нормативную role map и нужную формализацию internal API синхронизировать до реализации влияющих grants (NCP-14/Registry по установленному порядку). Делегирование выбора механизма не объявляет тихо принятым весь NCP-14, новую бизнес-роль, QUEUED semantics или произвольный нормативный diff. Числовые лимиты/retention остаются WORKING до своих решений; scope полномочий не расширяется.

До установленного tenant — отдельный durable security-auth event sink с минимальными проверенными transport/service facts и без доверия body tenant. Нельзя подделать organization для существующего SqlAuditWriter. После server authorization tenant denials/success пишутся существующим audit в транзакции с действием. Ошибка обязательного audit запрещает protected mutation; отказ audit/receipt service не маскируется telemetry fail-open.

Invalid credentials → authentication error; known unauthorized action/foreign scope → согласованный controlled403/404 без existence leak; outage обязательного verifier/store → unavailable/503 без выполнения, а не ошибочный постоянный success/deny. Существующие retry классификации актуализируются по internal contract: fresh nonce на HTTP попытку; bounded retries, idempotent transitions и G-107 reconciliation. Терминальный Operation не переоткрывается, реальная ошибка побеждает отложенную отмену, не заявляется exactly-once. Race cancel/start с WorkerRun закрывается общим Operation lock/CAS (G-119), не новым источником истины.

## 5. Порядок реализации в существующем плане

1. Ограниченный protocol/security PoC на pinned Temporal/SDK в изолированной test среде штатными средствами: native extension/mTLS/RPC ACL, task receipt register/check, happy path и attacks. Никаких реальных пользовательских Operation/model calls. До его результата feature feasibility — NOT VERIFIED.
2. Versioned internal contracts/credential и auth-control seam до handlers; schema/role map/provisioning/RLS, private TLS/audience/nonces, durable assignments/audit и retry rules. Старый insecure path не оставлять доступным как compatibility bypass.
3. До первого реального MANAGER_MESSAGE/другого Start producer совместно проверить OD-19 enforcement и **G-107 reconciler+allowlist**, delivery/replay/failure paths и observability. Закрытие только авторизации не разрешает producer. Не ждать S23 для этих условий S20.
4. Продолжить S20→S21 в общей G02 ветке после её внешних предпосылок. Старые Workflow histories replay; authentication I/O только Activities/transport, не Workflow код. G-110/versioning и G-126 остаются своими задачами, текущий ADR не меняет QUEUED/event envelope.
5. Перед S23 допустить Worker Activity path только с Gate/grants/result validation и актуальными per-call permissions. Общие проверки/review/delivery группы по ADR-127; отдельный полный pre-pr на каждом внутреннем Sxx не навязывается.

Это план задач внутри согласованных этапов/предпосылок, не новая группа/перестановка roadmap и не поручение начать код. SLICE-01 перед S17, model admission, отдельные бюджеты и approvals сохраняются. При провале PoC профиль/producer остаётся blocked до исправления механизма; безопасность не понижается ради зелёного статуса.

## 6. Приёмочные проверки реализации

- mTLS: wrong/expired/revoked certificate, trusted CA but unknown SAN, spoofed request.identity, namespace mismatch; no plaintext/direct unauthorised frontend/internal bypass.
- Worker: чужая очередь/все Workflow RPC/Start/Signal/Update/ById/batch/admin/history deny; допустимые activity polling/completion/heartbeat positive controls.
- Task issuance: invented/modified/stolen cross-principal token, task-kind/namespace/queue mismatch, unregistered token, sticky/inline path, eager denied; digest не даёт client self-register. Потерянные poll/ACK и повтор completion/heartbeat не блокируют корректный retry; native stale/attempt/timeouts сохраняются.
- Replicas/restart/failure: idempotent concurrent receipt registration, binding conflict, no register-before-deliver bypass, registry unavailable, restored/outdated receipts и revoked principal; auth-control endpoint без Temporal RPC; bounded load/latency/pool saturation измеряются, не объявляются SLO.
- Platform: wrong issuer/audience/key/version, изменённые method/path/body/action/assignment/Operation/Workflow/Run, duplicate nonce race/restart/store failure, fresh nonce after lost HTTP response → один domain transition/event/outbox/audit.
- Start с действительной dispatcher identity, но отсутствующим/чужим intent или изменёнными workflowId/type/queue/input deny; valid Manager identity/task receipt с запрещёнными вложенными Workflow Commands или staleGate assignment deny; valid Manager identity без dispatch assignment deny; Worker на Manager action deny; соседний Run/stale or revoked grant/ContextPackage deny; sender metadata не источник authority.
- Реальные PostgreSQL roles/grants/FORCE RLS, default deny/cross-tenant/reset pool, no broad api inheritance/DDL/ownership; empty/previous upgrade и drift0 при миграциях.
- TLS CA/SAN/downgrade/redirect/body-limit, anonymous audit без fake tenant, audit failure без mutation, отсутствие credential/token/raw payload в logs/traces/history/events/results.
- Replay поддерживаемых histories, duplicate/out-of-order Outbox, dispatcher crashes, cancel/start/outcome races и G-107 eventual reconciliation. Обязательные general/security/database reviews, применимые G1–G9/pre-pr/Linux CI остаются.

## 7. Evidence исследования, а не runtime certification

Изучены локальные code/config/contracts выше, canonical Registry и профильные IAM/Security/Auth/API/Operation требования. Два отдельных read-only задания: planner/architect по локальным узлам и Temporal feasibility по первичным pinned sources. Код/секреты/идентификаторы AI RES во внешние поисковые запросы не передавались; запросы общие по библиотеке.

Проверен Temporal source1.29.7 commit `1f74f0c8e9935980d92a39069185671bbbba7c7e`; SDK Python1.36.0 commit `4733537c4a1d523fa1f0081c18512d895f4f88b8`. Это документальное evidence API seams/ограничений, не успешный PoC. Применимость receipt протокола и native extension order требует тестов §6.

Первичные источники:

- [Default Authorizer и гранулы ролей](https://github.com/temporalio/temporal/blob/1f74f0c8e9935980d92a39069185671bbbba7c7e/common/authorization/default_authorizer.go), [RPC metadata](https://github.com/temporalio/temporal/blob/1f74f0c8e9935980d92a39069185671bbbba7c7e/common/api/metadata.go).
- [ClaimMapper/AuthInfo](https://github.com/temporalio/temporal/blob/1f74f0c8e9935980d92a39069185671bbbba7c7e/common/authorization/claim_mapper.go), [сертификат в interceptor](https://github.com/temporalio/temporal/blob/1f74f0c8e9935980d92a39069185671bbbba7c7e/common/authorization/interceptor.go).
- [CallTarget.Request и config factory](https://github.com/temporalio/temporal/blob/1f74f0c8e9935980d92a39069185671bbbba7c7e/common/authorization/authorizer.go), [native server extension options](https://github.com/temporalio/temporal/blob/1f74f0c8e9935980d92a39069185671bbbba7c7e/temporal/server_option.go).
- [Task token protobuf](https://github.com/temporalio/temporal/blob/1f74f0c8e9935980d92a39069185671bbbba7c7e/proto/internal/temporal/server/api/token/v1/message.proto), [serializer](https://github.com/temporalio/temporal/blob/1f74f0c8e9935980d92a39069185671bbbba7c7e/common/tasktoken/serializer.go).
- [Порядок frontend interceptors](https://github.com/temporalio/temporal/blob/1f74f0c8e9935980d92a39069185671bbbba7c7e/service/frontend/fx.go), [ранняя namespace validation](https://github.com/temporalio/temporal/blob/1f74f0c8e9935980d92a39069185671bbbba7c7e/common/rpc/interceptor/namespace_validator.go).
- [Eager dynamicconfig](https://github.com/temporalio/temporal/blob/1f74f0c8e9935980d92a39069185671bbbba7c7e/common/dynamicconfig/constants.go), [native activity completion checks](https://github.com/temporalio/temporal/blob/1f74f0c8e9935980d92a39069185671bbbba7c7e/service/history/api/respondactivitytaskcompleted/api.go).

Текущий итог: OD-19 выбор механизма принят по делегированию. G-104/106/111 не закрыты реализацией; реальный producer/WorkerRun не разрешён, требуются PoC/код/контракты/миграции/security evidence. Вопрос не возвращается владельцу как выбор между техническими библиотечными деталями; несовместимость с baseline или расширение полномочий потребует отдельного конкретного согласования.
