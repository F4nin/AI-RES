# ADR-125 — S19: immutable manifest явных version refs и внутренний ContextApplicationService

| Поле | Значение |
|---|---|
| Статус | ACCEPTED — техническое решение в делегированном scope S19; реализация и verification ещё выполняются |
| Дата | 2026-11-17 |
| Ответственный | Implementation Lead (Codex `/root`), по IMPLEMENTATION_CHARTER; документ подготовлен ограниченным заданием, интеграцию обеспечивает основной исполнитель |
| Проблема и контекст | S06 создал context package/version/items с exact FKs, append-only и digest, но application builder и сохранённого versioned manifest нет. S19 требует воспроизводимый immutable пакет из явных Requirement/Source/Artifact version refs с ACL до включения. Retrieval/ranking и text materialization относятся к последующим этапам. |
| Связанные требования | PROC-MVP immutable context; DATA-MVP-011; Context Builder criteria DOC-009 v0.4, в пределах минимального среза S19; ACL-before-context, provenance, fail-closed, audit; ADR-058 |
| Документы и разделы | [Промпт S19](../increments/prompts/S19_context_package_versioning.md) §5–6/9/13; DOC-077 §5; DOC-010 §9; DOC-005 §11.3; DOC-009 v0.4; DOC-006 §7.3 (ContextApplicationService); DOC-068 и DOC-072; canonical paths — Registry v4.1 §2; [CHARTER](../IMPLEMENTATION_CHARTER.md) §1/5 |
| Альтернативы | Только hash без сохранённого manifest не фиксирует builder/schema и затрудняет независимое восстановление; полный text snapshot потребовал бы extraction/materialization/secret handling вне минимального S19; прямые cross-module SQL reads нарушают владение доменными данными; новый public endpoint/event без canonical контракта недопустим; `MAX()+1`, mutable aliases и доверие caller-provided checksum/provenance исключены |
| Решение | Versioned ref-only manifest и строгие immutable types; module-owned metadata readers через injected ports; internal service с существующими read-policy checks и актуальной reauthorization; атомарные package/version/items/audit/idempotency; compatible expand manifest и истинное transaction sealing новой revision. Подробности ниже |
| Обоснование | Exact refs и server-resolved metadata дают воспроизводимый provenance без копирования исходных документов. Внутренний derived read snapshot не создаёт пользовательскую команду или новый grant. Domain metadata остаются у владельцев; технический формат выбирается в разрешённом scope промпта, canonical baseline не меняется |
| Влияние на компоненты и контракты | Новый `modules/context`; metadata readers requirements/sources/artifacts и typed ports; migration 0018/snapshot; exhaustive import contracts; unit/PostgreSQL/security/architecture tests и implementation traceability. Public OpenAPI/AsyncAPI, grants и Runtime DB boundary сохраняются |
| Миграции и совместимость | Только новая Alembic expand-ревизия: nullable JSONB manifest для legacy rows; старые immutable versions не backfill/overwrite. Новый сервис отклоняет retrieve без полного поддерживаемого manifest. Guard items проверяет creating transaction вместо равенства timestamps. Проверить empty/previous upgrade, drift, grants/RLS и existing tests; destructive downgrade не вводить |
| Риски и компромиссы | Ref-only package не доказывает parsing, безопасность исходных bytes, полноту контекста Worker или readiness; production source materialization и per-Run grants ещё отсутствуют. Legacy NULL явно недоступен через новый supported-manifest путь. Необходимо проверить конкурентный revoke, pool pressure из-за локального PolicyEngine и истинность seal под runtime role. Результаты проверки не предполагаются этим ADR |
| Затронутые тесты | `test_context_manifest.py`; tests module-owned readers; context PostgreSQL service/repository/security suites; migration empty/previous/drift/grants/RLS; архитектурные import tests; полный pre-pr и Linux CI по точному SHA |

## Формат и content identity

Manifest `schemaVersion = "1.0"`, `builderVersion = "explicit-refs-v1"` содержит `organizationId`, `projectId`, `items`. Каждый item содержит только `kind`, `versionId`, `objectId`, `versionNumber`, `contentDigest`; виды — `REQUIREMENT_VERSION`, `SOURCE_VERSION`, `ARTIFACT_VERSION`. Rule refs и произвольные поля не вводятся этим срезом.

`ContextRef`, `ResolvedRef`, `ContextManifest` — frozen/slots values. UUID типизированы, version number — положительный integer без bool coercion, digest — 64 hex с canonical lowercase. Набор непустой; exact `(kind, versionId)` уникален. Items сортируются по kind/versionId; JSON — UTF-8, sorted keys, compact separators, `allow_nan=False`. SHA-256 этого manifest образует content hash. Random package/version IDs, timestamps и текущее lifecycle-состояние источников не входят в содержимое manifest. Organization/project входят в hash: идентичные refs не переносят пакет между scopes.

