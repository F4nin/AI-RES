# AI RES — Аутентификация и управление пользовательскими сессиями

**Версия:** 1.1  
**Этап:** 13 — Архитектура безопасности и модель доступа  
**Статус:** выбранная проектная спецификация для MVP; параметры эксплуатации подлежат конфигурированию и security review.  
**Связанные документы:** `AI_RES_Identity_Access_Control_v1.1.md`, `AI_RES_Security_Architecture_v1.1.md`, `AI_RES_Security_Controls_and_Requirements_v1.1.md`.

## 1. Принятое проектное решение

AI RES реализует модель **Local Authentication for MVP + Pluggable Identity Provider**:

1. В MVP пользовательские учётные записи и аутентификация локальные, управляются AI RES.
2. В архитектуре с первого релиза предусмотрен интерфейс `IdentityProvider`, чтобы позднее подключить внешний OpenID Connect (OIDC) Identity Provider без изменения доменных сущностей пользователя, членства, ролей и ACL.
3. Для первого внешнего IdP поддерживается OIDC Authorization Code Flow с PKCE. SAML напрямую в AI RES не реализуется в MVP; при необходимости SAML может обслуживаться корпоративным IdP/broker, который предоставляет AI RES OIDC.
4. Подключение внешнего IdP — последующая возможность, не обязательная зависимость локального MVP.
5. Пользовательская идентичность не является полномочием: после аутентификации каждый запрос проходит отдельную авторизацию через Policy & Permission Engine.

**Почему выбран этот вариант:** он сохраняет автономность локального On-prem MVP и не вводит обязательный отдельный Identity Provider в локальную установку, но не запирает продукт в собственной схеме логина. Внешний IdP подключается через адаптер и не становится источником проектных ролей/ACL.

## 2. Архитектурная схема

```text
Browser
  -> Reverse Proxy (TLS)
  -> AI RES API
       -> Authentication Service
            -> Local Identity Provider (MVP)
            -> OIDC Provider Adapter (future)
       -> Session Service
       -> Authorization / Policy & Permission Engine
       -> Domain/Application Services

Manager Runtime / Worker Runtime / Temporal Activities
  -> отдельные service identities
  -> не используют пользовательские browser sessions
```

Компоненты:
- `Authentication Service` — login/logout, credential verification, external callback, identity normalization.
- `IdentityProvider` — порт с операциями authenticate/authorize callback/resolve subject; конкретные адаптеры не содержат доменных полномочий.
- `Local Identity Provider` — локальные credentials и локальная проверка пароля в MVP.
- `OIDC Provider Adapter` — будущий адаптер OIDC.
- `Session Service` — создание, продление, отзыв и проверка пользовательских сессий.
- `Authorization Service` — отдельная проверка доступа к объекту и операции.
- `Audit Service` — события безопасности без секретов и credential material.

## 3. Локальные учётные записи MVP

### 3.1 Создание и жизненный цикл
- Первый администратор создаётся только через одноразовую bootstrap-команду/процедуру при первоначальной установке.
- Запрещены встроенные универсальные логин/пароль и default credentials.
- Bootstrap secret передаётся через защищённый механизм установки, не записывается в Git, image, обычные логи или shell history; после использования становится недействительным.
- Последующие пользователи создаются приглашением администратора или управляемой административной процедурой.
- У каждой учётной записи стабильный внутренний `user_id`; email/username — изменяемые атрибуты и уникальные login identifiers в пределах организации.
- Состояния: `INVITED`, `ACTIVE`, `SUSPENDED`, `LOCKED`, `DISABLED`.
- Отключение пользователя немедленно отзывает активные сессии и блокирует новые аутентификации.
- Удаление пользователя не должно разрушать audit trail: предпочтительно деактивация и сохранение actor reference.

### 3.2 Пароли
- Хранить только salted password hash с Argon2id; параметры должны быть конфигурируемыми и соответствовать актуальным рекомендациям OWASP/производительности целевого сервера.
- Уникальная случайная соль для каждого пароля; pepper допустим только при хранении вне БД в секрет-хранилище.
- Не хранить и не логировать пароль, reset token, bootstrap secret или полный credential payload.
- Минимальная длина локального пароля — 15 символов; поддерживать длинные passphrase и password managers; не требовать произвольных регулярных смен без признаков компрометации.
- Проверять новый пароль по доступному локальному denylist распространённых/скомпрометированных паролей; не отправлять пароль во внешний сервис проверки.
- Изменение пароля требует повторной аутентификации; после смены пароля отзываются остальные сессии пользователя.

### 3.3 Восстановление
- В MVP восстановление выполняет администратор через безопасный reset/invite flow либо одноразовую ссылку, если настроен надёжный канал доставки.
- Reset token криптографически случайный, одноразовый, хранится только в виде hash, имеет короткий configurable TTL и связывается с конкретным пользователем и назначением.
- Ответ на запрос восстановления не раскрывает существование учётной записи.
- Для полностью изолированной On-prem установки допускается только администраторская процедура сброса с аудитом; нельзя вводить небезопасный универсальный recovery code.

