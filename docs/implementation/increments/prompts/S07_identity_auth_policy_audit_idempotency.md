# S07 — Identity, Local Auth, Policy Engine, Audit, Idempotency

**Фаза:** B. Persistence & Identity · **Соответствие Spec:** Spec Inc. 2 п.6–9 (реализация); Add. v1.3 §3.1 · **Roadmap:** `docs/implementation/IMPLEMENTATION_ROADMAP.md`

> **СТАТУС ПРОМПТА: PENDING_DEPS.** Исполнять только после перевода всех зависимостей в DONE.

## 1. Роль и полномочия

Ты — **Principal Architect и Implementation Lead проекта AI RES**. Ты отвечаешь за архитектурную целостность, технические решения, последовательность работ, интеграцию компонентов, качество, безопасность реализации и полноту технической документации.

**Полномочия.** В рамках общей концепции AI RES ты самостоятельно: проектируешь недостающие технические механизмы, выбираешь подходы, библиотеки и инструменты в пределах согласованного стека, определяешь структуру модулей и интерфейсов, разрешаешь технические противоречия и циклические зависимости, определяешь способы тестирования. Обычные технические решения не перекладываются на владельца — они принимаются, обосновываются и регистрируются как `ACCEPTED` в `docs/implementation/ARCHITECTURE_DECISION_LOG.md`.

**Границы (нарушать запрещено):** модульный Backend без microservice-per-domain; PostgreSQL `ai_res_db` — источник истины доменного состояния; Temporal — durable orchestration; LangGraph — внутреннее reasoning; отдельные Manager Runtime и общий Worker Runtime pool; 9 логических специализаций Workers, а не 9 сервисов; Readiness Gate перед **каждым** WorkerRun; Workers не пишут в доменную БД и не взаимодействуют напрямую (только через Manager → Policy → Temporal); immutable versions, provenance, audit, traceability; никакого автоматического одобрения требований, решений и Baseline агентами; Bifrost — кандидат до PoC и security review; Connector Platform — единственный путь к внешним системам; GitHub/GitLab — read-only в MVP.

Если решение требует изменить BASELINED-документ, бизнес-цель, границы MVP, права пользователя или критические гарантии безопасности — **не меняй их**: подготовь Normative Change Proposal в `docs/implementation/decisions/NORMATIVE_CHANGE_PROPOSALS.md` (причина, альтернативы, последствия, затронутые документы и тесты), при необходимости — запись в `DECISIONS_PENDING.md`, и выбери наиболее безопасный вариант, не нарушающий baseline.

## 2. Цель этапа

Local authentication MVP, opaque server-side sessions, CSRF, privileged TOTP MFA, bootstrap admin, Policy & Permission Engine (deny-by-default), fail-closed audit writer, idempotency service.

## 3. Нормативные источники (обязательно прочитать перед планом)

- `docs/architecture/AI_RES_Authentication_and_Session_Management_v1.1.md` — §1–§6, §8, §9, §10, §11, §12
- `docs/architecture/AI_RES_Identity_Access_Control_v1.5.md` — §2–§8, §10
- `docs/architecture/AI_RES_Security_Controls_and_Requirements_v1.2.md` — §2, §3, Дополнение v1.1 (AUTH-001…013)
- `docs/architecture/AI_RES_Security_Architecture_v1.2.md` — §2
- `docs/architecture/AI_RES_Secrets_and_Key_Management_v1.1.md` — §3, §4, §7
- `docs/architecture/AI_RES_Threat_Model_v1.1.md` — §5 (сценарии для auth/ACL)
- `docs/architecture/AI_RES_API_and_Interaction_Contracts_v1.10.md` — §6; Дополнение v1.7
- `docs/architecture/AI_RES_Operation_WorkerRun_Event_Model_v1.4.md` — §10
- `docs/architecture/AI_RES_Claude_Code_Implementation_Spec_v1.22.md` — §3 Non-negotiable constraints, §8 Test matrix/DoD, §9 Prohibited shortcuts, §10 Delivery report; Addendum v1.22 (приоритет Registry v4.1).
- `docs/architecture/AI_RES_Document_Registry_v4.1.md` — §2 (canonical версии и статусы); BASELINED ≠ реализовано, WORKING ≠ утверждено.

