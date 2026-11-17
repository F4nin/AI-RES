# ADR-126 — S18: декларативный язык, lifecycle правил и воспроизводимая оценка

| Поле | Значение |
|---|---|
| Статус | ACCEPTED — техническое решение в делегированном scope S18; итоговые verification/delivery gates ещё не установлены |
| Дата | 2026-11-17 |
| Ответственный | Implementation Lead (Codex `/root`); ограниченное авторство pure types/DSL и этого ADR распределено отдельно, интеграция и итоговые проверки — у основного исполнителя |
| Проблема и контекст | S06 содержит governance.rules/rule_versions, но не полный Registry/Engine и durable evaluation history. S18 должен обеспечить управляемый lifecycle, safe deterministic execution, иерархию и immutable evidence. При этом роли управления правилами, author/approver separation и фактический production-каталог не утверждены; эти бизнес-значения нельзя вывести из существующего project.read |
| Связанные требования | RULE-MVP-01..12; RULE-MVP-13 как basic validation/dry run; RULE-MVP-14 UI остаётся S36/post-MVP scope по исходным документам. IAM/ACL, human approval, no system override, audit, immutable versions; ADR-018/058 |
| Документы и разделы | [Промпт S18](../increments/prompts/S18_rules_registry_rules_engine.md) §5–6/9/13; Architecture Concept v4.6 §14–15 и current addenda; MVP Capability Matrix v3.3 v0.7/v0.8, UX-TRC-15; Traceability Dependencies Impact Analysis v1.0 §7.3; IAM v1.5 §2/7/8; Registry v4.1 §2; [CHARTER](../IMPLEMENTATION_CHARTER.md); [OD-14](../DECISIONS_PENDING.md) |
| Альтернативы | Произвольный Python/eval или файловая/сетевая логика правила — запрещены. Объединение Rules Engine с Policy Engine смешивает обязанности. Назначение Analyst/Admin новых grants, blanket self-approval policy или выдуманный системный каталог выходят за технический scope. Только текущие строки правил без immutable evaluation snapshots не дают исторического replay. Автопубликация после validation подменяет человеческое approval |
| Решение | Ограниченный typed JSON AST и immutable snapshots; Registry и чистый Engine отделены от Policy. Существующие статусы S06 сохраняются, approval и публикация разнесены. Registry сам выбирает полный applicable approved набор. Current live evaluation строит факты из авторизованного S19 context и серверного времени; результаты/входы/правила/исключения сохраняются неизменно с обязательным audit. Lifecycle authority остаётся отдельным fail-closed integration binding. Подробности ниже |
| Обоснование | Механизм можно реализовать и проверить на реальном PostgreSQL без активации новых бизнес-правил. Строгие границы сохраняют полномочия человека и позволяют последующим callers подключить capability только после согласования точных permissions и правил |
| Влияние на компоненты/контракты | `modules/rules` — types/language/engine/validation/registry/repository; internal application composition и trusted fact provider; forward Alembic revision, schema snapshot, import boundaries и tests. Naming `modules/rules` уточняет технический package path из ADR-018 (`ai_res.rules.*`), сохраняя отдельные логические Registry/Engine interfaces. Public routes/OpenAPI/AsyncAPI и production grants не расширяются |
| Миграции и совместимость | Только новая expand-ревизия после S19: persistent version counter и immutable validation/control/exception/evaluation records с tenant FKs/RLS и минимальными grants. Existing revisions не менять. Legacy version counter инициализируется из существующих данных один раз в migration; runtime выдаёт номер под lock/CAS. Проверить empty/previous upgrade, schema drift, RLS/grants и прежние S06 данные; destructive downgrade/reset не вводить |
| Риски и компромиссы | Safe AST не доказывает полноту семантического обнаружения конфликтов; неоднозначность отмечается явно. Production lifecycle/catalogue/fact-provider admission и pool pressure требуют проверки при реальном подключении. History replay не разрешает новую операцию. OD-14 сохраняется, его значение этим ADR не выбирается. Наличие механизма или fixture approval не означает допуск production-правил |
| Затронутые тесты | Types/DSL и deterministic engine/validation unit tests; PostgreSQL Registry/lifecycle/evaluation/exception/authorization tests; migration/drift/grants/RLS; architecture/import boundaries; redaction/audit atomicity/concurrency; full pre-pr и обязательный Linux CI точного SHA. Результаты фиксируются в stage report, не предполагаются этим ADR |

## 1. Язык и типы

`schemaVersion = "1.0"`; JSON definition содержит только `condition` и `effects`. Conditions: `eq/ne/lt/le/gt/ge`, `all/any/not`, `exists`. Поля — flat trusted FactSchema, не Python paths/attributes. Operators, поля, operand types и ключи закрыты; unknown/missing/extra fields и неподдерживаемая версия отвергаются. Логические условия непустые, `not` имеет ровно одного потомка. Нет eval, кода, imports, callbacks, regex execution, сети или доступа к файловой системе.

`MAX_DEPTH = 16`, `MAX_NODES = 256` — технические пределы безопасного разбора/обхода дерева, не бизнес-пороги, SLO или budget разрешённой операции. Они применяются к AST, включая прямое создание typed Conditions. Сложность не повышается автоматически из содержимого правила.

