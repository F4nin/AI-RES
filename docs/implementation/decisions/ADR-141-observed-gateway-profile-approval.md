# ADR-141 — завершение product wiring и human profile approval G156

**Дата:** 2026-11-18. **Статус:** ACCEPTED, техническая реализация в существующем
поручении G156. Это не новый подготовительный этап и не утверждение реальной модели.
Основание: DOC-076 v1.1 §3.1/7, IAM v1.5 §7–8, Auth v1.1 §5–6,
DOC-068 v1.1, Blueprint v1.0, OD-01/21 (владелец лично через CLI/API с аудитом).

## Решение

Explicit `bifrost-observed` composition использует существующий GovernedLLMGateway,
backend ModelRegistryAdmission и durable ModelAdmissionGuard. Default остаётся
unconfigured; injected authorizer, managed-version resolver, registry, transport
и budget ledger обязательны. Только Flash observed / NULL pin / NONE retries,
без embedding/fallback. Никаких DB credentials у Runtime.

Перед provider I/O коммитится unresolved receipt. Результат доступен только после
durable finalize; caller authorization и exact request-specific managed versions
проверяются перед finalize и после возможных DB waits. SSE буферизуется до native
terminal validation/finalize, в пределах существующего transport max_stream_bytes.
Любая внутрипоточная identity/reference или terminal-envelope inconsistency
финализируется как malformed, даже если последняя identity совпадает с принятой.
Timeout/cancel/unavailable outcome не очищают pending и сохраняют worst-case budget.

Оставшийся profile activation выполняется отдельным offline owner/migrator CLI
`python -m ai_res.cli.model_profile`. Это не API/router и не расширение narrow
EXECUTE-only identity operator ADR140. Используются уже существующие права
owner/migrator; новые roles, grants и migrations не нужны. CLI по умолчанию только
preview. Execute требует exact decision UUID confirmation, существующий MFA session
token без echo, отдельную обычную API identity для authentication и provisioned
owner connection/binding для mutation. Packaged policy по-прежнему deny; CLI не
создаёт ALLOW или account/session/binding. Входные файлы bounded, owned, regular,
без symlink и shared write; ошибки не выводят входные данные.

Human command отдельно связывает complete immutable profile snapshot, expectation,
observation и SHA-256 конкретного Bifrost acceptance artifact. Его предоставление
не доказывает quality/security evidence: приёмку делает человек. Проверяются live
member/user/factor/session, Policy вне UoW, затем повторные факты после waits.
Global approval fence сохраняет ограничение одного APPROVED профиля; invalid
executable profile, blocked/pending/stale generation отвергаются. Lifecycle UPDATE
и append-only audit с decision UUID атомарны. Replay требует fresh auth/Policy,
совпавший command digest и реальные immutable approved_by/approved_at; повтор не
снимает поздний block и не меняет lifecycle.

## Альтернативы и границы

Расширение EXECUTE-only principal потребовало бы additive0027 и новых grants.
Для этого административного одноразового пути выбраны существующие owner права;
они не выдаются API, Manager/Worker или модели. Frozen0026 не изменяется.
Audit table не имеет отдельного DB-enforced writer provenance; replay дополнительно
связан с фактическим immutable lifecycle. Полностью скомпрометированный owner вне
гарантий этого helper. Происхождение real provider evidence и человеческое решение
не подменяются hashes или успешными synthetic tests.

Public API/events/contracts/baselines/canonical documents не меняются. Управляемые
версии и observable metadata остаются разными фактами. Не реализуются новые бизнес-
поля, monthly budget, словарь data labels, grants, bootstrap или release/deployment.
Actual human Bifrost/identity/profile acceptance и OD21 остаются до включения;
SLICE-01 имеет отдельные data/license/budget gates. G02/S17/S20/S21 не стартуют.

## Evidence

Два независимых general/Python/architecture и security/database source reviews;
закрыты reverse-SSE durable block, final caller authorization, CLI Pydantic
composition, getpass fallback, second-profile и invalid executable candidate.
Actual PG tests проверяют commits до dispatch, block после reconnect, revoke,
generation/audit failures/cancel, approval/replay/concurrency, audit rollback,
policy-wait revoke, audit-wait session expiry и реальную CLI composition.
Точные counts/commands/SHA и ограничения — в существующем
[G156 отчёте](../increments/G02_identity_admission_operator_REPORT.md) и
[review протоколе](../reviews/G02_OBSERVED_APPROVAL_REVIEWS.md).
