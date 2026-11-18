# G156 — изолированный запуск и фактическая конфигурация Bifrost

**Дата:** 2026-11-18. **Промпт:** [audit scope](prompts/G02_bifrost_effective_isolation_audit.md). **Статус:** проверочный срез локально TESTED; effective-config integrity enforcement OPEN, полный G156 IMPLEMENTATION NOT VERIFIED. Подготовка IN_PROGRESS; G02/S17/S20/S21 NOT_STARTED.

## 1. Результат

Новый изолированный candidate Bifrost запущен штатным `start-bifrost.sh` с фиктивными credentials и отключённым upstream. Renderer/mount/auth/selected effective settings/network/log checks прошли. **Admin PUT изменяет live client settings и SQLite при неизменных rendered config bytes, image и Docker launch/mount/network configuration.** Это воспроизведение незакрытого условия безопасности, а не его устранение. Hash template/inspect недостаточен для допуска реального запроса.

Обнаружен отдельный дефект host-инспектора: Docker возвращает `Mounts` в разном порядке между чтениями одного контейнера. Список сортируется по уже проверенному уникальному Destination перед hashing; ни одно поле mount не исключается. RED/GREEN regression проверяет одинаковый hash после перестановки и другой hash после изменения Source. Исправление устраняет ложные отказы, не контролирует mutable Bifrost state.

## 2. Основание и источники

Прямая команда владельца, полный AGENTS/CONTEXT_RETENTION, Registry v4.1, DOC076 v1.1 §3.1/5/7, DOC015 v1.7 §8/9, security/threat/secrets baseline, ADR134–136, G156 plan и действующие quality/test gates. Canonical документы, требования, permissions и очередность не менялись. Итоговая проверка наличия Registry/manifest приведена в §9.

