# G156 — Candidate egress и runner: подготовительный отчёт

**Последующий checkpoint ADR135,2026-11-18:** SDK/build/native-fixture локально TESTED,32runtimecases(24patched+8official)PASS; patched synthetic SSE дефект исправлен, original official-image negative сохранён. [Финальное продолжение](G02_bifrost_candidate_patch_REPORT.md), [актуальный handoff](../CONTEXT_HANDOFF.md). Остальная запись ниже — evidence checkpoint ADR134 до patch;49file hash manifest отражает тот snapshot, а не последующее изменение общего fake helper. Current9file SDK/build/test hashes сохранены в новом отчёте. G156/live/profile/SLICE/G02 не завершены; работа остановлена по просьбе владельца до новой команды.

**Дата:** 2026-11-18. **Промпт:** [подготовительный scope](prompts/G02_candidate_egress_preparation.md). **Статус:** IN_PROGRESS; отдельные компоненты локально TESTED, **полный G156 IMPLEMENTATION NOT VERIFIED**. G02 и S17/S20/S21 NOT_STARTED; старт группы требует нового явного согласия владельца.

## 1. Реализованный scope

Отключённый candidate path: фиксированные synthetic requests → настоящий Bifrost → relay → private HTTPS claim в backend → единственный dispatch → durable settlement. Backend account/plan/tariff задаются серверной композицией. Отдельный runner резервирует попытку, fsync-ит INTENT, повторно проверяет host gate, выполняет один probe и сверяет точную попытку с durable accounting. Он не выполняет claim/settlement/retry/refund и не утверждает профиль.

Положительные native-Bifrost TEXT/JSON/TOOL проверки проходят на fake upstream. **Native SSE пока несовместим:** официальный pinned Bifrost теряет fingerprint в синтетическом terminal chunk. Адаптер отказывает; успешная отрицательная проверка не является поддержкой SSE. Concrete trusted host/freshness/key setup, product observed-profile wiring/owner lifecycle, live evidence, человеческая приёмка и SLICE-01 остаются незавершёнными.

## 2. Нормативная база

Registry v4.1; DOC075/076/078 v1.1 и manifest v1.3 из исходного локального diff; DOC076 §3.1/5/7, IAM/Auth service identities, ADR128–134. Required fingerprint VALUE для expectation сохраняется. Candidate ABSENT/NULL — факты, не approval. Canonical документы, mirror-map и compatibility baseline текущим срезом не изменялись. Общий technical budget остаётся одним исходным разрешением 2026-11-17: ≤10 USD и ≤8 попыток; смена даты не создаёт новый бюджет.

## 3. Файлы

| Область | Файлы / изменение |
|---|---|
| Pure LLM | `llm/candidate_payload.py`, `candidate_probe.py`; `llm/adapters/candidate_control.py`, `flash_candidate.py`: codec, private TLS client, profileless native probe, metadata-only evidence |
| Backend | `modules/model_registry/poc_control.py`, `candidate_runner.py`; `api/poc_admission_api.py`, `serve_candidate.py`; `cli/flash_candidate.py`: fixed-account service, отдельная app, mandatory TLS, bounded runner/source binding/JSONL |
| Relay | `infra/llm_poc/relay.py`: mandatory onceclaim, exact canonical outgoing bytes, settlement before success/DONE, redaction, private service identity |
| Contract | `contracts/internal/flash-candidate-control.v0.1.schema.json`; `tests/contract/test_candidate_control_contract.py` |
| Unit | `test_candidate_payload.py`, `test_candidate_control_client.py`, `test_flash_candidate.py`, `test_poc_admission_api.py`, `test_serve_candidate.py`, `test_flash_candidate_cli.py`; изменён `test_llm_egress.py` |
| Integration | `test_candidate_control_tls.py`, `test_flash_candidate_bifrost.py`, `fixtures/flash_candidate_fake_relay.py`; PostgreSQL: `test_llm_poc_control.py`, `test_llm_poc_control_tls.py`, `test_candidate_runner.py` |
| Implementation docs | ADR134, prompt, этот отчёт и review; HANDOFF/STATUS/G02_WORK/KNOWN_GAPS/traceability/ECC |