FactType: `BOOL`, `INT`, `NUMBER`, `CODE`. Bool не становится числом; NUMBER конечен, NaN/Infinity запрещены; CODE — bounded machine code, не свободный текст. Tuple-pairs имеют уникальные имена и canonical order. Frozen/slots types и detached serializers исключают мутацию через вложенный словарь/список. FactSnapshot фиксирует ID/version, context ID/hash, provider/schema versions и safe scalar values; значение False/0 отличается от отсутствующего факта.

Effects: `REQUIRE`, `FORBID`, `ESCALATE` с bounded target code; `MINIMUM_IMPACT` с ImpactClass; `ALLOW_EXCEPTION` с точным rule key. Нет effect, предоставляющего доступ или изменяющего grants. ALLOW_EXCEPTION — только предметное разрешение рассмотреть ограниченное исключение, а не самостоятельная активация исключения или permission на инструмент.

Canonical impact order: **I0_NO_IMPACT → I1_LOCAL → I2_DEPENDENT → I3_BROAD → I4_CRITICAL**. Короткие I0–I4 нормализуются к этим значениям. Источник — Traceability §7.3 и MVP UX-TRC-15; это категории влияния, не risk likelihood/confidence. Строка `.claude/rules/testing-and-verification.md` «Critical impact category I0» устарела и расходится с canonical шкалой. По установленной иерархии источников используется I4_CRITICAL; `.claude/` и canonical документы в S18 не редактируются.

RuleSnapshot содержит exact rule/version IDs, version number/key, level/tenant/object-type/operation applicability, immutable definition, автора, status/approval/validity и текущий suspension state. Semantic content hash не зависит от mutable lifecycle approval/status/control; полный snapshot serializer сохраняет и эти факты. Definition hash позволяет обнаруживать дубликаты отдельно от identity hash. Validation basis fingerprint включает complete snapshot state и FactSchema: retire/suspend/approval изменения не маскируются неизменным content hash.

## 2. Registry и lifecycle

Сохраняется существующий словарь `DRAFT → PROPOSED → APPROVED/REJECTED`, `APPROVED → RETIRED` и разрешённые S06 переходы. Validation — отдельный report, а не approval. Scheduled и Active — derived состояния по exact approval facts и интервалу действия, а не обход DB status guard. DRAFT/PROPOSED/REJECTED/RETIRED не участвуют в новой live evaluation.

Human approval facts могут быть зафиксированы на PROPOSED version до отдельной публикации. Переход в APPROVED — отдельный контролируемый шаг после проверки свежего validation basis. Это позволяет атомарно завершить прежнюю APPROVED version и опубликовать новую, сохраняя existing one-approved partial index и не создавая окно с отсутствующим правилом. Validity и approved_at проверяются относительно времени оценки; future approval не применяется задним числом.

Счётчик версии принадлежит rule identity. Новая версия получает номер под row lock/CAS; runtime `MAX()+1` не используется. Миграция может один раз инициализировать counter максимальным существующим номером, не превращая это в механизм дальнейшей выдачи. Approval/publication сериализуются с изменением относящегося к ним validation basis; stale report или изменение competing applicable rules требуют новой проверки.

Suspension/resume оформляются append-only control records и аудируются; rule content не переписывается. RETIRED окончателен для данной version, reactivation не обходит новый lifecycle. Записи controls/approval/history не заменяют проверки actor полномочий.

Перед публикацией выполняются schema/type/reference checks, обнаружение exact и structural near duplicates, detectable conflicts/hierarchy weakening, контрольные примеры/dry run. Автоматическая проверка не гарантирует semantic completeness и не утверждает правило. Потенциальные конфликты, которые нельзя доказать/разрешить детерминированно, явно возвращаются для человеческого review; они не превращаются в молчаливое разрешение.

## 3. Полномочия и production binding

Registry управляет версиями, Engine вычисляет предметные обязательства, Policy независимо разрешает фактические действия. Внутренний метод не является новым public endpoint. Existing project/source/context read checks позволяют читать входы для derived оценки, но не создают права approve/publish/retire/exception. Неизвестные lifecycle actions в packaged Policy остаются DENY.

Управляющий application boundary требует актуальную human session, server-side Policy decision для точной операции и exact rule/exception version/hash. User ID, approver ID и boolean «authorized» из входного payload не служат полномочием. Manager/Worker могут инициировать предложение только через разрешённый upstream контракт; самостоятельно approve/publish/activate они не могут. До согласования такого binding production путь не активируется.

Роли администраторов и author/approver separation не изобретаются. IAM §8 связывает запрет self-approval с настроенными классами действий, OD-14 сохраняет открытое решение для правил. Значение separation policy `None` означает отсутствие необходимого решения и deny activation; это не выбор универсального «самоутверждение разрешено» или «всегда запрещено». При explicit configured separation enforced result должен соответствовать точному scope Policy; default allow отсутствует.

