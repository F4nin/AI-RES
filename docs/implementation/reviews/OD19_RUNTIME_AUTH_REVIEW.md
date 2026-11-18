# OD-19 / ADR-129 — независимое review технического решения

**Дата:** 2026-11-17. База db8d4af34b0933aa2562adcf072b717eb0e3e3e9; ветка docs/ncp16-flash-identity-exception с предшествующим отдельным NCP16 diff. Scope этого review — ADR129/OD19 implementation docs, не runtime implementation.

Отдельный ncp16_security_review применил ECC security-reviewer/architect/code-reviewer blind-first/read-only к ADR129 до создания отчёта автора; не участвовал в его авторстве. Файлы/данные/секреты не менял, runtime/paid tests не запускал.

## Findings и исправления

1. MEDIUM: task-token receipt доказывал владение выдачей, но явно не авторизовал вложенные Workflow Commands. Добавлен ADR129§2.3: server-enforced typed command allowlist и backend assignment/Gate checks; запрещённые child/signal/continue/queue/type/input paths deny; negative test valid Manager token+malicious Commands. SDK protobuf confirms Commands содержат client-supplied queue/type/input.
2. MEDIUM: разрешённый Start по dispatch intent не имел конкретного auth-control check seam, Start ещё не имеет receipt. Добавлен ADR129§3.2: narrow read-only authoritative intent check доStart, exact execution/request binding и cancellation/read purpose checks; нет domain mutation/self-grant/Temporal RPC.

Обе правки — требования дизайна и PoC, не заявления runtime protection. Финальный verdict фиксируется после delta recheck.

## Финальный verdict

**APPROVE, открытых CRITICAL/HIGH/MEDIUM/LOW — 0.** Reviewer повторно проверил фактический ADR-129 (153 строки, 7 локальных ссылок, отсутствующих0), обе правки и связанные existing nodes/canonical границы. Реализуемость extension/receipt lifecycle/SDK остаётся NOT VERIFIED до PoC; G104/106/111 и право первого producer/WorkerRun не закрыты записью. Вывод получен до отчёта автора. Дополнение этого протокола фиксирует verdict, не расширяет его до runtime certification.
