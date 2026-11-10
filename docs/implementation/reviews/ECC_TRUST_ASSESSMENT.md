# ECC Trust Assessment (Spec Addendum v1.3 §4)

**Дата:** 2026-11-10 · **Выполнил:** Implementation Lead · **Статус:** выполнено; приёмка security owner — OD-03

| Критерий | Факт | Оценка |
|---|---|---|
| Издатель / источник | `github.com/affaan-m/ecc`, версия 2.2.3, commit `d2ef2680594f9a17526a6e1a2e18b3d242c5d17b` (6 Nov 2026); локальный checkout `../tools/ecc` | Сторонний open-source; версия зафиксирована коммитом |
| Способ установки | Manual project-local (`.claude/ecc/install-state.json`, target `claude-project`); нативные плагины не установлены (`~/.claude/plugins/installed_plugins.json` пуст); `enabledPlugins: {}` | Нет двойной установки |
| Hooks | `hookConsent: null`; в `.claude/settings.json` hooks отсутствуют | Не исполняются автоматически |
| MCP | `.claude/mcp-configs/mcp-servers.json` присутствует, но не подключён (нет `.mcp.json`) | Не активно |
| Permissions | `.claude/settings.local.json`: allow `Bash(bash *)`, `Bash(brew upgrade *)` | **Риск:** широкое разрешение `bash *` (не от ECC, локальная настройка пользователя) — рекомендуется сузить (OD-03) |
| Сетевой доступ | Команды: `/security-scan` запускает `npx ecc-agentshield` (загрузка незакреплённого npm-пакета); `/code-review` PR-режим использует `gh`; `/test-coverage`, `/build-fix` — `npx` локальных инструментов; `scripts/auto-update.js` существует, не подключён | `/security-scan` — только с согласия владельца; `/code-review` — только локально; auto-update не использовать |
| Секреты | Компоненты ECC не требуют секретов AI RES | — |
| Update policy | Автообновление не включено; обновление — только явным решением | Соответствует ecc-precedence.md |
| Telemetry | Не обнаружено включённой telemetry в project-local установке | Требует подтверждения при обновлении версии |
| Конфликты с правилами AI RES | Перечислены в `.claude/rules/ecc-precedence.md` | Управляются иерархией |

**Вывод:** допустимо как dev-time инструментарий при соблюдении ограничений выше. Решение об использовании — ADR-007.

## Дополнение: сверка целостности (2026-11-11)

428 файлов из `.claude/ecc/install-state.json`: 426 побайтно совпадают с `../tools/ecc` @ `d2ef268`; 2 (`.claude/AGENTS.md`, `commands/security-scan.md`) отличаются только удалённым префиксом `ecc:` (project-local установка). В `../tools/ecc` изменён `yarn.lock` (в проект не устанавливается). Установка идёт из каталога вне репозитория. Разрешения `Bash(bash *)`/`brew upgrade *` — OD-11.

**2026-11-11:** широкие разрешения `Bash(bash *)`/`brew upgrade *` удалены по просьбе пользователя (OD-11 закрыт).
