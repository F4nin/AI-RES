# LOCAL_DEVELOPMENT

Статус: **заготовка** — команды появляются по мере выполнения этапов; не заявлять как работающие до соответствующего отчёта.

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
| `make up` / `make down` | Локальный стек Compose | S03 |
| `make secrets-dev` | Генерация dev-секретов (без default credentials) | S03 |
| `make migrate` | Отдельный migration job | S04 |
| `make test-integration` | Testcontainers suites | S04 |
| `make bootstrap-admin` | Одноразовое создание первого администратора | S07 |
| `make frontend-check` | Lint, types, unit, E2E | S35 |

## Правила

- Секреты только через `infra/secrets/encrypted` (SOPS/age) и Compose secrets; `.env` не коммитится (`.gitignore`).
- Миграции не запускаются из API startup.
- Публичный порт — только reverse proxy.
