# G02 — подготовка допуска Flash: checkpoint

## Текущий checkpoint ADR131 — выбор состава реализован (контракт0.2)

**Основание:** владелец делегировал ранее заданный выбор обязательного fingerprint и поручил реализовать. Implementation Lead выбрал VALUE как обязательный для Flash expectation: это сохраняет доступный сигнал drift в контролируемой инженерии требований. Candidate observation хранит ABSENT/NULL/VALUE как факты. Неполная metadata не становится допустимым baseline; fingerprint не pin/grant/approval. Точные live values/evidence и profile/Bifrost human approvals остаются до включения. Прежний вопрос о выборе состава CLOSED по делегированию, повторного подтверждения не требуется. [ADR131](../decisions/ADR-131-flash-required-fingerprint.md).

**Статус:** это решение IMPLEMENTED и локально TESTED в отключённом validator. Полный G156/G02 **IMPLEMENTATION NOT VERIFIED**, S17/S20/S21 NOT_STARTED. Ниже этого checkpoint сохранены исторические сведения0.1; их PENDING/старые hashes/counts не являются текущим состоянием.

**Scope:** изменены `observed_identity.py` (active0.2 + обязательный expected VALUE) и его behavioral tests; создан `contracts/internal/llm-observed-identity.v0.2.schema.json`. Исходная schema0.1 сохранена byte-identical, активный parser отказывается её принимать. Это несовместимая ревизия неопубликованного WORKING internal контракта; productconsumers/persistedrecords отсутствуют, silent conversion и legacy admission route нет. Public API/Worker/events/mirror/baseline/DB/migrations/grants/secrets/Runtime не меняются. Новый ADR131, текущие HANDOFF/STATUS/passport/plan/DECISIONS_PENDING, ADL/ECC и обе traceability/gaps отражают делегированный выбор, с сохранением предыдущей истории. Canonical/Registry не редактировались.

**Git/среда:** прежние `feat/g02-manager-tools-planning`, HEAD`db8d4af34b0933aa2562adcf072b717eb0e3e3e9` плюс текущий diff; Darwin arm64/Python3.13.5/uv0.11.31. На старте38локальных файлов, их scope сохранён; точная hash-проверка в финальном evidence ниже. Commit/push/PR/merge не выполнялись: общий результат группы ещё не готов, исходный чужой diff не доставляется автоматически.

| Проверка | Точная команда | Результат дельты0.2 |
|---|---|---|
| TDD RED до code change | В backend: `.venv/bin/python -m pytest -q tests/unit/test_llm_observed_identity.py -k 'expected_flash_identity_requires or new_fingerprint_requirement or pre_decision_evidence'` | exit1;5failed/108deselected: old code принимал ABSENT/NULL expectations/0.1 и эмитил0.1 |
| TDD GREEN | В backend: `.venv/bin/python -m pytest -q tests/unit/test_llm_observed_identity.py` | exit0;121passed/0failed/skipped |
| G1/G2 regression | `make pre-push-fast` | exit0;ruff0,mypy174files0issues,15importcontractsKEPT/0broken,957passed/4warnings/0failed/skipped |
| G4 mirrors/compatibility | `make contracts-check contracts-test` | exit0;6/6checks,22passed; новая internal0.2 дополнительно явно покрыта backend tests |
| G5/G8 docs | `python3 -B docs/implementation/tools/check_prompts.py`; `python3 -B infra/scripts/scan_secrets.py`; `git diff --check` | все exit0;40prompts/0issues,0secrets,0diffissues |
| G7 | Отдельные blind-first Python/code и security review actualcode/schema/tests | оба APPROVE/openfindings0; security own read-only smoke schema/positive match+7negativecases exit0; финальный docs verdict — в протоколе |

