# ADR-133 — Ограниченный durable ledger технического допуска Flash

**Дата:** 2026-11-17. **Статус:** ACCEPTED technical implementation scope; компонент локально TESTED; полная подготовка IN_PROGRESS/NOT VERIFIED. Основание — порученная подготовка G02, ADR128 и уже разрешённый общий потолок10USD; технический план8attempts в [Flash admission](../groups/G02_FLASH_ADMISSION.md). Это не новый продуктовый бюджет, не дополнительный кошелёк и не разрешение начать S17/S20/S21.

## Решение

Следующий отключённый срез — backend-owned ledger в существующей ai_res_db, forward0024 после0023. Переиспользовать UnitOfWork/SQLAlchemy/Alembic/canonical_json/Decimal/redaction; не подменять process-local InMemoryBudgetLedger новой несовместимой реализацией общего BudgetLedgerPort. Никакого generic release_unknown или runtime budget establishment.

Четыре технические таблицы: один immutable authorization account с фиксированным UNIQUE scope, reservations/once-only dispatch claims, append-only settlements и metadata-only security audit. Account связывает original authorization, общий USD cap≤10, max attempts≤8, exact Flash route, plan/tariff hashes/rates и верхние bounds текущего плана. Новый UUID/процесс/run не создаёт второй кошелёк. Runtime не создаёт account, не меняет cap/rates/plan и не снимает sticky block. Реальные accounts/tariffs/profiles/approval/grants не seed-ить.

Reserve под account lock рассчитывает полную верхнюю стоимость сервером, сохраняет request/case refs, exact outbound-body hash/limits и plan/tariff binding, увеличивает sequence под lock и коммитит audit. UNIQUE(account_id,body_sha256) действует на всю историю, чтобы replay старого payload не мог израсходовать новую reservation. Каждый будущий case/replacement получает отдельный synthetic marker внутри body. Claim того же ticket допускается только один раз и коммитится до разрешения transport. Потерянный ответ после commit не даёт повторного permission. Pending переживает restart и блокирует следующий dispatch; TTL/autoclear не вводятся.

Known usage оценивается по immutable серверному тарифу, не по переданной клиентом стоимости. Exact settlement replay не дублирует charge/audit; conflicting evidence отказывается. UNKNOWN удерживает полный reserve. Overrun сохраняет возможный расход, ставит sticky block и audit до controlled refusal. Malformed/untrustworthy usage не считается нулевым расходом: полный UNKNOWN hold и block. Audit/store failure не выдаёт permission/result и не освобождает старый pending. Owner-only reconciliation/refund неизвестного расхода в первый срез не входит.

Тарифная актуальность не определяется придуманным TTL. Foundation проверяет exact immutable hashes и finite Decimal rates; trusted host ещё обязан подтвердить действующие официальные тарифы перед live run/возобновлением. При изменении тарифа остановиться до контролируемого amendment без обнуления бюджета. Пока hostcheck/runner/egress enforcement отсутствуют, live calls запрещены.

## Authority и безопасность

ENABLE+FORCE RLS/default deny с transaction-local exact technical account context; узкие existing API column grants, без новых DB roles/exemptions/fake organization. GUC/ticket — не proof authorization и не bearer grant. Trusted authenticated host/sole-egress enforcement ещё нужны; ledger не утверждает модель и не заменяет human approval. DB writer/time задаются server defaults и не доступны runtime INSERT; session-dependent CHECK не вводить.

## Последовательность и границы

1. Код ledger/forward migration/real PG failure-concurrency-restart-upgrade-role tests, independent database/Python/security reviews; applied revisions frozen.
2. Затем отдельный candidate permit/runner и enforcement в единственном egress relay. Ledger только в runner недостаточен: прямой Bifrost/relay вызов не должен обходить reservation/onceclaim. Exact body hash должен соответствовать окончательным отправляемым bytes после Bifrost transformation. Выбор trust seam ещё требует технического исследования/PoC; решение здесь его не подменяет.
3. Затем сводные gates, безопасный key setup, live evidence и отдельные human exactvalues/Bifrost/profile approvals; SLICE01 со своими условиями; после готовности подготовки — уведомление владельца и ожидание нового согласия на G02.

Existing immutable product ModelProfile/factory/BifrostTransport и product budget architecture не меняются. Ключ, provider calls, delivery/release, actual profile enablement и G02 в этот срез не входят. Candidate PoC не требует фиктивного APPROVED профиля. Monthly WORKING budget/owner/classification values не изобретаются.

## Проверки и риски

Нужны реальные PG grants/RLS/context reset; unique original authorization, concurrent reserve/claim/cap/attempts, exact bindings, duplicate/conflicting settlement, unknown/overrun/audit failure, отдельный процесс/restart, immutable history/actor anti-forgery, previous/empty upgrade/drift и logical restore metadata. Main risk — неготовый egress enforcement: локально TESTED ledger не даёт разрешения на расходы. Полный G156 остаётся OPEN; final evidence будет записано отдельно, исторические PASS не переносятся.

## Фактический checkpoint

0024 `a75c0eb164d9` применён только в disposable PG и заморожен: SHA256 `8e1ae3e9bc2249d9eaf40f0b5522dfdb72e6b85d8da86b67361e9ae29ff56751`. Автор34PGcases, root40PGcases с отдельными процессами/logical restore, root6actual drift/upgrade/security cases и fast957passed; два final independent reviews APPROVE/open0. Commands/exits/limitations — [отчёт](../increments/G02_flash_paid_ledger_REPORT.md), [review](../reviews/G02_PAID_LEDGER_REVIEWS.md). Private TLS/relay/runner/key/live не реализованы, G02 не начата.
