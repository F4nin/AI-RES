# AI RES — LLM Gateway и Model Registry

**Версия:** 1.1 | **Статус:** BASELINED (архитектурный дизайн; Bifrost production acceptance зависит от PoC).

## 1. Цель

Единый управляемый доступ Manager/Workers к внешним и локальным моделям с независимыми политиками AI RES, измерением стоимости и воспроизводимостью.

## 2. Архитектура

`Manager/Worker Runtime → LLMGatewayPort → AI RES Gateway Adapter → Bifrost → Provider/Local Model`.

AI RES Adapter — стабильный внутренний контракт; Bifrost — предпочтительная MVP реализация за адаптером. Ни один Runtime не импортирует provider SDK.

## 3. Model Registry

Обязательные поля: `model_profile_id`, provider, provider_model_id, pinned_model_version, capability flags (chat, structured output, tool calling, streaming, vision), context window, max output, data classifications, allowed regions/egress, cost rates, rate limits, timeout, retry class, fallback group, status, evaluation manifest ref, approved_at, deprecated_at.

Model alias разрешён для routing, но каждый WorkerRun фиксирует фактические provider/model/version/profile. Evaluation и release manifest используют immutable version, кроме явно ограниченного исключения §3.1. Поле `pinned_model_version` в исходной immutable-модели не заполняется rolling alias, fingerprint, датой или версией собственного profile/config.

### 3.1 DeepSeek Flash первого среза: принятое исключение NCP-16

**BASELINED по прямому решению владельца 2026-11-17.** Только DeepSeek Flash первого среза может использовать rolling alias без доказанного immutable snapshot. Pro/прочие profiles не получают это исключение и не становятся APPROVED автоматически. Не гарантируются повторный вызов прежней модели и обнаружение скрытого drift.

- Неизменяемо фиксировать версии AI RES code/profile/config/prompt/tools; отдельно связывать вызов и результат с разрешённым request model ID и наблюдаемой provider/model identity, временем и безопасным provider request reference. Fingerprint хранить при наличии как наблюдаемую metadata, а не selector или гарантию неизменности.
- Точный состав обязательной identity metadata и допустимые значения задаются версией контракта и проходят человеческую приёмку до включения. Отсутствие обязательного значения, неизвестная или неожиданная identity — отказ; не подставлять фиктивный pin. Это требование, не новый публичный DTO: схема/persistence/совместимость ещё должны быть спроектированы.
- Первое наблюдаемое значение не считается автоматически утверждённым. Candidate probes допустимы только в отдельно разрешённом PoC с бюджетом; их ответы — evidence приёмки, не результат включённого продуктового профиля.
- При обнаруженном drift блокировать результат до публикации/применения и дальнейшие вызовы затронутого профиля до повторной оценки и отдельного человеческого утверждения с аудитом. Для streaming частичный вывод не принимается как финальный до identity validation. Проверить действие блокировки при параллельных вызовах и рестарте; недоступность обязательной проверки не разрешает вызов.
- Наблюдение ответа может обнаружить drift только после уже выполненного/оплаченного запроса; оно не предотвращает первое обновление, не доказывает отсутствие скрытых обновлений и не восстанавливает прежнюю модель. Сохранённые WorkerResult/истории не переписываются.
- Запрещены silent fallback, автоматическое APPROVED, self-grant, расширение данных/egress или бюджета. Исключение не является Bifrost/security acceptance, model profile approval, разрешением расходов или release/deployment.

До включения профиля обязательны реализация и evidence admission/drift/persistence, аудируемого approval и применимых проверок §7. На дату принятия решения runtime-механизм исключения NOT IMPLEMENTED/NOT VERIFIED; существующий adapter остаётся disabled/fail-closed. Допуск не разблокируется одной записью документа.

## 4. Routing

Policy inputs: worker_role, task_class, sensitivity, context size, required capabilities, latency/cost budget, provider health, environment. Routing is deterministic policy; LLM cannot self-select unapproved model. Fallback only to an explicitly approved profile with equal-or-stricter data handling.

## 5. Security

Credentials остаются в gateway/credential broker. Redaction before provider. No prompt/response content capture by default. Egress allowlist. Usage and provider metadata may be recorded with data minimization. Provider outage does not trigger unapproved public fallback.

## 6. Failure semantics

Classify retryable vs non-retryable provider errors; bounded retries with jitter; respect Retry-After; circuit breaker per provider/model; cancellation propagation; idempotent request correlation; unknown provider outcome is reconciled where supported, never blindly repeated for side-effecting tool calls.

## 7. Bifrost acceptance PoC

Must verify structured output/schema adherence, tool calling, streaming, cancellation, timeouts, provider error mapping, fallback policy, rate limits, usage metering, secrets, logging, egress, model pinning, multi-tenant isolation, security advisories and upgrade path. Failure of any critical security condition blocks Bifrost deployment; adapter remains and alternative gateway may be selected without domain changes.

Для исключения §3.1 вместо доказательства immutable snapshot проверяются: ограничение только утверждённым Flash; разделение управляемых версий и наблюдаемой identity; missing/unexpected metadata; отсутствие автоматического утверждения первого ответа; drift до принятия результата, включая streaming; блокировка следующих вызовов, в том числе при concurrency/restart; новая версия приёмочного evidence и повторное человеческое approval; отсутствие silent fallback; безопасные audit/logs/traces. Остальные проверки этой секции сохраняются. Реальные provider evidence нельзя заменить fixtures.

## 8. MVP boundary

One provider/model profile after PoC; abstraction supports future local/multi-provider. No self-hosted model fleet or dynamic routing optimization in first vertical slice.

## История версии 1.1

2026-11-17: прямое owner approval ограниченного варианта B NCP-16; версия 1.0 сохранена как история. Изменена только нормативная гарантия указанного Flash-среза; runtime evidence и допуск профиля не заявляются.