**Security/test cases:** direct constructor, JSON Schema и parser одинаково отвергают ABSENT/NULL expectation; empty/unsafe/oversized VALUE также отклонён. Candidate absence/null сохраняются и не совпадают с valid VALUE expectation. Exact fingerprint/managed refs/generation comparison, unknown version/old0.1 refusal и no expectation→refusal покрыты. Модель не получает права принять observed identity; actual первый ответ не autoapproved. Результаты тестов синтетические, не evidence provider compatibility или durable block.

**ECC:** planner/architect отдельного read-only g02_prerequisite_plan проверил решение против DOC076§3.1/ADR128 и отсутствие runtime consumers. Root применил TDD/checklists и сам реализовал дельту. Независимые g02_python_contract_review и g02_scope_security_review проверили чужой код blind-first/read-only; прежний автор validator эту дельту не объявлен reviewer. Native commands/hooks не запускались. Набор/результаты — ECC_USAGE и [review](../reviews/G02_FLASH_IDENTITY_REVIEWS.md).

**Ограничения/следующий scope:** G3/G6 runtime/migration неприменимы этой pure delta; полного pre-pr/LinuxCI/audit/digests/supply-chain/live calls нет, поскольку группа и durable admission ещё не реализованы и runtime/config/data не менялись. Это не product VERIFIED. Состав metadata теперь определён: дальнейшая разрешённая работа — durable G156 admission/generation/block/audit/reapproval и budget ledger/candidate path по плану; live evidence/ключ/approval до включения сохраняются. При missing fingerprint в Bifrost/SSE допуск закрыт, никакого synthetic/previous value или автоматического ослабления. SLICE01 остаётся до S17 с собственным бюджетом; ADR129/G107 до S20. Нового вопроса владельцу в этой дельте нет.

**Финальное evidence дельты:** независимый security docs delta review после code review — APPROVE/C/H/M/L0, без чтения авторского отчёта. Read-only Python3 checker:74canonical/73manifesthashes/0missing/mismatch;242localfilelinks/0missing. SHA256-сверка38исходных локальных файлов:23byte-identical+15authorizededits,0unexpected; historicalschema0.1 byte-identical. Финальные prompts40/0,secrets0,diffcheck0,exit0. Freeze SHA256 current code `b36afaf3c513b12dab67fe374c57414d4353818ae183362b9d6d6e62f876a74d`; tests `913ccf3cd411fedf80577eb5baa9a3b9c069803d2f7f8432aeb5e36289b8de6c`; schema0.2 `01fdbc293005b9fe52bd4291e4eed9b8734f60c6385400f69ff175efb9ab4be0`. Нового runtime/CI/commit нет; последующие additions только фиксируют эти результаты, code/schema не меняют.

## Исторический checkpoint ADR130 — первый срез0.1

**Дата:** 2026-11-17. **Scope/план:** [G02_FLASH_ADMISSION](../groups/G02_FLASH_ADMISSION.md), [паспорт](../groups/G02_WORK.md). **Статус:** IN_PROGRESS; pure validator проверяется отдельно. **Полный G156 / G02 IMPLEMENTATION NOT VERIFIED.** Ни один Sxx не повышен до IMPLEMENTED/TESTED/VERIFIED/DONE.

## 1. Что реализовано

Восстановлены источники и фактический Git; определена цепочка Flash admission/G156→SLICE01→S17. Созданы паспорт группы, технический план и бюджетный конверт candidate PoC. Первый отключённый кодовый срез: strict versioned identity evidence parser/normalizer и exact comparison. Fingerprint ABSENT/NULL/VALUE различаются; controlled versions отделены от provider facts. Expectation не является approval/grant и не может autoapprove первый ответ.

Factory, routing, immutable-only Bifrost guard, ModelProfile, domain persistence и сервисный runtime не подключены к этому коду. Durable admission/generation/block/audit/reapproval и billing ledger/probe ещё не реализованы; live calls0, расход0USD.

## 2. Нормативная база и Registry

