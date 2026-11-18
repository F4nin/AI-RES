# SLICE-01 — эксперимент извлечения требований: Increment Report

**Дата:** 2026-11-18. **Промпт:** [SLICE-01](prompts/SLICE-01_requirements_experiment.md).
**Статус:** VERIFIED; код доставлен в main через PR #34. Проверенный source commit54730eb, mergef5b3211; деревья файлов идентичны.

## 1. Что реализовано

Работает отдельный инструмент разработки: публичный документ → Requirements-промпт →
существующий GovernedLLMGateway/LLMGatewayPort → WorkerResult 1.1 → проверки схемы,
цитат, provenance и типов → материал для просмотра владельцем. Это эксперимент
ADR-115 до S17/S23, а не продуктовый WorkerRun с Manager и Readiness Gate.

Реальный прогон версии 3 прошёл 2026-11-18T17:19:17.460761Z. Модель выделила один FR:
«The home page must show a list of articles pulled from either Feed, Global, or by Tag.»
Дословная evidence quote — `  - List of articles pulled from either Feed, Global, or by Tag` —
присутствует в строке 7 исходника; statement модели и цитата различаются. Результат:
[SLICE-01_RESULT.json](../reviews/SLICE-01_RESULT.json). Статус остаётся
DETERMINISTIC_CHECKS_PASSED_OWNER_REVIEW_REQUIRED; требования не утверждались автоматически.

Всего SLICE выполнил **6 платных вызовов**: три диагностических и три извлечения.
Учтено **0.0032058 USD**, остаток **9.9967942 USD** из разрешённых 10 USD.
Это консервативный расчёт по известному usage и peak/cache-miss ставкам; счёт
провайдера не сверялся. UNKNOWN/pending/blocked в новом account отсутствуют.
Старый technical account и его неизвестные исходы не сбрасывались.

## 2. Нормативная база и Registry

Основание: ADR-115, прямое поручение владельца начать SLICE-01, отдельный общий
лимит 10 USD и согласованный allowed_regions=[cn] для обычных INTERNAL-данных
без ПДн/коммерческой тайны. Бюджет и регион повторно не запрашивались.

Registry v4.1: наличие 74 canonical файлов проверено; отсутствующих нет.
Reviewer полностью прочитал 43 файла стартового набора Spec §2, саму Spec v1.22
и Architecture Completion v1.1 — 45 файлов, разрешая исторические ссылки через Registry.
Полное чтение завершено до live-вызовов. Первоначальный порядок чтения до написания
первой версии был нарушен; последующее чтение не отменяет этот процессный пробел.
Новых нормативных конфликтов для ограниченного tooling scope не обнаружено.
DOC-007 остаётся WORKING; canonical и contracts mirror не изменялись.

## 3. Файлы и scope

| Файлы | Изменение |
|---|---|
| backend/scripts/slice01/common.py, prepare.py, runtime.py, cli.py | Immutable manifests, отдельные Docker resources, frozen inputs, операторский CLI |
| backend/scripts/slice01/ledger.py, relay.py | Один durable account, строгая allowlist запросов, reserve/ARM/claim/settle, фиксированный upstream |
| backend/scripts/slice01/requirements.py, producer.py, owner.py | Prompt/проверки, governed composition, private quarantine, существующие human approval services |
| backend/tests/unit/test_slice01_*.py | Формат, provenance, секреты, бюджет, конкурентность, отказ и recovery |
| backend/tests/integration/test_slice01_bifrost.py, fixtures/slice01_native_*.py | Настоящий pinned Bifrost, relay/ledger/capture; synthetic upstream |
| backend/tests/integration/postgres/test_slice01_*.py | Настоящий disposable PostgreSQL: авторизация и owner/identity wiring |
| backend/tests/fixtures/slice01/ | MIT RealWorld source, лицензия и immutable provenance |
| docs/implementation/reviews/SLICE-01_* | Operator scripts, review/test/live evidence, диагностика и результат |
| implementation ADR/status/handoff/traceability/ECC/data-source docs | Scope и фактические результаты |

Продуктовый backend/src/ai_res, contracts/, архитектурные документы и Compose
не изменены. Исходный локальный diff G156 сохраняется отдельно; candidate_tariff.json
не включать в Git. Секреты и private runtime artifacts остаются в ignored infra/secrets.

## 4. API, контракты и события

Новых публичных API, DTO, событий и продуктовых permissions нет. Используются
существующие WorkerResult 1.1 и наблюдаемая identity 0.2. Tool-only findingTypes
сохраняет неизвестный declaredType и нормализует его в UNKNOWN без угадывания.
Поддерживаемый WorkerResult subset — findings; model metrics не принимаются.
Usage/cost/receipt time записывает доверенный оператор отдельно.

## 5. БД, миграции и совместимость

