# G156 / ADR138 — independent reviews, 2026-11-18

Ветка `feat/g02-manager-tools-planning`, HEAD
`db8d4af34b0933aa2562adcf072b717eb0e3e3e9` + scoped working diff.
Точные final hashes — [4 файла](G02_ADMISSION_LIFECYCLE_CODE_HASHES.json).

## Роли и независимость

- `admission_plan`: отдельное read-only planner/architect исследование, затем
  general/Python/database/pr-test review root-authored реализации. Прочитаны
  `.claude/agents/{planner,architect,code-reviewer,python-reviewer,database-reviewer,pr-test-analyzer}.md`.
  Reviewer не писал код/документы, не запускал runtime и не читал авторский отчёт
  до своих выводов. Проектные RLS/UUID/DoD выше общих Supabase/ECC рекомендаций.
- `lifecycle_security`: отдельное blind-first read-only security/architect/
  silent-failure review, с прочитанными одноимёнными ECC instructions. Не автор,
  не оператор Docker/PostgreSQL и не human/security owner продукта.
- `admission_normative`: отдельная read-only нормативная разведка Registry,
  стартовых canonical документов/применимых разделов и current addenda. Не code
  reviewer; выполнил syntax/local-ref/manifest checks, не pinned validation/runtime.
- Root — единственный автор кода/DDL/tests/snapshot/docs и оператор runtime;
  self-check не засчитывается независимым review. Python-testing и
  verification-loop применены как прочитанные checklists; Claude hooks/commands
  не запускались. Разрешение ролей — AGENTS §7 и G7 выбранного security/DB scope.

## Независимые выводы до apply

Оба reviewer признали per-profile transaction advisory fence допустимым без
расширения UPDATE grants/SECURITY DEFINER. Требования: READ COMMITTED, отдельный
snapshot после ожидания, active exact trigger/origin readiness, все четыре
lifecycle поля, обе очередности гонки, отсутствие DB lock через provider I/O.
Отмечены будущий owner lock order, dispatch window и wall-clock expiry limits.
Root включил эти условия в production implementation и ADR138.

Оба прочитали actual0025/admission.py до первого disposable apply и дали
**APPROVE / blocking findings 0**. Старые0017/0020–24 не менялись.

## Final source/test/snapshot review

Оба прочитали полный набор tests и exact snapshot delta относительно initial bytes:
только +20 строк function/owner/trigger/PUBLIC REVOKE, без прочих grants/data changes.
Проверены обе очередности begin/finalize, timestamp и все lifecycle поля, rollback,
таймаут, другие профили, шесть отсутствующих/неполных trigger состояний,
replica session, RR/Serializable refusal, privileges и previous upgrade.

Оба указали evidence limit: исходный previous-upgrade test сравнивал пустые
calls/audit. Root добавил непустые synthetic terminal receipt и две audit записи
под original0024 API grants; оба повторно проверили delta и закрыли это замечание.
Это усиление evidence, не найденный дефект production DDL.

Final verdict обоих: **APPROVE, open findings 0**. Все четыре final SHA256 сверены
каждым отдельно. Продуктовые hashes не менялись после pre-apply verdict.

Исправление тестового rollback root выявил в runtime и сообщил reviewers:
explicit psycopg transaction context заменён plain autocommit=False/manualrollback,
threaded owner SQL получил bounded timeout. Оба проверили final fixture. Начальный
прерванный прогон не выдан за PASS; root выполнил новый полный final scoped run.

Review не подтверждает runtime исполнение reviewer, real provider metadata,
human approval, full pre-pr/Linux CI или завершение G156. Точные root-команды и
результаты — [отчёт](../increments/G02_admission_lifecycle_fence_REPORT.md).

После первичных blind-first выводов `admission_plan` отдельно прочитал итоговые
report/review/hashes и context/status/traceability docs: APPROVE/open0.
Рекомендованные closeout counts сохранены в report; HANDOFF/STATUS уточнены:
main data writes задачей не выполнялись, checksum stores не заявляется.
Это docs review после source verdict, не замена независимости первой проверки.