AGENTS прочитан с диска включая §10/11, CONTEXT_RETENTION, CLAUDE, Registryv4.1, HANDOFF/STATUS/ROADMAP/CHARTER/tooling, группа/шаблон и S17 start conditions, применимые правила/checklists. Узкая подготовка опирается на DOC075/076/078v1.1, ADR128/129/115/127. Historical references/устаревшие строки не использованы как новые требования; S16/G01/ARCH01/DEP01 не переоткрываются. До следующего существенного persistence/transport среза требуется соответствующее полное обязательное чтение и сверка фактической схемы/ролей/head.

Registry и baseline manifest только проверяются; canonical файлы не редактировались этой работой. На старте NCP16/OD19 уже находились в29локальных файлах; их существующие изменения не выданы за новые авторские изменения этой сессии.

## 3. Файлы и scope diff

| Файлы | Изменение текущей работы |
|---|---|
| `backend/src/ai_res/llm/observed_identity.py` | Новый pure parser, metadata extraction, comparison и безопасные typed errors |
| `backend/tests/unit/test_llm_observed_identity.py` | Реальные behavioral/negative/schema cases, synthetic fixtures |
| `contracts/internal/llm-observed-identity.v0.1.schema.json` | Новый WORKING internal contract; structural schema + более строгая semantic validation в parser |
| `groups/G02_WORK.md`, `groups/G02_FLASH_ADMISSION.md` | Паспорт, chain/scope/этапы реализации и paid plan |
| `decisions/ADR-130-flash-observation-contract.md`, ADL | Технический выбор отключённого среза |
| HANDOFF, STATUS, KNOWN_GAPS, DECISIONS_PENDING, traceability, ECC_USAGE | Новая сводка/границы/вопрос, сохранены исходные записи |
| ROADMAP, prompts/README | Уточнено: ARCH01 DONE, реально ожидается SLICE01; порядок не меняется |
| Этот отчёт и `reviews/G02_FLASH_IDENTITY_REVIEWS.md` | Проверки и независимые verdicts, без runtime certification |

База/HEAD `db8d4af34b0933aa2562adcf072b717eb0e3e3e9`. Ветка создана `git switch -c feat/g02-manager-tools-planning` от исходной docs/ncp16-flash-identity-exception. Исходные19tracked+10new сохранены; в общие документы внесены дополнительные записи. Commit/push/PR/merge не выполнялись: общий результат группы ещё не готов, исходный чужой diff автоматически не доставляется.

## 4. API / контракты / события

Новая implementation-owned внутренняя схема0.1, не зеркало canonical и не endpoint. Public API, Worker DTO, events, существующий LLMGatewayPort/ModelIdentity и compatibility baseline не меняются. Новый контракт проверяется явными backend tests; старый contracts CLI без них недостаточен для его проверки. Конструирование expected identity не доказывает человеческого решения; trusted durable admission service ещё отсутствует.

## 5. Миграции и данные

Миграций, SQL snapshot changes, role/grant/RLS changes и операций с БД/данными/volumes нет. Revision0017 не редактировалась. PostgreSQL/restart/concurrency tests для полного admission отложены до его реализации; чистый validator не доказывает durable fail-closed. Никаких runtime или secret changes.

## 6. Самостоятельное техническое решение

ADR130 ACCEPTED в пределах реализации ADR128: отдельный строгий контракт/validator до integration. Metadata human acceptance ещё PENDING, profile/Bifrost approval отсутствуют. Scope и human authority не расширены.

## 7. Несогласованности / NCP

Новый NCP не требуется: исключение уже принято ADR128, canonical не меняются. Старое упоминание ARCH01 в ожидании S17 уточнено по фактическому DONE; очередь SLICE сохраняется. Исходные NCP16/OD19 записи сохранены. Review отметил различие обязательного provider request reference в плане и nullable в первоначальном коде; исправление отслеживается в протоколе review.

## 8. ECC: фактическое применение

