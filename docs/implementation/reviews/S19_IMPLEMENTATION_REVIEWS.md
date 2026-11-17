# S19 — независимые implementation reviews

Дата: 2026-11-17. База `745e7d989a75b5457497742e371f60aa8e33ffc0`, ветка `feat/s19-context-package-versioning` + рабочий S19 diff. Original12 governance files вне code review. Все reviewers — отдельные read-only Codex agents, blind-first: исходники/тесты/canonical до авторского отчёта/ADR/passport. Авторские агенты pure manifest и metadata readers не использованы как независимые reviewers своего кода.

| Проверяющий | Применённые ECC роли | Вывод |
|---|---|---|
| `s19_review` | code-reviewer, python-reviewer, architect, pr-test-analyzer, type-design-analyzer | Initial MEDIUM duplicate item refs; исправлен. Final APPROVE, открытых CRITICAL/HIGH/MEDIUM/LOW0 |
| `s19_security` | security-reviewer, silent-failure-hunter | Initial MEDIUM duplicate refs + отсутствие failure build audit; исправлены. Final APPROVE, открытых security findings0 |
| `s19_database` | database-reviewer, silent-failure-hunter; project DB constraints вместо Supabase | Initial MEDIUM duplicate refs + lock inversion с disable/revoke; исправлены. Final APPROVE, открытых DB findings0 |

## Находки и исправления

1. `ContextRepository.load`: проверка длины и принадлежности принимала persisted `[A,A]` для manifest `[A,B]`. Теперь дополнительно точное равенство actual_refs/expected; PG negative seed создаётся сразу неконсистентным, immutable rows не переписываются. Controlled refusal при duplicate/missing ref, unknown/invalid manifest, legacy NULL.
2. Missing/foreign ref прерывал assembly до persisted build-result audit. Теперь failed UoW rollback, затем отдельная безопасная запись `CONTEXT_PACKAGE_BUILD_FAILED`: typed refs, builder/schema, bounded reason; raw exception/source text отсутствуют. Success audit связан с immutable manifest через resource_id/manifestRef и содержит builder/schema/hash/exclusions. Ошибка failure audit даёт controlled dependency refusal, никогда ALLOW.
3. Прежний session → user/membership lock order мог конфликтовать с AccountService user/membership UPDATE → session revoke. Новый порядок org membership → user → project membership → session. Негативный PG regression синхронизируется Event при входе в lock_subject_grants; отказ после revoke, partial package отсутствует. Initial sleep-based test был усилен по review; это не изменение production policy.

Финальная дельта после исправлений рассмотрена всеми тремя. Дополнительно просмотрены explicit previous→head migration test с legacy data, grants/RLS/postflight; OTel parent trace/low-cardinality metrics/audit privacy test; concurrency retry/CAS, Artifact/Source versions, stable manifest и import boundaries.

## Ограничение интеграции

Security reviewer не установил текущий exploitable authorization bypass: production transport/runtime caller не добавлен. `*.read` разрешают включение/чтение derived metadata, не выдают право на произвольную запись бизнес-объектов. Будущая вызывающая команда обязана отдельно авторизовать свой domain action; нельзя открыть rebuild READ_ONLY_VIEWER только потому, что тест проверяет readable refs от такого актора. Условие записано в сервисе/ADR и G-157; это не новое предоставление permissions.

## Точные hashes финального code slice

| Файл | SHA-256 |
|---|---|
| `modules/context/service.py` | `0c410fa6c34f59f22835852e036e3bb10ef03fdf332095ee8b3f0716a4c02275` |
| `modules/context/repository.py` | `480d9e6912df6f01e35c504ff7ca821476834dee2e3ce8017a96b9313c20e07c` |
| migration0018 | `e16dedbbf8cf1cdbf30ecee63ad96bc865ebeae25bbd722fc03979f8adac66e8` |
| `policy/enforcer.py` | `ab444a8878e2396bf9e0a53fbe94a82d67278637f426ab36de4693371f82d2c7` |
| `test_context_builder.py` | `ddaaff27cbaf43f0a9167407fd83ee23c576e237029ade8b5796a1bb529dea84` |
| `test_context_migration.py` | `ee1b1194e83e6d003749ffafccef542d984bd93d7d3c46c96e6ed99e8bec9995` |
| `schema_snapshot.sql` | `3a2325780f09b8f05bc4ffd90c64ac078c3a4340f3909e3674baf14066ebf55a` |

Reviewers самостоятельно не запускали PostgreSQL/full pre-pr/CI. Security reviewer отдельно выполнил два read-only inline Python fake-session примера без файлов/БД; duplicate rejection exit0 — только дополнительная локальная проверка, не runtime evidence. `git diff --check` code reviewer exit0. Root107/695passed — отдельное evidence [отчёта](../increments/S19_context_package_versioning_REPORT.md); review не заменяет эти gates.


Docs evidence review тем же author-independent s19_review после исходных выводов: staged74 local file targets/0missing. MEDIUM duplicate G157 исправлен; stale passport runtime wording и pool-pressure prerequisite уточнены. Pool saturation относится к будущему caller по G157, не объявлена пройденной. Root full local pre-pr exit0, backend1565/infra369/runtime148/contracts22/Renovate10/PoC19,failed/skipped0; это evidence исполнителя, не запуск reviewer.


Final docs-only closeout review: отдельный s19_review read-only APPROVE/openfindings0 после LOW stale contract-map wording fix.10implementation Markdown до добавления этого протокола,102 local links/0missing по Git index, diff PASS. Reviewer через GitHub подтвердил exact-merge ci44112572923/contracts44112573004 success на99e5ec15cfb2343022cd972f0b66e4adfccbe435 и identical trees source head/merge. S19 DONE scoped, G01 IN_PROGRESS/S18 NOT_STARTED; docs SHA не приписан runtime evidence другого SHA. Этот абзац фиксирует фактический verdict, source не меняется.