## 4. Защита login endpoint

- Rate limit по сочетанию account identifier, source network/client signal и глобального порога; лимиты настраиваемые.
- Применять progressive delay и временную блокировку при повторных неудачах; не допускать простой постоянной блокировки аккаунта злоумышленником.
- Ошибки входа должны быть одинаковыми для неизвестного пользователя, неверного пароля и недоступной/заблокированной учётной записи, насколько это возможно без потери операционной диагностики в защищённом audit log.
- Защита от credential stuffing и brute force; security events для аномалий.
- Не раскрывать account existence через регистрацию, восстановление и login responses.

## 5. MFA

- MFA обязательна для `Organization Owner`, `Organization Admin`, `Project Admin` и иных привилегированных административных ролей в production-like профиле.
- Для MVP поддержать TOTP как первый фактор второго уровня; recovery codes — одноразовые, хранить только hash, выдавать один раз.
- Для обычных Analyst/Reviewer MFA может быть включена политикой организации; архитектура не должна ограничивать её только администраторами.
- MFA reset — отдельная привилегированная процедура с повторной проверкой личности, аудитом и уведомлением.
- WebAuthn/passkeys — рекомендуемое последующее усиление; не обязательная зависимость MVP.
- Внешний OIDC IdP может выполнять MFA; AI RES должен получать и проверять только доверенные, заранее согласованные assurance claims, а не выводить MFA из наличия OIDC.

## 6. Сессии браузера

- Использовать непрозрачный случайный session ID в cookie; состояние сессии хранить на сервере (PostgreSQL для MVP; Redis не является обязательной зависимостью).
- Не хранить access token, refresh token или session credential в `localStorage`/`sessionStorage`.
- Cookie: `HttpOnly`, `Secure` в HTTPS deployment, `SameSite=Lax` по умолчанию, ограниченный `Path`, без широкого `Domain`.
- Для state-changing запросов использовать CSRF protection (token + Origin/Referer validation по применимости); CORS — deny-by-default с явным allowlist.
- Ротация session ID после login, MFA completion, privilege elevation и иных security-sensitive transitions.
- Конфигурируемые начальные значения: idle timeout 30 минут; absolute lifetime 12 часов; более строгие значения для административных сессий. Эти значения — безопасные defaults, а не универсальная гарантия соответствия.
- Logout отзывает текущую сессию на сервере. Password reset, account disable, suspected compromise и role revocation инициируют отзыв всех соответствующих сессий.
- Сессии привязаны к user_id и security context; изменение ролей/членства должно применяться немедленно через revocation/version check, а не ждать истечения cookie.

## 7. OIDC внешний IdP — последующая возможность

- Реализовать отдельный `OIDC Provider Adapter` за интерфейсом `IdentityProvider`.
- Использовать Authorization Code Flow + PKCE (S256); запретить implicit flow и password grant.
- Проверять подпись, issuer, audience, expiry, nonce, state, redirect URI exact match и PKCE verifier.
- Разрешать только HTTPS issuer/discovery/JWKS endpoints из административно настроенного allowlist; защищать discovery/JWKS fetch от SSRF.
- Внешний `sub` связывать с внутренним неизменяемым identity mapping `(issuer, subject)`; email не использовать как единственный ключ связывания.
- JIT provisioning — выключен по умолчанию; включение только с явной политикой организации и допустимым доменом/группами.
- OIDC claims подтверждают authentication context, но не назначают автоматически права AI RES. Роли и project memberships остаются в AI RES, если отдельная синхронизация групп не спроектирована и не утверждена.
- SAML не реализуется напрямую в MVP; корпоративный SAML можно интегрировать через OIDC broker/IdP.
- При отключении/ошибке внешнего IdP нельзя автоматически переключать существующую внешнюю учётную запись на локальный пароль с тем же email (защита account takeover). Локальные break-glass accounts — отдельные, заранее созданные, ограниченные и аудируемые.

## 8. Сервисные идентичности

- Пользовательские browser sessions никогда не передаются Manager/Worker Runtime.
- API, Manager Runtime, Worker Runtime, Temporal Activities, Connector Gateway и LLM Gateway Adapter используют отдельные service identities.
- Внутренние credentials короткоживущие, audience-scoped и ротируемые; секреты не помещаются в prompt, LangGraph state, WorkerResult, Temporal history или обычную telemetry.
- Service identity подтверждает компонент, но не заменяет scoped Worker Run grant.
- Worker Run grant выдаётся отдельно trusted platform service и ограничивает project/Epic/Task/Run, ресурсы, операции, инструменты, model profile, срок действия и бюджет.

## 9. Обязательные события аудита

`AUTH_LOGIN_SUCCEEDED`, `AUTH_LOGIN_FAILED`, `AUTH_LOGOUT`, `AUTH_SESSION_REVOKED`, `AUTH_PASSWORD_CHANGED`, `AUTH_PASSWORD_RESET_REQUESTED`, `AUTH_PASSWORD_RESET_COMPLETED`, `AUTH_MFA_ENROLLED`, `AUTH_MFA_RESET`, `AUTH_ACCOUNT_INVITED`, `AUTH_ACCOUNT_DISABLED`, `AUTH_RATE_LIMITED`, `AUTH_OIDC_LOGIN_SUCCEEDED`, `AUTH_OIDC_LOGIN_FAILED`, `AUTH_IDENTITY_LINKED`.

