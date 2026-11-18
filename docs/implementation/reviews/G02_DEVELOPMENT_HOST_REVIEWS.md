# G156 / ADR136 — независимое review development host

2026-11-18, `feat/g02-manager-tools-planning`, HEAD `db8d4af34b0933aa2562adcf072b717eb0e3e3e9` плюс uncommitted scope. Точные10code/test hashes — [артефакт](G02_DEVELOPMENT_HOST_CODE_HASHES.json). Исторический SDK review не переносится на новые файлы.

## Независимость и метод

`host_plan` отдельно применил ECC planner/architect к существующим interfaces/ADR133–135, затем написал только candidate_host.py/test_candidate_host.py. Root написал composition/account reader/source binding/standalone listener/tests и документацию. Авторы не считаются reviewers своих файлов.

`host_python_review`: отдельный blind-first read-only general/Python/database-query/pr-test-analyzer. `host_security`: отдельный blind-first read-only security/architect/silent-failure reviewer всего нового среза. Оба сначала исследовали фактический код, без авторского отчёта. Claude native agents/hooks/slash commands не запускались. Проверяющие не запускали Docker/DB/HTTPS/model calls.

## Findings и закрытие

CRITICAL/HIGH не обнаружены. MEDIUM устранены и проверены повторно:

- Структурный Docker gate принимал root и `no-new-privileges:false`: теперь exact nonroot/NNP checks и negative tests. Security reviewer самостоятельно воспроизвёл прежнее принятие synthetic inspect record read-only Python smoke.
- Одно чтение stdout могло обрезать Docker JSON: bounded loop, timeout/cancel/overflow cleanup и split-read tests.
- Локальные файлы могли измениться во время HTTP/Docker await: final local re-read после последнего observer и mutation test.
- Git provenance наследовал redirect overrides: GIT_* очищаются, actual top-level проверяется, actual two-repository fixture доказывает поведение.
- Любая printable строка принималась как virtual key: теперь только complete Bifrost format; provider-shaped/rawhex/malformed mounts отклоняются без echo.
- Concrete factory предполагала единственный Docker executable/socket: добавлена явная trusted observer injection; environment/context auto-discovery не вводится.
- Произвольный root мог описывать другой checkout: root должен совпасть с выполняемым source checkout. После изменения кода требуется новый процесс; hot-reload provenance не заявляется.
- Settings prod/default-prod не отказывали заранее: local/test-only плюс API role до config/resources; negative tests.
- Control composition lifecycle/per-claim tests отсутствовали: добавлены revalidation, account check, settlement после revoke, cleanup construct/cancel.
- Новый PG-test использовал autobegin=False session без begin: исправлено; final actual PG22cases PASS. Это defect теста, не query.
- Git fixture мог наследовать hooks/signing: global/system config исключены, hooks disabled, signing false, timeout5. Final scanner false-positive в synthetic env fixture исправлен коротким fake value+соответствующим no-echo assertion; независимая security delta APPROVE/open0, production5hashes неизменны.

Env-only standalone listener теперь accounting-only: claims DENIED даже при activation=true; settlement остаётся authenticated HTTPS и engine закрывается lifespan. Новый trusted control context предоставляет gated claims, не монтирует публичный API и сам не создаёт listener.

## Итог и собственные проверки reviewers

Python/general/database: **APPROVE, open0**. Собственные read-only AST8PASS, Ruff10files exit0, diffcheck0. Security: **APPROVE, open0** по source и последующей test-only delta. Его structural reproduction и actual `_git_head` read-only smoke exit0; runtime выполнения не приписываются reviewer.

Root runtime evidence — [отчёт](../increments/G02_candidate_development_host_REPORT.md): fast1389PASS, affected142PASS, realPG22PASS. Review — оценка source/test scope, не human security-owner/Bifrost/profile approval.

## Сохраняющиеся границы

Docker inspect связывает immutable image/launch config/mount mappings и hashes текущих host files. Bytes уже смонтированного inode после atomic replace не проверены. Он **не** доказывает неизменность rendered `/app/data`/SQLite Bifrost configuration, actual network isolation или отсутствие admin mutations. Это отдельная обязательная проверка до live. Официальный HTML snapshot не доказывает правильность reviewed rates; реальные descriptor/account/key setup сейчас отсутствуют. G156/pre-pr/LinuxCI/live/provider acceptance/SLICE/G02 остаются незавершёнными.
