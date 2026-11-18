# G156 — observed gateway и человеческое утверждение профиля

**2026-11-18.** Продолжение существующего G156; два независимых read-only
проверяющих. Author reports/checkpoint knownFinding не читались до первого
собственного source pass. Root — автор fixes/CLI/PG tests/integrator/runtime;
activation_scope — автор profile_approval.py и его unit tests, не reviewer себя.

`observed_general_review`: явно прочитанные ECC code-reviewer, python-reviewer,
silent-failure-hunter; scope correctness/async/compatibility/architecture/tests.
`observed_security_review`: security-reviewer + database/architecture checklist;
scope identity/authorization/lifecycle/locks/replay/budget/redaction/paths.
Проверяющие только читали source и считали hashes; tests/Docker/CI/provider calls
выполнял root. Native Claude commands/hooks и product QA не имитируются.

| Находка | Исправление | Итог |
|---|---|---|
| HIGH: X→approved Y в SSE оставлял receipt VALIDATED | inconsistent stream/terminal → no observation; reverse drift/ref/envelope regressions | CLOSED, оба APPROVE |
| HIGH/security, MEDIUM/general до activation: caller revoke после begin | bound exact profile/request + authorize/managed versions до и после durable finalize | CLOSED, оба APPROVE |
| HIGH: dataclasses.replace для Pydantic Settings ломал CLI execute | validated Settings construction; реальный `_execute` unit и PG composition | CLOSED, оба APPROVE |
| HIGH/security: второй APPROVED мог обойти ограничение первого профиля | global approval lock + current other-APPROVED check | CLOSED, security APPROVE |
| MEDIUM: invalid observed candidate мог сломать executable registry после approval | reuse ModelProfile loader validation до lifecycle write | CLOSED, security APPROVE |
| MEDIUM: getpass fallback мог читать credential с echo | GetPassWarning переводится в refusal до stdin fallback | CLOSED, security APPROVE |
| Test failure: reason code искали в безопасном exception message | assertions по AdmissionDenied.code | CLOSED, general APPROVE |

Оба final source verdict: **APPROVE, open findings 0**. Проверенный source —
[hash artifact](G02_OBSERVED_APPROVAL_CODE_HASHES.json). После verdict добавлены
рекомендованные PG policy-wait/session-expiry/real-CLI composition cases; отдельный
source-only delta review зафиксирован ниже при завершении.

Review не является human Bifrost/model/profile approval, actual real-provider
timeout evidence, полномочием выдать grants или разрешением запуска G02/SLICE.

**Финальные delta reviews:** оба APPROVE для test trigger-entry sequence и
эквивалентного CLI validated-config refactor; general reviewer отдельно APPROVE
для последнего fixture_inputs/trailing-comma layout. Runtime source unchanged:
profile_approval16b6f6c…, CLI f58e30f…, final PG5763bee… . Final artifact содержит
эти exact hashes. Root affected31PG PASS, fast1538PASS, scanner0findings; весь
backend2853PASS до эквивалентного config refactor. Infra369/runtime148/PoC19PASS.
