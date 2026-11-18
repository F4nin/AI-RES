# G156 — native Bifrost isolation / effective-config audit: independent reviews

**2026-11-18.** Ветка `feat/g02-manager-tools-planning`, HEAD `db8d4af34b0933aa2562adcf072b717eb0e3e3e9` + scoped working diff. [4code hashes](G02_BIFROST_ISOLATION_CODE_HASHES.json), [author report](../increments/G02_bifrost_effective_isolation_REPORT.md).

## Scope и независимость

Root — автор/integrator/runtime owner. `bifrost_audit_review` — отдельный code/Python/test reviewer; `bifrost_isolation_security` — отдельный security/architect/silent-failure reviewer. Оба read-only/blind-first по фактическим новым helper/integration tests, затем отдельно по `candidate_host.py` canonicalization и unit regression. Первые выводы сформированы до авторского отчёта. Reviewers не писали файлы, не запускали runtime/tests/Docker и не являются авторами кода. Native результаты выполнил root; они не приписываются reviewers.

## Findings и исправления

| Reviewer | Severity | Evidence / failure | Исправление / результат |
|---|---|---|---|
| General/Python | MEDIUM | Helper ожидал wrapper `provider["provider"]`, но pinned GET возвращает ProviderResponse напрямую | `actual = provider`; source delta APPROVE |
| Security | MEDIUM | Negative direct-key probe не включал необходимый `x-bf-direct-key:true`, не проверял opt-in branch | Заголовок добавлен; source delta APPROVE |
| Root native diagnostic | False-refusal defect | Один running container возвращает Mounts в разном порядке; только этот раздел inspect меняется, sorted contents равны | Unit RED1failed/77deselected; сортировка validated unique Destination с сохранением всех полей; GREEN78hosttestsPASS, native6PASS |

## Финальные source verdicts

General/Python/test: **APPROVE/open0**, включая delta in-container stat/hash по closed path allowlist и quoted positional shell arguments, API omission caveat, disposable dormant retention1 и framework preservation. Mount-order delta: validated unique destinations до sorting, input не мутируется, reorder invariant и Source sensitivity доказаны behavioral test; stale descriptor не принимается автоматически.

Security: **APPROVE/open0**, CRITICAL/HIGH/MEDIUM/LOW0 в изменённом scope. Закрыта direct-key evidence ошибка. Raw rendered/admin/VK/provider response bytes не экспортируются; synthetic-only credentials и no-provider server, internal network/noports, resource cleanup и main-stack preservation ограничены audit. Mount-order correction сохраняет security checks и все поля hash.

Первоначальные final audit hashes: helper `b0145d1de5628936c4e3999ff63d086e5e821eac7f1da83cfd3274794d684ac4`, integration `cb151c195237ca7d7568de00002e9f22488beb65c761f0ca973bd6fbfa4d21dc`. Inspector и unit соответствуют hash artifact. После последней consumer-count assertion integration hash стал `9a1eda073bbe582d389a653b7bcaf0e543ef9bba7b3909ff1c172e87a72e144c`. **Оба reviewers отдельно проверили эту дельту и checkpoint documentation: APPROVE/open0.** Counts34/10/5/5 сверены по helper; consumer отказывает неполной/лишней summary. Runtime6PASS/7.18s и scopedRuff выполнены root после неё, production source/unit hashes прежние.

Оба final docs verdict подтвердили согласованность OPEN/G02 NOT_STARTED и ограничения omitted fields/selected DB/topology/logs/retention. После verdict root заполнил только фактические final checks: scanner0, prompts40/0, Registry74/manifest73/4codehashes0mismatch, links259/0missing, baseline119→106unchanged+13scoped/0missing, main18running/0other. Эти выполненные root проверки не являются независимым runtime review reviewers.

## Граница verdict

APPROVE относится к корректности ограниченного audit/checker diff. **Admin mutation live/SQLite при unchanged rendered bytes/image/canonical inspect воспроизведена и оставляет effective-config integrity gate OPEN.** Это не human/security-owner acceptance Bifrost/profile, не full SQLite/plugins/routing/effective-state proof и не approval live calls/SLICE/G02. Реальный ключ/accounts/tariffs не создавались;modelcalls/spend0. Full pre-pr/LinuxCI всей подготовки ещё нужны.
