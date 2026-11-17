# S16 — Bifrost PoC и первый provider profile: Increment Report

**Дата:** 2026-11-17 · **Промпт:** [S16](prompts/S16_bifrost_poc_provider_profile.md). **Реализация независимого среза:** TESTED локально (`pre-pr` exit0), ожидается кодовый Linux CI. **Приёмка полного S16:** BLOCKED (immutable pinning / NCP-16 и реальные provider-проверки). **IMPLEMENTATION NOT VERIFIED для реального DeepSeek; S16 не DONE.**

## 1. Что реализовано

После явно разрешённого старта S16 выполнен документальный pinning sub-PoC и затем реализованы независимые от нормативного решения части:

- Native HTTP/SSE `BifrostTransport` за существующим `ProviderTransport`: строгий разбор identity/usage/finish, schema/tool validation, bounded bytes/events/arguments, incremental SSE, закрытие HTTP при отмене; fixed internal URL, scoped VK, no cookies/ambient proxies/redirects/retries/fallback.
- Fail-closed immutable evidence: встроенных bindings нет; известные rolling aliases DeepSeek отвергаются до HTTP даже при фиктивном version label/binding. Factory по умолчанию остаётся unconfigured, настоящих model profiles не добавлено.
- Отдельный HTTPS relay: fixed `api.deepseek.com:443`, разрешённый POST path/model/формат/tokens, отдельная service auth; проверка всех DNS IP на public и numeric connect с исходными Host/SNI + TLS verification. Provider credential заменяется только в gateway boundary. Live flag и provider-key mount отсутствуют в поставляемом overlay.
- Закреплённый Bifrost 2.5.1 в opt-in Compose. Gateway-only случайные dev credentials через существующий SOPS/age механизм; renderer пишет mode0600 config в tmpfs без secret argv/env. Admin Basic auth и отдельный scoped inference VK. Временный SQLite config/auth store на tmpfs, logs/content stores выключены. Каталоги pricing/params/MCP локальны, без внешнего bootstrap и фиктивного model pin.
- Консервативный учёт неизвестного списания: post-dispatch parse/identity/network failures, timeout/cancel и stream без usage сохраняют весь резерв. Typed preflight без dispatch не списывается. Исходный deterministic double сохраняет прежнюю семантику.
- Поведенческие unit/security tests, изолированный no-paid runtime probe, Compose policy, Make/CI/supply-chain integration, runbook, план минимальных платных проб и смета.

Внешних DeepSeek inference/API-запросов — 0, платных попыток — 0, расход агента на модель — 0 USD; остаток общего лимита S16 10 USD. Это не проверка баланса аккаунта или чужих расходов. Реальный provider key не создавался и не читался. Три новые локальные dev credentials созданы штатно; прежние значения сохранены, затем повторный init — 0 written.

## 2. Нормативная база и проверка Registry

