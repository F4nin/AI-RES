# tooling/ — инструменты сохранения контекста и навигации (ADR-040)

| Инструмент | Что делает | Где настроено | Промпт | Внешний трафик |
|---|---|---|---|---|
| session-brief hook | Подставляет в Claude Code краткую сводку (STATUS + CONTEXT_HANDOFF + git) при startup/resume/clear/compact; в Codex документы читаются явно | `.claude/hooks/session-brief.mjs`, `.claude/settings.json` | `CONTEXT_RETENTION.md` | нет, read-only |
| `CONTEXT_HANDOFF.md` | Единый файл продолжения работы | `docs/implementation/` | `CONTEXT_RETENTION.md` | нет |
| Context7 MCP | Документация библиотек, remote HTTP с OAuth | `.codex/config.toml` для Codex; `.mcp.json` для Claude Code | `CONTEXT7.md` | да: имя библиотеки и общий вопрос |
| Serena MCP | Локальная семантическая навигация (LSP); в Codex доступны только четыре инструмента чтения | `.codex/config.toml`, `.mcp.json`, `.serena/project.yml`; Serena v2.1.0 закреплена полным SHA | `SERENA.md` | код обрабатывается локально; установка Serena/зависимостей/LSP может требовать сеть |

Не использовано намеренно: ECC `ck` (пишет в `~/.claude/ck` и в нативную память — глобальные изменения), `strategic-compact` hook (скрипт не установлен в проекте).
### MCP для Codex: конфигурация и локальная приёмка (2026-11-17)

**Локальный runtime — PASS:** в Codex 0.169.0 проверены OAuth Context7, шесть содержательных MCP-вызовов и эффективный allowlist Serena; следующий запуск по умолчанию проверен отдельно. Оба сервера в `.codex/config.toml` сохраняют `enabled = false`. Evidence и ограничения — `../DECISIONS_PENDING.md`, «Локальная приёмка Codex и публикация результатов». Этот файл действует для локального Codex в доверенном проекте; `.mcp.json`, Claude hooks и slash commands автоматически в Codex не переносятся. Глобальная конфигурация не изменена; OAuth credentials сохранены клиентом вне Git. При дальнейшем подключении проверять эффективную конфигурацию и локальные overrides.

Context7 использует `https://mcp.context7.com/mcp/oauth`, без API keys/токенов в репозитории. Serena закреплена на `5e4f5cd173c7ff3eed37ee3f1de6c266b937c5dc` (локально сверено с v2.1.0); зависимости самой Serena и LSP ещё требуют проверки воспроизводимости. Оба клиента выбирают проект через `--project-from-cwd`: запускать из корня этого checkout; при другом cwd сервер может выбрать другой проект. Привязки к домашнему каталогу или конкретной ОС нет. Наличие переносимой конфигурации не подтверждает runtime на непроверенных ОС.

Порядок повторной проверки в разрешённом scope (выполнен при локальной приёмке; новые подключения/загрузки должны быть охвачены поручением владельца):

1. Проверить, что проект доверен клиенту, применён проектный config, а Serena показывает только `get_symbols_overview`, `find_symbol`, `find_referencing_symbols`, `search_for_pattern`. При другом наборе инструментов не вызывать сервер до устранения расхождения.
2. Проверить Context7 общим вопросом о библиотеке и Serena навигацией по Python согласно `CONTEXT7.md` и `SERENA.md`. Зафиксировать версии клиента/сервера, HEAD/diff, фактические вызовы и результаты; отсутствие инструмента или пропуск — NOT VERIFIED.
3. Завершить проверочную сессию, убедиться, что оба сервера выключены по умолчанию и проектный diff не содержит credentials или побочных изменений исходников. OAuth credentials остаются в хранилище клиента, вне Git.

Для Claude Code `.mcp.json` остаётся отдельной конфигурацией: HTTP endpoint и SHA/параметры запуска Serena согласованы с Codex; контекст `ide-assistant` сохранён. Codex allowlist и `enabled = false` на Claude Code не распространяются. Его подключения/разрешения проверяются через `/mcp` в самом Claude Code; автоматического запуска в ходе подготовки не было.

Офлайн-проверка синтаксиса из корня проекта использует уже установленный Python с `tomllib`/PyYAML, без `uv run` или синхронизации окружения:

