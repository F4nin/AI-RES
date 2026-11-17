# G01 — Правила и контекст: паспорт работы

**Дата:** 2026-11-17 · **Статус группы:** IN_PROGRESS · **Текущий этап:** S19. Это промежуточный снимок выполнения; полный pre-pr PASS, доставка S19 выполняется.

## Идентификация и полномочия

Поручение владельца: «Реализуй группу G01 по DEVELOPMENT_GROUPS.md с сохранением всех этапов, проверок и правил AGENTS.md.» Основание процесса — [AGENTS §10–11](../../../AGENTS.md), `docs/implementation/DEVELOPMENT_GROUPS.md` (исходный локальный process-документ, оставлен вне stage commit), ADR-124 и [CONTEXT_RETENTION](../tooling/CONTEXT_RETENTION.md).

Разрешён последовательный полный цикл **S19 → S18**. Общий результат — immutable-контекст из точных версий и управляемые версионируемые правила, пригодные для последующей интеграции Manager/Gate/retrieval. Группа не включает S17, S20–S39, UI правил, retrieval/ranking, реальные LLM-вызовы или human approval требований/профилей/Baseline. SLICE-01 перед S17 и отложенные model/security approvals сохраняются.

Основной исполнитель и координатор общих файлов/runtime — Codex `/root`. ECC-планирование и ограниченные непересекающиеся подзадачи выполняются отдельными агентами по AGENTS §7; это не параллельный запуск других групп. Независимые reviewers работают read-only, blind-first и не проверяют собственное авторство.

Рабочая копия: `/Users/ekaterinamarusova/AI-RES-Workspace/AI-RES`; ветка текущего этапа `feat/s19-context-package-versioning`. Проверенная база/HEAD при старте — `745e7d989a75b5457497742e371f60aa8e33ffc0` (`main`; основной исполнитель подтвердил fetch). Текущий SHA и diff перед проверкой/доставкой устанавливаются заново через Git; этот паспорт не приписывает непроверенному diff прежний CI.

До поручения существовали **12 изменённых/новых governance-документов**: AGENTS; ADL; HANDOFF; DECISIONS_PENDING; ECC_USAGE; ROADMAP; STATUS; индекс промптов; CONTEXT_RETENTION; tooling README; DEVELOPMENT_GROUPS; GROUP_WORK_TEMPLATE. Они сохраняются отдельно, не считаются результатом реализации и не включаются автоматически в commit этапа. Основной исполнитель сохранил исходный снимок в `/tmp/g01-original-worktree.json`; временный путь — рабочая страховка, не постоянное evidence. Пересекающиеся строки общих документов интегрируются координатором без потери исходных изменений.

## План и зависимости

| Этап | Промпт / отчёт | Точные зависимости и evidence DONE | Owner/security блокеры | Реализация / готовность | PR / SHA / CI |
|---|---|---|---|---|---|
| S19 | [Промпт](../increments/prompts/S19_context_package_versioning.md); отчёт по принятому пути `increments/S19_context_package_versioning_REPORT.md` готовится при интеграции | S06/S07 — DONE в [STATUS](../IMPLEMENTATION_STATUS.md); S06 [отчёт](../increments/S06_domain_content_schema_REPORT.md), PR5/a7db82c; S07 [отчёт](../increments/S07_identity_auth_policy_audit_idempotency_REPORT.md), PR6/86328e4. Это evidence зависимостей, не новый runtime-прогон | Промпт не задаёт блокирующих owner-решений. Текущие security/compatibility/migration gates должны пройти до DONE | IN_PROGRESS; полнота реализации и проверки ещё устанавливаются | Не создан; нового CI нет |
| S18 | [Промпт](../increments/prompts/S18_rules_registry_rules_engine.md); отчёт по принятому пути `increments/S18_rules_registry_rules_engine_REPORT.md` | S07/S06; проверить повторно перед стартом | Язык условий и прочие технические решения — ADR в рамках scope; новые бизнес-права/BASELINED изменения требуют владельца | NOT_STARTED; исходный индекс READY, выполнение не начиналось | — |

S18 начинается после завершения полного цикла и доставки S19, включая точные обязательные gates и проверку интегрированной базы. Уже DONE этапы S00–S16 не повторяются. Внешней зависимости на допуск реальной модели для S19/S18 в промптах нет; это не разрешает обойти такие допуски другим этапам.

## Владение файлами и средой