## 4. Зависимости и условия старта

- **Этапы-зависимости (должны быть DONE):** S05 (Core tenant и execution schema + RLS)
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

- Argon2id (параметры конфигурируемы), минимальная длина 15, local denylist; login rate limiting/lockout по DOC-023 §4.
- Sessions в PostgreSQL: opaque id, rotation после login/MFA/elevation, idle 30 мин / absolute 12 ч (configurable defaults), revoke; cookie `ai_res_session` (имя конфигурируемо, OD-03), HttpOnly/Secure/SameSite=Lax.
- CSRF (`X-CSRF-Token`, конфигурируемо) + Origin check для cookie-аутентифицированных state changes; CORS deny-by-default.
- TOTP MFA для Organization Owner/Admin, Project Admin; recovery codes (hash).
- Bootstrap admin: одноразовая CLI-процедура, секрет из Compose secret, инвалидируется после использования.
- Service identities (api/dispatcher/consumer/manager/worker) — отдельные, короткоживущие credentials; браузерные сессии не передаются.
- Policy Engine (ADR-017): RBAC+ABAC/ACL, approval-required, reason codes, fail-closed; autonomy A0–A2 enforcement point.
- Audit writer: запись в `audit.audit_events` в той же транзакции, сбой → отказ защищённого действия.
- Idempotency service: scope `(organization, actor scope, command, key)`, fingerprint, HMAC+key_id, replay, 409 `IDEMPOTENCY_KEY_REUSED`.
- `GET /api/v1/me` (getCurrentUser) как первый endpoint по контракту.
- Прогрессивная задержка вместо hard lockout; доверие XFF только Caddy.

**Не входит:**
- OIDC adapter (post-MVP, только interface).
- UI логина (S35).

## 6. Обязательные решения (ACCEPTED) для этого этапа

- ADR-015 — Набор PostgreSQL ролей по нормативным документам
- ADR-017 — Policy & Permission Engine — in-process модуль
- ADR-024 — Idempotency HMAC keys с key-id
- ADR-032 — Статусы этапов и определение DONE
- ADR-035 — Контуры тестирования и evidence для P0-этапов
- ADR-037 — Независимая проверка P0-этапов (замена per-stage human sign-off)
- ADR-038 — План проектирования недостающих endpoint и событий

**Решения, которые нужно принять и зарегистрировать на этапе:**
- Маршруты login/logout/MFA/recovery: проектируются в overlay по DOC-023 (ADR-009/ADR-038); зафиксировать ADR этапа.
- Параметры Argon2id (по OWASP, конфигурируемые).
- Недостающие endpoint/events этапа проектируются в overlay `contracts/*/extensions/` (статус WORKING) до handler по ADR-009 и ADR-038 (OD-09 решён владельцем 2026-11-11); contract tests обязательны.

## 7. Результаты реализации

- iam/auth/policy/audit/idempotency модули
- endpoints login/logout/me (по контракту; login/logout отсутствуют в OAS v1.3 → NCP-06 или internal auth router по DOC-023 — решить ADR)
- tests
- S07 report

## 8. ECC: обязательные agents, skills, commands

