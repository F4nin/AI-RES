# S16 — проверка фиксации версии модели

**Дата:** 2026-11-17. **Метод:** документальная часть PoC, без inference/API-запросов к провайдеру. **Результат:** immutable selection в публично документированном API DeepSeek не подтверждён; приёмка профиля BLOCKED. На момент исследования S16 не был завершён; позднее технический milestone закрыт по owner decision ADR-123. Это не подтверждает pinning и не принимает NCP-16.

**Граница этого документа:** первоначальный документальный checkpoint на базе37b9a37 до кодовой реализации. Последующий adapter/relay/реальный отключённый Bifrost и его19 runtime checks описаны в актуальном [отчёте S16](../increments/S16_bifrost_poc_provider_profile_REPORT.md); исходная матрица ниже относится к этому предварительному sub-PoC и не отменяет последующее evidence.

## Требование и наблюдения

База исследования — чистый `main` `37b9a37edb04d31b448c44e9b64052b19cb411d7`, сверенный с `origin/main` после `git fetch origin main`. Ветка продолжения — `feat/s16-bifrost-poc`. S13/S15 DONE; владелец явно выбрал S16 в текущей сессии. Разрешение на исследование не является approval модели или Bifrost.

| Источник | Проверенное положение | Вывод |
|---|---|---|
| [DOC-076](../../architecture/AI_RES_Model_Gateway_and_Model_Registry_v1.0.md) §3, §7 | Фактическая identity Run; immutable version для evaluation/release; проверка pinning | Дата/строка в локальном профиле недостаточна |
| [DOC-075](../../architecture/AI_RES_Architecture_Completion_and_Baseline_Decisions_v1.0.md) §3.2 | Непривязанные aliases запрещены в baseline evaluation/release evidence | Исключение требует решения владельца и синхронизации canonical |
| [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/) — просмотр 2026-11-17, request `model` | Перечислены `deepseek-flash` и `deepseek-v4-pro`; selector для snapshot не документирован | Документирован только выбор alias; недокументированный ID не угадывался |
| Та же спецификация, response `system_fingerprint` | Metadata конфигурации backend; параметра выбора этой конфигурации нет | Наблюдение не закрепляет и не восстанавливает прежнюю модель |
| [DeepSeek Changelog](https://api-docs.deepseek.com/updates/) — просмотр 2026-11-17, запись 2026-10-17 | Версия Flash обновлена при сохранении API alias | Один alias уже адресовал разные версии |
| [DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/) — просмотр 2026-11-17 | Flash alias сопоставлен текущей `DeepSeek-V4.1-Flash-1017` | Это описание текущей модели, не гарантия immutable endpoint |

**Граница вывода:** не найден документированный механизм выбора неизменяемой версии в рассмотренном публичном интерфейсе. Это не доказывает невозможность частного snapshot-контракта/endpoint провайдера. Реальный `/models`, inference и попытка вызвать version label не выполнялись. Достоверность возвращаемой identity на реальном ответе не проверена. Public docs изменяемы; дата просмотра и содержание наблюдения зафиксированы здесь, побитовой snapshot страницы не создавался.

Текущее `gateway.py:138–139` строит `ModelIdentity` из профиля; обычный ответ использует её в `:249`, stream заменяет identity профилем в `:426`. `transport.py:35–41` не несёт доказательства фактической версии. До подключения реального transport соответствие должен доказать адаптер либо должна быть явно изменена нормативная семантика. Эти места существуют с S15; реального провайдера по умолчанию нет. Новая уязвимость или уже выполненный неверный вызов этим исследованием не заявляются.

## Матрица DOC-076 §7

| Проверка | Статус в этом checkpoint | Следующее evidence |
|---|---|---|
| Model pinning | BLOCKED: документальное несоответствие интерфейса требованию; runtime NOT RUN | Подтверждённый immutable selector или решение NCP-16 |
| Structured output/schema adherence | NOT RUN | Реальный ответ через адаптер + локальная schema validation |
| Tool calling | NOT RUN | Реальная генерация типизированного вызова, без исполнения внешнего действия |
| Streaming | NOT RUN | Реальный SSE, usage, завершение и закрытие соединения |
| Cancellation/timeouts | NOT RUN | Прерывание/дедлайн, отсутствие retry неизвестного списания, консервативный бюджет |
| Provider errors | NOT RUN | Типизированные 4xx/5xx/timeout без утечки тела |
| Fallback policy | NOT RUN для Bifrost | Запрет неутверждённого профиля/провайдера; Pro остаётся CANDIDATE |
| Rate limits | NOT RUN | Локальный admission + поведение 429/Retry-After без обхода бюджета |
| Usage metering | NOT RUN | Usage, тарифы, неизвестные списания и доступный billing отдельно |
| Secrets/logging | NOT RUN для Bifrost | Canary-тесты без content capture, ключ только у gateway |
| Egress | NOT RUN | Allowlist домена/порта + запрет обхода, private IP, redirects и DNS rebinding |
| Multi-tenant isolation | NOT RUN | Изоляция запроса, identity, бюджета и metadata между scope |
| Security advisories/upgrade path | NOT RUN | Выбранная закреплённая версия Bifrost, advisories и план обновления |

Ни одна NOT RUN проверка не объявляется PASS. Bifrost не установлен/не выбран по версии, образ не загружался; код адаптера и Compose не менялись. Платные вызовы — 0, retries — 0, usage — не получен, расход этого исследования — **0 USD**, неизрасходованный лимит S16 — **10 USD**. Billing аккаунта не проверялся; 0 USD относится к отсутствию вызовов агента, не к балансу аккаунта или чужим расходам. Новые credentials не читались/не создавались/не передавались; штатный локальный secret scanner при проверке сопоставляет существующие dev-secret values без их вывода.

Локальная модель отложена для первого среза по DOC-075 §3.1, DOC-076 §8 и решению владельца «Ollama последним» в DECISIONS_PENDING. Общая проверка local model из Infrastructure §8.2 не объявляется выполненной; отдельного блокера первого среза она не вводит. LangGraph runtime ещё S23; совместимость здесь также не проверена.

## Предлагаемый порядок продолжения

1. Решить [NCP-16](../decisions/NORMATIVE_CHANGE_PROPOSALS.md#ncp-16--deepseek-flash-и-immutable-model-pinning) без подмены immutable version fingerprint'ом. До решения не включать профиль. Варианты и последствия готовы к review; ни один не принят автоматически.
2. Зафиксировать версию Bifrost, проверить лицензию/advisories; описать в ADR точный adapter/egress deployment. Предложение архитектора: закрытый Bifrost → ограниченный relay/proxy → только `api.deepseek.com:443`, без прямого внешнего маршрута у Bifrost/Runtime. Одна открытая Compose-сеть `egress` не ограничивает адрес назначения. Это проектный вариант, не реализованная или проверенная защита.
3. Реализовать HTTP/SSE адаптер за `LLMGatewayPort`, проверку identity по выбранной семантике, schema/tool validation, типизированные ошибки, бюджет и отмену, rate limits и telemetry без содержимого. Профиль CANDIDATE не обходить ради PoC: способ изолированного допуска тестов отдельно описать и проверить, production-like routing остаётся закрытым до человеческой приёмки.
4. До платного тестирования представить смету по актуальным официальным тарифам, пределы tokens/retries/calls и консервативный учёт неизвестных списаний. Минимальный кандидат набора: structured output, function-call generation, завершённый stream, отменённый stream; окончательный набор и стоимость пока не утверждены. Error/security ветки — локально; это не замена реальной совместимости.
5. Выполнить остальные §7 tests, независимые code/security/python/failure/test/architecture reviews, полный `make pre-pr`, Linux CI; затем отдельная приёмка Bifrost и approval профиля владельцем с аудитом. Не начинать SLICE-01/S17 автоматически.

## Связанные документы

[Отчёт S16](../increments/S16_bifrost_poc_provider_profile_REPORT.md), [независимые проверки](S16_PREFLIGHT_REVIEWS.md), G-156, OD-01/OD-21. Промпт S16 §9 содержит неточные ссылки на THR IDs: secrets — THR-004, egress/SSRF — THR-005/009, telemetry leakage — THR-018, fallback — THR-019. При продолжении использовать содержательные controls canonical Threat Model; номера в старом промпте не отменяют проверок.
