# LOCAL_DEVELOPMENT

Статус: команды S01–S04 работают (см. отчёты); остальные — заготовка, не заявлять как работающие до соответствующего отчёта. Подробности стека: `docs/runbooks/local-stack.md`.

## Требования к машине (проверено в S00)

Python 3.13 (ADR-001), uv 0.11+, Docker 29 + Compose v2, Node 22 LTS для contract/UI инструментов (ADR-004, ADR-019; локально сейчас Node 26 — см. G-03), PostgreSQL клиент 16 (опционально).

## Планируемые команды

| Команда | Назначение | Появится в |
|---|---|---|
| `make backend-install` / `backend-check` / `backend-test` | uv sync --locked; ruff+mypy+import-linter; pytest | S02 |
| `make contracts-install` | `uv sync --locked`, `npm ci --ignore-scripts` | S01 |
| `make contracts-check` | Валидация, lint, зеркало, breaking-change | S01 |
| `make contracts-test` | pytest негативных/позитивных тестов toolchain | S01 |
| `make contracts-baseline` | Принять текущие контракты как baseline (решение владельца) | S01 |
| `make backend-check` | ruff, mypy, unit tests | S02 |
| `make secrets-dev` | Генерация dev-секретов и локального TLS Postgres (SOPS/age, без default credentials) | S03 ✅ |
| `make up` / `make down` / `make reset CONFIRM=yes` | Стек Compose; `down` сохраняет тома, `reset` удаляет их | S03 ✅ |
| `make infra-check` / `infra-test` / `infra-test-runtime` / `infra-verify-digests` / `backend-audit` | Политики Compose, статические и runtime-тесты, digests, аудит зависимостей | S03 ✅ |
| `make migrate` | Отдельный migration job (`alembic upgrade head` как `ai_res_migrator` → `SET ROLE ai_res_owner`); `make up` уже запускает его при старте стека | S04 ✅ |
| `make test-integration` | PostgreSQL 16 Testcontainers suites (миграции, роли/гранты, RLS, tenant context, drift) — нужен Docker | S04 ✅ |
| `make backend-test-unit` | Быстрый набор без Docker | S04 ✅ |
| `make db-snapshot` | Пересоздать reviewed design snapshot `backend/ops/postgres/schema_snapshot.sql` (дифф проверять вручную) | S04 ✅ |
| `make bootstrap-admin` | Одноразовое создание первого администратора | S07 |
| `make frontend-check` | Lint, types, unit, E2E | S35 |

## Правила

- Секреты только через SOPS/age → Compose secrets (`infra/secrets/runtime`, git-ignored); `local.enc.yaml` per-machine и не коммитится; `.env` не коммитится.
- Миграции не запускаются из API startup: их выполняет только одноразовая служба `migrate`. Если меняете `infra/config/postgres/entrypoint.sh` (pg_hba), нужен `docker compose restart postgres`: hba пересобирается только при старте контейнера.
- Роли БД создаются provisioning-ом (`provision_roles.sql`, суперпользователь), а не миграцией; схемы, гранты и RLS — Alembic.
- Публичный порт — только reverse proxy.

## Защищённый транспорт G02

`infra/compose.g02.yaml` подключается после `infra/compose.yaml`. У него
отдельное имя Compose-проекта `ai-res-g02-protected`. Контур можно запускать
через выбор `outbox-dispatcher` и его зависимостей в выделенном dev/test
окружении. Для проверки на временном PostgreSQL используется
`python -B -m infra.temporal_auth_poc.protected_candidate` из backend venv.
Команды сборки образов и результаты записаны в отчёте S20.

Для собранного `ai-res/temporal-native:g02-local` команда
`infra/scripts/supply_chain.sh --g02-native-only` создаёт SBOM и проверяет
связанные Go-пакеты. CI блокирует находки HIGH/CRITICAL с доступным
исправлением, неуспешный скан и отсутствие инвентаря Go для бинарника.

Проверка перехода со stock Temporal выполняется из корня репозитория командой
`backend/.venv/bin/python -B -m infra.temporal_auth_poc.compose_cutover`.
Она использует те же собранные образы, плюс закреплённый образ stock Temporal.
Проверка на временной БД сохраняет закрытые истории при переключении и завершает
тот же ожидающий legacy Run после возврата на stock. Probe ждёт фиксации
повторной постановки отклонённой задачи в очередь перед возвратом.
Для рабочего переключения
требуется сначала остановить приём legacy Start и дождаться завершения открытых
Run. Откат после допуска новых native Run требует своей проверки.

После инициализации обычного локального SOPS-пакета `python -B -m
infra.scripts.secrets_dev init-g02` готовит `infra/secrets/g02` и отдельный
зашифрованный пакет. На macOS для этой команды нужен OpenSSL 3 с поддержкой
Ed25519. `G02_PROTECTED_DIR` указывает на этот закрытый каталог.
`G02_REQUEST_MAX_BYTES`, `G02_CREDENTIAL_MAX_BYTES`, `G02_MAX_CONNECTIONS`,
`G02_CREDENTIAL_TTL_SECONDS` и `G02_NAMESPACE_RETENTION_SECONDS`
задаются явно из доверенной конфигурации окружения. Числа временного стенда
имеют силу только внутри сценария приёмки.

Запуск `api` в этом профиле требует read-only манифеста
`G02_RECONCILIATION_FILE`. Модель `BoundStartSchedule` определяет его форму.
Каждая запись `scopes` задаёт точные `organization_id` и `project_id`,
а `admitted_operation_types` перечисляет допущенные `MANAGER_MESSAGE`
или `PLAN_EXECUTION`. `server_name` — `temporal-workflow`. Пути файлов внутри
контейнера задаются как `/run/secrets/temporal_frontend_ca`,
`/run/secrets/temporal_reconciliation_cert` и
`/run/secrets/temporal_reconciliation_key`. Частота, размер страницы,
дедлайны и режим post-ACK поступают из этого же манифеста. API проверяет
состав конфигурации до запуска сверки.

При восстановлении утраченного каталога из запечатанного пакета
`active-certs` пуст. Повторный допуск leaf требует явной публикации
проверенного fingerprint доверенным оператором. Отсутствующий fingerprint
остаётся отзывом. Закрытый каталог, временные профили и их ключи остаются
в игнорируемых путях.
