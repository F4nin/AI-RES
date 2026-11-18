# NCP-16 B — принятие ограниченного исключения Flash: отчёт

**Дата:** 2026-11-17. **Статус:** нормативное решение ACCEPTED; документационная часть оформлена. Runtime исключения NOT IMPLEMENTED/NOT VERIFIED. Scope — подтверждённое владельцем исключение и последующий лимит технического прогона; продуктовые этапы не запускались.

## 1. Что реализовано

Оформлено исключение DeepSeek Flash первого среза: immutable AI RES artifacts, отдельно наблюдаемая identity, fail-closed при обнаруженном drift до повторной человеческой приёмки. Риски hidden drift/невозможности возврата snapshot приняты владельцем. Бюджет технического прогона допуска — общий потолок10USD; модельных вызовов0.

## 2. Нормативная база и проверка Registry

DOC-075/076/078 v1.1, Registry v4.1 датированная редакция NCP-16, manifest v1.3. Три v1.0 и manifest1.2 сохранены. Bootstrap-путь Registry сохранён из-за существующих ссылок AGENTS/CLAUDE/tooling; dated revision и hash различают редакцию.

## 3. Созданные и изменённые файлы

Новые три canonical v1.1 и manifest1.3; Registry, путь manifest в contracts/mirror-map.json; актуальные refs семи prompts и ROADMAP. Implementation ADR128/NCP/DECISIONS_PENDING, STATUS/HANDOFF/GAPS/ECC и две traceability карты. [Review](../reviews/NCP16_EXCEPTION_REVIEW.md).

## 4. Изменения API / контрактов / событий

Wire API/DTO/JSON Schema/AsyncAPI не менялись; шесть machine mirrors прежние. Только manifest pointer. Identity/admission/drift schema и совместимость ещё проектируются до включения; запрещён fake pinned_model_version. Compatibility baseline не заменялся.

## 5. Миграции и совместимость

Миграций/изменений данных нет; исторические документы сохранены. Существующий код immutable-only и disabled adapter не ослаблены.

## 6. Решения

[ADR128](../decisions/ADR-128-flash-observed-identity-exception.md) фиксирует решение владельца, а не самостоятельное изменение гарантии агентом. Техническое оформление — versioned prose, сохранённый bootstrap Registry, полный новый manifest.

## 7. Несогласованности / NCP

NCP-16 B ACCEPTED только в заданном scope. Нормативная развилка закрыта; G-156 остаётся OPEN по реализации допуска. Исторические checkpoints PROPOSED не переписываются; новая сводка явно имеет приоритет.

## 8. ECC

Root: doc-updater/verification-loop как прочитанные checklists. Отдельный g02_dependencies: planner/architect read-only impact assessment. Отдельный ncp16_security_review: blind-first security/code/docs review, без отчёта автора. Нативные Claude commands/hooks не запускались.

## 9. Проверки

База db8d4af34b0933aa2562adcf072b717eb0e3e3e9 плюс рабочий diff этой задачи, Darwin arm64/Python3.13.5.

| Проверка | Команда / метод | Результат |
|---|---|---|
| Contracts | UV_NO_SYNC=1 UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never PYTHONDONTWRITEBYTECODE=1 make contracts-check contracts-test | exit0; mirror/OAS/AsyncAPI/JSON Schema/Spectral/breaking6/6PASS; tests22passed |
| Prompts | python3 -B docs/implementation/tools/check_prompts.py | exit0;40prompts/0issues |
| Secrets | python3 -B infra/scripts/scan_secrets.py | exit0;0findings |
| Manifest | read-only inline Python3: Registry§2/current manifest set, ID/path uniqueness, SHA256/bytes всех файлов | 74canonical/73hashed,0missing/mismatch |
| Links/scope | read-only inline Python3: Markdown file targets и Git changed/untracked allowlist | PASS;26files/133local links/0missing |
| Format | git diff --check и проверка trailing whitespace новых файлов | PASS после исправления одной строки Registry |

## 10. Security / authorization

Проверены формулировки: Flash-only, no fake pin, no self-grant/fallback, missing identity fail-closed, drift блокирует результат/следующие calls, нет автоматического approval/расходов/rollout. Runtime authorization cases не выполнялись: код не менялся. Отдельный согласованный бюджет не отменяет key/admission/план расходов.

## 11. Независимое review

[Протокол](../reviews/NCP16_EXCEPTION_REVIEW.md): CRITICAL/HIGH/MEDIUM0; один LOW по старой фразе «canonical не менялся» исправлен. Последующая бюджетная запись отличена от исходного approval исключения; отдельный reviewer повторно проверил совокупный diff26files/133links, финал APPROVE/openfindings0.

## 12. Ограничения

Backend/build/runtime/container/full pre-pr/новый Linux CI не запускались: узкий docs+manifest-pointer scope, продуктовый milestone не реализуется/не повышается до VERIFIED. Платные запросы0,ключ не получен. Качество модели, provider compatibility и runtime drift protection не доказаны. Доставка Git не выполнялась в этой сессии обсуждения; рабочая ветка docs/ncp16-flash-identity-exception.

## 13. Контекст и traceability

Актуальные owner решения/оставшиеся gates внесены в STATUS/HANDOFF/GAPS/DECISIONS_PENDING, ADR/NCP/ECC и обе traceability карты. Исторические статусы/отчёты S16 не повышены; источник canonical для будущих prompts обновлён.

## 14. DoD

Документационная согласованность/источники/hash/mirrors/review выполнены; runtime/migration/release gates неприменимы к этой записи и не объявлены пройденными.

## 15. Следующая работа

Продолжать обсуждение по одному вопросу. Нормативное исключение и предел10USD решены; доступ/создание ключа доступен владельцу. До реальных вызовов нужны точный план и тарифы, защищённое подключение ключа, реализация admission/drift и остальные условия приёмки профиля. SLICE-01 и старт G02 сохраняют свои предпосылки.
