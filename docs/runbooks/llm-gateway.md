# S16 — локальный PoC Bifrost

Это отключённый candidate-контур для разработки и проверок. Он не включает реальную модель, не создаёт APPROVED-профиль и не завершает S16. Приёмка model pinning — [NCP-16](../implementation/decisions/NORMATIVE_CHANGE_PROPOSALS.md#ncp-16--deepseek-flash-и-immutable-model-pinning); техническое решение — ADR-122.

## Запуск и проверка

Из корня checkout:

```sh
make llm-poc-up
make llm-poc-check
```

Нужны установленные зависимости из lock-файлов, Docker и штатные SOPS/age. Первая команда дополняет существующий зашифрованный dev-store только тремя недостающими случайными credentials (admin, scoped virtual key, relay auth), сохраняет прежние значения и запускает две службы. Provider key она не генерирует. Обычный `make up` этот overlay не включает; `make pre-pr` проверяет его после основного runtime-набора.

`llm-poc-check` сначала проверяет конфигурацию контейнера relay: штатная команда без live flag, без provider-key env и без provider-key mount. Затем до любого model-shaped запроса проверяет disabled health. При любом отклонении завершает проверку отказом. Credentials передаются локальному probe через stdin, не argv/env; вывод содержит только названия проверок и booleans. Probe проверяет auth/admin/VK, запрет Pro, сеть/порты, отсутствие secret values в env/logs. Внешних inference-запросов он не делает. Положительный контроль TCP до relay отделён от отрицательного контроля внешнего маршрута.

Остановка только этих служб с сохранением основного стека и volumes:

```sh
make llm-poc-down
```

`/app/data` Bifrost — tmpfs. При restart config/auth store пересоздаётся из template и Compose secrets, durable state в нём не предполагается. Это служебная SQLite стороннего gateway, не доменная БД AI RES; Model Registry остаётся в PostgreSQL. Logs/content stores и внешние connectors выключены. Доступа к Docker socket, app/data/workflow сетям и публичным портам нет.

## Диагностика

Health у relay возвращает `status: disabled`. Это liveness процесса с закрытым forwarding, не готовность выполнять платный запрос. Admin/inference Bifrost используют один listener, но admin защищён отдельной Basic auth, inference — scoped virtual key. Runtime не подключён к PoC-сетям и credentials не получает.

Не выводить raw config.json, `docker inspect` environment целиком, secret files или необработанные logs. Bifrost может по ошибочной конфигурации потребовать внешний pricing bootstrap: используемые здесь `framework.pricing.*_url` указывают на локальные readonly каталоги, без открытия внешнего маршрута для Bifrost. Первоначальная попытка file-only auth + default remote pricing не стартовала; это исправлено ephemeral config store и локальными файлами.

Проверяемый transport 2.5.1: `sha256:5ec9873acaf1687556b6e4dd854b92b539d9debf87a5a683b66338648b84d3c8`, release SHA `7cb75fb2f8276ca48d0792c857fecb67b8879e2f`. Каталоги — небольшая operator metadata PoC по официальным [тарифам DeepSeek](https://api-docs.deepseek.com/quick_start/pricing/) на 2026-11-17 и формату закреплённого Bifrost; они не подтверждают фактическую модель или billing. `server_side_model`/фиктивный snapshot не задаются.

## Условия реальных запросов

До платного тестирования нужно решить NCP-16, предоставить provider credential штатным защищённым способом вне чата и подготовить точную composition/допуск изолированного PoC. Поставляемый overlay не содержит provider-key mount или live flag; просто запустить `llm-poc-up` недостаточно для egress. `LLMGatewayPort` factory остаётся unconfigured, evidence bindings пусты, известные rolling aliases transport отвергает до HTTP. Изменять эти условия ради зелёного теста запрещено.

Для будущего live test нужен отдельный проверенный overlay/допуск и [план расходов](../implementation/reviews/S16_PAID_TEST_PLAN.md), в пределах общего 10 USD S16. Только gateway-boundary relay получает реальный provider key; model/Runtime его не получают. Реальную отмену, billing, provider compatibility, pinning и security acceptance нельзя вывести из локальных MockTransport-тестов или 19 no-paid проверок. После тестов владелец отдельно принимает Bifrost и утверждает точную версию профиля с аудитом. Durable ledger, input token estimate и product placement остаются ограничениями G-145/G-152.
