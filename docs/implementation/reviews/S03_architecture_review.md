# S03 — Architecture conformance review (agent `architect`, independent, blind-first)

Источник: отчёт субагента `architect` (read-only: у субагента не было права записи, текст перенесён Implementation Lead без изменения содержания и сокращён до существа). Дата: 2026-11-11.

**Общий вывод.** Топология соответствует DOC-015 §3–6, §9 и scope промпта S03: Caddy, api, postgres 16, temporal + schema/namespace jobs, temporal-ui (admin), minio + init, otel-collector; Manager/Worker-заготовок и расширения MVP нет; опубликован только Caddy на 127.0.0.1:8443; образы по tag+digest; секреты через SOPS/age → Compose secrets; hardening проверяется статически и по inspect; actions по SHA; WORKING-значения помечены. Отклонения (третья БД Temporal, MinIO из исходников, report-only скан сторонних образов, пароль Temporal в env процесса) зафиксированы в ADR-042…045 и KNOWN_GAPS.

## HIGH
- **H1.** Роль `ai_res_checkpointer` имела `CREATE` на схему `langgraph` (`provision.sh`), что противоречит ADR-036 («setup() DDL в runtime не вызывается») и DOC-015 add. 1.6 («runtime роли без DDL и владения»); тест закреплял нарушение как positive control.
- **H2.** Тест «SCRAM-only» не мог упасть (фильтр исключал `trust`, а `scram-sha-256` всегда присутствовал из `current_setting`).

## MEDIUM
- **M1.** `pg_hba`: `host all all all scram-sha-256` пускает любого с сети `data` как суперпользователя; `CONNECT` на БД `postgres` у PUBLIC.
- **M2.** Для Manager/Worker нет способа достичь Temporal без нарушения PERSIST-023 (Temporal на `data`+`admin`); решить сеть до S11 (например, `workflow`); правило check_compose для Manager/Worker.
- **M3.** Egress deny-by-default выполнен частично: `ingress` не internal (у Caddy неограниченный исходящий трафик); unit-тест допускал `worker-runtime` в `egress`.
- **M4.** runtime-job проходит зелёным при полном skip.
- **M5.** Скан слоёв образов не заглядывает в gzip-слои и не имеет positive control.
- **M6.** `local.enc.yaml` per-developer, но коммитабелен: чистый клон/CI ломается; нет `.sops.yaml`.
- **M7.** Неполный CI-scope промпта: нет Testcontainers-интеграции, oasdiff (ADR-039/G-20), pip-audit (ADR-037 слой 1).
- **M8.** Temporal frontend принимает неаутентифицированные вызовы с `data`/`admin` (Security Arch §2.1; DOC-015 §9.2).
- **M9.** OTel Collector не подключён к api и не редактирует атрибуты (core-дистрибутив без redaction processor).

## LOW
L1 — третья БД `temporal_visibility_db` относительно DOC-015 §5.1 («ai_res_db и temporal_db»): подтвердить владельцем. L2 — консоль MinIO (9001) слушает на всех интерфейсах, доступна всем участникам `data`; UI Temporal без аутентификации. L3 — Release Manifest: нет схемы, `digest: null` у собранных образов, нет сводки скана/профилей. L4 — `make down --volumes` без подтверждения (DOC-015 §15). L5 — `|| true` в `setup-schema.sh`. L6 — egress-тест данных без positive control. L7 — healthcheck Caddy проверял только конфиг. L8 — версия uv в Dockerfile ≠ CI; нет OCI revision label. L9 — hadolint не покрывает caddy Dockerfile; пороги различаются; старые версии Trivy/Syft/otel. L10 — scope `scan_secrets.py`. L11 — STATUS (компонентный раздел) устарел.

## Пункты промпта: отсутствуют / частично
- **Отсутствуют:** CI Testcontainers-интеграция; oasdiff cross-check; pip-audit.
- **Частично:** egress deny-by-default (M3); langgraph provisioning (H1); формат Release Manifest (L3); тест «секрет не в слоях образа» (M5); PERSIST-023 — только существующие сервисы (G-29); observability новых компонентов (M9); `make up` из чистого клона (M6).
- **Покрыто:** остальной scope §5 и тесты §9.
