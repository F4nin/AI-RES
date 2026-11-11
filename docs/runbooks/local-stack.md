# Runbook: локальный стек AI RES (Docker Compose)

Статус: проверено на macOS (Docker Desktop 29.2, Compose v5) в S03. Linux CI-прогон не проверялся локально (см. отчёт S03).

## Требования
Docker 29+ с Compose v2, `uv` 0.11+, `sops` и `age` (macOS: `brew install sops age`; Linux CI: `infra/scripts/install_tools.sh`), Python 3.13.

## Первый запуск (из чистого клона)
```
make secrets-dev   # создаёт age-ключ ВНЕ репозитория, генерирует случайные секреты и локальный TLS-сертификат Postgres, шифрует в infra/secrets/encrypted/local.enc.yaml (per-machine, не коммитится)
make up            # собирает собственные образы, поднимает стек, ждёт healthy и успешного завершения one-shot job
make infra-test-runtime   # runtime-evidence на живом стеке
```
Единственный опубликованный порт — `127.0.0.1:8443` (Caddy, внутренний TLS-CA: браузер/curl предупредит о сертификате; `curl -k`).
Приложение пока не имеет маршрутов (S02), поэтому корень отвечает 404 Problem Details.

## Остановка и очистка
- `make down` — останавливает стек, удаляет контейнеры и сети; **тома данных (Postgres, MinIO) сохраняются**.
- `make reset CONFIRM=yes` — **необратимо удаляет тома данных** локального стека (DOC-015 §15: нужно явное подтверждение).
- `make secrets-clean` — удаляет расшифрованные секреты (`infra/secrets/runtime`). Зашифрованный файл и age-ключ остаются.

## Секреты
- Расшифрованные секреты — `infra/secrets/runtime/` (git-ignored, 0600). Контейнеры получают их как Compose secrets (`/run/secrets/*`); каждый сервис — только свои (проверяется `check_compose.py`).
- `infra/secrets/encrypted/local.enc.yaml` зашифрован под age-ключ **этой машины** и не коммитится (git-ignored). На другой машине `make secrets-dev` создаст свои секреты; если файл есть, а ключа нет — команда остановится с пояснением, а не создаст новый ключ молча.
- age-ключ: `~/.config/ai-res/age/keys.txt` (переопределяется `AI_RES_AGE_KEY_FILE`). **Храните резервную копию отдельно**: без ключа файл не расшифровать. Ключ нельзя коммитить.
- Повторный `make secrets-dev` НЕ перегенерирует существующие секреты и не заменяет файлы (замена ломает bind mount запущенных контейнеров). Ротация — осознанная операция: удалить `local.enc.yaml`, выполнить `make reset CONFIRM=yes` (базы хранят старые пароли), затем `make up`. Полный процесс ротации с аудитом (DOC-019 §5) не реализован.
- TLS для Postgres: локальный CA и серверный сертификат генерируются вместе с секретами (срок 825 дней — WORKING); сетевые подключения к Postgres только по TLS и SCRAM, права по ролям и БД — в `pg_hba.conf` (`infra/config/postgres/entrypoint.sh`).
- Известное исключение: пароль БД Temporal находится в окружении процесса `temporal-server`/`temporal-sql-tool` (читается из файла-секрета в `start.sh`), но не в `docker inspect` и не в логах.

## Доступ к админ-интерфейсам
Temporal UI и MinIO Console намеренно недоступны с хоста и из ingress-сети (сеть `admin` — internal). Постоянного способа открыть их из браузера в S03 нет: для разовой отладки используйте `docker compose ... exec <service> ...` (CLI внутри контейнера) или временный отладочный override-файл с портом на 127.0.0.1, который не коммитится и снимается после работы (нарушает инвариант «опубликован только Caddy»).

## Проверки
- Без запущенного стека (но с Docker и файлами секретов в `infra/secrets/runtime/`): `make infra-check` (политики на рендеренном Compose, все профили, dev/test), `make infra-test` (статические тесты).
- Сеть: `make infra-verify-digests`, `make backend-audit`.
- Живой стек: `make infra-test-runtime` (в CI с `AI_RES_REQUIRE_STACK=1` отсутствие стека — ошибка, а не skip).
Образы: `infra/scripts/supply_chain.sh` — SBOM (Syft) и скан (Trivy); блокирует только собственные образы (ADR-043); исключения — `infra/security/vulnerability-exceptions.yaml`.

## Диагностика
- `docker compose -p ai-res -f infra/compose.yaml -f infra/compose.dev.yaml ps -a` и `logs <service>`; логи не содержат секретов (проверяется тестом).
- `bind source path does not exist` при `up`: секреты были пересозданы; выполните `make secrets-dev` (он идемпотентен и не заменяет файлы).
- Порт 8443 занят: освободите порт; публикация ограничена loopback.
