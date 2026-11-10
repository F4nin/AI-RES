# AI RES — Модель угроз

**Версия:** 1.1  
**Статус:** BASELINED — threat treatment design; reassessment required per deployment profile.

## 1. Метод

Используется комбинированный подход: asset/threat/risk analysis, STRIDE для системных границ и отдельный перечень угроз LLM/agentic systems. Оценка риска качественная: вероятность (низкая/средняя/высокая), влияние (низкое/среднее/высокое/критическое), итоговый приоритет. Численные оценки не вводятся без threat workshop и конкретного deployment profile.

## 2. Активы

| Актив | Конфиденциальность | Целостность | Доступность |
|---|---|---|---|
| Исходные документы, репозитории, интервью | Высокая | Высокая | Средняя |
| Требования, решения, Baseline, CR | Высокая | Критическая | Высокая |
| Context Packages, память, индексы, embeddings | Высокая | Высокая | Средняя |
| Credentials, API keys, signing/age keys | Критическая | Критическая | Высокая |
| Tool/Connector Registry и policies | Высокая | Критическая | Высокая |
| Worker Runs, Temporal state, checkpoints | Высокая | Высокая | Высокая |
| Артефакты и OpenAPI/диаграммы | Высокая | Высокая | Средняя |
| Audit Log и security telemetry | Высокая | Критическая | Высокая |
| Образы, зависимости, конфигурация и release manifests | Средняя | Критическая | Высокая |

## 3. Нарушители и источники угроз

- внешний анонимный/аутентифицированный атакующий;
- скомпрометированная пользовательская учётная запись;
- злонамеренный или ошибочный пользователь организации;
- скомпрометированный сервис/контейнер/зависимость;
- вредоносный или скомпрометированный MCP/API provider;
- злонамеренный или ошибочный документ/репозиторий/веб-источник;
- prompt injection в содержимом, которое агент анализирует;
- ошибочно сконфигурированный администратор;
- модель/провайдер, возвращающий некорректный или небезопасный результат.

## 4. Границы доверия

1. Browser/User → Reverse Proxy/API.
2. API → Domain Services.
3. Domain Services → Manager Runtime.
4. Manager → Temporal → Worker Runtime.
5. Runtime → Context Builder/Retrieval → PostgreSQL/MinIO.
6. Runtime → Tool Gateway → local/API/MCP tools.
7. Runtime → LLM Gateway Adapter → Gateway → external/local model.
8. Admin → Temporal UI/MinIO Console/operations.
9. Build/release pipeline → container images/configuration/deployment.

Каждая граница требует идентификации субъекта, авторизации действия и проверки данных. Внутреннее расположение компонента не делает его доверенным автоматически.

## 5. Реестр сценариев угроз

| ID | Сценарий | Последствие | Основные меры | Начальный приоритет |
|---|---|---|---|---|
| THR-001 | Indirect prompt injection в PDF/Markdown/репозитории заставляет агента раскрыть данные или вызвать инструмент | Утечка/несанкционированное действие | Untrusted content, ACL, tool allowlist, policy check, approval, red-team tests | Высокий |
| THR-002 | Worker использует права сервисной учётной записи шире Task/Run scope | Межпроектный доступ/изменение | Scoped grants, per-operation authorization, service identity, audit | Критический |
| THR-003 | Ошибка ACL в RAG/графе/кеше возвращает чужие фрагменты или summary | Утечка данных | ACL before retrieval, cache partitioning, graph path filtering, negative tests | Критический |
| THR-004 | Prompt/tool output содержит секрет и он попадает в LLM, Temporal, logs или result | Компрометация credentials | Host-side credential broker, redaction, payload minimization, secret scanning | Критический |
| THR-005 | SSRF через URL/document parser/connector вызывает доступ к metadata/internal services | Захват внутренних сервисов/данных | Egress allowlist, URL validation, DNS/IP checks, redirect restrictions, proxy | Высокий |
| THR-006 | Подмена MCP server/tool schema или supply-chain package | Произвольные действия/утечка | Trusted registry, pin versions, review, allowlist, isolated adapter, SBOM | Высокий |
| THR-007 | BOLA/IDOR в API позволяет обратиться к чужому Project/Epic/Artifact | Утечка/изменение | Object-level authorization on every request, opaque IDs not treated as auth | Критический |
| THR-008 | Подделка Temporal Signal/Update или прямой доступ к Temporal UI | Несанкционированное изменение Workflow | Backend authorization, restricted UI, service auth, audit | Высокий |
| THR-009 | Злоумышленник использует egress/LLM для exfiltration через модельные prompts | Утечка корпоративных данных | Data classification, model routing policy, redaction, egress controls | Критический |
| THR-010 | Слишком широкие tool permissions и excessive agency | Внешнее/необратимое действие | Deny-by-default writes, approvals, preview/diff, bounded autonomy | Высокий |
| THR-011 | Poisoning memory/exemplar/evaluation data | Систематическое ухудшение решений | Provenance, curation, human approval, evaluation gates, rollback | Средний/высокий |
| THR-012 | Недоверенный generated SQL/HTML/Markdown/diagram/code исполняется или рендерится небезопасно | XSS/инъекция/компрометация | Output validation, safe rendering, parameterized APIs, no arbitrary execution | Высокий |
| THR-013 | Компрометация Docker host или чрезмерные privileges контейнера | Полный компромисс среды | Non-root, no socket/privileged, host hardening, patching, backups | Критический |
| THR-014 | Секреты попадают в backup/config repository | Длительная компрометация | SOPS/age, key custody, encrypted backup, access separation, rotation | Высокий |
| THR-015 | Audit Log изменён/удалён администратором или атакующим | Потеря доказательств | Append-only semantics, restricted DB role, export/backup, integrity monitoring | Высокий |
| THR-016 | Resource exhaustion через циклы агентов, большие файлы, retries или tool calls | DoS/рост расходов | Budgets, file limits, timeouts, concurrency caps, rate limits, bounded retries | Высокий |
| THR-017 | Подмена образа/зависимости/Compose config | Выполнение вредоносного кода | Digest pinning, SBOM, scanning, provenance/signing, review | Высокий |
| THR-018 | Утечка данных через Langfuse/observability dashboards | Раскрытие prompt/payload | No payload by default, redaction, RBAC, retention, separate audit | Высокий |
| THR-019 | Model fallback переключает запрос на неподходящий provider/location | Нарушение data residency/policy | Fallback allowlist, same-or-stricter classification policy, explicit route | Высокий |
| THR-020 | Ошибка восстановления связывает Workflow с неверной версией контекста/артефакта | Некорректные действия/порча состояния | Immutable refs, Recovery Manifest, reconciliation, hold ambiguous runs | Высокий |

