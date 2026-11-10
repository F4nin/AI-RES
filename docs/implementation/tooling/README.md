# tooling/ — инструменты сохранения контекста и навигации (ADR-040)

| Инструмент | Что делает | Где настроено | Промпт | Внешний трафик |
|---|---|---|---|---|
| session-brief hook | Подставляет в сессию краткую сводку (STATUS + CONTEXT_HANDOFF + git) при startup/resume/clear/compact | `.claude/hooks/session-brief.mjs`, `.claude/settings.json` | `CONTEXT_RETENTION.md` | нет, read-only |
| `CONTEXT_HANDOFF.md` | Единый файл продолжения работы | `docs/implementation/` | `CONTEXT_RETENTION.md` | нет |
| Context7 MCP | Актуальная документация библиотек | `.mcp.json` (`@upstash/context7-mcp@4.6.0`) | `CONTEXT7.md` | да: имя библиотеки и вопрос |
| Serena MCP | Семантическая навигация/рефакторинг по коду (LSP) | `.mcp.json` (`serena@v2.1.0`, uvx из GitHub) | `SERENA.md` | нет (локально; загрузка пакета при первом запуске) |

Не использовано намеренно: ECC `ck` (пишет в `~/.claude/ck` и в нативную память — глобальные изменения), `strategic-compact` hook (скрипт не установлен в проекте).
Первое подключение MCP: Claude Code запросит одобрение `.mcp.json`; затем `/mcp` — проверить статус. Если Serena не стартует — записать в KNOWN_GAPS, работать без неё.
