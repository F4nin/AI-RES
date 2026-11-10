# AI RES — LLM Gateway и Model Registry

**Версия:** 1.0 | **Статус:** BASELINED (архитектурный дизайн; Bifrost production acceptance зависит от PoC).

## 1. Цель

Единый управляемый доступ Manager/Workers к внешним и локальным моделям с независимыми политиками AI RES, измерением стоимости и воспроизводимостью.

## 2. Архитектура

`Manager/Worker Runtime → LLMGatewayPort → AI RES Gateway Adapter → Bifrost → Provider/Local Model`.

AI RES Adapter — стабильный внутренний контракт; Bifrost — предпочтительная MVP реализация за адаптером. Ни один Runtime не импортирует provider SDK.

## 3. Model Registry

Обязательные поля: `model_profile_id`, provider, provider_model_id, pinned_model_version, capability flags (chat, structured output, tool calling, streaming, vision), context window, max output, data classifications, allowed regions/egress, cost rates, rate limits, timeout, retry class, fallback group, status, evaluation manifest ref, approved_at, deprecated_at.

Model alias разрешён для routing, но каждый WorkerRun фиксирует фактические provider/model/version/profile. Evaluation и release manifest используют immutable version.

## 4. Routing

Policy inputs: worker_role, task_class, sensitivity, context size, required capabilities, latency/cost budget, provider health, environment. Routing is deterministic policy; LLM cannot self-select unapproved model. Fallback only to an explicitly approved profile with equal-or-stricter data handling.

## 5. Security

Credentials остаются в gateway/credential broker. Redaction before provider. No prompt/response content capture by default. Egress allowlist. Usage and provider metadata may be recorded with data minimization. Provider outage does not trigger unapproved public fallback.

## 6. Failure semantics

Classify retryable vs non-retryable provider errors; bounded retries with jitter; respect Retry-After; circuit breaker per provider/model; cancellation propagation; idempotent request correlation; unknown provider outcome is reconciled where supported, never blindly repeated for side-effecting tool calls.

## 7. Bifrost acceptance PoC

Must verify structured output/schema adherence, tool calling, streaming, cancellation, timeouts, provider error mapping, fallback policy, rate limits, usage metering, secrets, logging, egress, model pinning, multi-tenant isolation, security advisories and upgrade path. Failure of any critical security condition blocks Bifrost deployment; adapter remains and alternative gateway may be selected without domain changes.

## 8. MVP boundary

One provider/model profile after PoC; abstraction supports future local/multi-provider. No self-hosted model fleet or dynamic routing optimization in first vertical slice.
