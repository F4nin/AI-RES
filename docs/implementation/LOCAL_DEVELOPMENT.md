# LOCAL_DEVELOPMENT

Статус: команды S01–S03 работают (см. отчёты); остальные — заготовка, не заявлять как работающие до соответствующего отчёта. Подробности стека: `docs/runbooks/local-stack.md`.

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
| `make migrate` | Отдельный migration job | S04 |
| `make test-integration` | Testcontainers suites | S04 |
| `make bootstrap-admin` | Одноразовое создание первого администратора | S07 |
| `make frontend-check` | Lint, types, unit, E2E | S35 |

## Правила

- Секреты только через SOPS/age → Compose secrets (`infra/secrets/runtime`, git-ignored); `local.enc.yaml` per-machine и не коммитится; `.env` не коммитится.
- Миграции не запускаются из API startup.
- Публичный порт — только reverse proxy.
