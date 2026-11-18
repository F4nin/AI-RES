# G156 — изолированный запуск и фактическая конфигурация Bifrost

Прямое поручение владельца2026-11-18: продолжить подготовку, проверить изолированный запуск и фактическую конфигурацию Bifrost. Это отдельный проверочный checkpoint после ADR136; G02/S17/S20/S21 не запускаются.

Использовать прежний проверенный candidate image с новым provenance check, штатный renderer и только новые синтетические credentials. Одноразовые контейнеры/SQLite/tmpfs/internal network; без real provider client, основного стека, accounts/tariffs/profile seeds и ключей. Не повторять cold SDK build без cache miss/новой причины. Действующие canonical/Compose/config/patch/build/frozen migrations не менять.

Проверить фактически смонтированные/отрендеренные bytes и mode внутри running mount namespace; выбранные live и DB-backed client/provider/VK/auth/catalogue settings через API; auth/model/direct-key negatives с positive relay control; реальные network membership/noports/outbound negative; известные canaries в logs/env. Raw admin/VK/provider responses и credentials не экспортировать. Empty/omitted API fields, выбранные settings и read-only DB-backed queries не считать полной проверкой SQLite или hidden live state.

Контролируемой admin mutation воспроизвести изменение live/SQLite при неизменных file/launch facts. Нестабильность Docker inspector исследовать; минимальную исправляемую ошибку наблюдателя покрыть RED/GREEN regression, сохраняя exact binding всех значимых полей. Исправление не закрывает effective-config enforcement gate.

ECC planner/architect/security/silent-failure для scope и рисков; python-testing/verification-loop как прочитанные checklists; два отдельных blind-first read-only general/Python/test и security reviewers. Автор владеет runtime, reviewers не меняют файлы/контейнеры. Выполнить native tests, затронутые unit/static/fast checks, secret scan и проверку сохранности исходного diff. Full G156/pre-pr/LinuxCI/live/human acceptance не приписывать audit.

Сохранить отчёт/review/hashes, HANDOFF/STATUS/паспорт/план/gap/traceability/ECC. Уведомить о фактическом результате проверки и ближайшем незавершённом шаге; всю подготовку готовой не объявлять при открытом gate.
