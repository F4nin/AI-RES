# G156 — candidate configuration integrity

Основание: прямая команда владельца2026-11-18 продолжить реализацию после audit; [ADR137](../../decisions/ADR-137-candidate-configuration-integrity.md). Реализовать только preparatory seam целостности Bifrost до reserve/claim. G02/S17/S20/S21 NOT_STARTED; real key/provider/account/tariff/profile setup не выполнять.

Отдельные pinned hardened build/launcher/transport patch; fresh bootstrap до LoadConfig, exact rendered inputs, compile-time outer URI allowlist, sticky file/live/read-only logical SQLite guard, boot marker. Прежние fingerprint SDK artifacts, mutable audit, canonical и основной Compose/runtime сохранить. Не выключать SQLite/auth, не исключать данные безопасности из snapshot ради green.

Host0.2 и source binding включают новые inputs, actual namespace checks + health + StartedAt и exact reviewed integrity binding. Default unconfigured/старый descriptor отказывают. Shared gate до reserve/probe/onceclaim, settlement не блокировать. Bounded subprocess/stdout/time/cancel, no secret argv/env/raw exports. Никакого нового бюджета/human approval.

ECC planner/architect, Go/Python/testing/verification checklists; ограниченный Go author; два отдельных blind-first read-only general/Go/Python/test и security reviewers. Runtime последовательно у root. Проверки по ADR137/QUALITY_GATES: targeted Go/race/native/failure suites, fast/static/secrets/provenance/doc preservation. Применимость full pre-pr/LinuxCI не подменять targeted evidence. Сохранить report/review/hashes/context/status/gaps/traceability/ECC и следующий незавершённый шаг; всю подготовку готовой не объявлять без остальных gates.