`from_dict` отклоняет неподдерживаемую schema/builder version, missing/extra fields, неизвестные виды, невалидные refs/digests и arbitrary text/locator/provenance. `to_dict` возвращает отделённую mutable копию, не ссылку на immutable value.

## Владение metadata и авторизация

Вход сервиса — только exact refs и server-authenticated actor. Object ID, version number и digest получают module-owned readers под transaction-local tenant context; caller не сообщает доказательства ACL, provenance или целостности. Source/Artifact используют сохранённый checksum immutable версии; Requirement — canonical hash неизменяемых semantic fields, без mutable lifecycle. Межмодульные зависимости передаются через typed ports; context не получает прямой доступ к peer ORM/repository или unrestricted SQL других доменов.

`ContextApplicationService` остаётся внутренним приложенческим интерфейсом: нет browser route, новой матрицы ролей, service grant, Worker/Manager DB credential или фактического Runtime Run. Существующие `project.read` и соответствующие `requirement.read`/`source.read`/`artifact.read` проверяются для точных объектов до включения. Ref-only snapshot — производное представление уже разрешённого чтения, не новый бизнес-grant. Missing и inaccessible refs дают одинаковый controlled отказ; частичный успешный пакет не сохраняется.

Предварительная policy-проверка выполняется без caller DB transaction; окончательная локальная revalidation — непосредственно перед записью под authority locks, блокирующими concurrent revoke/update до commit. Проверяются текущие session/user/membership/MFA facts, не stale hints DTO. При retrieve и idempotency replay повторяются текущая ACL и exact metadata/integrity checks. Исторический ALLOW не заменяет новый доступ. Remote HTTP/LLM/Temporal calls внутри DB transaction не вводятся. S19 покрывает same-key/CAS/revoke concurrency. Pool-pressure/saturation не измерялась и остаётся обязательной проверкой перед будущим production caller/transport по G157; она не объявляется PASS S19.

## Атомарность, migration и наблюдаемость

Package version number выделяется под lock/CAS. Package pointer, immutable version, все items, mandatory audit и idempotency result записываются одной UoW; ошибка любого обязательного шага откатывает сборку. Existing IdempotencyService сохраняет HMAC/key reuse/replay semantics; retry не создаёт новый пакет, reauthorization перед replay остаётся обязательной.

Сохранённый manifest nullable только для совместимости старых строк. Новые сервисные версии всегда содержат полный manifest; retrieve legacy NULL или повреждённого/неподдерживаемого manifest fail-closed. Новая forward revision 0018 заменяет time-based item seal проверкой transaction identity, не переписывая предыдущие revisions и не изменяя исходные версии.

Сборка/rebuild аудируется атомарно: actor/correlation, package/version refs, builder/result и content hash; исходные документы, credential values, raw storage locations и prompts в audit/telemetry не копируются. OTel spans не экспортируют exception payload; metric labels ограничены фиксированными operation/outcome. Telemetry outage не обходит обязательный audit.

Нового ContextBuilt domain event в canonical AsyncAPI нет. В согласии с rationale ADR-079/ADR-082 используется mandatory audit; выдуманный event/outbox payload не добавляется. Это не исключение из атомарности существующих контрактных событий и не разрешение будущим этапам пропускать их.

## Границы evidence

ACCEPTED относится к техническому выбору, не к выполнению DoD. Статус реализации, результаты tests/migrations/reviews/pre-pr/Linux CI и фактический SHA фиксируются отдельно в stage report и [паспорте G01](../groups/G01_WORK.md). S19 не завершает полный Context Builder, Gate, per-Run authorization, retrieval, model quality или product/security acceptance; последующие этапы сохраняют свои зависимости и approvals.


## Уточнение реализации transaction seal и интеграции

`creation_transaction_id xid8` nullable для legacy и заполняется только server BEFORE INSERT stamp `pg_current_xact_id()`. В отличие от `xmin`, top-level xid8 корректно работает при SAVEPOINT/subtransactions; в отличие от `created_at=now()` не зависит от timestamps. Старым строкам не приписывается выдуманная creating transaction, они sealed. Metadata-хэш Requirement не включает mutable status/approval lifecycle. Builder остаётся trusted internal helper; его будущая вызывающая команда обязана независимо авторизовать собственное действие, read grants здесь определяют только inclusion/read derived metadata (G157). Новых production grant bindings/route/Runtime caller нет.