Новых миграций, ролей, grants и схем нет; head c97e3bf386f1 сохранён. Через reviewed
maintenance job создан один CANDIDATE и exact operator binding с атомарным audit.
Владелец лично завершил MFA и подтвердил профиль через отдельный CLI. Фактический
postflight: APPROVED profile 1, identity generation 3/unblocked, admission versions 3,
VALIDATED calls 3, MODEL_PROFILE_APPROVED audit 1. VALIDATED означает проверку identity,
а не успешную S14 validation: первые два extraction результата были отвергнуты.

Повторные версии использовали только ACCEPT_IDENTITY существующего сервиса;
profileVersion=1, approvedAt и исходное profile approval не менялись. Owner/migrator
credential есть только у отдельного offline-процесса; обычный caller использует API role.
Это доверенный development operator, не Worker Runtime продукта.

## 6. Технические решения

[ADR-142](../decisions/ADR-142-slice01-experimental-composition.md): отдельный инструмент,
точные code/config/prompt/body refs, private frozen native inputs и схема, pinned Bifrost,
один общий account 10 USD. До I/O консервативно резервируется 0.6024576 USD
(2M input + 2048 output по 0.30/1.20 USD за 1M); известный usage заменяет резерв.
UNKNOWN удерживает резерв и блокирует новые попытки. Повторы и fallback отключены.

Новые immutable версии добавляются AUTHORIZE_VERSION под тем же flock/hash/head/fsync.
HEADER, cap, расходы и история не перезаписываются; старые refs/digests не используются
заново, старые процессы отказывают после смены manifest. Перед activation старый
runtime остановлен, SQL IN_FLIGHT отсутствуют. Для новых managed refs получено новое
наблюдение и личное identity approval; прежние provider facts не перепривязывались.

## 7. Найденные проблемы и исправления

| Версия | Фактический результат | Исправление |
|---|---|---|
| V1 | Governed call состоялся, но tool отказал; исходный ответ/точная причина не сохранены | Private bounded quarantine до финализации/валидации и безопасные machine receipts |
| V2 | Два JSON-документа вместо одного outer object; цитата из строки 15 указана как lines:12-12 | Явный пример единого JSON и derived numberedLines с frontmatter/пустыми строками |
| V3 | Полный автоматический путь прошёл: S14, IDs, checksum, quote/range, type, секреты | Ответ не исправлялся и не нормализовался для принятия |

Исходный WorkerResult-компонент V2 отдельно прошёл S14, но диагностическое
объединение всё равно не прошло grounding. Нормализованный результат не принимался
и не публиковался. [Диагностика](../reviews/SLICE-01_V2_FAILURE_DIAGNOSIS.json).

Review закрыл native/schema freeze gaps, live-image override, imported initializer,
MFA lock order, истёкшую deprecation, отсутствие проверки live admission controls у
нового probe, runtime drift во время human review и секреты в JSON-escaped quarantine.
Проверка capture действует до записи для обоих stages и вложенных JSON strings,
с ограничениями глубины/байтов/числа значений. Отказ capture не теряет accounting.

MFA helper теперь использует только HTTP status/stable code, не локализованный
error detail. Один ручной OTP на запуск, без автоматического retry; enrollment resume
сохранён. Агент не вычислял OTP и не выполнял личные решения владельца.

## 8. ECC

Root — интеграция, host composition, реальный оператор тестов; planner,
python-testing и verification-loop применены как прочитанные checklists.
slice_budget_transport написал ledger/tests и независимо проверял чужие composition,
owner/capture и MFA helper. slice_runtime_plan написал relay/tests, независимо
проверял чужие requirements/ledger/host и полностью прочитал startup sources.
slice_requirements_design написал requirements/owner/capture/helper delta и tests,
независимо проверял чужие ledger/relay. Авторы себя не утверждали.
Native slash commands/hooks и продуктовый QA не имитировались. Детали — ECC_USAGE.md.

## 9. Проверки

Среда live: Darwin arm64, Python 3.13, existing dev PostgreSQL/TLS и pinned Bifrost.
Все команды относятся к HEAD 5bc8324e967713a607c93f20d54cb3fc57e76fcb + рабочему diff;
точные hashes источников записаны в evidence. Эти исполнения не приписываются будущему SHA.