## 6. STRIDE coverage

| STRIDE | Примеры AI RES | Контроли |
|---|---|---|
| Spoofing | Подмена пользователя, service identity, MCP endpoint | Authentication, mTLS/service credentials, signed/pinned artifacts |
| Tampering | Изменение требований, policy, artifacts, audit, model routing | Immutable versions, approvals, checksums, append-only audit |
| Repudiation | Отрицание tool call/approval/изменения | Correlation IDs, audit event, actor and policy version |
| Information Disclosure | Cross-project retrieval, prompt leakage, logs, model egress | ACL, data classification, redaction, egress policy |
| Denial of Service | Runaway agents, oversized inputs, provider/tool floods | Budgets, quotas, limits, circuit breakers, bounded retries |
| Elevation of Privilege | Worker confused deputy, overbroad service account, forged signal | Scoped grants, per-operation policy, backend authorization |

## 7. Приоритеты обработки

**До MVP:** THR-001–010, THR-012–018 как архитектурные/тестовые требования; THR-013 и THR-017 как инфраструктурные controls.  
**До production-подобного On-prem:** incident runbooks, stronger key custody, service-to-service TLS decision, backup isolation, security monitoring and periodic recovery/security drills.  
**Перед включением code execution или outbound writes:** отдельный threat review, sandbox/approval design и независимый penetration test.

## 8. Допущения и открытые вопросы

- В MVP предполагается один локальный On-prem deployment, а не публичный multi-tenant SaaS.
- Не выбран окончательный Identity Provider и схема MFA/SSO.
- Не выбран окончательный LLM provider; LLM Gateway поддерживает оба класса, но MVP стартует с одного.
- Bifrost требует PoC и security review.
- Уровни классификации данных и retention должны быть согласованы с организациями-владельцами данных.
- Вероятности угроз являются предварительными и должны пересматриваться после PoC и threat workshop.


---

# Дополнение v1.1 — threat treatment baseline

Статус: BASELINED (design). Threats to address in MVP: prompt injection in source/tool output; cross-project/tenant data leakage; BOLA/IDOR; excessive Worker/tool authority; secret exfiltration; unsafe file/parser payloads; connector token compromise; event replay/duplicate side effects; Temporal workflow manipulation; poisoned memory/index; model provider data exposure; log/trace leakage; supply-chain compromise; backup/key loss; denial-of-service/cost exhaustion.

Mandatory controls: untrusted-source labeling; ACL before retrieval/context; scoped expiring grants; per-call policy; idempotency/replay protection; secret broker boundary; egress allowlist; resource/token/time budgets; audit; dependency/image scanning; backup restore drills; emergency revoke/disable. Residual risks and likelihood/impact must be reassessed for each deployment profile; no certification claim.
