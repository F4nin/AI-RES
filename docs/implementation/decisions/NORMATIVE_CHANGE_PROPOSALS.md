# NORMATIVE_CHANGE_PROPOSALS — предложения по изменению нормативных документов

Статус по умолчанию — **PROPOSED**. Явные решения владельца действуют в объёме, указанном в соответствующих разделах. Для NCP-14 принят описанный scope внутреннего Platform API. Для NCP-16 принят вариант B. Для NCP-17 принят узкий допуск статуса по делегированию владельца. Остальные предложения остаются открытыми.

## NCP-19 — передача защищённой записи Outbox в Backend

**ACCEPTED по поручению владельца продолжить реализацию NCP-19 после
описания точного scope.** ADR-129 закрепляет полномочия в Backend и отделяет
роль доставки Outbox от доменной записи. В сетевом стенде эти части
связаны внутренним вызовом. Штатному запуску в отдельных процессах
нужен проверяемый переход между ними.

Принят приватный ar2-вызов от существующей identity
`OUTBOX_DISPATCHER` с отдельным audience и nonce. Диспетчер передаёт
только точные строку Outbox, владельца lease, номер попытки и поколение
replay. Namespace допускается конфигурацией identity. Backend читает
саму запись через узкую функцию по действующему lease, завершает чтение
и вызывает существующие защищённые Start либо Cancel. Ответ ограничен
исходом доставки. Run ID и тело события из внешнего запроса не принимаются.
Backend получает Run через native Start с уже утверждённой проверкой
исходной истории и фиксирует его после повторной проверки назначения.
Обычная fencing-проверка подтверждения Outbox сохраняется при позднем
ответе. Temporal auth-control остаётся отдельным metadata-only входом.

Роль Outbox сохраняет текущий SQL-допуск. Backend получает только
EXECUTE узкого чтения активного lease. Общий SELECT Outbox,
произвольная мутация назначения и передача API credentials
диспетчеру исключены. Scope закреплён в DOC-087 и DOC-068 v1.7.
Проверки охватывают неверный namespace и identity, отзыв, истёкший lease,
повторного signed request, потери ответа после Start и отсутствия
Temporal RPC в открытой DB-транзакции. Вариант с общим процессом и
двумя DB credentials расширил бы область компрометации диспетчера.

## NCP-18 — версия состояния Epic для Manager

**ACCEPTED по делегированию владельца, 2026-11-21.** DOC-002 §7 требует связывать существенное решение Manager с
версией состояния Epic. ADR-165 даёт Backend восстанавливаемую проекцию.
DOC-086 v0.4 закрывает shape, а Platform role по DOC-068 и миграции
0040 видит только назначенное взаимодействие и колонки текущей команды.

Выбрана отдельная версия private ответа для точных активных
назначения, Epic и Run. Backend формирует минимальный набор разрешённых
метаданных существующей проекции, фиксирует версию фактически переданного
снимка и связывает её с новым Proposal. Разрешены статус Epic и его
версия, статус назначенной Operation, отметка об открытом вопросе и
последовательность журнала, статус решения и номер версии Plan,
счётчики Task по статусам. Точное описание выдачи и минимальный SQL-допуск
фиксируются в DOC-086/DOC-068 до подключения. Передача истории ответов
по-прежнему требует отдельного доказательства Policy, ACL и классификации
по NCP-14. Прямой доступ Manager к PostgreSQL, исходникам и истории
других Epic не требуется.

