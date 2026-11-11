# S03 — Disposition независимых review (ADR-037 слой 2)

Ревьюеры (свежий контекст, blind-first, без чтения отчёта автора): `security-reviewer`, `architect`, `silent-failure-hunter`, `code-reviewer`. Отчёты: `S03_security_review.md`, `S03_architecture_review.md`, `S03_silent_failure_review.md`, `S03_code_review.md`.
Итого: 0 CRITICAL; HIGH — 12 записей (security 4, architecture 2, silent-failure 5, code 1; многие пересекаются), MEDIUM — 32, LOW — 55 (по заявленным ревьюерами счётчикам; детали в отчётах). Статус: FIXED — исправлено и проверено тестом; GAP — не исправлено, зарегистрировано в KNOWN_GAPS/ADR; ACCEPTED — осознанно принято с обоснованием.

| Находка (источники) | Статус | Что сделано / где |
|---|---|---|
| check_compose обходится: профили, network_mode, секреты по сервисам, egress, bind-mount, пустая модель, `_FILE` значение, healthcheck disable, COPY --from, пустой Dockerfile (sec H-1, silent 5) | FIXED | `check_compose.py`, `test_check_compose.py` (52 теста); `--profile '*'` |
| Postgres без TLS, широкий `pg_hba`, CONNECT на `postgres` (sec H-2, arch M1, G-25) | FIXED | TLS (локальный CA), `hostssl` по ролям/БД, `reject`; тесты cleartext→отказ, TLS Temporal подтверждён `pg_stat_ssl` |
| `wait_stack` проходит вхолостую (sec H-3, silent 4) | FIXED | ожидаемые наборы сервисов, missing/timeout = fail; 8 тестов |
| `scan_secrets` слепые зоны; пустые секреты в CI (sec H-4, silent 6–7) | FIXED | JSON-ключи, спецсимволы, токены, root-файлы, не-UTF8, вложенный plaintext в SOPS; скан в CI с реальными значениями; 16 тестов |
| `CREATE` у checkpointer в `langgraph` (arch H1) | FIXED | только USAGE; тест инвертирован, DML positive control |
| SCRAM-only тест не может упасть (arch H2, silent 3) | FIXED | множество методов `pg_hba` ⊆ {scram, reject}, нет md5-хэшей, ssl=on |
| `supply_chain.sh` ничего не сканирует при сбое compose (silent 1) | FIXED | список образов захватывается заранее; ожидаемые образы; SBOM непустой |
| runtime skip → зелёный CI (arch M4, code M2, silent 2) | FIXED | `AI_RES_REQUIRE_STACK=1` в CI → fail |
| per-machine `local.enc.yaml` ломает чистый клон/CI (code H1, arch M6) | FIXED | файл в .gitignore; ключа нет при существующем файле → понятная ошибка; защита `AI_RES_SECRETS_WORLD_READABLE` только в CI |
| скан слоёв образа вхолостую; egress-тест данных; plain-HTTP тест (code M3–M4, arch M5/L6, silent 8–10) | FIXED | gzip/tar рекурсия + canary positive control; bash-проба с positive control; 400 на cleartext |
| `|| true` в setup-schema, namespace.sh (arch L5, silent 11) | FIXED | допускается только «already exists»/«not found» |
| `make down` удаляет тома (code M5, arch L4) | FIXED | `down` сохраняет тома; `make reset CONFIRM=yes` |
| contracts.yml `git fetch` при persist-credentials false (code M1) | FIXED | убран, `origin/$BASE_REF` |
| runbook неточности (code M6) | FIXED | исправлен |
| тест manifest без схемы (code M7, arch L3) | FIXED | jsonschema-валидация + негативные случаи |
| pip-audit нигде не запускается (arch M7) | FIXED | `make backend-audit` + CI |
| healthcheck Caddy/MinIO, timeout-minutes CI, hadolint caddy, verify_digests при 0 pin, test_serve target, `--chown=0:0` | FIXED | см. diff |
| Исключения уязвимостей глобальны по CVE (sec M-1, silent 12) | GAP | G-35 |
| Сторонние образы report-only, `--ignore-unfixed` (sec M-1, silent 13) | ACCEPTED | ADR-043, G-24 |
| MinIO из исходников с `go get` (sec M-2) | ACCEPTED | ADR-042, G-30 |
| Temporal без authn/authz, UI с write (sec M-3, arch M8) | GAP | G-36 |
| Консоль/API MinIO достижимы с `data` (sec M-4, arch L2) | GAP | G-37 |
| Сеть для Manager/Worker → Temporal (arch M2) | GAP | G-38; решить в S11 (правило check_compose допускает `app`/`workflow`) |
| Неограниченный исходящий трафик Caddy (arch M3) | GAP | G-34 (тест фиксирует текущее поведение) |
| OTel не подключён, нет redaction (arch M9) | GAP | G-22 (S13) |
| CI: нет Testcontainers-job, oasdiff (arch M7) | GAP | G-20; интеграционных тестов нет до S04 |
| CI-риски fork-PR (sec M-8) | GAP | G-27 (первый прогон на удалённом CI; политика approval на уровне репозитория) |
| Третья БД `temporal_visibility_db` (arch L1) | ACCEPTED | ADR-044; подтверждение владельца — DECISIONS_PENDING/NCP не требуется как блокер, но отмечено в G-39 |
| Остальные LOW (версии uv, OCI label, ротация ключей, неатомарная запись секретов и др.) | GAP/ACCEPTED | перечислены в отчётах; существенные — G-33, G-39 |

## Повторное review (2026-11-11)

Свежие `security-reviewer` и `silent-failure-hunter` (blind-first): `S03_security_rereview.md`, `S03_silent_failure_rereview.md`. Все прежние HIGH — FIXED и подтверждены; открытых HIGH/CRITICAL нет.
Новые находки, FIXED: bind-mount `secrets/` обходил allowlist секретов (sec M-1); произвольная non-internal сеть давала egress (sec M-2); дыра «lower-case идентификатор» в `scan_secrets` (silent N1); `infra-test-runtime` без стека давал exit 0 локально (silent N2); `pytest.skip(pytrace=…)` (найдено при прогоне).
Остальное — G-40 и существующие G-27, G-34…G-39 (ACCEPTED/GAP).