Registry v4.1: 74 records / 74 unique IDs / 74 unique paths, missing0 (read-only check, не содержательная сертификация всего baseline). Применены DOC-076 §2–8, DOC-075 §3, DOC-078 §5, API Contracts v1.10 §11, Infrastructure v1.7 §8/9, Security v1.2 §6/9, Secrets v1.1 §2–4, Threat Model v1.1 и Spec §3/8/9; применимые startup sources и текущие owner/ADR decisions прочитаны исполнителями в своём scope. Canonical/Registry не менялись. Исторические версии разрешались через Registry. Лицензия закреплённого OSS source — [Apache2.0](https://github.com/maximhq/bifrost/blob/7cb75fb2f8276ca48d0792c857fecb67b8879e2f/LICENSE).

**Discrepancy:** public DeepSeek API документирует обновляемые aliases без подтверждённого immutable selector. Fingerprint или текущая версия в профиле этого не исправляют. Отсутствие public docs не исключает private endpoint. [Evidence](../reviews/S16_MODEL_PINNING_POC.md), [NCP-16](../decisions/NORMATIVE_CHANGE_PROPOSALS.md#ncp-16--deepseek-flash-и-immutable-model-pinning). Local-model не блокирует первый срез: DOC-075 §3.1 + DOC-076 §8 и owner Ollama-last; не объявляется PASS.

## 3. Созданные и изменённые файлы

| Область | Файлы / изменение |
|---|---|
| Backend | `backend/src/ai_res/llm/adapters/{__init__,bifrost}.py`, `gateway.py`, `errors.py`: transport и внутренний possibly_billed marker |
| Backend tests | `test_bifrost_adapter.py`, `test_llm_egress.py`, `test_llm_gateway.py` |
| Infra candidate | `infra/compose.llm-poc.yaml`, `infra/llm_poc/{relay.py,start-bifrost.sh,config.template.json,pricing.json,model-parameters.json,mcp-library.json}` |
| Infra checks | `check_compose.py`, `secrets_dev.py`, `check_llm_poc.py`, `supply_chain.sh`; tests `test_llm_poc_policy.py`, `test_bifrost_config.py`, `test_check_llm_poc.py`, существующий `test_check_compose.py` |
| Delivery | Makefile, `.github/workflows/ci.yml`: opt-in local commands, полный pre-pr/CI проверяет candidate; scanner включается с AI_RES_SCAN_LLM_POC=1 |
| Docs | Этот отчёт, pinning evidence, [implementation review](../reviews/S16_IMPLEMENTATION_REVIEWS.md), [paid-test plan](../reviews/S16_PAID_TEST_PLAN.md), [runbook](../../runbooks/llm-gateway.md); status/handoff, ADL ADR-122, G-156/NCP-16, pending decisions, ECC и traceability |

## 4. Изменения API / контрактов / событий

Публичный API/OpenAPI/AsyncAPI/Worker DTO и зеркало `contracts/` неизменны. `LLMError.possibly_billed` — внутренний необязательный metadata-флаг (defaultFalse), новый adapter marker opt-in. Не добавлены business fields, approval endpoints или Model Registry bypass.

## 5. Миграции и совместимость

Нет Alembic-ревизий, записей в Model Registry или изменения доменной схемы. SQLite Bifrost — его временная служебная конфигурация на tmpfs, не доменное хранилище AI RES. Нормальный `make up` сохраняет прежний состав; отдельный overlay/profile включается для PoC и полного validation. Volumes не удалялись; обычные локальные migration job и синтетические данные полного существующего test-набора охвачены разрешением AGENTS §10.

## 6. Решения, принятые самостоятельно

**ADR-122 ACCEPTED:** отключённая интеграция, relay topology, ephemeral config/auth store, локальные каталоги и консервативный неизвестный расход. Технический мандат в действующем scope; это не human acceptance Bifrost, не APPROVED модель и не исключение из pinning baseline. NCP-16 остаётся PROPOSED.

## 7. Устранённые несогласованности / NCP

Model pinning исследован без ложного immutable claim. В реальном контейнере первоначальная file-only auth/default remote pricing конфигурация не стартовала: auth требует store, pricing bootstrap требовал внешний сайт. Исправлено временным config store и readonly file:// catalogs, без открытия внешнего маршрута Bifrost. Scanner выявил два false-positive оформления: placeholder admin password и длинное expression в тесте; изменено представление, scanner/allowlist не ослаблены. Ошибочные THR IDs старого промпта трактуются по содержательным canonical controls; local-model scope уже разрешён baseline, нового blocker не создаётся.

## 8. ECC: фактически использованные agents, skills, commands

`planner` — отдельный preimplementation план и source research; `architect` — отдельная оценка topology/pinning и scope local-model; TDD и python-testing/tdd-workflow — прочитанные checklists у исполнителей с тестами до/вместе с кодом. `tdd-guide` — отдельное retrospective test-design review и мутации4/4 в памяти, без ложного утверждения RED хронологии. `code-reviewer`/`python-reviewer`/`pr-test-analyzer` — независимые взаимные review чужих файлов; `security-reviewer`/`silent-failure-hunter` — отдельный reviewer всего среза. `doc-updater`/`verification-loop` — checklist исполнителя. Полный набор нативных Claude slash commands не запускался; применены доступные Codex agents/checklists. Context7/Serena не экспонированы; компенсация — локальные файлы и официальная документация без project-content egress. Подробности — ECC_USAGE и review report.

## 9. Тесты и проверки

База чистый `main`/`origin/main` `37b9a37edb04d31b448c44e9b64052b19cb411d7`, сверена fetch/diff. Текущий implementation run — `72865e824c055aa426a4b8dbface1044a723e051` + описанный рабочий diff; опубликованный кодовый SHA будет зафиксирован после commit. Среда Darwin25.6.0 arm64, Python3.13.5, uv0.11.31, временный Node22.23.5/npm10.9.9 и установленный OpenSSL3 через PATH только процесса.

| Gate / команда | Фактический результат |
|---|---|
| Registry read-only check | 74 records/unique paths, missing0, exit0 |
| `make -j1 pre-push-fast` после кода | exit0:625passed,14kept/0broken,4warnings; mypy150files. Первая sandbox-попытка exit2 (uv cache access), повтор штатно вне sandbox PASS |
| Целевые backend tests adapter/relay/gateway | 202passed,0failed/skipped,exit0 после исправления Unicode; синтетические HTTP/ASGI fixtures |
| Targeted infra policy/renderer/checker | 114passed,exit0; новые probe preflight tests4passed отдельно |
| TDD / мутации | Adapter/relay initial import RED; budget13failed→57passed; Unicode tools2failed и content/relay4failed→GREEN; isolated policy/probe mutations4/4 detected |
| `make llm-poc-up` | После offline/auth исправления exit0, оба container healthy. Bifrost index5ec9873… (amd64/arm64), transport2.5.1 |
| `make llm-poc-check` | 19passed/0failed,exit0: реальные local auth/isolation/log/env проверки; не provider compatibility |
| Первый полный `make -j1 pre-pr` | exit2 на secret scan: contracts22,Renovate10,backend1461passed/540warnings,14kept; 2 scanner findings исправлены. Нельзя объявлять полный PASS |
| Заключительный `make -j1 pre-pr` | exit0: contracts22,Renovate10,backend1461/540warnings,infra369,отдельныйruntime148,PoC19passed;failed/errors/skipped0;secret scan0. Лог `/private/tmp/s16-pre-pr-final.log`. Команда: PATH Node22.23.5/OpenSSL3 + UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 make -j1 pre-pr |
| Ruff/mypy/shell/diff | ruff backend/infra PASS; backend mypy150files и relay strict1file PASS; shell syntax/diff PASS |
| Secret scan после исправления | `PYTHONDONTWRITEBYTECODE=1 infra/.venv/bin/python -B infra/scripts/scan_secrets.py` exit0/0findings |
| Prompts / ссылки | check_prompts.py exit0:40prompts/0issues; read-only local link/anchor check16Markdown files/106links/0issues |
| Remote digests | `make infra-verify-digests` exit0:21pinned images/0mismatch |
| Linux CI кодового SHA / additional jobs | Ещё не опубликован код. Ранние docs-only contracts runs ниже не считаются CI реализации |

## 10. Security / authorization cases

Доказаны локально: до HTTP отказ CANDIDATE/unknown/empty evidence/fake alias pin, metadata mismatch/fallback refusal; bounded malformed JSON/SSE/tools, отсутствие внешних schema refs/cookie carry-over; cancellation cleanup; uncertain charge вместо освобождения бюджета; DNS public-only, numeric IP/TLS SNI construction, запрет redirects/headers/paths/models/server tools; immutable disabled relay config перед no-paid probe. Реально в контейнере: anonymous/wrong VK и admin misuse denied, scoped VK не управляет gateway и не допускает Pro, admin positive control, relay reachable, direct external route denied, no host ports, нет credential values в env и canary content в logs. Mock TLS options не доказывают реальную provider TLS/совместимость. Общий hard provider spend cap/межпроцессный durable budget не доказаны.

## 11. Независимое review

[Протокол](../reviews/S16_IMPLEMENTATION_REVIEWS.md). Отдельный security/failure reviewer всего среза и reciprocal code/Python/test review исключали собственные файлы авторов. Исправлены MEDIUM invalid-Unicode parsing и порядок no-paid preflight. Открытых CRITICAL/HIGH/MEDIUM/LOW на проверенном отключённом срезе0. Это не owner/security acceptance настоящего provider path. Финальные numerical/evidence-only docs updates отдельно не объявляются повторным runtime review.

## 12. Не выполненные проверки, ограничения, риски

NCP-16, реальная immutable identity, DeepSeek compatibility/structured output/tool calling/stream/cancel/429/billing и human acceptance остаются невыполненными. API Chat provider не следует считать поддерживающим native json_schema только по fixtures Bifrost: реальная feature mapping ещё проверяется до включения профиля. G-145 durable budget/placement, G-146 audited profile approval, G-149 Collector LLM metadata, G-150 classification из ContextPackage и G-151 vocabularies сохраняются. Input token estimate остаётся WORKING, unknown reservation не равен точному billing. Локальная модель отложена; LangGraph runtime S23 не реализован. GitHub при push сообщил два существующих открытых lodash alerts (high/medium) в `contracts/package-lock.json`, read-only API подтвердил; зависимости не менялись, это не новый чистый dependency audit и не scope их обновления.

## 13. Обновлённые документы и статусы

Scope в §3; implementation sources/status/traceability обновляются по фактическим gates. Canonical, Registry и contracts не редактировались. PROF-01 не запускался; работа остаётся в S16, SLICE-01/S17 не разблокированы.

## 14. Статус DoD

- Выполнен независимый кодовый срез adapter/relay/Compose/negative tests/no-paid live PoC, ADR/runbook/план расходов, независимые review.
- Финальные локальные gates PASS; новый кодовый Linux CI ожидается и сохраняется по факту.
- Не выполнены полный DOC-076 §7 live-provider suite, точный profile approval path/metadata и human Bifrost/model acceptance. **S16 не DONE, реальный provider path NOT VERIFIED.**
- N/A для этой дельты: публичные contract/API/event изменения, Alembic migration/RLS изменения.

## 15. Можно ли начинать следующий этап

Нет автоматического перехода. Дальше продолжается тот же S16: решение NCP-16, защищённый provider-key setup, точный допуск изолированных реальных тестов по подготовленной смете, оставшиеся tests/review/gates, затем human acceptance. Технические доработки и sandbox escalation не являются разрешением ослабить BASELINED.

## 16. Доставка

[PR #28](https://github.com/F4nin/AI-RES/pull/28), ветка `feat/s16-bifrost-poc`. Первый head `72865e8` содержал только документальный pinning checkpoint; [contracts push44079543077](https://github.com/F4nin/AI-RES/actions/runs/44079543077)/[PR44079591347](https://github.com/F4nin/AI-RES/actions/runs/44079591347) success,22passed в каждом,0failed/skipped; PR-only baseline guard на push неприменим. Эти runs не доказывают последующий код. Кодовый head, новый полный CI и итоговый PR state фиксируются после фактической публикации. Merge независимого отключённого среза допускается после его review/pre-pr/точного Linux CI по AGENTS§10; это не acceptance Bifrost/model и не DONE полного S16. Приёмка остаётся BLOCKED до решения NCP-16 и оставшихся provider/human gates.
