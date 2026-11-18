# OD-19 — решение по защите Runtime и Platform API: отчёт

**Дата:** 2026-11-17. **Статус:** ACCEPTED design по делегированию владельца; protocol PoC и implementation NOT VERIFIED. Scope — решение и план, без запуска продуктового этапа.

## 1. Результат

[ADR-129](../decisions/ADR-129-runtime-transport-and-authority.md) выбирает механизм с учётом существующих узлов: один Temporal namespace, две очереди, Activity-only Worker, mTLS и native authorizer с task-issuance receipts. Platform API сохраняет Ed25519 основу и получает private TLS, request binding, отдельный audience, nonce protection и server-owned assignments. Полномочия модели не расширяются.

## 2. Нормативная база

Registry §2, DOC-006 §7.2/9, IAM/Security/Auth и persistence/Operation инварианты. Выбор OD-19 делегирован владельцем. Синхронизация конкретной role map/internal contract необходима до реализации; общий ADR её не подменяет. Canonical/manifest в задаче OD-19 не менялись; предшествующая NCP-16 редакция сохранена.

## 3. Файлы

Новые ADR-129, этот отчёт и протокол review. Обновлены ADL, DECISIONS_PENDING, HANDOFF, STATUS, GAPS, ECC, contract traceability и NCP-14 annotation. Предшествующий diff NCP-16 не сброшен и не переоткрыт.

## 4. API / контракты

Wire/schema/handler изменений нет. Versioned internal credential/API и auth-control seam проектируются до handlers. ar1/текущие consumers не меняются молча; public API и compatibility baseline прежние.

## 5. Миграции и данные

Не выполнялись. Планируются forward migrations для security receipts, assignments и узкой Platform API DB role с согласованными provisioning/RLS/normative bindings. Manager/Worker и Temporal auth extension не получают domain DB credentials.

## 6. Решения

ADR-129 ACCEPTED Implementation Lead по прямому owner delegation. Отвергнуты shared Writer, новые namespaces и MAC-wrapper. HTTP nonce одноразовый; Temporal task-issuance receipt проверяется повторно для корректных RPC retries.

## 7. Gaps и условия реализации

OD-19 больше не ждёт выбора технического механизма владельцем. G-104/106/111 остаются OPEN по PoC/реализации. G-107 reconciler и allowlist обязательны до первого producer. G-110/G-126/SLICE/model approval/budget и другие вопросы не закрываются этим ADR.

## 8. ECC

Root: прочитанные architect/doc-updater/verification-loop checklists. Отдельные g02_dependencies — planner/architect по существующим узлам; od19_temporal_feasibility — pinned primary sources; ncp16_security_review — независимый blind-first security/architecture review до отчёта автора. Native Claude commands/hooks не запускались.

## 9. Проверки

База db8d4af34b0933aa2562adcf072b717eb0e3e3e9 плюс предшествующий NCP-16 diff и текущие OD-19 документы. Среда: Darwin arm64, Python3.13.5.

| Проверка | Команда / метод | Результат |
|---|---|---|
| Prompts | python3 -B docs/implementation/tools/check_prompts.py | exit0;40prompts/0issues |
| Secrets | python3 -B infra/scripts/scan_secrets.py | exit0;0findings |
| Format | git diff --check | exit0 |
| Canonical/manifest/ссылки/scope | read-only inline Python3, финальная проверка совокупного diff | exit0;74canonical/73hashes0mismatch,147local links/0missing;29files docs+manifest-pointer only |
| Независимое review | Отдельный read-only reviewer, initial и delta | APPROVE;2MEDIUM исправлены, открытых0 |

Прежний contracts suite22passed относится к проверке NCP-16. OD-19 не меняет contract files; повторный запуск не заявляется.

## 10. Security cases

Документально проверены: service identity не заменяет authority; exact dispatch/purpose/Run binding; server authorization вложенных Commands; запрет Worker Workflow RPC; registration-before-delivery; replay/restart fail-closed; отсутствие Temporal RPC в auth-control; audit без выдуманного tenant. Runtime cases не запускались. Полная матрица обязательна по ADR §6 перед допуском.

## 11. Независимое review

[Протокол](../reviews/OD19_RUNTIME_AUTH_REVIEW.md). Два MEDIUM исправлены: вложенные Commands и server-side Start intent check. Final APPROVE, открытых CRITICAL/HIGH/MEDIUM/LOW0. Автор не подменял независимое review самопроверкой.

## 12. Не выполненные проверки

Code/build/container/DB/Temporal PoC/runtime/private-key/paid-call проверки, полный pre-pr и новый Linux CI не запускались: scope — решение и план, продуктовый Sxx не реализуется и не повышается до VERIFIED. API seams в источниках не являются runtime evidence. Требуются реальные server/SDK, replicas/restart/failure tests.

## 13. Контекст

ADL/решения/STATUS/HANDOFF/GAPS/ECC/NCP annotation обновлены с сохранением технических gates. Canonical по OD-19 не менялись. Ветка общая с ещё локальным NCP-16 diff; commit/push/PR в этом обсуждении не выполнялись.

## 14. DoD

Документационные проверки/review выполнены. Runtime/migration/product delivery gates неприменимы к самой записи решения и сохраняются перед включением. Наличие ADR не доказывает защиту работающей системы.

## 15. Следующий безопасный шаг

Реализация по отдельному поручению в рамках G02/существующих предпосылок: ограниченный protocol PoC, затем contracts/TLS/authority/persistence и независимое review. До реального Start producer нужны OD-19 enforcement и G-107; до WorkerRun — Gate/grants. Выбор технических деталей делегирован; конкретный incompatible baseline diff или новые бизнес-права потребуют отдельного решения.

Финальный checkpoint: все указанные deterministic команды exit0, prompts40/0, secrets0, diffcheck0; совокупный diff29files включает ранее проверенный NCP16 scope. Новый OD19 source/config/runtime diff отсутствует. Initial и delta review ADR129 — APPROVE после исправления2MEDIUM.