- `g02_prerequisite_plan`: отдельный read-only planner/architect определил цепочку и code seams; затем ограниченное авторство трёх новых validator/schema/test файлов с прочитанными Python/TDD/contract инструкциями. Автор не считается независимым reviewer.
- Основной исполнитель: doc-updater/verification-loop как явно прочитанные checklists scope, источников, diff/сохранности, применимых checks и контекста; независимый расчёт бюджета Decimal.
- `g02_scope_security_review`: blind-first read-only code/security competence, docs chain/approval/budget и затем кодовая дельта.
- `g02_python_contract_review`: blind-first read-only Python/code/test/type review actual parser/schema/cases.
- Нативные Claude commands/hooks не запускались. Serena/Context7 не были нужны: локальное чтение/rg и официальные общие provider docs покрыли задачи. Database/runtime review не объявлены выполненными: соответствующей реализации пока нет; при следующем срезе они обязательны.

## 9. Проверки

Среда текущего checkpoint: Darwin arm64, Python3.13.5, uv0.11.31, Git2.50.1,ruff0.17.4,mypy2.4.1. Проверяемая версия — указанный HEAD плюс текущий незакоммиченный diff новых файлов/implementation docs и сохранённый исходный NCP16/OD19 diff. Все counts ниже относятся к этому отключённому срезу, не к VERIFIED продукта.

| Gate | Команда | Результат текущего прогона |
|---|---|---|
| G8 | `python3 -B docs/implementation/tools/check_prompts.py` | exit0;40prompts,0issues |
| G5 | `python3 -B infra/scripts/scan_secrets.py` | exit0;0findings |
| G1/G2 | В backend: `.venv/bin/python -m pytest -q tests/unit/test_llm_observed_identity.py tests/unit/test_bifrost_adapter.py tests/unit/test_llm_gateway.py` | exit0;245passed,0failed/skipped;108новыхcases |
| G1/G2 | `make pre-push-fast` | exit0;ruff0,mypy174sourcefiles0issues,15importcontractsKEPT/0broken;944passed,4warnings,0failed/skipped |
| G4 | `make contracts-check contracts-test` | exit0;6/6CLI checks,22passed; новая схема покрыта backend tests, не приписывается CLI |
| G7 | Два независимых read-only review | [Протокол](../reviews/G02_FLASH_IDENTITY_REVIEWS.md) |
| G8/G9 | Read-only inline Python3: Registry records→files/SHA256, Markdown links, original-file hashes; `git diff --check` | exit0;74canonical/73hashes/0missing/mismatch;221localfilelinks/0missing на checkpoint до финального добавления evidence. Original29:21byte-identical+8intentionallyupdatedimpldocs,0unexpected. Финальные counts после context additions — ниже |

Первый запуск вспомогательного inline canonical/link checker завершился exit1 из-за overescaped regex самого проверочного выражения; source files не менял. Исправленный read-only checker выше exit0. Это не было отсутствием canonical или успешной проверкой на первом запуске. TDD RED до создания модуля: collection exit2 (missing module), затем GREEN; промежуточные fixture/path/type/lint errors автора исправлены до финального245. Финальные schema-description-only уточнения перепроверяются целевым новым набором, без повтора всего fast suite.

Финальный checkpoint после context/review additions: повторные prompts40/0,secrets0,`git diff --check`exit0; Registry74canonical/73manifesthashes/0missing/mismatch,Markdown224localfilelinks/0missing. Сверка SHA256 всех29исходных локальных файлов:20byte-identical,9изменились только в implementation docs, перечисленных в scope; unexpected changes вне implementation0. Исходные canonical/mirror/ADR128/129/reports/prompts сохранены; index prompts/README — новый дополнительный изменённый файл. Ветка/HEAD сверены повторно, Git-доставки нет.

