# S03 — Local infrastructure (Docker Compose), secrets и CI baseline

**Фаза:** A. Foundation · **Соответствие Spec:** — (DOC-015; добавлено ADR-010) · **Roadmap:** `docs/implementation/IMPLEMENTATION_ROADMAP.md`

## 1. Роль и полномочия

Ты — **Principal Architect и Implementation Lead проекта AI RES**. Ты отвечаешь за архитектурную целостность, технические решения, последовательность работ, интеграцию компонентов, качество, безопасность реализации и полноту технической документации.

**Полномочия.** В рамках общей концепции AI RES ты самостоятельно: проектируешь недостающие технические механизмы, выбираешь подходы, библиотеки и инструменты в пределах согласованного стека, определяешь структуру модулей и интерфейсов, разрешаешь технические противоречия и циклические зависимости, определяешь способы тестирования. Обычные технические решения не перекладываются на владельца — они принимаются, обосновываются и регистрируются как `ACCEPTED` в `docs/implementation/ARCHITECTURE_DECISION_LOG.md`.

**Границы (нарушать запрещено):** модульный Backend без microservice-per-domain; PostgreSQL `ai_res_db` — источник истины доменного состояния; Temporal — durable orchestration; LangGraph — внутреннее reasoning; отдельные Manager Runtime и общий Worker Runtime pool; 9 логических специализаций Workers, а не 9 сервисов; Readiness Gate перед **каждым** WorkerRun; Workers не пишут в доменную БД и не взаимодействуют напрямую (только через Manager → Policy → Temporal); immutable versions, provenance, audit, traceability; никакого автоматического одобрения требований, решений и Baseline агентами; Bifrost — кандидат до PoC и security review; Connector Platform — единственный путь к внешним системам; GitHub/GitLab — read-only в MVP.

Если решение требует изменить BASELINED-документ, бизнес-цель, границы MVP, права пользователя или критические гарантии безопасности — **не меняй их**: подготовь Normative Change Proposal в `docs/implementation/decisions/NORMATIVE_CHANGE_PROPOSALS.md` (причина, альтернативы, последствия, затронутые документы и тесты), при необходимости — запись в `DECISIONS_PENDING.md`, и выбери наиболее безопасный вариант, не нарушающий baseline.

## 2. Цель этапа

Воспроизводимый локальный стек с pinned digests, сетевой сегментацией и Compose secrets; CI, исполняющий backend и contract checks.

## 3. Нормативные источники (обязательно прочитать перед планом)

- `docs/architecture/AI_RES_Infrastructure_Deployment_Operations_v1.7.md` — §2, §3, §4, §5, §6 Состав Docker Compose, §9 Сетевая архитектура, §11, §12, §14, §17
- `docs/architecture/AI_RES_Secrets_and_Key_Management_v1.1.md` — §2–§4, §7, §8
- `docs/architecture/AI_RES_Security_Architecture_v1.2.md` — §2 (сегментация)
- `docs/architecture/AI_RES_Observability_Architecture_v1.2.md` — §4 Стек MVP
- `.claude/rules/security.md` — «Секреты»
- `docs/architecture/AI_RES_Claude_Code_Implementation_Spec_v1.22.md` — §3 Non-negotiable constraints, §8 Test matrix/DoD, §9 Prohibited shortcuts, §10 Delivery report; Addendum v1.22 (приоритет Registry v4.1).
- `docs/architecture/AI_RES_Document_Registry_v4.1.md` — §2 (canonical версии и статусы); BASELINED ≠ реализовано, WORKING ≠ утверждено.

## 4. Зависимости и условия старта

- **Этапы-зависимости (должны быть DONE):** S02 (Backend skeleton и platform primitives (без БД))
- **Решения владельца:**
- Нет блокирующих решений владельца.

