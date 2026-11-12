# S12 — Независимые review

**Дата:** 2026-11-12 · Агенты (read-only, blind-first, отчёт автора не читали): `security-reviewer`, `silent-failure-hunter`. Основание запуска — `ecc-precedence.md`, п. 2: граница безопасности (SSE/ACL), проверка целостности загрузки, fail-closed поведение отмены. Не запускались: `fastapi-reviewer` (фреймворк WORKING), `architect`, `code-reviewer`, `pr-test-analyzer`, `type-design-analyzer` — решение исполнителя: изменение укладывается в существующие паттерны S08–S11, слои 1–2 ADR-037 (детерминированные проверки и тесты) покрывают остальное; это ограничение отражено в отчёте (§12).

## Итог
CRITICAL 0 · HIGH 1 (зафиксирован как gap, не исправлен в S12) · MEDIUM 15 (исправлены 8, остальные — gaps) · LOW — частично.

## Исправлено в S12
| Источник | Находка | Исправление |
|---|---|---|
| silent M1 | Сбой авторизации/зависимости в потоке сообщался как `access_revoked` | `close` с `access_revoked` только для AUTH/ACCESS/NOT_FOUND, иначе `unavailable` + лог |
| silent M2 | Ошибка чтения истории обрывала поток без кадра и лога | `try/except` → лог + `close unavailable` |
| silent M4 | Пропуск sequence (нет проверки смежности) | `ProjectEventReader._contiguous`: событие известного агрегата принимается только при `last+1`, дыра удерживается |
| silent M5 / security 3 | Переполнение курсора выбрасывало батч; курсор >2048 символов ломал возобновление | батч отдаётся до `gap`; `MAX_TRACKED=24` (под лимит токена); после `gap` — `close resync` |
| silent M8 | `reject_upload` не проверял rowcount | возвращает bool; при проигранной гонке — 409, а не ложный «failed verification» |
| silent M9 | Мёртвый fallback `sha256 or b""` мог записать пустой digest | заменён утверждением |
| silent M10 / security 4 | Новый `httpx`-клиент на каждый completeUpload | один `S3ObjectStore` на приложение |
| security 1 | Опрос SSE продлевал idle-окно сессии | `authenticate(token, touch=False)` |

## Зафиксировано как gap (решение/этап указаны в KNOWN_GAPS)
| Находка | Gap |
|---|---|
| silent H1 / security 5: CANCEL_REQUESTED без повторной reconciliation (активные WorkerRun, закрытый workflow) | G-117 (усиливает G-107) |
| silent M3 / security 10: поздний коммит нового агрегата за settle-окном | G-114 |
| security 2, 3: лимиты потоков; курсор привязан к сессии | G-118 |
| security 6: TOCTOU в `confirm_cancellation` | G-119 |
| silent M7 / security 9, 8, 7: версия объекта не фиксируется; код отказа неразличим; нет проверки владельца при отмене | G-120 |
| silent M6: retention и простой курсор | G-114/G-118 (WORKING-параметр retention) |
| silent L1–L7 | не исправлялись; L6 (составная checksum multipart) входит в G-115/G-120 |
| security 10: `completion_policy_version="wip-1"`, `project.events_read` одним правом на пять типов | G-116, G-113 |

## Не подтверждено исполнением
Ревьюеры тесты не запускали. Утверждения о `created_at` (время начала транзакции) проверены автором: в схеме это `DEFAULT now()` = начало транзакции, поэтому риск M3 реален и записан.
