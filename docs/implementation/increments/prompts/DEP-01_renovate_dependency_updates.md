# DEP-01 — Управляемые обновления зависимостей Renovate

**Основание:** ADR-113; явный выбор владельца 2026-11-17 после ARCH-01. Отдельное уточнение той же сессии: «Renovate — установи также самостоятельно» разрешает установку GitHub App только на `F4nin/AI-RES` после проверки и доставки конфига. Ранее установка оставлялась владельцу; новое поручение меняет исполнителя этой операции, не политику обновлений.

## 1. Цель и scope

Настроить `renovate.json`: weekly schedule, minimumReleaseAge 14 days для обычных обновлений, security exceptions без этой задержки, управляемый поток PR, запрет automerge, digest/SHA pinning. Охватить Python pyproject/uv.lock через pep621, npm, Actions, контейнеры, uv versions и shell image variables; MinIO tag + source commit и все связанные own-image references обновляются вместе. Конфигурацию проверить настоящим pinned Renovate, а не только JSON Schema.

Допустимы `renovate.json`, локальный/CI validator и его acceptance checks, Makefile и необходимые implementation docs. Не обновлять сами продуктовые зависимости/образы, не менять public contracts, migration/RLS, canonical, Compose topology, секреты и конфигурации Claude/MCP. GitHub App — selected repository only; не выбирать All repositories, не выдавать доступ другим приложениям. Renovate PR обновлений остаются за человеком; постоянное Git-разрешение доставки DEP-01 не разрешает автоматически сливать будущие dependency PR.

## 2. Источники и зависимости

AGENTS §2/7/10, CLAUDE, Registry v4.1, Spec v1.22 §3/§8 и addenda v1.22/1.22.1; DOC-015 v1.7 §12–14; IMPLEMENTATION_CHARTER/ROADMAP/STATUS/HANDOFF, tooling README, QUALITY_GATES, TEST_STRATEGY, ECC_USAGE, KNOWN_GAPS G-24/G-31, ADR-043/113. CI-01 VERIFIED/DONE, ARCH-01 VERIFIED/DONE. Чистая проверенная база `823decd81833bdffe9b957b95ddf736f82ed6597`, сверена с remote main; рабочая ветка `feat/dep-01-renovate-config`.

## 3. План и технические решения

1. Инвентаризация реальных manifests/variables/связанных pins; read-only план независимого ECC planner.
2. Промпт и конфиг; WORKING schedule/timezone/PR limits и pinned validator зафиксировать ADR-121. Не изобретать manager uv: он обслуживается pep621.
3. Проверить strict config validation, RE2 extraction и replacement production patterns на синтетических версиях/commit/digests; отсутствие частичного match повреждённой MinIO пары. Проверить правила scheduling/security/limits и связность references.
4. Включить проверку конфига в существующий CI без отключения остальных gates; локальные проверки, blind-first общее/security review, исправления, полный pre-pr, Linux CI и доставка.
5. После проверенного конфига в main выполнить разрешённую установку GitHub App при доступности механизма; проверить onboarding/доступ только к нужному репозиторию. При интерактивном GitHub login/consent без доступного браузерного инструмента зафиксировать конкретную недоступность и оставшееся действие; локальный validator не выдавать за установку App.

## 4. ECC

`planner` — отдельное read-only исследование до реализации; `verification-loop` — явно прочитанный checklist исполнителя. `code-reviewer` и `security-reviewer` — независимые read-only blind-first review (G7: конфигурация supply-chain updates и будущая запись внешним App). Нативные Claude commands/hooks не запускаются. DB/Temporal specialist не требуется: эти механизмы не меняются. Для проверки доступных внешних capabilities применён навык plugin-management; найденные, но неподключённые интеграции не считаются доступными/установленными.

## 5. Acceptance и DoD

- Политика ADR-113 реализована: обычные PR weekly + 14 days, major/stateful review labels, никаких automerge/deployments. Vulnerability alerts не ждут weekly schedule/age и требуют включённых GitHub dependency graph/alerts; произвольные Docker/source CVE не объявлять автоматически исправляемыми.
- Все custom patterns проверены настоящим Renovate RE2/extraction/update engine. MinIO tag/commit/own refs и Caddy source/own refs не расходятся; собственные `ai-res/*` не ищутся как внешние Docker artifacts.
- Checksum-bound SOPS/age и прочие вручную поддерживаемые pins явно перечислены; не менять URL отдельно от checksum и не ослаблять проверки подлинности.
- `make pre-push-fast`, config acceptance, полный `make -j1 pre-pr`, secret/diff checks и Linux CI (audit/digests/hadolint/actionlint/SBOM/vulnerability) успешны; CRITICAL/HIGH review findings устранены.
- G1/G2/G5/G7/G8/G9 применимы; новые G3/G4/G6 сценарии не требуются при неизменённых runtime/API/DB. Существующий regression pre-pr/CI сохраняется.
- G-31: отделить strict validator evidence от фактического App runtime/onboarding. G-24: не закрывать существующие vulnerabilities одной настройкой Renovate.
- Обновлены status/handoff, ADR, gaps, ECC и отчёт по INCREMENT_REPORT_TEMPLATE (`increments/DEP-01_renovate_dependency_updates_REPORT.md`), review (`reviews/DEP-01_REVIEWS.md`). Отдельные статусы конфигурации и App installation; при недоступной установке этап целиком не объявлять полностью выполненным.
- После DEP-01 остановиться; PROF-01/S16/SLICE-01 и продуктовые этапы не запускать.

**Уточнение закрытия владельцем 2026-11-17:** после доставки кода, полного pre-pr, независимых review и Linux CI владелец прямо поручил перевести DEP-01 в выполненные перед очисткой контекста. Инкремент закрывается **DONE по решению владельца**, конфигурация **VERIFIED**. Прежнее условие удерживать весь этап IN_PROGRESS до App confirmation заменено этим решением; App installation/onboarding и первый hosted run остаются **NOT VERIFIED**, отдельным follow-up G-31. Это не подтверждение фактического выбора настроек Mend и не runtime acceptance App. Следующий этап в рамках закрытия не запускается.
