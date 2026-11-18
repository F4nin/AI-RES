# SLICE-01 — development experiment

Инструмент ADR-115/142 работает отдельно от product Worker Runtime. Он использует
существующий LLMGatewayPort и S14 WorkerResult validation; domain requirements,
Baseline, Manager и Readiness Gate не исполняются.

Реальный V3 результат и тесты описаны в
[отчёте](../../../docs/implementation/increments/SLICE-01_requirements_experiment_REPORT.md).
Источник — публичный MIT RealWorld routing.md с immutable commit/checksum, не частное приложение.

## Точный контекст и один бюджет

Планы, credential mounts, wallet, quarantine и receipts находятся только в ignored
`infra/secrets/slice01/authorization-2026-11-18`. V1 лежит в корне, следующие
immutable планы — `versions/N`. Wallet общий в корневом `wallet/`; отдельного cap
на версию нет. AUTHORIZE_VERSION добавляет новый parent→child manifest, сохраняет
все расходы и навсегда исключает прежние refs/digests. При UNKNOWN/pending/blocked
продолжение запрещено. Нельзя удалять account, переписывать HEADER/.head или снова
вызывать initialize для исправления ошибки.

Текущие файлы package, imported initializer, source/schema, library, native inputs,
images и prompt bundle связаны hashes. Любое изменение требует новой версии плана.
LLM не получает доступ к grants, wallet, host, DB credentials или browser session.
Доверенный caller — development operator с API role; отдельный offline owner
process получает migrator credential только после личного подтверждения.

## Запуск оператора

Команды выполняются из `backend`, через существующее locked окружение.
Для существующего контекста всегда явно указывайте актуальный `--directory`.
Default directory относится только к исходной V1 и не выбирает новую версию автоматически.

```sh
uv run --locked python -B -m scripts.slice01.cli status --directory ../infra/secrets/slice01/authorization-2026-11-18/versions/3
```

Для нового тестового контекста:

1. Проверить актуальные официальные peak/cache-miss тарифы и их соответствие
   фиксированным 0.30/1.20 USD за 1M. Не подставлять вымышленное время проверки.
2. Остановить прежний owned runtime командой `stop`, сохраняя account/артефакты;
   убедиться, что SQL admission не имеет IN_FLIGHT/blocked.
3. `prepare --directory .../versions/N --tariff-checked-at <UTC>` создаёт новый
   immutable план и credentials. Для N>1 wallet не инициализируется.
4. `activate-version --directory .../versions/N` отдельно добавляет только новый
   manifest к прежнему wallet после проверок parent/runtime/current generation.
5. `start`, затем `preflight`: реальные owner/MFA/Policy/profile checks без расходов.
6. `bootstrap`: один отдельно разрешённый quarantined configuration probe.
7. `acceptance --evidence-file <actual-evidence.json>`, затем `prepare-decision`.
   Артефакт должен подтверждать exact hashes реально выполненных тестов; флаг
   LOCAL_CHECKS_PASSED сам по себе ничего не доказывает.
8. Владелец лично запускает `approve` для первого CANDIDATE или `accept-identity`
   для нового контекста уже APPROVED profile, с exact `--confirm-decision UUID`.
   В Terminal он вводит ПРИНИМАЮ; автоматического confirmation нет.
9. После фактического receipt/audit выполнить `run` один раз и просмотреть результат.
10. `stop` удаляет только recorded owned containers/networks, без volumes/основного
    стека. Cleanup/status metadata остаются доступны после истечения плана;
    dispatch/approval после expiry запрещены.

Повторение старого paid request не является способом исправления результата.
Новая попытка — новый контекст/ref и отдельная версия в том же общем бюджете.

## Формат и диагностика

Модель возвращает один JSON object с `workerResult` и `findingTypes`. Код не
исправляет ответ и не сдвигает locator для принятия. Source text/checksum
не меняются; numberedLines — производная подсказка с frontmatter/пустыми строками.

До gateway finalization нормализованный ответ сохраняется как явно untrusted
private quarantine, после проверки секретов/экранированных JSON strings и bounds.
Это не domain artifact/принятый WorkerResult. Отдельный receipt содержит stage/code,
hash/size/usage; model/source content не пишется в stdout/logs/traces/Temporal.
Capture failure не обходит accounting и не разрешает публикацию.

Только после S14 и downstream checks, exact source/version/checksum, literal quote
в указанном диапазоне строк, registry type/UNKNOWN и финальной авторизации появляется
`requirements-result.json`. Его статус OWNER_REVIEW_REQUIRED не утверждает требование.
Литеральная цитата не доказывает semantic completeness или качество модели.

## Проверки

```sh
uv run --locked pytest tests/unit/test_slice01_*.py tests/integration/test_slice01_bifrost.py tests/integration/postgres/test_slice01_owner.py tests/integration/postgres/test_slice01_producer.py -q
uv run --locked mypy --strict --follow-untyped-imports scripts/slice01
```

Native fixtures используют настоящий pinned Bifrost/relay/capture и synthetic
upstream без provider key/egress/main DB. PostgreSQL fixtures настоящие, но с
plaintext test-only engine adapter; они не являются TLS evidence. Live проверен
отдельно в dev-стеке с verify-full. Полный pre-pr и обязательный Linux CI сохраняются.