| Тип | Имя (установлено в `.claude/`) | Назначение на этапе |
|---|---|---|
| agent | `planner` | декомпозиция этапа на вертикальные срезы перед реализацией |
| agent | `architect` | архитектурное соответствие плана и результата нормативной архитектуре (read-only review) |
| agent | `code-reviewer` | независимое общее code review |
| agent | `silent-failure-hunter` | поиск проглоченных ошибок, небезопасных fallback и fail-open путей |
| agent | `python-reviewer` | review Python-кода |
| agent | `tdd-guide` | тесты до реализации (DoD — по testing-and-verification.md, не «80% coverage») |
| agent | `pr-test-analyzer` | оценка полноты поведенческих и негативных тестов |
| agent | `security-reviewer` | независимое security review |
| agent | `fastapi-reviewer` | review FastAPI слоя (ADR-008) |
| agent | `database-reviewer` | review миграций, ролей, RLS, запросов (с учётом ecc-precedence: RLS через transaction-local context, не Supabase) |
| skill | `python-patterns` | идиомы и типизация Python |
| skill | `python-testing` | pytest, fixtures, parametrization (без FastAPI-примеров как обоснования стека) |
| skill | `tdd-workflow` | red → green → refactor |
| skill | `error-handling` | типизированные ошибки, bounded retries |
| skill | `verification-loop` | финальная верификация этапа |
| command | `/plan` | план этапа до кода |
| command | `/code-review` | локальный review изменений (без PR-режима) |
| command | `/quality-gate` | проверка quality gates |
| command | `/python-review` | review Python изменений |
| command | `/test-coverage` | отчёт покрытия как дополнительная метрика |
| command | `/fastapi-review` | review FastAPI |
| command | `/security-review` | встроенная команда Claude Code: security review изменений ветки |

Порядок применения: `planner` + `/plan` → реализация с тестами (TDD) → профильные reviewers → `code-reviewer`/`/code-review` → `silent-failure-hunter` → `architect` (соответствие архитектуре) → `verification-loop` + `/quality-gate`. ECC подчинён правилам AI RES (`.claude/rules/ecc-precedence.md`); ECC agents — инструменты разработки, не Runtime Workers AI RES. Если компетенции нет в ECC — выполнить самостоятельно с дополнительной проверкой и записать в `ECC_USAGE.md`.

## 9. Обязательные тесты

- Stale/revoked/expired session → 401.
- CSRF отсутствует/неверен/чужой Origin → 403.
- Privileged роль без MFA → доступ к privileged действиям запрещён.
- Bootstrap secret повторно → отказ; default credentials отсутствуют.
- Policy outage/exception → deny; неизвестное действие → deny.
- Audit write failure → защищённое действие откатывается.
- Idempotency: параллельные одинаковые запросы → одна запись; другой fingerprint → 409.
- Логи/трейсы не содержат пароль, cookie, TOTP seed, recovery codes (golden test).
- Brute-force: rate limit срабатывает.
- AUTH-005: одинаковые ответ и время для существующей/несуществующей учётки; progressive delay.
- AUTH-008: отзыв сессий при смене пароля, отключении, отзыве роли.
- AUTH-012: человек/сервис/Worker не подменяют друг друга.
- AUTH-013: покрытие auth-событий аудитом.
- Смена session ID после login/MFA (fixation); recovery codes одноразовые; повтор TOTP отклонён; login-CSRF.
- Подделанный XFF не обходит rate limit.
- Невалидная/без версии policy-конфигурация → deny.

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
- `docs/implementation/increments/S07_identity_auth_policy_audit_idempotency_REPORT.md` — Increment Report по шаблону `docs/implementation/INCREMENT_REPORT_TEMPLATE.md`.
- Независимые review — `docs/implementation/reviews/S07_*.md`.
- DECISIONS_PENDING.md (OD-03 статус)
- decisions/NORMATIVE_CHANGE_PROPOSALS.md (NCP-06)

## 13. Definition of Done

- Все SEC P0 тесты этапа зелёные.
- security-reviewer review без открытых HIGH.
- Policy matrix покрывает все действия, введённые к этому этапу.
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

Создать `docs/implementation/increments/S07_identity_auth_policy_audit_idempotency_REPORT.md` по шаблону `docs/implementation/INCREMENT_REPORT_TEMPLATE.md` (все разделы обязательны).

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

- AUTH-001..013
- AUTH-MVP-*
- SEC-001..035 (P0 части)
- SEC-MVP-*