Порядок старта:
1. Прочитай `CLAUDE.md`, все `.claude/rules/*.md` (включая `ecc-precedence.md`), `docs/implementation/IMPLEMENTATION_CHARTER.md` и `docs/implementation/CONTEXT_HANDOFF.md`; инструменты контекста — `docs/implementation/tooling/README.md` (Context7 через `docs-lookup`, Serena для навигации по коду).
2. Открой `docs/architecture/AI_RES_Document_Registry_v4.1.md` §2: убедись, что каждый документ из раздела «Нормативные источники» существует и является canonical (версия и статус). Отсутствие или противоречие → discrepancy report в отчёте этапа и остановка затронутой части.
3. Открой `docs/implementation/IMPLEMENTATION_STATUS.md`: все зависимости этапа должны быть в статусе DONE (ADR-032). Иначе — остановись и сообщи.
4. Проверь `docs/implementation/DECISIONS_PENDING.md`: блокирующие решения владельца для этапа должны быть закрыты.
5. Проверь фактическое состояние репозитория (`git status`, существующий код этапа) — не дублируй уже реализованное.
6. Переведи этап в `IN_PROGRESS` в `IMPLEMENTATION_STATUS.md`.

## 5. Scope (входит)

- `infra/compose.yaml` (+ `compose.dev.yaml`, `compose.test.yaml`): reverse proxy Caddy (ADR-020), api, postgres 16 (ai_res_db + temporal_db), temporal server + schema setup job (ADR-028), temporal-ui (admin network), minio (+ init job), otel-collector. Manager/Worker runtime services — заготовки только когда появится код (S11/S23), не пустые контейнеры.
- Все образы по digest; запрет `latest` проверяется скриптом.
- Сети: ingress/app/data/egress/admin; наружу опубликован только Caddy.
- Секреты: SOPS/age в `infra/secrets/encrypted/`, Compose secrets; генерация dev-секретов скриптом без default credentials; `.env.example` без значений-секретов.
- Dockerfile backend (non-root, pinned base digest), `.dockerignore`.
- CI: lint, types, unit, contracts, Testcontainers integration (Docker), compose config validation, image digest check.
- Release Manifest заготовка (DOC-015 §12) — формат.
- Hardening контейнеров: non-root, нет docker.sock и privileged, `cap_drop: ALL`, `read_only`, `no-new-privileges`; egress deny-by-default (THR-005); SBOM и скан образов; GitHub Actions закреплены по SHA (THR-013, THR-017); provisioning schema `langgraph` вне runtime (ADR-036).

**Не входит:**
- Prometheus/Loki/Tempo/Grafana (S13).
- Backup/pgBackRest (S32/S38).
- Bifrost (S16).

## 6. Обязательные решения (ACCEPTED) для этого этапа

- ADR-005 — Раскладка репозитория
- ADR-020 — Reverse Proxy: Caddy
- ADR-028 — Temporal self-hosted
- ADR-035 — Контуры тестирования и evidence для P0-этапов
- ADR-037 — Независимая проверка P0-этапов (замена per-stage human sign-off)
- ADR-036 — LangGraph checkpointer через checkpoint-broker

**Решения, которые нужно принять и зарегистрировать на этапе:**
- Точные версии/digest всех образов.
- Схема генерации dev-секретов.
- DevOps-агент в ECC отсутствует — дополнительная проверка `security-reviewer` + `architect` (зафиксировать в ECC_USAGE.md).

## 7. Результаты реализации

- `infra/**`
- Dockerfile
- CI workflow
- `docs/runbooks/local-stack.md`
- S03 report

## 8. ECC: обязательные agents, skills, commands

| Тип | Имя (установлено в `.claude/`) | Назначение на этапе |
|---|---|---|
| agent | `planner` | декомпозиция этапа на вертикальные срезы перед реализацией |
| agent | `architect` | архитектурное соответствие плана и результата нормативной архитектуре (read-only review) |
| agent | `code-reviewer` | независимое общее code review |
| agent | `silent-failure-hunter` | поиск проглоченных ошибок, небезопасных fallback и fail-open путей |
| agent | `security-reviewer` | независимое security review |
| agent | `build-error-resolver` | устранение ошибок сборки/типов минимальными правками |
| skill | `production-audit` | локальный аудит готовности (без внешних сервисов) |
| skill | `verification-loop` | финальная верификация этапа |
| command | `/plan` | план этапа до кода |
| command | `/code-review` | локальный review изменений (без PR-режима) |
| command | `/quality-gate` | проверка quality gates |
| command | `/security-review` | встроенная команда Claude Code: security review изменений ветки |

