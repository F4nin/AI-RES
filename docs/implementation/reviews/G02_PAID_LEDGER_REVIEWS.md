# G156 paid ledger — независимые reviews

**Дата:**2026-11-17. Scope: HEAD `db8d4af34b0933aa2562adcf072b717eb0e3e3e9` + новый0024/module/two PG suites и exact4-table catalogue delta. Это review подготовительного компонента, не live authorization/G156 acceptance.

Оба reviewers работали read-only/blind-first без авторского отчёта, не запускали Docker/tests и не меняли файлы. Код и tests создавали отдельный исполнитель/root; автор не выдаётся за независимого reviewer.

| Reviewer | Проверено | Final verdict |
|---|---|---|
| g02_python_contract_review | Database/Python/code/tests, DDL before apply, balance/reason fixes, оба PG suites и closed catalogue | APPROVE/open0 |
| g02_scope_security_review | Security/code/fail-closed, DDL before apply, оба PG suites/authority boundaries | APPROVE/open0 |

Frozen SHA0024 независимо проверен: `8e1ae3e9bc2249d9eaf40f0b5522dfdb72e6b85d8da86b67361e9ae29ff56751`.

Исправлены MEDIUM mixed balance snapshots (account FOR UPDATE + coordinated real PG test) и LOW unhashable reason (INVALID_USAGE/full reserve/block). All-history bodyhash UNIQUE устраняет потенциальное использование новой reservation старым relay payload. Остальных CRITICAL/HIGH/MEDIUM/LOW findings нет.

Source coverage включает original spend/cap/8 attempts, server-derived costs, unknown holds, claim concurrency/replay, exact manifest/body/ticket, settlement replay/conflict, invalid/overrun commit-before-refusal, audit rollback, immutable accounts/history, narrow grants/FORCE RLS/reset, empty/previous upgrade. Root tests действительно используют разные интерпретаторы и pg_dump/freshDB/psql с exact4-table history/actor comparison; physical recovery не заявляется.

Reviewers не подтверждают своим запуском авторские34/root40 runtime PASS или root snapshot/drift: команды выполнили автор/root. Private TLS seam, host authorization, freshness, trusted provider parsing и real model acceptance отсутствуют; grant/approval из наличия claim не следует. Отдельная read-only рекомендация A для future egress — технический план, не security acceptance кода.