События содержат actor/subject, timestamp, outcome, reason code, correlation_id, source metadata минимально необходимого уровня, auth method и session reference. Пароли, токены, cookies, TOTP seeds и полные claims не записываются.

## 10. Требования и критерии приёмки

| ID | Требование | Приёмка |
|---|---|---|
| AUTH-001 | MVP поддерживает локальные пользовательские учётные записи без обязательного внешнего IdP | Установка и вход работают при недоступности внешних IdP |
| AUTH-002 | Authentication Provider реализован через заменяемый интерфейс | Local provider проходит contract tests; OIDC adapter может быть добавлен без изменения доменной модели |
| AUTH-003 | Пароли хранятся только как Argon2id hash с уникальной солью | DB inspection не находит plaintext; параметры hash проверены |
| AUTH-004 | Bootstrap не использует default credentials и одноразовый secret | Повторное использование bootstrap secret отклоняется; секрет отсутствует в image/logs |
| AUTH-005 | Login защищён от brute force и account enumeration | Rate-limit/progressive delay и generic responses проверены |
| AUTH-006 | MFA обязательна для привилегированных ролей в production-like профиле | Admin login без MFA блокируется; recovery flow аудируется |
| AUTH-007 | Browser sessions — opaque server-side sessions в защищённых cookies | Cookie flags, rotation, CSRF и server-side revocation проверены |
| AUTH-008 | Logout/disable/reset/revocation прекращают действие сессии | Повторное использование отозванной cookie даёт 401 |
| AUTH-009 | Внешняя федерация реализуется через OIDC Code + PKCE | Negative tests для issuer/audience/nonce/state/PKCE/redirect URI |
| AUTH-010 | Внешняя identity mapping основана на issuer + subject | Email change не создаёт новую identity и не связывает чужой аккаунт |
| AUTH-011 | OIDC claims не назначают проектные права без отдельной политики | Неизвестные/подменённые role claims не дают grants |
| AUTH-012 | Service identities отделены от human identities и Worker grants | Browser session не принимается Runtime; Run без grant не выполняет protected operation |
| AUTH-013 | События аутентификации аудируются без секретов | Audit test подтверждает event completeness и отсутствие credential material |

## 11. Безопасные значения по умолчанию

| Параметр | Значение по умолчанию | Примечание |
|---|---|---|
| Auth mode | Local | MVP |
| External IdP | Disabled | Подключается отдельно |
| OIDC flow | Authorization Code + PKCE S256 | Future adapter |
| Password hashing | Argon2id | Work factor benchmarked on target |
| Minimum password length | 15 characters | Long passphrases supported |
| Admin MFA | Required | Production-like profile |
| Analyst MFA | Organization policy | Не выключать архитектурную возможность |
| Session idle timeout | 30 min | Configurable |
| Session absolute lifetime | 12 h | Configurable |
| Session storage | PostgreSQL | Redis optional |
| Cookie | HttpOnly + Secure + SameSite=Lax | Secure обязателен при HTTPS |
| CSRF | Enabled | Для cookie-authenticated state changes |
| OIDC JIT provisioning | Disabled | Explicit opt-in only |
| SAML | Via OIDC broker | No direct MVP implementation |

## 12. Вне объёма MVP

- Прямая реализация SAML SP.
- SCIM provisioning/deprovisioning.
- WebAuthn/passkeys.
- Полноценный enterprise identity governance.
- Автоматическое сопоставление групп внешнего IdP с ролями AI RES без отдельной политики.
- Multi-tenant federation и сложные cross-organization account linking.

## 13. Связанные требования и дальнейшие проверки

- `IAM-*` — роли, членство, ACL и policy decisions: `AI_RES_Identity_Access_Control_v1.1.md`.
- `SEC-*` — системные security controls: `AI_RES_Security_Controls_and_Requirements_v1.1.md`.
- `INFRA-*` — deployment, TLS, secrets, networks: `AI_RES_Infrastructure_Deployment_Operations_v1.3.md`.

Перед implementation baseline выполнить threat review login/recovery/session flows, abuse-case tests, dependency review и security test на account linking.


---

# Дополнение v1.1 — authentication acceptance baseline

Статус: BASELINED (design). Local authentication is MVP. Passwords hashed with Argon2id using reviewed parameters; no plaintext/reversible storage. Opaque server-side sessions in HttpOnly/Secure/SameSite cookies; state-changing requests require CSRF protection; session rotation on login/privilege change; server-side revocation; rate limiting and generic auth errors. Privileged admin MFA (TOTP or stronger) is mandatory for production-like deployments. OIDC Authorization Code + PKCE is future adapter; email/claims do not auto-assign AI RES project roles.