PostgreSQL acceptance может использовать ограниченную fixture configuration **настоящего PolicyEngine** и реальных human principals, показывая положительные и отрицательные механизмы. AllowAll и успешный mock не доказывают authorization. Fixture grants не попадают в packaged config и не утверждают production authority.

Аналогично S19/G-157, будущая вызывающая команда должна отдельно авторизовать собственное domain action. `pass`/historical replay от Rules Engine не является grant или approval для вызывающей команды. Перед production caller проверяются service/transport binding, свежесть permissions/facts, concurrency и pool-pressure/saturation; отсутствие такого caller не маскируется как выполненная runtime интеграция.

## 4. Current facts, engine и immutable evidence

Current fact provider в этом срезе получает **авторизованный точный S19 ContextPackageVersion** и выдаёт только технические metadata facts: `context_item_count: INT`, `context_has_source`, `context_has_artifact`, `context_has_requirement: BOOL`. Их значения выводятся сервером из sealed manifest. User assertions, исходный текст документов, prompts, secrets и raw storage locations в facts не включаются. Новый fact provider/field catalogue требует собственного trusted binding и checks; этот ADR не придумывает содержательные бизнес-факты или активные правила.

Current evaluation выбирает серверное live time; клиент не может backdate её для использования expired rule/exception. Чистый Engine получает explicit time вместе с exact fact/rule/exception snapshots и поэтому воспроизводим. Registry выбирает полный applicable approved набор по всем уровням; caller не выбирает удобный subset. DRAFT definition не разбирается как live rule и не влияет на новую оценку. Отсутствие правил/необходимых данных не означает автоматического разрешения критичной операции.

Missing comparison fact даёт UNKNOWN, а не False/pass; `exists` отдельно проверяет наличие. Иерархия не является «последняя запись выигрывает»: совместимые обязанности объединяются, минимум impact может повышаться, обязательство/запрет нижнего уровня не отменяет системное. Несовместимые REQUIRE/FORBID фиксируются как conflict; не выбирается молча менее строгое последствие.

Structured result сохраняет evaluation ID/time, input fact/context versions/hashes, considered/applied rule refs, matched conditions/evidence, conflicts/missing data, обязательства/ограничения/эскалации, minimum impact class и один из canonical statuses: `pass`, `pass_with_obligations`, `blocked`, `conflict`, `insufficient_data`. Result не содержит скрытого reasoning или автоматического business approval.

Persistent evaluation хранит immutable snapshots фактов, полного ruleset, exceptions, engine/schema versions, result/hash, инициатора и optional previous evaluation link. Изменение действующего правила не переписывает старый результат. Historical replay работает по сохранённым snapshots/time и явно не является текущим разрешением. Новая оценка — новая запись; retry — existing idempotency semantics.

## 5. Исключения

RuleException фиксирует exact target version/content hash/effect hash, permission-rule version, **точный EvaluationScope**, human approval, finite `[valid_from, valid_to)`, reason code, risk refs и compensation refs; revoke сохраняется как явный lifecycle факт. Истечение и отзыв не удаляют историю, но исключают применение в последующих live evaluations.

Исключение применяется только если target rule/effect соответствует сохранённым hashes, scope совпадает, human approval действительно, интервал открыт, нет отзыва и **активное сработавшее вышестоящее** правило содержит ALLOW_EXCEPTION для exact target key. Lower/same-level permission, expired/nonmatching permission, другая версия/hash или недостаточные данные не создают waiver. Target SYSTEM не переопределяется никогда; независимые системные ограничения сохраняются даже при разрешённом исключении к нижнему правилу.

Отсутствие production permission-rule catalogue означает отсутствие автоматически доступных исключений. Конкретные правила и human authority не создаются миграцией или этим ADR; примеры живут только в tests.

## 6. Persistence, audit и gates

Новые tenant records защищаются ENABLE/FORCE RLS, composite tenant FKs, append-only/no-truncate и минимальными runtime grants. Immutable evaluation + mandatory audit + idempotency completion записываются одной UoW. Отказ audit откатывает бизнес-запись; remote HTTP/LLM/Temporal и human wait в DB transaction отсутствуют. Access к сохранённому результату повторно авторизуется; historical manifest не заменяет текущую ACL.

OTel export содержит только allowlisted технические признаки; metric labels не получают domain IDs/произвольные targets. Audit связывает initiator/correlation/evaluation/version refs и безопасный результат; исходный контент не экспортируется. Telemetry failure не обходит mandatory audit. Новый domain event без canonical AsyncAPI контракта не придумывается, как в rationale ADR-079/082.

S18 acceptance обязан доказать четыре обязательных cases: нижний уровень не ослабляет системный, DRAFT не применяется, expired exception не действует, одинаковые exact inputs/time дают воспроизводимый результат. Дополнительно нужны lifecycle authority negatives, missing/unknown/invalid DSL, cross-tenant isolation, stale validation basis, concurrent version/publication, immutable history/replay, exception hierarchy/expiry/hash binding, audit rollback и migration coverage. Independent blind-first reviews, full `make pre-pr` и Linux CI точного SHA сохраняются. Этот ADR фиксирует выбор; он не объявляет ни один из ещё не выполненных gates успешным.