После последнего изменения только schema description повторено в backend: `.venv/bin/python -m pytest -q tests/unit/test_llm_observed_identity.py` — exit0,108passed/0failed/skipped. Freeze SHA256: observed_identity.py `f429de3b7aa9ba89df0b6159ea2ff7c5982195dad4aebd8636db3076ddfa87bb`; test_llm_observed_identity.py `04285cc44461aed7e29670d35ae7118e3cff3c4bed262f1e66e80e197deccec1`; schema `7b86805200269a6b18bc0eb522f257c5f2373ccc5c16a8a6b0065127d647f0e6`. Последняя prose-дельта не меняет code/schema rules и не повод повторять весь локальный набор. Полные245/944results относятся к тем же code/tests/rules, с предыдущим description.

## 10. Security / authorization cases

Текущие поведенческие tests проверяют missing/unknown fields и versions, duplicate/malformed/oversized JSON, wrong types, invalid timestamps/refs, cross-provider/Pro/request/routing/fallback, fingerprint presence/value drift, managed-version mismatch, missing expectation/generation mismatch, отсутствие source content и secret-shaped metadata в evidence/errors. Это проверки parser/comparison, не product authorization, не доказательство sticky block или admission после restart.

## 11. Независимое review

Отдельные blind-first reviewers, без авторского отчёта на первом проходе; фактические findings/исправления/verdicts — в [G02_FLASH_IDENTITY_REVIEWS](../reviews/G02_FLASH_IDENTITY_REVIEWS.md). Оба финальных code/security и Python/contract review **APPROVE/openfindings0**; ранний docs verdict сохранён отдельно. Provider-ref и semantic-note findings исправлены. Security reviewer дополнительно выполнил read-only smoke3positive+8negative,exit0; второй reviewer — static-only, чужой запуск ему не приписан.

## 12. Не выполнено / ограничения

Полный pre-pr, Docker/PG/Temporal/MinIO/Bifrost runtime, migrations, dependency audit/digest/supply-chain jobs и Linux CI не запускались в этом промежуточном отключённом срезе. Причина — идёт подготовка внешней предпосылки, финальная реализация группы не готова, runtime/DB/config не менялись; отсутствие запусков не PASS. Обязательства финальной общей проверки сохранены. Цена из официальных документов — расчёт; provider compatibility, usage, точная identity/fingerprint сохранность через Bifrost и реальные списания ещё не измерены. Ключ не подключён. Без live evidence модель не VERIFIED. Управляемые hashes в synthetic fixture не доказательство реальной версии.

## 13. Контекст и статусы

HANDOFF/STATUS/паспорт фиксируют G02 подготовку IN_PROGRESS, S17/S20/S21 NOT_STARTED; G156 OPEN. ADL130, gaps, both traceability maps, ECC, DECISIONS_PENDING и индекс обновлены в объёме этого шага. Новый текущий вопрос — приёмка metadata состава; прочие owner-вопросы одновременно не ставятся. Пока ответа нет, human acceptance PENDING. Ответ на metadata не является profile/Bifrost approval или новым бюджетом.

## 14. DoD

Чистый отключённый parser/comparison может иметь собственное локальное test evidence. Полный G156 DoD не выполнен: ❌durable admission/block/audit/ledger/probe, ❌PG concurrency/restart, ❌live-provider, ❌human approvals, ❌финальные local/Linux gates. DoD S17/S20/S21 не выполнялся и не заявляется. Public/migration changes текущего среза — N/A.

## 15. Продолжение

Продолжить отключённый G156 из плана: versioned admission binding и PostgreSQL enforcement, budget ledger/candidate path; никакого обхода product factory/guards. Вопрос metadata обсуждён с владельцем отдельно до включения. Безопасный key setup и live PoC только после готового инструмента/ledger, в существующем потолке10USD. Затем представить реальные identity/evidence/Bifrost/profile на human acceptance; SLICE01 требует своих данных/бюджета и completion перед S17. Для первого S20 producer закрыть ADR129/G107. Не начинать другую группу и не повторять DONE.
