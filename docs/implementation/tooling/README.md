# tooling/ — инструменты сохранения контекста и навигации (ADR-040)

| Инструмент | Что делает | Где настроено | Промпт | Внешний трафик |
|---|---|---|---|---|
| session-brief hook | Подставляет в сессию краткую сводку (STATUS + CONTEXT_HANDOFF + git) при startup/resume/clear/compact | `.claude/hooks/session-brief.mjs`, `.claude/settings.json` | `CONTEXT_RETENTION.md` | нет, read-only |
| `CONTEXT_HANDOFF.md` | Единый файл продолжения работы | `docs/implementation/` | `CONTEXT_RETENTION.md` | нет |
| Context7 MCP | Актуальная документация библиотек | `.mcp.json` (`@upstash/context7-mcp@4.6.0`) | `CONTEXT7.md` | да: имя библиотеки и вопрос |
| Serena MCP | Семантическая навигация/рефакторинг по коду (LSP) | `.mcp.json` (`serena@v2.1.0`, uvx из GitHub) | `SERENA.md` | нет (локально; загрузка пакета при первом запуске) |

Не использовано намеренно: ECC `ck` (пишет в `~/.claude/ck` и в нативную память — глобальные изменения), `strategic-compact` hook (скрипт не установлен в проекте).
Первое подключение MCP: Claude Code запросит одобрение `.mcp.json`; затем `/mcp` — проверить статус. Если Serena не стартует — записать в KNOWN_GAPS, работать без неё.

## Быстрый локальный путь и когда что запускать (CI-01)
| Команда | Что проверяет | Время (замер 2026-11-14) | Когда |
|---|---|---|---|
| `make pre-push-fast` | ruff, mypy `--strict`, import-linter, тесты без Docker (unit, architecture, contract) | ≈ 8 с | перед каждым пушем и после каждой правки кода |
| `make backend-test` | весь backend-набор с реальными PostgreSQL 16 и Temporal | ≈ 275 с | перед закрытием шага; при правках схемы, ролей, RLS, миграций |
| `make pre-pr` | всё, что делает CI (контракты, backend, инфраструктура, поднятие стека, runtime-тесты, скан секретов) | десятки минут | **обязателен** перед тем, как назвать этап VERIFIED; Linux CI остаётся финальным доказательством |

`pre-push-fast` — ранний сигнал, а не доказательство. Правки только в `docs/implementation/**` не запускают `ci.yml` (CI-01 шаг 3): скан секретов по репозиторию выполнится на ближайшем пуше с другими файлами или командой `make infra-scan-secrets`.

