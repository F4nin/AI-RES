# AI RES — Контроли и проверяемые требования безопасности

**Версия:** 1.2  
**Статус:** BASELINED — mandatory security requirements; runtime tests are release blockers.

## 1. Правила чтения

`MUST` — обязательное требование предлагаемого security baseline. `SHOULD` — рекомендуемое требование, отступление требует rationale и принятия риска. Статусы `PROPOSED` означают, что требование сформулировано, но ещё не утверждено пользователем. Приоритет: P0 — блокирует MVP/security gate; P1 — требуется до production-подобной эксплуатации; P2 — последующее усиление.

## 2. Требования

| ID | Требование | Приоритет | Проверка | Статус |
|---|---|---:|---|---|
| SEC-001 | Каждый API endpoint, работающий с объектом, MUST выполнять object-level authorization | P0 | Negative BOLA/IDOR tests | PROPOSED |
| SEC-002 | ACL MUST применяться до retrieval, graph traversal, cache response, summarization и export | P0 | Cross-project leakage tests | PROPOSED |
| SEC-003 | Каждая Worker Run MUST иметь scoped grants с expiry; права не наследуются автоматически | P0 | Grant boundary/expiry tests | PROPOSED |
| SEC-004 | Каждый tool/connector side effect MUST проходить независимую policy authorization перед исполнением | P0 | Deny/allow integration tests | PROPOSED |
| SEC-005 | Worker/Manager MUST NOT иметь прямой произвольный доступ к provider credentials | P0 | Runtime secret inspection | PROPOSED |
| SEC-006 | Secrets MUST NOT appear in prompts, Context Packages, Worker Results, Temporal History, logs or traces | P0 | Canary secret tests | PROPOSED |
| SEC-007 | LLM requests MUST route through AI RES LLM Gateway Adapter and approved Gateway | P0 | Network/API integration test | PROPOSED |
| SEC-008 | Provider/model routing MUST enforce data classification and egress policy | P0 | Routing policy tests | PROPOSED |
| SEC-009 | Fallback MUST use only explicitly allowed provider/model profiles and MUST re-evaluate data policy | P0 | Fallback negative tests | PROPOSED |
| SEC-010 | External writes MUST be deny-by-default in MVP unless separately approved and scoped | P0 | Connector policy tests | PROPOSED |
| SEC-011 | Untrusted source/tool output MUST NOT modify system/org/project rules or grants | P0 | Prompt injection test suite | PROPOSED |
| SEC-012 | MCP servers and tools MUST be registered, versioned, allowlisted and policy-checked | P1 | Registry and runtime tests | PROPOSED |
| SEC-013 | Services MUST use separate service identities and least-privilege credentials | P0 | Credential inventory/permission review | PROPOSED |
| SEC-014 | PostgreSQL, Temporal, MinIO and Redis MUST NOT be publicly exposed | P0 | Compose/network scan | PROPOSED |
| SEC-015 | Only Reverse Proxy MUST expose user-facing ingress in MVP | P0 | Port scan and Compose review | PROPOSED |
| SEC-016 | Runtime containers MUST be non-root, non-privileged and MUST NOT mount Docker Socket | P0 | Container config scan | PROPOSED |
| SEC-017 | Runtime resources, file sizes, execution time, concurrency and retries MUST be bounded | P0 | Load/abuse tests | PROPOSED |
| SEC-018 | URL fetchers/connectors MUST prevent SSRF, private IP access and unsafe redirects | P0 | SSRF test suite | PROPOSED |
| SEC-019 | Domain audit MUST record actor, action, resource, scope, policy decision and correlation IDs | P0 | Audit event tests | PROPOSED |
| SEC-020 | Audit data MUST be protected from ordinary application update/delete paths | P1 | DB role and tamper tests | PROPOSED |
| SEC-021 | Telemetry MUST redact secrets and sensitive payloads by default | P0 | Canary and log inspection | PROPOSED |
| SEC-022 | Admin interfaces MUST be restricted to authorized administrators | P0 | Network/auth tests | PROPOSED |
| SEC-023 | Temporal Signals/Updates MUST be authorized by Backend before dispatch | P0 | Forged signal tests | PROPOSED |
| SEC-024 | Generated HTML/Markdown/SQL/OpenAPI/diagrams MUST be validated/safely rendered before use | P1 | Injection and schema tests | PROPOSED |
| SEC-025 | Container images MUST be pinned by digest for reproducible deployment | P1 | Release manifest check | PROPOSED |
| SEC-026 | Release images SHOULD have SBOM, vulnerability scan and provenance/signature evidence | P1 | CI/release evidence | PROPOSED |
| SEC-027 | Secret rotation/revocation MUST have documented owner and runbook | P1 | Rotation drill | PROPOSED |
| SEC-028 | Backups containing sensitive data MUST be encrypted and access-controlled | P0 | Backup restore/access test | PROPOSED |
| SEC-029 | Critical approval MUST bind to exact object version/hash | P0 | Approval mutation test | PROPOSED |
| SEC-030 | Security-relevant events MUST be monitored and alertable | P1 | Alert simulation | PROPOSED |
| SEC-031 | Security incidents MUST have containment, credential revocation, evidence preservation and recovery runbooks | P1 | Tabletop exercise | PROPOSED |
| SEC-032 | AI evaluation suite MUST include prompt injection, data exfiltration, cross-project leakage and tool misuse cases | P0 | Evaluation Set coverage | PROPOSED |