Проверки должны подтвердить отказ для чужого или отозванного назначения,
ограниченный payload, отсутствие source text, сохранение v0.4 и повтор
записи Proposal с той же версией. [Решения владельца](../DECISIONS_PENDING.md#g02--s20--передача-версии-состояния-epic-в-manager).

### Редакции DOC-086 v0.5 и DOC-068 v1.6

После поручения продолжить подключение выпущены
[DOC-086 v0.5](../../architecture/AI_RES_Platform_Internal_API_v0.5.yaml)
и [DOC-068 v1.6](../../architecture/AI_RES_PostgreSQL_Migration_and_Access_Strategy_v1.6.md).
Registry и manifest v1.8 фиксируют редакцию дизайна.

DOC-086 v0.5 добавляет два приватных POST по путям
`/internal/v5/operations/{operationId}/manager-input` и `/manager-draft`
под тем же префиксом. Подпись ar2 привязана к точным пути, действию и
хешу тела. Вход чтения содержит `workflowId` и `workflowRunId`. Ответ с
`Cache-Control: no-store` содержит `operationId`, текущее назначенное
`message`, серверный UUID `contextVersionId` и закрытый объект `epicState`.
Его поля ограничены `epicVersion`, `epicStatus`, `operationVersion`,
`operationStatus`, `questionSequence`, `hasOpenQuestion`, `planVersion`,
`planDecision` и `taskCounts`. Значения статусов используют действующие
словари агрегатов, счётчики неотрицательны, поля отсутствующего плана
равны null. Запись использует прежние поля черновика и обязательный
`contextVersionId`. Manager получает контекст внутри Activity, а в
Workflow History сохраняются существующие компактные результаты.
Действующие маршруты v0.3 и v0.4 и их shape сохраняются.

DOC-068 v1.6 разрешает Platform API вызов фиксированной Backend-функции
формирования снимка и булевой проверки его ссылки. При формировании
проверяются tenant, действие, действующее назначение, точные Operation
и Workflow Run, стадия RUNNING и принадлежность Epic взаимодействию.
Миграция 0052 атомарно сохраняет первый снимок назначения и аудит выдачи.
Повтор того же Run возвращает сохранённую версию. Нужны неизменяемая
таблица с FORCE RLS, ограниченная проверка ссылки при записи Proposal
и INSERT только нового столбца ссылки в роли существующей команды
черновика. Ссылка проверяется на точность назначения и Run и участвует
в SHA-256 новой версии Proposal. После выдачи снимка попытка записать
черновик прежним маршрутом отклоняется; существующие записи и назначения
без выдачи сохраняют прежний путь. Manager Runtime сохраняет только
приватный ar2-доступ. Модель доступа к широким исходным таблицам и
допуск текста истории вопросов остаются за действующими правилами.

## NCP-17 — наблюдение G-107 после ACK

**ACCEPTED по делегированию владельца, 2026-11-20.** ADR-151 и миграция 0047
допускают Describe точного назначенного Manager Run до ACK. Для G-107 выбран отдельный
служебный допуск исключительно к статусу точного связанного Manager или
Plan Run, включая после ACK. Scope подтверждается по namespace, workflow ID,
Run ID, типу назначения, операции и проекту. Допуск не предоставляет History,
list, отмену, доступ к содержимому результата и изменение Operation.

Выбран отдельный ограниченный допуск в DOC-068 v1.5. Действие ADR-151
сохраняет исходный scope. Проверки
покроют чужой Run, namespace, назначение, роль, статусы до/после ACK, отзыв
и недоступность authorizer. До реализации сверки доменные эффекты должны
быть установлены отдельным доказательством. Терминальный Temporal status
и отсутствие Manager draft сами по себе такого доказательства не дают.

[Решение и границы](../DECISIONS_PENDING.md#g02--s20s21--наблюдение-g-107-после-ack).

| ID | Документ(ы) | Причина | Предлагаемое изменение | Альтернативы | Последствия | Затронутые тесты | Связанные ADR |
|---|---|---|---|---|---|---|---|
| NCP-17 | DOC-068, ADR-151, native auth-control | G-107 требует сверки точного Run после ACK | Изолированный допуск к статусу Manager/Plan Run | Сохранить текущий только Manager до ACK | Узкий дополнительный служебный доступ | Exact Run, tenant, workflow purpose, ACL, audit и отказ History | ADR-129, ADR-151 |
| NCP-01 | Implementation Spec v1.22 → v1.23 (DOC-041); Registry | §2 и исторические addenda ссылаются на устаревшие версии; порядок инкрементов содержит циклы C1–C8; нет этапов Auth/Policy, Rules, Requirements approvals, UI; operation_type/check_code registries — WORKING | Синхронизировать §2 с Registry v4.1; добавить addendum v1.23 с последовательностью S00–S39 (или ссылкой на неё) и правилом разделения Inc.5/7/8/20/22; зафиксировать начальный operation_type registry (ADR-013) и механизм check_code registry | Оставить Spec как есть (Addendum v1.22 уже даёт приоритет Registry) | Устраняет двусмысленность для будущих сессий | — | ADR-010, ADR-013 |
| NCP-02 | DDL v1.0 (DOC-065, WORKING); Physical Model v1.2 (DOC-064) | Нет DDL для `agents.worker_results`, `audit.audit_events`, `work.task_dependencies`; DDL предполагает brownfield; Roles SQL ссылается на отсутствующую таблицу | Выпустить DDL v1.1 по фактическим Alembic ревизиям S05–S06; описать greenfield-профиль и правило создания Operation для `createTask` (ADR-012) в DOC-064 §8 | Оставить DDL как design snapshot | Синхронизация design ↔ реализация | PERSIST-*, drift check | ADR-011, ADR-012, ADR-016 |
| NCP-03 | Persistence Blueprint v1.0 (DOC-072) §5, §6 | Цепочка PDB-0003/0008/0009 избыточна в greenfield | Добавить greenfield-вариант: создание `work.tasks` с конечными ограничениями, PDB-0008 = N/A | — | Нет | PERSIST-001 | ADR-011 |
| NCP-04 | Worker Contracts v1.1 (DOC-007, WORKING) | Нужен BASELINED контракт до VERIFIED S14/S23 | По итогам S14 — v1.2 с финальными полями и перевод в BASELINED | Оставить WORKING | Стабильность контракта | S14 4 точки валидации | ADR-021 |
| NCP-05 | AsyncAPI v1.6 (DOC-008) | `gateResultId` → `readinessEvaluationId` (DOC-055 §3.2) | Новая major версия Gate-событий | — | Consumers обновляются | Contract tests событий | ADR-023 |
| NCP-06 | Public API v1.3 (DOC-050, WORKING) | **Расширен по PREP review (ARC-1):** кроме auth нет endpoint/event для approve плана и требований, review/publish артефактов, Baseline/CR, impact, retrieval, connectors, decisions — перечень по этапам S07, S21, S26, S28–S31, S36 составляется до решения OD-09. Нет login/logout/MFA маршрутов (DOC-023); Task без `operationId`; нет approval-команд требований; 24 Spectral warning `operation-description` | v1.4: auth endpoints по DOC-023; additive `Task.operationId`; approval команды DOC-003; descriptions | Internal контракт вне OAS | Публичный контракт расширяется additive | schemathesis | ADR-012. **S07:** auth-маршруты (login, logout, csrf, password, MFA) уже спроектированы и реализованы в overlay `contracts/openapi/extensions/identity_auth.yaml` (WORKING, ADR-063); формализация в v1.4 остаётся за владельцем, статус NCP — PROPOSED |
| NCP-07 | Registry v4.1 → v4.2 | Отразить принятые NCP | Обновить версии/статусы | — | — | manifest SHA-256 | ADR-009 |
| NCP-08 | Public API v1.3 `createTask` (DOC-050), DOC-055 §2.5, DOC-064 TX-03 | `createTask` отвечает 201 без `operationId`; команда, создающая Operation, обязана отвечать 202+Location; Task вне PlanVersion даёт исполнение без одобренного плана | Зафиксировать: Task создаётся внутри активной Operation после включения в одобренный PlanVersion; additive `Task.operationId`; решить 201 vs 202 для proposal; политика rework после terminal Operation (новая Operation + `derived_from_task_id`) | Новая root Operation на каждый createTask (отозвано в ADR-012) | Контракт createTask; S21 | createTask вне Operation; rework после terminal | ADR-012, ADR-034 |
| NCP-12 | Authentication v1.1 §4 (rate limit) | Текст требует лимиты по account, source signal и глобальному порогу, но не говорит, отказывают ли ip/global | Уточнить: ip и global — сигнал и метрика, отказывают account и (account, ip) (ADR-071) | Жёсткие пороги при доверенном IP | Меньше риск DoS за прокси | Тесты throttle (режим сигнала) | ADR-071 (PROPOSED до решения владельца) |
| NCP-09 | Event Model v1.4 §4 (DOC-055) ↔ AsyncAPI v1.6 `OperationWorkerRunEventData` (DOC-008) | Event Model требует `data.eventType`; AsyncAPI не перечисляет его и запрещает лишние поля (`additionalProperties: false`) | Решить, где источник истины: либо убрать `eventType` из Event Model §4 (тип уже в CloudEvents `type`), либо добавить поле в AsyncAPI | Оставить расхождение | Contract tests событий, consumers | tests/contract/test_event_envelope.py | ADR-054 |
| NCP-10 | API Contracts v1.10 §Events (DOC-056) ↔ AsyncAPI v1.6 | API Contracts перечисляет `correlationid` и `traceparent` как атрибуты envelope; канонические сообщения AsyncAPI допускают только 9 атрибутов (`correlationId` — в `data`; `traceparent` не поддержан) | Привести API Contracts к AsyncAPI либо расширить AsyncAPI атрибутами `correlationid`/`traceparent` | Оставить | W3C Trace Context для событий (Observability) | tests/contract/test_event_envelope.py | ADR-054 |
| NCP-11 | State Machine v1.2 (`workerRunEventTypes`) ↔ AsyncAPI v1.6 | Тип `worker_run.created` есть в реестре State Machine, но канонического сообщения в AsyncAPI нет (36 моделей против 37 типов) | Добавить сообщение `com.aires.worker_run.created.v1` в AsyncAPI либо убрать тип из реестра | Оставить | Валидация события создания WorkerRun | `LISTED_BUT_NOT_MODELLED` в contract-тесте | ADR-054 |
| NCP-13 | Event Model v1.4 §15 ↔ AsyncAPI v1.6 | §15: consumers игнорируют неизвестные опциональные поля (аддитивное поле внутри major — non-breaking); AsyncAPI v1.6 закрывает каноническую схему (`additionalProperties:false`), и S10 отвергает такое событие как `SCHEMA_REJECTED` | Либо оговорить в Event Model, что для canonical envelope аддитивные поля требуют нового major, либо открыть `data.details` и `extensions` в AsyncAPI | Оставить как есть (текущее поведение S10) | Rolling-deploy без карантина при аддитивных полях | `test_contract_rejects_foreign_attributes…` | ADR-054, ADR-086, G-103 |
| NCP-14 | API Contracts v1.10 §7.2 / §9; Decision v1.6 §2.5 п.5 | §7.2 допускает внутренний Platform API, но не задаёт его контракт, аутентификацию вызывающих и capability; §2.5 п.5 ожидает QUEUED после подтверждённого scheduling, а у роли dispatcher нет записи в доменные таблицы (S11 ставит QUEUED→RUNNING первой Activity) | Включить контракт внутреннего Platform API (WORKING overlay `contracts/internal/…v0.1.yaml`) в нормативный пакет и уточнить, кто подтверждает QUEUED | Оставить overlay WORKING (текущее поведение S11) | Единый контракт Runtime↔Application Services; ясная семантика QUEUED | test_internal_platform_api (контракт↔маршруты) | ADR-088, ADR-089, G-109, G-110 |
| NCP-15 | Identity & Access v1.5 / PostgreSQL Migration & Access Strategy v1.1 (набор ролей); Infrastructure v1.7 §10.4 | Набор ролей БД BASELINED и не содержит роли для мониторинга; DOC-025 требует health/availability PostgreSQL, а серверные метрики (блокировки, соединения, размер) недоступны без учётных данных БД | Добавить роль `ai_res_monitor` (NOLOGIN-группа + login, `pg_monitor`, без доступа к доменным таблицам), отдельный секрет и сервис exporter'а в сетях `data` + `observability` | Оставить application-side метрики пула (текущее поведение S13); дать exporter'у существующую роль (расширение прав вне baseline) | Видимость PostgreSQL на сервере; новая учётная запись и поверхность атаки | runtime grants audit, `check_compose` (секреты), negative: роль не читает доменные таблицы | ADR-099, G-125 |
| NCP-16 | DOC-075 §3.2; DOC-076 §3/§7; DOC-078 §5; при выборе исключения — связанные API identity/schema, Registry и manifest | S16: immutable selection не подтверждён публичным API DeepSeek; rolling alias и fingerprint не закрепляют модель | Выбрать один из вариантов в разделе ниже; сейчас PROPOSED, baseline сохранён | A: получить provider evidence, сохранив baseline; B: точное исключение для Flash первого среза | B уменьшает гарантию воспроизводимости, требует явного owner/security решения и согласованного canonical update | Реальный identity/pinning test либо утверждённые drift/missing-metadata/reapproval tests; остальные S16 gates сохраняются | G-156; OD-01/OD-21; нового ACCEPTED ADR нет |

## NCP-16 — DeepSeek Flash и immutable model pinning

**ACCEPTED вариант B владельцем 2026-11-17; нормативная часть оформлена, runtime-реализация не выполнена.**

**NCP-16, решение владельца 2026-11-17: ACCEPTED вариант B только для DeepSeek Flash первого среза.** Нормативная развилка закрыта; DOC-075/076/078 v1.1 и manifest v1.3 фиксируют исключение. Управляемые версии AI RES неизменяемы; наблюдаемая provider identity отделена, drift блокирует результат и дальнейшие вызовы затронутого профиля до повторной человеческой приёмки. Скрытый drift/возврат прежней модели не гарантируются. Это документационное изменение: identity/admission/drift runtime NOT IMPLEMENTED/NOT VERIFIED, профиль/Bifrost не утверждены, платные вызовы не разрешены. G-156 сохраняет технические условия допуска; SLICE-01 и G02 не разблокированы автоматически. Доступ к кабинету DeepSeek есть, владелец может создать ключ в любой момент; значение ключа не получено/не подключено. Последующим прямым решением владельца установлен общий потолок 10 USD на технический прогон допуска Flash/Bifrost, включая retries/ошибки с возможным списанием. Это не целевой расход и не лимит на каждый запуск; SLICE-01 автоматически не включён. До вызовов подготовить минимальный план с актуальными тарифами/верхней оценкой и контролем остатка; ключ ещё не подключён. [ADR-128](ADR-128-flash-observed-identity-exception.md).

**История предложения до подтверждения владельца:** технический milestone S16 впоследствии закрыт прямым решением владельца (ADR-123); это не approval изменения гарантии. [Документальное evidence](../reviews/S16_MODEL_PINNING_POC.md), [отчёт](../increments/S16_bifrost_poc_provider_profile_REPORT.md). Решение о нормативном исключении — владелец/security owner лично. До решения действовали исходные DOC-075/076/078; теперь действуют их v1.1 с ограниченным исключением. Включение профиля по-прежнему BLOCKED до реализации admission/drift и остальных gates; технический S16 DONE. Переписка с поддержкой — возможный источник evidence варианта A, не обязательное условие закрытия этапа и не порученное внешнее действие.

Ожидается: alias для routing допустим, но evaluation/release используют immutable version, Run фиксирует фактическую identity. Наблюдается: публичная спецификация Chat API перечисляет aliases, changelog меняет модель за alias, fingerprint — metadata backend, не selector. Отсутствие публичного механизма не исключает частного endpoint/договора; такой механизм не продемонстрирован. Ни один платный запрос для этого вывода не выполнялся.

| Вариант | Конкретное действие и условие продолжения | Последствия |
|---|---|---|
| A — сохранить baseline | Получить от DeepSeek документацию/договорную гарантию вызова неизменяемого snapshot через endpoint/ID и провести минимальный реальный pinning test в разрешённом бюджете. Версия в профиле без такой гарантии не считается доказательством | Canonical гарантия сохраняется; возможность и срок неизвестны. До evidence профиль/приёмка заблокированы. Контакт с провайдером от имени владельца не разрешён автоматически |
| B — ограниченное исключение | Разрешить для первого среза только DeepSeek Flash через rolling alias с отдельной записью наблюдаемой identity; после явного решения согласованно обновить DOC-075 §3.2, DOC-076 §3/§7, DOC-078 §5, затронутые API identity/schema и Registry/manifest. В implementation ADR одного разрешения недостаточно | Прежнюю модель нельзя выбрать повторно; воспроизводимость прежнего запуска не гарантируется. Это ослабление BASELINED гарантии, а не реализация immutable pinning |

Принятые обязательные ограничения B (реализация/evidence ещё требуются):

- Отдельно хранить закреплённые версии профиля/config/prompt/tools и наблюдаемые provider/model metadata. Не записывать rolling alias или fingerprint как будто это immutable `pinned_model_version`; точные поля и совместимость спроектировать после решения.
- Фиксировать разрешённые request/response model IDs, fingerprint при наличии, время и provider request ref без prompts/payloads. Отсутствие или неизвестное значение обязательной identity metadata — отказ, а не выдуманная версия.
- Обнаруженный drift блокирует использование результата и последующие вызовы до новой оценки и человеческого утверждения профиля с аудитом. Первый вызов изменившейся модели уже мог быть обработан/оплачен: response-based detection не предотвращает его, не доказывает обнаружение всех смен весов и не восстанавливает старую модель.
- Никаких автоматических APPROVED, новых providers/fallback, self-grant, расширения данных/egress или бюджета. Pro остаётся CANDIDATE; лимит S16 10 USD и отдельная Bifrost/security приёмка сохраняются.
- Тесты: missing/unexpected model/fingerprint metadata, drift до передачи результата, блокировка дальнейших вызовов, отсутствие silent fallback, новая версия профиля/повторная приёмка, безопасные logs/traces/audit. Полная матрица DOC-076 §7, `pre-pr`, Linux CI и независимые review не отменяются.

Замена провайдера/локальная модель — отдельное решение при желании владельца, не часть принятого B. Local-model PoC не создаёт нового блокера первого среза (DOC-075 §3.1, DOC-076 §8 и решение Ollama-last). Решение владельца и canonical v1.1 разрешают только описанное исключение; запись NCP сама по себе не реализует enforcement и не включает профиль.

## OD-19 / NCP-14: технический выбор принят, нормативная синхронизация до реализации

Владелец делегировал технический выбор OD-19; ADR-129 принят Implementation Lead. Это не принятие целиком остальных PROPOSED NCP или QUEUED semantics. Перед grants/новым внутренним протоколом требуется согласованная role map (отдельная Platform API DB identity без broad api-group inheritance; auth-control identity Temporal без domain grants), versioned internal credential/API и применимые canonical/Registry annotations. В текущей задаче canonical, schema/wire и DB не менялись; права не расширены. Применение конкретного несовместимого нормативного изменения нельзя подменить ссылкой на общий ADR.

### Решение владельца 2026-11-18

Владелец подтвердил scoped обновление роли и защищённого контракта по ADR-129.
Нормативная фиксация — DOC-068 v1.2, DOC-084 v0.2, DOC-082 v1.4 и Registry §9.
Точный scope — отдельная Platform API роль, private TLS, привязанный ar2,
durable nonce и server-owned execution assignments. Развилка QUEUED сохраняется
в существующем scope NCP-14. Runtime принятие и G-107 требуют отдельного evidence.

### Дополнение владельца от 2026-11-18

Подтверждены чтение сообщения назначенного запуска, запись черновика и
создание задач из точного утверждённого плана. Нормативные границы
зафиксированы в DOC-068 v1.3, DOC-085 v0.3, DOC-082 v1.5 и Registry §10.
Утверждение выполняет уполномоченный человек, запуск Worker следует Gate.

### Предложение для адаптивного intake · 2026-11-19

**ACCEPTED владельцем 2026-11-19.** Process v1.9 §4–5 требует выбирать следующий вопрос с учётом
предыдущих ответов и `UNKNOWN`. DOC-085 v0.3 определяет закрытый ответ `ManagerInput`
из `operationId` и `message`. Изолированный журнал восстанавливает состояние Epic.
Его данные недоступны Manager по действующему ответу.

Владелец выбрал отдельную версию ответа `manager-input` для существующего ar2 action
с состоянием вопросов и ответов назначенного Epic. Backend получает Epic из
проверенного assignment, применяет действующие ACL и допустимую классификацию,
передаёт только необходимый контекст напрямую в Activity по private TLS.
Model Gateway остаётся
единственной точкой обращения к модели, в Temporal history и аудит идут refs
и metadata. Утверждённый scope закреплён в DOC-086 v0.4, DOC-068 v1.4 и manifest v1.6. Действующий v0.3 продолжает обслуживать прежних клиентов.

Альтернатива — оставить v0.3 и выполнять на сервере только контроль одного
активного вопроса и подавление уже известных тем. Этот вариант покрывает часть
инвариантов журнала, а следующий вопрос Manager выбирает без истории.

Проверки после согласования включают совпадение контрактов и handler, exact Run,
cross-Epic отказ, `UNKNOWN`, восстановление проекции и отсутствие текста в
Temporal history. Отдельная авторизованная human-команда ответа на вопрос
проектируется как WORKING overlay по ADR-009/038.