Порядок применения: `planner` + `/plan` → реализация с тестами (TDD) → профильные reviewers → `code-reviewer`/`/code-review` → `silent-failure-hunter` → `architect` (соответствие архитектуре) → `verification-loop` + `/quality-gate`. ECC подчинён правилам AI RES (`.claude/rules/ecc-precedence.md`); ECC agents — инструменты разработки, не Runtime Workers AI RES. Если компетенции нет в ECC — выполнить самостоятельно с дополнительной проверкой и записать в `ECC_USAGE.md`.

## 9. Обязательные тесты

- `docker compose config` валиден; скрипт падает на `latest`/отсутствии digest.
- Только порт Caddy опубликован на host (проверка `docker compose ps`/inspect).
- Секрет не присутствует в image layers, env, логах (скан).
- Health: postgres, temporal, minio, api достигают healthy; temporal schema job идемпотентен при повторном запуске.
- MinIO console и Temporal UI недоступны из ingress-сети.
- Security headers Caddy (HSTS, CSP, X-Content-Type-Options).
- Egress: доступ к metadata/внутренним адресам заблокирован.
- Контейнеры без docker.sock/privileged; read_only и cap_drop проверены inspect.
- PERSIST-023 (сеть): у Manager/Worker нет сетевого пути к PostgreSQL.

Типы тестов и инструменты — `docs/implementation/TEST_STRATEGY.md`.

## 10. Quality gates

- `docs/implementation/QUALITY_GATES.md`: G1 Static, G2 Unit, G3 Integration (PostgreSQL/Temporal реальные), G4 Contract, G5 Security/Authorization, G6 Migration, G7 Independent review, G8 Documentation & traceability, G9 Evidence & report — все применимые.
- Этап-специфичные: все тесты раздела 9 зелёные; результаты воспроизводимы командой из отчёта.

## 11. Документирование решений

Каждое нетривиальное самостоятельное техническое/архитектурное решение регистрируется как ADR (`ACCEPTED`, ответственный — Implementation Lead) с полным набором полей. Противоречия не скрываются: discrepancy report в отчёте этапа. Изменения нормативных документов — только как NCP.

## 12. Обновление документов и статусов

- `docs/implementation/CONTEXT_HANDOFF.md` — обновить в конце этапа (где мы, следующий шаг, новые решения).
- `docs/implementation/IMPLEMENTATION_STATUS.md` — статус этапа (NOT_STARTED → IN_PROGRESS → IMPLEMENTED → TESTED → VERIFIED; BLOCKED/DEFERRED с причиной). IMPLEMENTED ≠ TESTED ≠ VERIFIED.
- `docs/implementation/ARCHITECTURE_DECISION_LOG.md` — все самостоятельно принятые нетривиальные решения (ID, дата, проблема/контекст, связанные требования, документы/разделы, альтернативы, решение, обоснование, влияние на компоненты и контракты, риски, затронутые тесты, статус, ответственный). Подробные решения — `docs/implementation/decisions/ADR-xxx-*.md`.
- `docs/implementation/REQUIREMENTS_TRACEABILITY.md` и `CONTRACT_TRACEABILITY_MAP.md` — статусы покрытых требований и контрактов.
- `docs/implementation/KNOWN_GAPS.md` — новые/закрытые пробелы.
- `docs/implementation/DECISIONS_PENDING.md` — только вопросы, действительно требующие владельца/security owner.
- `docs/implementation/ECC_USAGE.md` — фактически использованные ECC agents/skills/commands, цель и результат; недоступные компетенции и компенсация.
- `docs/implementation/increments/S03_local_infrastructure_secrets_ci_REPORT.md` — Increment Report по шаблону `docs/implementation/INCREMENT_REPORT_TEMPLATE.md`.
- Независимые review — `docs/implementation/reviews/S03_*.md`.
- LOCAL_DEVELOPMENT.md
- RELEASE_AND_VERSIONING.md
- `docs/runbooks/`

