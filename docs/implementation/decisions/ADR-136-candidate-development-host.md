# ADR-136 — Trusted development host для candidate-прогона

**2026-11-18, ACCEPTED technical scope** по продолжающемуся поручению владельца на подготовку. Не запуск G02/S17/S20/S21; не approval модели или тарифа.

Собрать существующие runner/ledger/probe/control в отключённую host-композицию. Закрытый защищённый JSON связывает единственный original authorization/account с точным manifest, исходниками, конфигурацией, локальным образом и проверенным runtime snapshot. Источник исходников учитывает dirty/new Python и точные patch/build inputs. Host не создаёт account, tariff, profile, grant или секрет.

Актуальность тарифа проверяется новым ограниченным HTTPS GET фиксированной официальной pricing-страницы на каждой validation; raw snapshot должен совпасть с отдельно проверенным descriptor. Нет придуманного TTL, scraping цен или автоматического принятия нового тарифа. Изменение страницы, outage или несовпадение descriptor/DB прекращает dispatch до контролируемого пересмотра. Snapshot hash сам по себе не подтверждает правильность ручной оценки опубликованных цен. Реальный descriptor пока не создаётся.

Runner проверяет gate до reserve и после него. Обёртка control повторяет host validation непосредственно перед ledger claim; положительный HTTP ответ по-прежнему требует committed onceclaim/audit. Settlement не блокируется изменением freshness/host conditions: уже возможное списание необходимо учитывать. Конечное окно между claim и send сохраняется; атомарность внешнего provider с БД не заявляется.

Readonly Docker inspector допустим только в trusted development host; Manager/Worker/relay не получают Docker socket или DB credentials. Inspector не запускает/меняет контейнеры. Проверяются фактические immutable container/image IDs, отсутствие небезопасных привилегий/mounts/публичных портов и exact reviewed runtime digest. Mount Source/Destination и hashes host-path files не доказывают bytes уже смонтированного inode после atomic replace. Проверка конфигурации не доказывает effective rendered/SQLite/admin state или live network isolation: отдельный изолированный запуск и его security acceptance остаются обязательными.

AsyncExitStack закрывает DB engine, probe и tariff client при construction failure, ошибке выполнения и cancellation. Ключ провайдера остаётся только в relay; runner получает только mounted Bifrost virtual key. Значения credentials не входят в JSON, argv/env, evidence или ошибки. Setup SOPS/age → Compose secrets и final review/regression/pre-pr/Linux CI обязательны до live activation.

Проверки: source/config/runtime/tariff mismatch и outages; malformed/unsafe local files; guards до reserve/claim, accounting после revoke; original account/rates/bounds; cleanup при ошибках/cancellation; независимые Python/general/security reviews. Миграции0020–24, product factory, official image/main stack и canonical документы не меняются. Статус реализации и точные результаты фиксируются в отчёте после проверок.

## Native audit и канонизация mounts,2026-11-18

Прямая команда владельца на проверку изолированного запуска выполнена отдельным [audit checkpoint](../increments/G02_bifrost_effective_isolation_REPORT.md). Docker между inspect читает Mounts в разном порядке: ошибка canonical hash подтверждена native diagnostic и unit RED. Принята минимальная канонизация по уже validated unique Destination, все mount fields остаются связанными hash. Exact expectedRuntimeSha256 не заменяется/не принимается автоматически; до real descriptor требуется новая проверка. Это исправление наблюдателя в прежнем scope, не изменение host wire/version/public contract или Bifrost конфигурации.

Native renderer/settings/auth/network/log checks прошли; контролируемая admin mutation меняет live client и SQLite при неизменных rendered bytes/image/canonical inspect. **Effective configuration integrity OPEN:** прежде требуемое доказательство неизменности не получено, конкретный enforcement mechanism остаётся следующим preparatory seam. Отключение config_store не принято: nil store в pinned source обходит auth middleware. Main stack/real secrets/accounts/approvals не менялись; full G156/live/security acceptance не заявлены.