| Проверка | Команда / evidence | Результат |
|---|---|---|
| V2 полный scope | pytest tests/unit/test_slice01_*.py + native + два PG файла; /tmp/slice01-v2-final.xml | 371 passed, 0 failed/errors/skipped, 35.52s |
| V3 affected scope | pytest tests/unit/test_slice01_requirements.py tests/integration/test_slice01_bifrost.py; /tmp/slice01-v3-final.xml | 87 passed, 0 failed/errors/skipped, 22.35s |
| Быстрый проектный gate | make pre-push-fast | 1896 passed, 4 deprecation warnings, 15.12s; Ruff/mypy/import contracts PASS |
| Tool modules | uv run --locked mypy --strict --follow-untyped-imports scripts/slice01 | 10 modules PASS |
| Secrets | make infra-scan-secrets | 0 findings |
| MFA compatibility | pytest -c backend/pyproject.toml docs/implementation/reviews/SLICE-01_OWNER_MFA_TEST.py | 28 passed, 0 failed/skipped, 0.12s |
| Полный локальный gate | env PATH с установленным OpenSSL 3.6.3; make -j1 pre-pr | exit0: contracts22/Renovate10/backend3228 (541warnings)/infra369/runtime148/PoC19; failed/skipped0 |
| Runtime audit / image pins | make backend-audit; make infra-verify-digests | exit0: известных уязвимостей0; 21pins/0mismatch |
| Linux CI / доставка | [ci44363805060](https://github.com/F4nin/AI-RES/actions/runs/44363805060), [contracts44363804982](https://github.com/F4nin/AI-RES/actions/runs/44363804982), [PR34](https://github.com/F4nin/AI-RES/pull/34) | SUCCESS на exact54730eb; backend3228/541warnings/908.55s, infra-static221/runtime148/PoC19, все дополнительные gates PASS; MERGEDf5b3211 |

Постоянные evidence: [V1](../reviews/SLICE-01_TOOLING_EVIDENCE.json),
[V2](../reviews/SLICE-01_TOOLING_EVIDENCE_V2.json),
[V3](../reviews/SLICE-01_TOOLING_EVIDENCE_V3.json),
[live V3](../reviews/SLICE-01_LIVE_EVIDENCE_V3.json). Counts разных прогонов не суммируются.
TOOLING-файлы сохраняют подготовительные pre-live snapshots, включая унаследованные
формулировки о ещё необходимых наблюдениях/приёмке. Их bytes/hash после owner
acceptance не менялись. Последующее выполнение этих условий подтверждено LIVE_V3
и RESULT, а не переписыванием исторического test evidence.
Native тесты используют настоящий Bifrost/relay/capture и synthetic provider.
PG fixtures используют настоящий PostgreSQL, но plaintext test-only adapter;
они не доказывают TLS. Live operator проверил verify-full в фактическом dev-стеке.

Новые migrations/API/SSE/Temporal процессы не добавлены, поэтому отдельные новые
contract/backfill/replay gates неприменимы; соответствующие регрессионные наборы
по-прежнему входят в полный pre-pr. G1–G9 и дополнительные CI jobs не отменены.

## 10. Security / authorization

Проверены revoked/expired MFA session, отсутствие OWNER/активного фактора,
запрет policy, deprecation, изменённые refs/schema/native inputs, blocked/pending/stale
admission, budget exhaustion/UNKNOWN/corruption/truncation, concurrency/restart,
secret-shaped/escaped content, prompt injection, fabricated quote, unknown type,
неверные IDs/enum, malformed JSON. При отказе accepted artifact не создаётся.

Контейнеры без host ports/Docker socket; только relay имеет provider key и fixed
upstream egress с TLS/SNI. Источник и результат не попадают в telemetry/Temporal.
Все три owned runtime остановлены после своих прогонов, volumes/основной стек и
старый G156 runtime не удалялись. Profile approval/identity — личные audited действия.

## 11. Независимое review

General/architecture/Python/security/database компетенции применены отдельными
reviewers blind-first; final open CRITICAL/HIGH/MEDIUM = 0 на exact reviewed hashes.
Hashes и границы source-only review — в tooling evidence; MFA delta reviewed отдельно.
Source review не подменяет реальные model calls, CI или просмотр результата владельцем.

## 12. Ограничения

Один публичный MIT документ, одно итоговое требование; корпус мог быть в обучении.
Это не оценка полноты/качества модели, производительности или production readiness.
Буквальная цитата не доказывает семантическое следование statement. Повторяемость
rolling alias ограничена NCP-16; fingerprint не является immutable model pin.
Счёт провайдера не проверялся. Локальный pre-pr и exact source Linux CI закрыты; merge tree равен проверенному. Автоматический post-merge CI44367265491 наблюдался ещё выполняющимся и не выдаётся за PASS; его contracts44367265219 уже SUCCESS.

## 13. Документы и traceability

Обновляются ADR-142/ADL, STATUS/HANDOFF, ECC_USAGE, TEST_DATA_SOURCES, prompt/index,
implementation traceability и новые review/evidence/result artifacts. Canonical,
baseline manifest и contracts не изменены. Старый локальный diff не перезаписывался.

## 14. DoD

- Выполнен реальный governed call с лично принятым profile/identity и enforced budget.
- WorkerResult/schema/provenance/type/secret checks прошли, результат предъявлен владельцу.
- Лицензия, source version/checksum, prompt/code/config/body refs и costs сохранены.
- Независимое review завершено; обязательный exact Linux CI и Git delivery завершены; дополнительный автоматический post-merge прогон не приписывается к проверенному SHA.

## 15. Следующий этап

S17/G02 не начаты. SLICE-01 закрыт; по прямому указанию владельца остановиться.
Владелец обновит контекст и даст отдельный approval на начало следующей разработки. Requirement/Baseline approval и deployment
этим экспериментом не предоставлены.

Финальное [CI evidence](../reviews/SLICE-01_CI_EVIDENCE.json) различает source54730eb, mergef5b3211 и post-merge workflow. Код после проверки не менялся.