- S19: `backend/src/ai_res/modules/context/`, typed metadata readers в модулях-владельцах и внедряемые ports, unit/PostgreSQL/security/architecture tests, forward migration `0018`, соответствующий schema snapshot, import contracts и implementation evidence. Подробный технический выбор — [ADR-125](../decisions/ADR-125-context-manifest.md).
- Основной исполнитель владеет service/repository/migration/wiring, общими `backend/pyproject.toml`, snapshot, STATUS/HANDOFF/ADL/traceability/ECC/gaps и stage report. Ограниченные задания распределены на pure manifest, metadata readers и этот паспорт/ADR; одновременных правок одних файлов не поручено.
- Public API, canonical contracts и `docs/architecture/` не меняются. Новых permissions, model profiles и платных вызовов S19 не требует. Manifest — внутренний технический контракт; новый endpoint/event без canonical контракта не вводится.
- Alembic head и реальные grants/RLS проверяются до применения миграции. Предыдущие revisions immutable. Manifest добавляется совместимым expand; legacy NULL не выдаётся за восстановленный manifest. Текущий dev-стек/данные не сбрасываются.
- Общий runtime использует последовательно `/root`: перед полным прогоном фиксирует checkout/SHA/diff, назначение среды и миграционное состояние. Первоначальный pre-prepr snapshot не менял стек; текущий последовательный pre-pr пересобрал API и применил expand0018 штатной migration job. Volumes и существующие секреты сохранены. Disposable Testcontainers допустимы по §10. Другие агенты не запускают Compose/миграции общего стека.
- Следующий этап использует проверенную интегрированную базу и совместимый migration path. Удаление volumes/данных, reset, ротация существующих секретов, bootstrap администратора и production/deployment остаются вне разрешения группы.
- Egress/расходы — только существующие точные разрешения; новых LLM-расходов группа не разрешает. Git commit/push/PR/merge выполняет координатор по §10 после gates, не включая чужой diff.

## Gates и выполнение

Для каждого этапа сохраняются исходные G1–G9 из [QUALITY_GATES](../QUALITY_GATES.md), [TEST_STRATEGY](../TEST_STRATEGY.md) и промпта. Неприменимость отдельных runtime/API/event проверок требует обоснования в stage report, а не общего освобождения группы.

S19: strict manifest unit tests; реальный PostgreSQL, immutable versions, exact refs/ACL/cross-project отказ; reauthorization при чтении/replay и fail-closed outage; audit atomicity/idempotency; migration empty/previous/drift/grants/RLS; redaction и OTel без исходного контента. Перед VERIFIED обязательны применимые static/contracts/backend/infra проверки, полный `make pre-pr`, отдельные independent reviews и Linux CI точного SHA с дополнительными security/supply-chain jobs. Команды сверяются с текущими Makefile/CI до запуска.

S18: дополнительные инварианты RULE-MVP — нижний уровень не ослабляет системный, DRAFT не применяется, истёкшее исключение не действует, одинаковый вход даёт одинаковый результат. Safe condition language без `eval`; human approval исключений и lifecycle сохраняются. Gate matrix и состав review уточняются после чтения источников этапа при его старте.

Фактически применены отдельный read-only ECC planner для S19 и tdd-guide/pr-test-analyzer для плана негативных тестов; pure manifest автор использовал прочитанные python-patterns/python-testing/tdd-workflow как checklists. Три отдельные независимые code/Python/architecture, security и database review завершились APPROVE/openfindings0 после исправлений; авторские проверки не заменяли review. Claude slash commands/hooks не запускались. Итоговый журнал и evidence консолидирует координатор в ECC_USAGE и stage report.

Промежуточное evidence pure manifest: `uv run --frozen --no-sync pytest tests/unit/test_context_manifest.py -q` из `backend` — RED до production на отсутствующем модуле, затем exit 0, **70 passed**, failed/skipped 0; targeted Ruff и strict mypy двух pure production-файлов — exit 0. Это локальная проверка ограниченного среза, не завершение G1–G9, не runtime verification и не evidence последующих изменений. Этот ранний70-case срез дополнен107-case PG/unit/telemetry/migration проверкой; независимые reviews завершены, полный pre-pr PASS, Linux CI ещё впереди.

## Продолжение и остановка

Текущий этап — S19: завершить Git-доставку с Linux CI, затем закрыть evidence/статусы; service/metadata ports/repository/migration и независимые reviews интегрированы. Фиксировать команды/среду/exit codes/counts/skips, точный SHA/diff и ссылки по мере фактического выполнения; незапущенное не отмечать PASS.

Следующий внутри группы — S18 после полного завершения S19. На момент снимка новых owner-блокеров не установлено; незавершённые gates остаются незавершённой работой, а не успешным результатом. При внешнем блокере записать причину/evidence и нужное решение в паспорт и handoff, остановить затронутую работу по §9; другую группу не выбирать. Сохранение контекста — этот паспорт, STATUS/HANDOFF и отчёты соответствующих этапов, обновляемые координатором.

Группа DONE только после DONE обоих этапов, отдельной доставки каждого, проверки общего результата и сохранения evidence. После DONE G01 остановиться до новой команды. Human/security-owner approval и product/release acceptance не подменяются статусом группы.


## Checkpoint S19 перед доставкой

Current final code slice получил APPROVE трёх отдельных reviewers, openfindings0; hashes — [S19 review](../reviews/S19_IMPLEMENTATION_REVIEWS.md). Targeted107passed (20builder,13metadata,70manifest,1previous-migration,3schema), failed/skipped0; fast695passed/14kept; backend-audit no known vulnerabilities, image pins21/0mismatch. Полный pre-pr PASS exit0 (backend1565,infra369,runtime148,contracts22,Renovate10,PoC19,failed/skipped0), Linux CI/PR/merge ещё впереди; S19 TESTED local/доставка IN_PROGRESS, S18 не начат. Отдельный read-only план S18 подготовлен без кода/новых grants. Владелец подтвердил единственное активное редактирование; пауза по авторству двух безопасных hunks снята, текущий код сохранён и reviewed. Original12 process docs остаются вне автоматического stage commit. Потраченное время ожидания/проверок фиксируется по реальным логам; скорость группового подхода не измерена.
