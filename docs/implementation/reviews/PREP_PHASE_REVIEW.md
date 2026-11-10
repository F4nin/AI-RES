# PREP_PHASE_REVIEW — независимые review подготовительной фазы

**Статус:** ЗАВЕРШЕНО 2026-11-11. Исправления внесены блоками `PREP review amendments` в `tools/adrs.py` и `tools/stages.py`, документы и промпты перегенерированы (`check_prompts.py`: 40 промптов, 0 проблем). Продолжение после паузы 2026-11-10.

**Ревьюеры (ECC, read-only):**
- `architect`: roadmap, ADR, промпты;
- `database-reviewer`: ADR-003/011–016/023/024/030/033, промпты S04–S06, S10, таблица ролей;
- `security-reviewer`: ADR-007/015/017/020/022/024/029/031/033, промпты S02/S03/S07/S16/S23, ECC trust, DECISIONS_PENDING.

## 0. Выполненный план (бывший RESUME)

1. Внести исправления блоком `# --- PREP review amendments ---` в конце `docs/implementation/tools/adrs.py` и `stages.py`. Блок мутирует `ADRS`/`STAGES` по ID; каждая правка помечается ID замечания (ARC-n / DB-n / SEC-n). План действий описан в колонке «Планируемое решение» ниже.
2. Обновить `reqs.py`: THR-005, 013 и 017 → S03; THR-015 → S05/S07; THR-014 → S03/S37; THR-016 → S17/S23 вместо «S37 (+ этапы по области)».
3. Перезапустить генерацию и проверки:
   - `python3 docs/implementation/tools/gen.py .`
   - `python3 docs/implementation/tools/reqs.py .`
   - `python3 docs/implementation/tools/check_prompts.py`
4. Обновить вручную ведущиеся файлы: `DECISIONS_PENDING.md` (новые OD), `decisions/NORMATIVE_CHANGE_PROPOSALS.md` (новые NCP), `KNOWN_GAPS.md`, `reviews/ECC_TRUST_ASSESSMENT.md` (результат сверки хэшей), `ECC_USAGE.md` (результаты review).
5. Заполнить колонку «Итог» в этом файле. Создать `reviews/PREP_PHASE_REPORT.md` (на него ссылается STATUS) и выдать пользователю финальный отчёт.

## 1. Факты, уже проверенные по источникам

| Проверка | Результат |
|---|---|
| Composite FK `worker_runs(operation_id,task_id)→work.tasks(operation_id,id)` | BASELINED: DOC-064 §58, §90, §162; DOC-055 §447; DOC-005 §581 |
| Rework после terminal Operation | DOC-055 §116, §353: новая Operation (или дочерняя через `parent_operation_id`); terminal не reopen |
| DOC-065 (DDL) и DOC-069 (Roles/RLS SQL) | В Registry имеют статус **WORKING** («шаблон, требует адаптации»). Адаптация грантов и политик возможна через ADR, без NCP |
| DOC-069: API и audit | `USAGE ON SCHEMA audit` выдан только outbox/consumer/auditor; у api_group нет INSERT на `audit.outbox_events`/`audit_events` (подтверждает DB-2/ARC-4) |
| DOC-069: UPDATE на immutable | `GRANT SELECT, INSERT, UPDATE ON execution.readiness_evaluations TO ai_res_api_group` (подтверждает DB-4) |
| DOC-069: event-таблицы | FORCE RLS, политика только `TO ai_res_api_group`; outbox_group с SELECT увидит 0 строк (подтверждает DB-3) |
| Checkpointer | DOC-006 §351: «доступ только соответствующему Runtime/service role»; INF-MVP-005; Spec Add. v1.18 / PERSIST-023: у Manager/Worker нет DB credentials и сетевого пути. Это **конфликт BASELINED-документов** и решается владельцем (CLAUDE.md §2) |
| Целостность ECC | 428 файлов в install-state: 426 побайтно совпадают с `../tools/ecc` @ `d2ef268`. 2 отличаются (`.claude/AGENTS.md`, `commands/security-scan.md`) только тем, что инсталлер убрал префикс `ecc:` в project-local режиме, это безопасно. В `../tools/ecc` изменён `yarn.lock` (не устанавливается в проект) |
| Permissions `Bash(bash *)`, `Bash(brew upgrade *)` | Локальная настройка пользователя. Implementation Lead её **не меняет**: изменение настроек только по решению пользователя (OD-03) |

