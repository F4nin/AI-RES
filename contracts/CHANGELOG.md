# Contracts changelog

Формат: дата · контракт · изменение · совместимость. Зеркало canonical файлов изменяется только пересинхронизацией после новой canonical версии (ADR-009).

## 2026-11-11 — S01
- Создано зеркало: Public API v1.3, Domain Events AsyncAPI v1.6, Worker Contracts v1.1 (WORKING), Operation/Readiness Gate Schema v1.0 и State Machine v1.2 (WORKING), Continuous Improvement Contracts v1.0. SHA-256 сверены с Baseline Manifest v1.2.
- `contracts/baseline/` — принятый снимок для breaking-change detection.
- Спецификации не изменялись.

## 2026-11-11 — S07
- Overlay `openapi/extensions/identity_auth.yaml` (WORKING, ADR-038/063): `/auth/login`, `/auth/logout`, `/auth/csrf`, `/auth/password`, `/auth/mfa/enrollment`, `/auth/mfa/enrollment/confirm`, `/auth/mfa/verify`. Только добавление; canonical v1.3 не менялся. Совместимость: аддитивно.
- Spectral `aires-idempotency-key`: операция может не объявлять `Idempotency-Key` только с письменным `x-idempotency-exempt` (≥20 символов).

## 2026-11-12 — S07 (решения владельца, ADR-071/072)
- `/auth/mfa/enrollment` теперь принимает `{currentPassword}` (обязательно); неверный пароль — 422 `invalid_current_password`. `/auth/password`: неверный текущий пароль — 422 (раньше 401). Overlay WORKING; потребителей вне репозитория нет. Совместимость: изменение WORKING overlay, не canonical.