Backend paths в таблице относительны `backend/src/ai_res/`; tests — `backend/tests/`. Переносимая сборка fake-relay fixture проверена: собственный content-addressed cache и запуск immutable image ID; основной `ai-res/api:dev` не используется и не изменён. `.dockerignore` и COPY inputs читаются только после NOFOLLOW/NONBLOCK/fstat/type/size checks, tar ограничен32MiB.

## 4. API / contracts / events

Новая WORKING internal control schema0.1 и отдельная private app: POST `/candidate/v1/claim`, POST `/candidate/v1/settlement`. Нет mount в product public/internal app, reserve/account-create/profile-approve HTTP, новых domain events или изменения публичных DTO. Existing Ed25519 ar1: LLM_GATEWAY issuer → API audience + узкая capability. HTTPS, точные version/codec/hash/size/template/cap обязательны. Caller не выбирает account/rates/charge/permissions.

## 5. Persistence / совместимость

Нового DDL нет; используются frozen0020–0024. PostgreSQL tests создавали только disposable fixtures, не мигрировали основной dev stack. Ledger reservation/claim/audit коммитятся до разрешения dispatch. Ошибочный usage блокирует и удерживает полный резерв; UNKNOWN не освобождает его. Потеря callback ACK после commit может оставить уже SETTLED запись: relay не делает противоположный UNKNOWN/retry, DB остаётся истиной. Product gateway/factory/immutable profile guards не включались.

## 6. Технические решения

[ADR134](../decisions/ADR-134-candidate-egress-claim.md): online private-TLS backend claim вместо нового offline signed permit/replay cache. Synthetic marker находится внутри каждого нового body; permanent bodyhash uniqueness исключает привязку старого запроса к новой reservation. Native probe не получает fake APPROVED profile, provider key или domain DB. Source binding учитывает HEAD и разрешённые dirty source bytes, с ограниченным обходом и запретом чтения credentials/artifacts.

## 7. Найденные несовместимости

Actual pinned image `maximhq/bifrost:v2.5.1@sha256:5ec9873acaf1687556b6e4dd854b92b539d9debf87a5a683b66338648b84d3c8`:

- Bifrost опускает `stream:false`; codec уже допускает только этот документированный default.
- Для SSE добавляет ровно `cache-control: no-cache`; relay принимает только это одиночное значение, другие значения/дубли отказывает до dispatch.
- Иной returned model label отмечается как server-side fallback. Две отрицательные проверки сохраняют отказ; совместимость фактического provider label ещё неизвестна.
- При одинаковом непустом upstream fingerprint первый native chunk содержит его, а synthetic terminal finish+usage содержит пустую строку. Strict adapter отказывает INVALID_RESPONSE. **Проблема открыта**, first-value fill/игнорирование terminal fingerprint запрещены.