## 3. Security gates

**Before MVP internal use:** SEC-001–011, 013–019, 021–024, 028–029, 032.  
**Before production-like On-prem:** SEC-012, 020, 025–027, 030–031 plus operational review.  
**Before enabling code execution or outbound writes:** separate threat assessment, sandbox controls, explicit approval workflow and independent penetration testing.

## 4. Requirement lifecycle

Все SEC requirements должны быть заведены в общий каталог требований с типом NFR/SyR/CON, связаны с Threat IDs, компонентами, задачами реализации и Verification Cases. Статус PROPOSED не означает утверждение. После утверждения требования получают владельца, baseline/version и критерий приёмки.


---

## Дополнение v1.1 — требования AUTH-001—AUTH-013

Для MVP обязательны требования AUTH-001—AUTH-008 и AUTH-012—AUTH-013. AUTH-009—AUTH-011 являются требованиями к будущему OIDC Adapter и должны быть покрыты contract/security tests до его включения.

| ID | Требование | Приоритет | Проверка |
|---|---|---|---|
| AUTH-001 | Local Authentication работает без внешнего IdP | MUST / MVP | Отключить внешнюю сеть/IdP и выполнить login |
| AUTH-002 | Authentication Provider отделён интерфейсом | MUST / MVP | Contract tests Local provider; доменная модель не зависит от provider |
| AUTH-003 | Пароли хранятся как Argon2id hashes | MUST / MVP | DB inspection, hash parameter test |
| AUTH-004 | Bootstrap admin без default credentials, одноразовый bootstrap secret | MUST / MVP | Повторное использование отклоняется; secret scan image/logs |
| AUTH-005 | Защита login от brute force и account enumeration | MUST / MVP | Rate-limit, progressive delay, generic response tests |
| AUTH-006 | MFA обязательна для привилегированных ролей | MUST / MVP | Admin login без MFA denied |
| AUTH-007 | Opaque server-side browser sessions и CSRF protection | MUST / MVP | Cookie flags, CSRF, rotation, session storage tests |
| AUTH-008 | Logout/reset/disable/revocation отзывают sessions | MUST / MVP | Reuse revoked session rejected |
| AUTH-009 | OIDC Authorization Code + PKCE S256 | SHOULD / Future | OIDC protocol negative tests |
| AUTH-010 | OIDC identity mapping `(issuer, subject)` | SHOULD / Future | Email change/account-linking tests |
| AUTH-011 | OIDC claims не назначают AI RES permissions автоматически | MUST / Future | Forged role/group claims cannot grant access |
| AUTH-012 | Human, service и Worker Run identities разделены | MUST / MVP | Cross-identity misuse tests |
| AUTH-013 | Authentication security events аудируются без секретов | MUST / MVP | Event coverage and secret-leak scan |

AUTH требования дополняют SEC controls и не заменяют их. Подробные flows и критерии — `AI_RES_Authentication_and_Session_Management_v1.0.md`.


---

# Дополнение v1.2 — mandatory security requirements baseline

Статус: BASELINED (design). Требования SEC-001..SEC-0xx P0 являются release blockers для MVP; P1 controls обязательны до production-like deployment; P2 controls планируются по risk. Статус `BASELINED` означает, что требования утверждены как проектный baseline, а не что они уже реализованы.

Для всех P0: test evidence must be attached to release. Critical security/privacy failure, cross-project data leakage, unauthorized side effect, privilege escalation, secret exposure or bypass of human approval blocks release. RLS tests must run under non-owner runtime identities. Missing tenant/project context denies access. Runtime roles must not own tables or have BYPASSRLS/SUPERUSER/DDL.