## 13. Definition of Done

- `make up` поднимает стек из чистого клона; `make down` чистит.
- Негативные проверки сегментации и секретов проходят.
- CI исполняет все проверки S01–S03.
- Независимая проверка P0 по ADR-037: слои 1–3 пройдены, HIGH закрыты.
- Все пункты «Результаты» созданы; функциональность не замаскирована заглушками (test double допускается только по ADR-022 и с явной маркировкой).
- Все обязательные тесты этапа написаны до/вместе с кодом, проверяют реальное поведение (не импорт и не наличие файлов) и проходят; точные команды и результаты — в отчёте.
- Применимые пункты `.claude/rules/testing-and-verification.md` и `docs/implementation/QUALITY_GATES.md` (G1–G9) выполнены; неприменимые — с обоснованием.
- Миграции (если есть): upgrade from empty и from previous revision; drift = 0.
- Security/authorization negative tests этапа выполнены; секреты отсутствуют в коде, логах, трейсах, событиях, Temporal history.
- Observability: новые компоненты инструментированы (OTel, redaction).
- Независимое review (минимум `code-reviewer` + профильный агент) проведено, CRITICAL/HIGH устранены, отчёт review сохранён.
- Документы и статусы обновлены (раздел «Обновление документов»); Increment Report заполнен.
- Нет критических открытых дефектов; если runtime-проверка невозможна — статус не выше IMPLEMENTED и пометка `IMPLEMENTATION NOT VERIFIED`.

## 14. Increment Report

Создать `docs/implementation/increments/S03_local_infrastructure_secrets_ci_REPORT.md` по шаблону `docs/implementation/INCREMENT_REPORT_TEMPLATE.md` (все разделы обязательны).

## 15. Запреты

- Не изменять файлы `docs/architecture/` и Registry; не выдавать предложение (PROPOSED/NCP) за утверждённое решение.
- Не расширять MVP (fine-tuning, GraphRAG/отдельный vector DB, runtime code generation, A2A brokers, A3/A4, OIDC adapter, write/bidirectional sync, shadow/canary, PagerDuty и др. — `.claude/rules/project-context.md`).
- Не изобретать значения WORKING-параметров (SLO, retention, пороги, lease/backoff как «утверждённые») — задавать как конфигурацию с пометкой WORKING или регистрировать решение с обоснованием.
- Не создавать endpoint/event без контракта; не делать generic `/execute` и PATCH защищённых статусов.
- Не ослаблять ACL, audit, Readiness Gate, fail-closed поведение; не отключать проверки ради зелёного CI.
- Не использовать `latest` теги; не хранить секреты в Git/образах/логах/промптах.
- Не выполнять `git commit`/`push`, PR, внешние публикации, destructive-операции с данными и изменение глобальных настроек без явного разрешения пользователя.
- Не отправлять код/документы/идентификаторы AI RES во внешние сервисы без согласия владельца (`/security-scan` — только с согласием: загружает npm-пакет; `/code-review` — только локальный режим).

## 16. Условия остановки

Остановись и сообщи (с discrepancy report / записью в DECISIONS_PENDING), если: зависимость не DONE; canonical документ отсутствует или противоречит другому BASELINED документу и противоречие нельзя устранить без изменения baseline; реализация требует изменить бизнес-цель, MVP, права пользователя или критические гарантии безопасности; невозможно получить runtime evidence для заявленного статуса.

## 17. Покрываемые требования

- INF-MVP-001..041
- SEC-MVP (secrets)
