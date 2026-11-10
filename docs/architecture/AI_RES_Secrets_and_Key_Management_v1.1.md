# AI RES — Управление секретами и криптографическими ключами

**Версия:** 1.1  
**Статус:** BASELINED — secrets design; rotation/recovery runtime tests pending.

## 1. Классы секретов

- LLM provider API keys и gateway credentials.
- GitHub/GitLab access tokens и connector credentials.
- PostgreSQL/Temporal/MinIO/Redis service credentials.
- Signing keys, SOPS/age private key, TLS private keys/certificates.
- Backup encryption keys и recovery credentials.
- Session/JWT signing secrets и внутренние service credentials.

## 2. Архитектурный принцип

Секреты принадлежат инфраструктуре и host-side adapters, а не агентам. Manager/Worker получает право выполнить разрешённую операцию через Gateway, но не получает исходный provider key. Если секрет необходим адаптеру, он извлекается только на стороне adapter/credential broker с минимальным scope.

## 3. MVP storage/bootstrap

- SOPS + age для шифрования секретов, которые необходимо хранить рядом с конфигурацией в Git.
- age private key хранится отдельно от Git и deployment bundle; доступ ограничен администраторами.
- Docker Compose secrets передают расшифрованные значения только соответствующим сервисам.
- Plaintext не допускается в `.env` tracked files, Docker image layers, source code, logs, traces, prompts, Context Packages, Worker Results или Temporal History.
- Локальные plaintext bootstrap files должны иметь ограниченные filesystem permissions и исключаться из backup без шифрования.
- Compose secrets не считаются полноценным динамическим Vault; adapter к Vault/enterprise secret manager остаётся будущей точкой расширения.

## 4. Runtime access

- Каждый сервис получает отдельный credential.
- Credentials не разделяются между Manager и Worker без явной необходимости.
- Worker Run не получает provider credentials напрямую.
- Tool/Connector adapter получает только credentials конкретной интеграции и конкретного scope.
- Secret retrieval и использование фиксируются в security audit без записи значения.
- Rotation/revocation не должны требовать пересоздания бизнес-объектов; активные Run при отзыве критического credential безопасно останавливаются или переходят в controlled failure.

## 5. Ротация и отзыв

Для каждого секрета фиксируются owner, purpose, consumers, scope, created_at, last_rotated_at, expiry/rotation policy, revocation procedure и incident contact. Периодичность зависит от типа credential и требований provider; конкретные интервалы задаются после threat/risk review, а не выдумываются универсально.

Обязательные события ротации: подозрение на утечку, увольнение/смена администратора, смена provider permissions, компрометация host/backup, обнаружение в логах или репозитории. При инциденте: revoke → rotate → verify consumers → audit → preserve evidence.

## 6. Ключи и backup

- SOPS/age private key и backup encryption keys хранятся отдельно от зашифрованных backup.
- Восстановление требует документированного доступа к ключам; тестировать восстановление на отдельном окружении.
- Recovery Manifest содержит идентификаторы/версии ключей, но не сами ключи.
- Критические ключи не должны быть доступны тому же service account, который может удалить backup.

## 7. Запрещённые места хранения

LLM prompts/responses, LangGraph state/checkpoints, Temporal Workflow history, tool arguments visible to model, Worker result payloads, обычные application logs, OpenTelemetry attributes, screenshots, generated documentation, source control plaintext и unencrypted backups.

## 8. Приёмочные проверки

- Secret scanning репозитория и release artifacts.
- Проверка отсутствия секретов в Docker image layers и контейнерных env dumps, кроме целевого secret mount.
- Canary secret не появляется в LLM prompt, Worker result, Temporal history, logs/traces.
- Rotation/revocation проверяется на работающем и ожидающем Worker Run.
- Backup restore выполняется с корректным key custody без помещения ключей в Recovery Manifest.


---

# Дополнение v1.1 — secrets baseline

Статус: BASELINED (design). MVP uses SOPS + age for encrypted configuration at rest and Docker Compose secrets for runtime delivery. age private key remains out-of-band and is not committed. Runtime components receive only required secrets; provider/connector credentials remain in Gateway/Adapter boundary. Rotation uses overlapping credentials where provider permits, update secret, reload/restart dependent adapter, verify health, revoke old credential, audit. Signing/encryption/backup keys have separate purposes and rotation/recovery procedures. Secret values never enter LLM context, WorkerRunEnvelope, Temporal history, logs, traces, artifacts or error messages.

Vault/enterprise Secret Manager adapter is post-MVP; architecture must not hardcode SOPS as runtime secret API.