```sh
infra/.venv/bin/python -B -c 'import json, tomllib, yaml; from pathlib import Path; tomllib.loads(Path(".codex/config.toml").read_text()); json.loads(Path(".mcp.json").read_text()); yaml.safe_load(Path(".serena/project.yml").read_text()); print("TOML/JSON/YAML: 3/3 PASS")'
git diff --check
```

Это проверка трёх форматов, не проверка схемы настроек конкретной версии клиента, OAuth или runtime. Дополнительно при подготовке сверены allowlist, флаги CLI по исходникам Serena, SHA/тег и сохранность остальных настроек; evidence — `DECISIONS_PENDING.md`, «Подготовка конфигурации MCP».

Основания: [настройка MCP в Codex](https://developers.openai.com/codex/mcp/), [одноразовые CLI overrides](https://developers.openai.com/codex/config-advanced/), [Context7 OAuth](https://context7.com/docs/resources/all-clients), [MCP в Claude Code](https://code.claude.com/docs/en/mcp). Параметры Serena проверены по исходникам закреплённой версии; порядок — в `SERENA.md`.

## Быстрый локальный путь и когда что запускать (CI-01)
| Команда | Что проверяет | Время (замер 2026-11-14) | Когда |
|---|---|---|---|
| `make pre-push-fast` | ruff, mypy `--strict`, import-linter, тесты без Docker (unit, architecture, contract) | ≈ 8 с | перед каждым пушем и после каждой правки кода |
| `make backend-test` | весь backend-набор с реальными PostgreSQL 16 и Temporal | ≈ 275 с | перед закрытием шага; при правках схемы, ролей, RLS, миграций |
| `make pre-pr` | контракты, backend, инфраструктура, поднятие стека, runtime-тесты, скан секретов | десятки минут | **обязателен** перед тем, как назвать этап VERIFIED; Linux CI остаётся финальным доказательством |

`pre-push-fast` — ранний сигнал, а не доказательство. Правки только в `docs/implementation/**` не запускают `ci.yml` (CI-01 шаг 3): скан секретов по репозиторию выполнится на ближайшем пуше с другими файлами или командой `make infra-scan-secrets`.

`make pre-pr` не заменяет дополнительные jobs CI: `make backend-audit`, `make infra-verify-digests`, hadolint/actionlint и `infra/scripts/supply_chain.sh`. Проверять оба workflow на точном опубликованном SHA, включая counts/skips и security jobs.

### Локальные предпосылки и переносимость

Для dev-secrets нужна внешняя CLI `openssl`, способная выполнить используемое в `infra/scripts/secrets_dev.py` преобразование Ed25519 PKCS#8 seed в public key (`openssl pkey -inform DER -pubout -outform DER`). Python/npm lock-файлы эту CLI не фиксируют. В приёмке системный LibreSSL 3.3.6 завершил этот вызов ошибкой, а тот же неизменённый тест с уже установленным OpenSSL 3.6.3 прошёл. Проверять `openssl version` и разрешение команды через PATH; при необходимости выбрать установленную совместимую CLI только для процесса запуска. Не записывать путь конкретного Mac в проектный config и не менять глобальный PATH как побочный эффект.

Заключительный локальный прогон: `make -j1 pre-pr`, exit 0, 635,48 с; contracts 22, backend 1291, infra 307, отдельный runtime 148; ошибок/пропусков нет. Runtime-набор уже входит в infra и затем повторяется отдельной целью Makefile; суммы — исполнения, не уникальные тесты. В backend 540 предупреждений; Spectral использует неизменённый baseline с 27 warning entries. Это не утверждение нулевого числа предупреждений.

Среда: Darwin 25.6.0 arm64, Python 3.13.5, uv 0.11.31, Node 22.23.5/npm 10.9.9, OpenSSL 3.6.3. Локальный Mac — проверенная среда, а не ограничение разработки/сборки/эксплуатации одной ОС. Новый Linux CI оценивается отдельно; новую матрицу Windows/WSL2 владелец не требовал. Чистая установка backend/contracts/infra и npm прошла во временных каталогах; unpinned Hatchling и patch-версии Python/Node остаются ограничениями побитовой воспроизводимости сборки.