Pinned upstream source: [config loader](https://github.com/maximhq/bifrost/blob/7cb75fb2f8276ca48d0792c857fecb67b8879e2f/transports/bifrost-http/lib/config.go), [config handlers](https://github.com/maximhq/bifrost/blob/7cb75fb2f8276ca48d0792c857fecb67b8879e2f/transports/bifrost-http/handlers/config.go), [provider handlers](https://github.com/maximhq/bifrost/blob/7cb75fb2f8276ca48d0792c857fecb67b8879e2f/transports/bifrost-http/handlers/providers.go). Изучены локальные проверенные исходники; внешний запрос использовал только общий upstream URL без проектных данных. GET config по умолчанию читает live client, `from_db=true` — ConfigStore; provider/VK queries дают выбранные DB-backed facts, не полный snapshot всех таблиц.

## 3. Scope и файлы

Ветка `feat/g02-manager-tools-planning`, HEAD `db8d4af34b0933aa2562adcf072b717eb0e3e3e9` + рабочий diff. На старте119изменённых/new files, включая прежние NCP16/OD19/canonical/SDK/host срезы. Сохранность проверяется по исходным byte hashes; прежний diff не присваивается этому checkpoint. Commit/push/PR/merge/newCI не выполнялись: общая подготовка ещё не принята, исходный большой diff автоматически не публикуется.

| Файл | Дельта этого checkpoint |
|---|---|
| `backend/src/ai_res/modules/model_registry/candidate_host.py` | Только сортировка validated unique mounts перед hash |
| `backend/tests/unit/test_candidate_host.py` | Один behavioral regression: reorder invariant + Source sensitivity |
| `backend/tests/fixtures/bifrost_effective_audit.py` | Новый disposable server без provider client и boolean-only native probe |
| `backend/tests/integration/test_bifrost_effective_isolation.py` |6native tests: actual renderer/mounts/effective/auth/network/mutation/logs |
| `docs/implementation/**` | Prompt/report/review/hash, ADR136 clarification, context/статусы/gap/traceability/ECC |

## 4. API / контракты / совместимость

Public/product API, events, schema mirrors, private control wire и host descriptor0.1 не менялись. Нет автоматического принятия старого `expectedRuntimeSha256`: exact comparison сохраняется, descriptor перед live должен быть заново построен и проверен с текущими source/runtime bindings. Реальных descriptors ранее не создавали. Version prefix hash не менялся: уточнена канонизация неупорядоченной коллекции, значения всех её полей сохранены.

## 5. Миграции и данные

Новых revisions/DDL/grants/seeds нет; frozen0020–24/snapshot неизменны. PostgreSQL/Temporal/MinIO основного стека не использовались и не мигрировались. Disposable SQLite принадлежит исключительно новому audit Bifrost. Его данные находятся в tmpfs и исчезают с тестовым контейнером; volumes основного стека не удалялись.

## 6. Фактическая среда и конфигурация

Python3.13.5, macOS26.6.2/arm64 (результат `platform.platform()`), Docker Engine29.2.0. Установленные lock-based окружения; fast без sync/network. Candidate image `sha256:ab781fd7c8032ead0009e62b577c40e29503b73e47e84742f4dd1670a8a62615`; binary SHA256 `08a355456ba9947a1fe009587e2eb4525cf1b3a0158649d968adc9a1cd4f99b8`. Patch/source/toolchain прежние ADR135; image cache использован с новым actual-binary/provenance check, не с повторным cold SDK build. Собран/переиспользован отдельный Python fixture image по actual backend build inputs, без retag основного API image.

| Наблюдение | Фактический результат |
|---|---|
| Renderer и5input mounts | Digests текущих bytes совпадают; rendered config mode0600. Hash считается внутри running mount namespace, raw rendered bytes не экспортируются |
| Live и SQLite client | Logging false, content logging disabled true, retention/offload false, per-request storage override false, direct keys false, inference auth true, drop-excess true, max body1MB |
| Zero-valued lists | API опускает пустые allowed_origins/logging_headers/whitelisted_routes; проверено отсутствие exposed nonempty override. Это не доказательство hidden empty state; template bytes проверены отдельно |
| Auth/storage/catalogues | Admin auth enabled, SQLite connected; logs/cache/object storage disconnected; три catalogue URLs — локальные file URLs |
| Provider/VK | Только DeepSeek; relay `http://llm-gateway:8081`, retry0/timeout30s; raw capture flags false; один active VK только DeepSeek Flash, allow_all_providers false, disable_content_logging true |
| Auth/model negatives | Anonymous/wrong VK/direct-key opt-in denied; VK/anonymous management denied; другая модель denied; rejected requests не доходят до relay |
| Positive control | Scoped VK доходит до отключённого relay ровно один раз; admin GET успешен. HTTP503 возвращает сам synthetic server; реального provider client в нём нет |
| Сеть | Два новых контейнера только в одной новой internal network, no published ports. Relay positive TCP проходит, numeric1.1.1.1:443 negative блокируется |
| Логи/env | Известные synthetic credentials, полный VK и content canary отсутствуют |
| Mutation | Authenticated PUT меняет drop-excess live+DB; file/image/canonical inspect unchanged; выбранные security flags/framework сохранены. Gate OPEN |

34boolean effective checks,10auth checks,5mutation и5backpressure-restore checks; consumer проверяет число полей. Для PUT upstream требует положительный `log_retention_days`, хотя bootstrap с отключёнными logs допускает dormant0: **только в disposable fixture** установлено1, logging не включается. PUT также не принимает framework MCP sync0, поэтому framework не отправляется и отдельно проверяется неизменным. Backpressure возвращается true; весь изменённый SQLite/tmpfs затем удаляется с собственным контейнером. Это не продуктовые retention settings и не полное восстановление SQLite к исходным bytes.

## 7. Решения и устранённые дефекты

[ADR136 clarification](../decisions/ADR-136-candidate-development-host.md): только канонизация mounts. Structural checks, exact image/source/config refs, final revalidation и fail-closed exceptions сохранены. Effective-integrity gate этим не закрыт; config_store нельзя просто отключить ради обхода SQLite: pinned server при nil store пропускает auth middleware. Конкретный remediation design не утверждался этим audit.

## 8. ECC и независимое review

Root применил planner/architect по source/runtime scope; явно прочитанные ECC python-testing/verification-loop — как test/evidence checklists. Contract-first прочитан для оценки необходимости; новых независимых API consumers/contract changes нет, schema machinery не добавлялась. Два отдельных blind-first read-only reviewers: `bifrost_audit_review` (general/Python/test) и `bifrost_isolation_security` (security/architect/silent-failure). Они проверили реальные файлы до отчёта автора; runtime выполнял только root.

MEDIUM provider response envelope и direct-key opt-in header исправлены; final audit/mount-order delta APPROVE/open0. Финальная test-only проверка количества полей получила отдельный delta review. Нативные Claude slash commands/hooks/QA Worker/human approval не имитировались. Полный [протокол](../reviews/G02_BIFROST_ISOLATION_REVIEWS.md), [4code hashes](../reviews/G02_BIFROST_ISOLATION_CODE_HASHES.json).

## 9. Проверки

Все команды из корня репозитория, тот же HEAD + scoped diff. Логи `/tmp/bifrost-effective-*.log` временные; эта сводка сохраняет обязательное evidence.

| Команда / gate | Результат |
|---|---|
| `backend/.venv/bin/python -B -m pytest -q backend/tests/unit/test_candidate_host.py -k runtime_mount_order --tb=short` | RED1failed/77deselected,exit1 до исправления |
| `backend/.venv/bin/python -B -m pytest -q backend/tests/unit/test_candidate_host.py --tb=short` | GREEN78passed,0failed/skipped,0.29s,exit0 |
| `backend/.venv/bin/python -B -m pytest -q backend/tests/integration/test_bifrost_effective_isolation.py --tb=short` |6passed,0failed/skipped,33.18s после fix; final после count-schema assertion6passed,7.18s,exit0 |
| `UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 make -j1 pre-push-fast` |1390passed/4existing deprecation warnings,0failed/skipped,9.74spytest,exit0; Ruff0,mypy194sourcefiles0issues,15importcontractsKEPT |
| Scoped Ruff4files, `git diff --check` |exit0 после последней test-only count-schema правки |

Fast выполнялся до последней test-only строки consumer count validation; runtime6 и scoped Ruff повторены после неё. Production source/host unit hashes с fast не менялись. Полный fast повторно без причины не запускался.

Первоначальные native попытки не объявлены PASS: tmpfs archive404; неверная обёртка provider/framework response; empty API slices; PUT dormant retention/framework validation; затем7.20s run5passed/1failed обнаружил нестабильный Mounts hash. Дополнительный read-only diagnostic подтвердил: изменился только порядок Mounts, после сортировки содержимое одинаково. Последовавший unit RED и tiny inspector correction отделены от настройки Bifrost. Одна ранняя exploratory попытка без сохранённого tool session output не используется как evidence. Проверки не отключались и skip/xfail не добавлялись.

Final read-only проверки, все exit0:

- `infra/.venv/bin/python -B infra/scripts/scan_secrets.py`:0findings.
- `python3 -B docs/implementation/tools/check_prompts.py`:40stage prompts/0issues; новый preparatory prompt отдельно сверен с командой владельца и source scope.
- Inline `python3 -B` checker прочитал Registry §2 и текущий manifest:74canonical paths/0missing/0duplicateIDs/paths,73hashes/0mismatch;4current code hashes совпадают.
- Тот же checker проверил259local file links в14task Markdown docs:0missing; external URLs и fragment anchors не проверялись.
- Baseline SHA checker:119исходных файлов,106byte-identical+13только разрешённых scoped additions/edits,0missing.13изменённых исходных путей —2source/unit и11implementation docs;6новых файлов —2audit code и4prompt/report/review/hash artifacts. Итого19затронутых task files. Diff остальных106исходных файлов не присваивается checkpoint.
- `git diff --check`:exit0. Docker list после cleanup:18existing main-stack containers running,0других running containers; native teardown дополнительно проверил неизменность всех baseline IDs/StartedAt. Это контроль запуска контейнеров, не полный data checksum основного стека.

## 10. Security cases и ограничения

G1/G2 пройдены fast/unit; G3 — только isolated native Docker audit, не реальный provider. G4 N/A product contract change; upstream response shapes проверены настоящим сервером. G5 — выбранные auth/model/egress/logs negatives и independent review, не весь security/supply-chain gate. G6 N/A migration change. G7 — два независимых source reviews, не human/security-owner acceptance. G8/G9 — checkpoint context/report/traceability.

Одна internal network синтетического стенда не доказывает будущую topology relay/control/egress из двух сетей Compose. Noports/internal membership не означает недоступность контейнеров Docker host. Numeric-IP negative не доказывает отсутствие любого egress/SSRF; DNS/multi-hop/future proxy policy не проверены. Контроль canaries не является доказательством отсутствия любых возможных утечек. GET selected settings не проверяет все SQLite tables, plugins/routing, hidden runtime state или credential identity redacted APIs. Полный SQLite/WAL snapshot не заявляется. Mounted digests отражают проверенный момент, не непрерывную неизменность.

Полный backend/PG/Temporal/pre-pr/LinuxCI/audits/digests/SBOM/real-provider/paid ledger/auth control regressions не выполнялись этим checkpoint: соответствующие поверхности не менялись, а подготовка как целое ещё не готова к приёмке. Они остаются обязательными перед VERIFIED/доставкой, исторический CI сюда не переносится. Applied0020–24/SDK hashes не обновлялись.

## 11. Документация и сохранность

Обновлены HANDOFF/STATUS, G02 passport/Flash plan, G156 gap, ADR136 clarification/ADL, requirements+contract traceability, ECC journal, prompt/index, report/review/hashes. DECISIONS_PENDING/ROADMAP/canonical/mirrors не менялись: нового owner/business решения не появилось. Исходная119file baseline сохранена за исключением явно перечисленных scoped source/unit/context дополнений.

## 12. DoD и продолжение

Проверка изолированного запуска завершена с зафиксированным отрицательным результатом по неизменности effective config. Локально протестирован tiny inspector fix. **До ключа/live нужно разработать и реализовать защиту rendered/effective/admin/SQLite configuration перед reserve/claim, с mutation/restart/failure negatives и независимым security review.** Не заменять её одним file hash/inspect hash или отключением auth-dependent store. Это ближайший подготовительный шаг.

Далее остаются owner lifecycle/product admission wiring, общие final regression/pre-pr/LinuxCI, свежие reviewed tariff/account/key setup, реальные технические observations и human Bifrost/profile acceptance, SLICE01 с собственными data/license/budget gates. До S20 отдельно ADR129/G107. Model calls0/spend0; real key/account/tariff/profile seeds не создавались. Готовность всей подготовки не достигнута, продуктовый G02 не разблокирован; новый старт группы требует явного согласия владельца после уведомления о завершении подготовки.
