# S18 — независимые implementation reviews

**Дата:** 2026-11-17. База `d5342ac915303a1de3d15f3a911b11243d656dc3` + S18 stage diff. Ревьюеры не являются авторами S18, работают read-only, blind-first: сначала код/тесты/canonical, без отчёта автора. Три заключения APPROVE, открытых CRITICAL/HIGH/MEDIUM0; final general delta подтверждена всеми тремя. Native Claude agents/commands не заявляются: ECC role instructions применены отдельными Codex reviewers.

| Reviewer | Компетенции и фактическое применение | Результат |
|---|---|---|
| `/root/s19_review` (S18 не автор) | code-reviewer, python-reviewer, type-design, pr-test-analyzer, architect; typed AST/results, hierarchy/exception/lifecycle/transaction/current Policy/tests/module boundaries | APPROVE включая final namespace delta; open findings0 |
| `/root/s19_security` (S18 не автор) | security-reviewer, silent-failure-hunter; failclosed/unknown/MFA/separation, SYSTEM invariants, exact exception permissions, RLS/replay/leaks | APPROVE включая final namespace delta; open findings0 |
| `/root/s18_database_review` (новый reviewer, storage author исключён) | database-reviewer, silent-failure-hunter; migration/counter/backfill/CAS/RLS/FKs/grants/appendonly/hash/replay/lock order | APPROVE включая final namespace delta; open findings0 |

## Подтверждённые findings и исправления

1. Security MEDIUM: storage принимал self-consistent result с `facts.context_id=A`, но `scope.object_id=B`. Независимый inline Python repro сначала подтвердил приём, после фикса — ожидаемый ValueError. S18 provider теперь требует exact context object/type/operation/provider + tenant/time/schema/engine binding; PG negatives покрывают mismatch и forged result. Другой future provider не может молча переиспользовать этот fixed provider contract.
2. Database MEDIUM: `validation_report(project, id)` мог вернуть org report, видимый через shared RLS, после project-level `rules.validate`. Добавлено точное organization/project совпадение до возврата, иначе controlled404. PostgreSQL regression RED: DID NOT RAISE,1failed; GREEN:1passed exit0. Org-policy namespace не заменяется проектным grant.
3. По concurrency assessment live evaluation берёт тот же org registry lock до authority/asOf/rules/exceptions, что publication/suspend/revoke, затем same-UoW context revalidation. Это устраняет mixed READ COMMITTED basis; исторический replay читает сохранённые snapshots.

Предварительный HIGH общего reviewer о пропущенных allowance guards отозван после чтения текущего файла с hash: guards уже присутствовали. Это не подтверждённый дефект и не выполненное исправление. Разница первоначальных промежуточных reads не используется как evidence отсутствия защиты в финальном срезе.

## Финальные source hashes

| Файл | SHA-256 |
|---|---|
| `application/rules.py` | `1c7ac7294768597c91bd0af6d0acb46e1ce22df3bfaba598d6c5a0537259d69b` |
| `rules/repository.py` | `69d0ae57eafa908e306bf0aa03905901ca354be02a34a70aecdf6158cdffdcca` |
| `rules/registry.py` | `90e6ba395405ecb90fb8ecd22b615ad144ae7007649eb3f9eb50a5aef451b379` |
| `rules/engine.py` | `600becc897dab1ac81183d39b03efe7c271e11cdeaebda411fb0a42d59fe42c1` |
| migration0019 | `1a4112a690314a432988cfedc67b96e9c6ecf5a62f1b6de6754068a87f471a91` |
| `context/service.py` | `773295bf0982f88111853f5864fa1099ab5110ce6ad15d5fb85d7656843e3d00` |
| schema snapshot | `9617592fd6cbfdb0773a41d287207842a44d694cd6eaa6f4a7c28bc1b5804955` |

## Evidence и пределы

Ревьюеры не запускали полный PostgreSQL/pre-pr/CI и не меняли файлы/DB/runtime. General reviewer выполнил git diff --check exit0, security inline repro fixed scope binding exit0. Exact test counts/local gates/Linux привязаны в [S18 report](../increments/S18_rules_registry_rules_engine_REPORT.md), review не заменяет их.

Не установлено текущего внешнего exploit: transport отсутствует. Это не основание оставлять внутренние namespace/integrity дефекты; оба исправлены до delivery. Default packaged management DENY и unconfigured separation denies activation сохранены. Manager DRAFT+rationale подтверждается storage acceptance, upstream Manager transport/service grants/production catalogue/OD14/pool admission остаются G158. Numeric coverage не измерялось, no secret detector perfection claim. Дополнительная security-owner/business approval этим review не выдаётся.

После review удалена только лишняя пустая строка EOF repository (cached diff --check); приведённый hash относится к whitespace-only cleanup, semantics неизменны.