Primary-source проверка commit `7cb75fb2f8276ca48d0792c857fecb67b8879e2f`: DeepSeek использует [OpenAI streaming handler](https://github.com/maximhq/bifrost/blob/7cb75fb2f8276ca48d0792c857fecb67b8879e2f/core/providers/openai/openai.go#L1491); его synthetic terminal строится через [helper без fingerprint](https://github.com/maximhq/bifrost/blob/7cb75fb2f8276ca48d0792c857fecb67b8879e2f/core/providers/utils/utils.go#L4552). SDK patch/image upgrade не применялись. Исследуется минимальная локальная коррекция с проверкой каждого raw frame, включая suppressed finish/usage; это пока не решение и не evidence исправления.

## 8. ECC и фактические исполнители

Root: architect/security/contract-first/test-analysis, integration и docs; doc-updater/verification-loop прочитаны как checklists, native slash commands/hooks не запускались. `g02_prerequisite_plan`: автор backend control и runner; независимо проверял чужие codec/client/relay/probe. `g02_python_contract_review`: автор codec/native probe/Bifrost fixture; независимо проверял чужие backend/root TLS/schema файлы. Эти агенты не считаются независимыми reviewers собственных файлов. `g02_scope_security_review`: отдельный read-only reviewer всех boundaries, не автор. Детали и исправления — [протокол](../reviews/G02_CANDIDATE_EGRESS_REVIEWS.md). Общий Docker/PostgreSQL runtime использовался последовательно, main stack не перезапускался.

## 9. Проверки текущего рабочего diff

База/HEAD: `db8d4af34b0933aa2562adcf072b717eb0e3e3e9`, ветка `feat/g02-manager-tools-planning`, незакоммиченный diff, macOS/Python3.13.5/Docker29.2.0/PostgreSQL16 Testcontainers. Точное содержимое49 code/test/contract файлов фиксирует [SHA256 manifest](../reviews/G02_CANDIDATE_EGRESS_CODE_HASHES.json); implementation docs исключены во избежание self-reference. Все строки ниже — отдельные команды, **не складывать пересекающиеся наборы**.

| Команда / scope | Результат |
|---|---|
| `make pre-push-fast` (root, после runner fixes) | exit0; Ruff PASS, mypy191sourcefiles0issues, import-linter15KEPT/0broken; **1281passed/4warnings**,8.79s (повтор после formatting-only исправлений scanner false positives) |
| `.venv/bin/python -m pytest -q tests/unit/test_candidate_payload.py` | автор:78passed; Ruff/mypy PASS |
| `.venv/bin/python -m pytest -q tests/unit/test_poc_admission_api.py tests/integration/postgres/test_llm_poc_control.py` | автор:54passed11.53s,30ASGI+24realPG; затем ASGI расширен до32passed0.18s |
| `.venv/bin/python -m pytest -q tests/unit/test_candidate_control_client.py` | root:20passed; входят в fast |
| `.venv/bin/python -m pytest -q tests/unit/test_llm_egress.py` | root:78passed0.31s после narrow header delta; Ruff PASS |
| `.venv/bin/python -m pytest -q tests/integration/test_candidate_control_tls.py tests/integration/postgres/test_llm_poc_control_tls.py` | root:18passed10.42s,14realTLS+4TLS/realPG; затем TLS suite расширен до15cases |
| `.venv/bin/python -m pytest -q tests/integration/test_candidate_control_tls.py tests/unit/test_serve_candidate.py tests/contract/test_candidate_control_contract.py tests/unit/test_llm_egress.py` | root:108passed, до двух последних header-negative cases; TLS15/serve5/schema12/relay76 |
| `.venv/bin/python -m pytest -q tests/unit/test_flash_candidate.py` | автор:135passed0.34s после secret-echo regression; Ruff/mypy PASS |
| `.venv/bin/python -m pytest -q --tb=short --maxfail=1 tests/unit/test_flash_candidate_cli.py tests/integration/postgres/test_candidate_runner.py` | автор:43passed7.43s,29unit+14realPG; Ruff4files/mypy2sources PASS |
| `.venv/bin/python -B -m pytest -q tests/integration/test_flash_candidate_bifrost.py --tb=short` | автор: **21passed/0failed/skipped,41.40s**:13bootstrap/security +8actual official Bifrost/fake provider; **SSE — negative refusal**, не readiness. Ранний cold own-cache build:13passed134.73s до security delta |
| `make contracts-check contracts-test` | root:6/6validators +22passed7.81s,exit0 |
| `make infra-check` | root:Ruff PASS,4Compose combinations22/22/22/24services,0violations,exit0 |
| `make infra-scan-secrets` | root:0findings,exit0 после formatting-only fixes; scanner/allowlist не менялись |
| Registry/manifest/local Markdown checker; `git diff --check` | root:74canonical/73hashes0mismatch,305localfilelinks0missing,exit0; diffcheck0;49code/test/contract hashes совпали |

Исторические RED/failures сохранены: initial TLS fixture2failed/6passed (Python3.13 strict CA constraints, исправлена fixture); initial serving fixture1failed/12passed (явный runtime db_user); initial Bifrost3passed/1SSEfailed, затем7passed/1SSEfailed. Последний тест честно фиксирует incompatibility. Secret scanner сначала сообщил6 literal-assignment matches на обычных token-count expressions/tuple parsing; formatting-only исправления сохранили semantics и дали0findings без изменения scanner. Один повтор fast попал в промежуточный TDD RED нового fixture test (2F821 missing constants); после авторского GREEN текущий полный fast1281passed. Production guards не ослаблялись. Full backend ранней persistence фазы1901passed/3legacyfailed остаётся историческим fail; targeted исправления не превращают его в новый full PASS.

## 10. Security / authorization

Проверены missing/wrong issuer/audience/capability, duplicate Authorization, plaintext+spoofed Forwarded headers, wrong CA/SAN, nonregular/symlink/writable key files, control outage, duplicate/unknown JSON, lexical types, hash/body/cap/stream/template mismatch, onceclaim/replay/concurrency/audit rollback, known settlement lost ACK, contradictory usage facts, SSE secret fragments/interleaving, no-DONE-before-accounting, malformed native identity/fallback/stream drift, actual known credential echo, cancel/timeout, unknown billing holds, exact runner ticket/accounting mismatch, source forbidden reads/bounds и evidence fd/flock cleanup.

## 11. Независимое review

General cross-review только чужих файлов + отдельный security review: исправлены contradictory settlement facts, split/interleaved secret export, TLS-file permissions, source discovery и malformed JSONL lock leak; финальный security delta APPROVE/open0. Verdict не закрывает известную actual-Bifrost SSE несовместимость. Fixture-bootstrap delta получил отдельный security re-review: MEDIUM pre-check `.dockerignore` read CLOSED, финал APPROVE/open0. Shared docs source-check не выявил overclaim.

## 12. Невыполненное / ограничения

Нет реального key setup/provider calls/billing/live identity values/profile approval/словаря классификаций; model spend0USD, real account/tariff/profile seeds отсутствуют. HostFactory execution пока требует concrete trusted composition; сухой CLI без неё не делает DB/HTTP, `--execute` отказывает HOST_UNCONFIGURED. Нужны freshness source/revalidation, безопасная подача ключа и полный metadata manifest; service token не выдаёт этих approvals. Новый кандидатный тест использует fake control/upstream, поэтому не доказывает бюджет; реальный PG/TLS проверен отдельно. Нет full pre-pr/Linux CI итогового diff/новой Git delivery. Исторические CI не присваиваются текущим файлам.

## 13. Документы и traceability

Обновляются HANDOFF/STATUS/G02_WORK, KNOWN_GAPS, requirements/contract traceability и ECC; normative/mirror/baseline не меняются. ADR134 остаётся technical scope, не acceptance профиля. Прежние checkpoints сохраняются как история.

## 14. DoD

Codec/private control/relay/probe/runner реализованы и локально проверены; независимые boundary review выполнены. Portable fixture own-image build и21case verification завершены. Полная Bifrost SSE compatibility, concrete host gate, final combined gates/live/human acceptance **не завершены**. Статус подготовки остаётся IN_PROGRESS; G156 не VERIFIED/DONE.

## 15. Следующий безопасный шаг

Продолжить минимальное SSE исправление с отдельным technical ADR/проверкой Go serialization и build provenance, сохраняя fail-closed; затем concrete host/freshness composition и повтор затронутых checks/review. До live нужны безопасный ключ и точные разрешения/evidence; первый ответ не autoapproval. После G156 отдельно SLICE-01 со своей лицензией/бюджетом; до S20 — ADR129 enforcement/G107. О завершении подготовки отдельно сообщить владельцу. **G02 без его нового согласия не начинать.**

Current fixture cache context SHA256: `25d89c13d87601e6db31c25c8d4de143984c6aff1bbb4db72e5548b8f05dc6c1`, own immutable image `sha256:50c042c07ff2df8e2158a7bbb3ff88a26c34f12f79cb4bfadd56bf8599e30f71`. Main API image остался `sha256:1ecf488b97fa48b6c229060740d0732049a82a63471d934d085238556b10745b`. Собственный cache сохранён, временные containers/network удалены, runtime освобождён. Исходный40file checkpoint:30byte-identical+10authorizedimplementationdocs edits,0missing; protected canonical/mirror/старые отчёты не изменились.