## 2. Замечания и планируемые решения

Сокращения: ARC = architect, DB = database-reviewer, SEC = security-reviewer.

| ID | Sev | Суть | Планируемое решение | Итог |
|---|---|---|---|---|
| ARC-1 | HIGH | OAS v1.3 (26 ops) не покрывает auth/MFA, approvals плана и требований, review/publish, Baseline/CR, impact, retrieval, connectors, decisions; ADR-009 запрещает контракты вне canonical; предложение «internal-контракта» в S07 противоречит ADR-009 | Расширить NCP-06 до полного перечня endpoint/event по этапам. Убрать из S07 вариант internal-контракта. Пометить S07, S21, S26, S28–S31, S36 как BLOCKED (OD-04) либо запросить у владельца правило WORKING-расширения контракта (новый OD). Charter: любое изменение контракта идёт через владельца | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| ARC-2 / DB-1 | HIGH | ADR-012: (а) ACCEPTED→WAITING_FOR_HUMAN запрещён (DOC-055 §2.4); (б) команда с Operation отвечает 202+Location, а createTask отвечает 201 без operationId; (в) outbox-команда в S09 до появления dispatcher/workflow; (г) Task вне PlanVersion; (д) rework после terminal невозможен из-за composite FK | Пересмотреть ADR-012: createTask разрешён только внутри активной non-terminal Operation (PLAN_EXECUTION, TX-03), без собственного outbox-старта, до включения в одобренный PlanVersion. Семантику публичной команды вынести в NCP-08. Новый ADR-034: rework после terminal Operation = новая root Operation + новая Task (`derived_from_task_id`, additive) + WorkerRun `derived_from_worker_run_id`. Соблюдает и composite FK, и DOC-055 §116; подтверждение — NCP (non-blocking) | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| ARC-3 / SEC-1 / DB-9 | HIGH | LangGraph checkpointer против запрета DB-доступа runtime; нет роли; `setup()` = runtime DDL | Новый OD (owner): конфликт DOC-006 §351 / INF-MVP-005 и Spec v1.18 / PERSIST-023. Предложение ADR-035: варианты (а) роль `ai_res_checkpointer` только на schema `langgraph` + сетевой allowlist; (б) checkpoint-брокер через Application Service. Схему создаёт provisioning job, не runtime. Тесты: чужой thread, чужие schemas, autogenerate не видит langgraph. S23 BLOCKED до решения | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| ARC-4 / DB-2 | HIGH | API не может писать outbox/audit (DOC-069) | ADR-036 (адаптация WORKING DOC-069): api_group получает USAGE audit + INSERT-only на `outbox_events`/`audit_events`. Тесты грантов и атомарности под реальной ролью `ai_res_api` (S05) | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| SEC-2 | HIGH | THR-005/013/014/015/016/017 без этапа | reqs.py mapping (RESUME п.2). S03: non-root, без docker.sock/privileged, cap_drop, read_only, no-new-privileges, egress deny-by-default (тест metadata/внутренних адресов), SBOM + скан, Actions pinned по SHA. S05/S07: ai_res_api не может UPDATE/DELETE audit_events. Integrity export — S37 | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| SEC-3 | HIGH | `Bash(bash *)` в settings.local.json; хэши ECC | Хэши сверены (§1). Permissions → OD-03, рекомендация пользователю сузить до S02. Сам не меняю | ВЫНЕСЕНО ВЛАДЕЛЬЦУ (OD-11); настройки не менялись; хэши сверены |
| ARC-5 / DB-5 / DB-6 / ARC-13 | MED | PERSIST-001..024 «все в S05» недостижимы; PERSIST-017..020 без evidence; ADR-011 принят до NCP-03 | Матрица PERSIST→этап→инструмент: 015/016→S10, 021→S32/S37, 022→S37, 023→S03/S23, 003/004 (single head, `--sql`)→S04. Синтетическая test-only expand/backfill/validate ревизия для 017–020. ADR-011 записать как «N/A pending owner (NCP-03)» | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| ARC-6 | MED | Worker Run grants и WorkerDefinition registry без этапа-владельца | grants → S17; WorkerDefinition registry → S14 | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| ARC-7 | MED | Approval-ядро в S26, а нужно в S20/S21 | Вынести общее ядро Approval + separation of duties в S20 (или новый этап перед S20); в S26 оставить requirement-специфику | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| ARC-8 | MED | Embeddings (S27) и E2E (S36) без провайдера vs ADR-022 | S27/S28: только FTS (WORKING) до OD-01, embeddings — gated OD-01. E2E: явный test-профиль | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| ARC-9 | MED | ADR-008 FastAPI против `coding-standards.md` (WORKING, «предложить владельцу») | Новый OD: подтверждение владельцем ADR-008. Правило не править без владельца | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| ARC-10 | MED | Нет этапа графов/output-схем 9 специализаций; нет валидаторов Mermaid/PlantUML (UX-ART-33); представления MD/DOCX/PDF не в scope S31 | Добавить в scope: S23/S24 (графы специализаций) или новый этап; валидаторы → S31; representations → S31 | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| SEC-4 | MED | S07: нет тестов AUTH-005/008/012/013, fixation, recovery one-time, TOTP replay, login-CSRF | Добавить в тесты S07 | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| SEC-5 | MED | Rate limit/XFF spoof; security headers | ADR-020: доверять XFF только от Caddy (trusted_proxies), Caddy перезаписывает XFF; progressive delay вместо hard lockout. Тесты: S03 (headers HSTS/CSP/XCTO), S07 (spoof XFF) | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| SEC-6 | MED | ADR-022 опирается на конфигурируемый профиль | Default профиль = prod; test double в отдельном пакете, исключённом из prod-образа; тест импорта в prod-образе | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| SEC-7 | MED | ADR-017: защита policy-конфигурации, cross-process вызовы | Policy config версионирована в репо, checksum при старте; невалидная/без версии → deny-all + alert; изменения через review + security owner; аудит решений с policy version; Manager/Worker не вызывают policy in-process, а идут через API Application Service / Tool Gateway (S17), где на каждый tool call вызывается PolicyDecisionPort | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| SEC-8 | MED | S16: THR-004/009/016/018/019 | Тесты S16: нет fallback на неразрешённого провайдера/регион; provider key только у адаптера; Bifrost не логирует prompts; budget/timeouts; egress deny-by-default для всех | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| SEC-9 / DB-12 | MED | SSE: отзыв сессии/прав, подделка Last-Event-ID; курсор `(aggregate,sequence)` не годится для мультиагрегатного потока; нет event history для S06 агрегатов | ADR-033: opaque HMAC-подписанный курсор (map aggregate→sequence), привязан к session/фильтру; ACL на каждое событие + периодическая проверка сессии, закрытие стрима при revoke. S06 создаёт append-only event history для агрегатов с AsyncAPI-событиями | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| SEC-10 | MED | «security-reviewer без HIGH» — та же модель, не независимо | Новый OD-07: sign-off человека (security owner) для P0-этапов S03/S05/S07/S37 как release gate (не блокирует последовательность). Формулировка в DoD | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| DB-3 | MED | RLS для outbox/consumer групп | ADR-036: политики для outbox_group/consumer_group (cross-tenant, без GUC); UPDATE только по delivery-колонкам; SELECT на event history у dispatcher по умолчанию снять. Тест S10: dispatcher видит outbox всех tenants | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| DB-4 | MED | UPDATE на readiness_evaluations/worker_results | ADR-036: REVOKE UPDATE/DELETE на immutable таблицах + trigger; тест под ai_res_api; discrepancy с DOC-069 | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| DB-7 | MED | Digest не закреплён; тесты под суперпользователем | ADR-003: digest в `infra/images.lock`; RLS/grant тесты только под login-ролями | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| DB-8 | MED | FORCE RLS блокирует backfill под owner | ADR-036: явные migration-политики для migrator/owner; тест | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| DB-10 | MED | Drift-snapshot циркулярен; CHECK aggregate_type только OPERATION/WORKER_RUN | ADR-016: snapshot ведётся вручную, review независимый + сверка с DOC-065; aggregate_type через reference-таблицу, расширяется ревизиями S06/S10 | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| DB-11 / SEC-11 | MED/LOW | Дубль на границе ротации HMAC; компрометация ключа | ADR-024: двухфазная ротация (accepted → active); digest считается по всем неархивным key_id; advisory xact locks по отсортированным digest. Runbook компрометации — S37. Конкурентный тест | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| DB-13 | MED | `SET LOCAL` без bind; `NULLIF(...,'')` | S04: `set_config(name, value, true)` с bind-параметрами; политики через NULLIF; тест «пустая строка → 0 строк, не ошибка» | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| ARC-11 | LOW | S01 DoD «чистый клон» + lock-файлы при запрете commit | «Чистая копия рабочего дерева»; commit — OD-06 | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| ARC-12 | LOW | S12: completion snapshot дублирует S21; агрегатор без PlanItems; SOURCE_INGESTION до pipeline | Снять из S12 то, что принадлежит S21/S27 | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| ARC-14 | LOW | Правки CLAUDE.md и rules (ADR-006/015) не подтверждены владельцем | Новый OD: подтверждение правок инструкций второго уровня | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| DB-14 | LOW | ADR-030: TTL сессий/idempotency/lease и рост outbox | Истечение — переход состояния, а не удаление; physical purge выключен до OD-02; алерт на рост (S13) | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| DB-15 | LOW | Drift operation_type registry ↔ таблица | Тест drift в S05 | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| DB-16 | LOW | Терминология login vs group ролей; «Runtime доступ к API» у migrator | Уточнить ADR-015 (login `ai_res_api` ∈ `ai_res_api_group` и т.д.). NCP не нужен: rules приведены к нормативным документам | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| SEC-12 | LOW | ADR-029: правил LOW нет | До S18 класс LOW не присваивается; LLM/self-assessment не влияют на класс; тест в S24 | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |
| SEC-13 | LOW | S02: секрет cursor-HMAC из env; ротация cursor key | Тесты S02 | ПРИМЕНЕНО (см. ADR-012/034/035, правки ADR-003…033, stages, OD-07…OD-11, NCP-06/08) |

## 3. Ожидаемые изменения статусов этапов (после применения)

- **Новые BLOCKED:** S23 (checkpointer OD); S07, S21, S26, S28–S31, S36 (контрактный разрыв, ARC-1), если владелец не даст правило WORKING-расширений.
- **Не меняются:** S16, S33, S38 — BLOCKED. S01 остаётся READY.
- **Новые OD в DECISIONS_PENDING:**
  - checkpointer (конфликт BASELINED);
  - правило расширения контрактов;
  - подтверждение ADR-008 (FastAPI);
  - подтверждение правок CLAUDE.md и rules;
  - OD-07: security-owner sign-off P0.
- **Новые NCP:** NCP-08 (семантика createTask и rework после terminal); расширение NCP-06.
