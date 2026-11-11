import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from stages import STAGES
from adrs import ADRS, D

ROOT = sys.argv[1]
IMP = os.path.join(ROOT, "docs/implementation")
PR = os.path.join(IMP, "increments/prompts")
os.makedirs(PR, exist_ok=True)
BY = {s["id"]: s for s in STAGES}
ADR_T = {a["id"]: a["title"] for a in ADRS}

def fname(s): return f"{s['id']}_{s['slug']}.md"

# transitive blocking
def trans_block(sid, seen=None):
    seen = seen or set()
    s = BY[sid]; out = set()
    for d in s["deps"]:
        if d in seen: continue
        seen.add(d)
        if BY[d]["gate"] == "BLOCKED": out.add(d)
        out |= trans_block(d, seen)
    return out

# cycle check
def check_cycles():
    state = {}
    def visit(n, path):
        if state.get(n) == 1: raise SystemExit(f"cycle: {path+[n]}")
        if state.get(n) == 2: return
        state[n] = 1
        for d in BY[n]["deps"]: visit(d, path + [n])
        state[n] = 2
    for n in BY: visit(n, [])
    order = [s["id"] for s in STAGES]
    for s in STAGES:
        for d in s["deps"]:
            assert order.index(d) < order.index(s["id"]), (s["id"], d)
    for s in STAGES:
        for a in s["adrs"]: assert a in ADR_T, (s["id"], a)
check_cycles()

def eff(s):
    if s["gate"] == "DONE": return "DONE", "—"
    if s["gate"] == "BLOCKED": return "BLOCKED", "Нет"
    tb = trans_block(s["id"])
    if tb: return "BLOCKED (транзитивно: " + ", ".join(sorted(tb)) + ")", "Нет"
    if s["gate"] == "READY": return "READY", "**Да**"
    return "PENDING_DEPS", "Нет (после DONE зависимостей)"

# ---------------- prompts ----------------
ROLE = """Ты — **Principal Architect и Implementation Lead проекта AI RES**. Ты отвечаешь за архитектурную целостность, технические решения, последовательность работ, интеграцию компонентов, качество, безопасность реализации и полноту технической документации.

**Полномочия.** В рамках общей концепции AI RES ты самостоятельно: проектируешь недостающие технические механизмы, выбираешь подходы, библиотеки и инструменты в пределах согласованного стека, определяешь структуру модулей и интерфейсов, разрешаешь технические противоречия и циклические зависимости, определяешь способы тестирования. Обычные технические решения не перекладываются на владельца — они принимаются, обосновываются и регистрируются как `ACCEPTED` в `docs/implementation/ARCHITECTURE_DECISION_LOG.md`.

**Границы (нарушать запрещено):** модульный Backend без microservice-per-domain; PostgreSQL `ai_res_db` — источник истины доменного состояния; Temporal — durable orchestration; LangGraph — внутреннее reasoning; отдельные Manager Runtime и общий Worker Runtime pool; 9 логических специализаций Workers, а не 9 сервисов; Readiness Gate перед **каждым** WorkerRun; Workers не пишут в доменную БД и не взаимодействуют напрямую (только через Manager → Policy → Temporal); immutable versions, provenance, audit, traceability; никакого автоматического одобрения требований, решений и Baseline агентами; Bifrost — кандидат до PoC и security review; Connector Platform — единственный путь к внешним системам; GitHub/GitLab — read-only в MVP.

Если решение требует изменить BASELINED-документ, бизнес-цель, границы MVP, права пользователя или критические гарантии безопасности — **не меняй их**: подготовь Normative Change Proposal в `docs/implementation/decisions/NORMATIVE_CHANGE_PROPOSALS.md` (причина, альтернативы, последствия, затронутые документы и тесты), при необходимости — запись в `DECISIONS_PENDING.md`, и выбери наиболее безопасный вариант, не нарушающий baseline."""

START = """1. Прочитай `CLAUDE.md`, все `.claude/rules/*.md` (включая `ecc-precedence.md`), `docs/implementation/IMPLEMENTATION_CHARTER.md` и `docs/implementation/CONTEXT_HANDOFF.md`; инструменты контекста — `docs/implementation/tooling/README.md` (Context7 через `docs-lookup`, Serena для навигации по коду).
2. Открой `docs/architecture/AI_RES_Document_Registry_v4.1.md` §2: убедись, что каждый документ из раздела «Нормативные источники» существует и является canonical (версия и статус). Отсутствие или противоречие → discrepancy report в отчёте этапа и остановка затронутой части.
3. Открой `docs/implementation/IMPLEMENTATION_STATUS.md`: все зависимости этапа должны быть в статусе DONE (ADR-032). Иначе — остановись и сообщи.
4. Проверь `docs/implementation/DECISIONS_PENDING.md`: блокирующие решения владельца для этапа должны быть закрыты.
5. Проверь фактическое состояние репозитория (`git status`, существующий код этапа) — не дублируй уже реализованное.
6. Переведи этап в `IN_PROGRESS` в `IMPLEMENTATION_STATUS.md`."""

DOCS_COMMON = """- `docs/implementation/CONTEXT_HANDOFF.md` — обновить в конце этапа (где мы, следующий шаг, новые решения).
- `docs/implementation/IMPLEMENTATION_STATUS.md` — статус этапа (NOT_STARTED → IN_PROGRESS → IMPLEMENTED → TESTED → VERIFIED; BLOCKED/DEFERRED с причиной). IMPLEMENTED ≠ TESTED ≠ VERIFIED.
- `docs/implementation/ARCHITECTURE_DECISION_LOG.md` — все самостоятельно принятые нетривиальные решения (ID, дата, проблема/контекст, связанные требования, документы/разделы, альтернативы, решение, обоснование, влияние на компоненты и контракты, риски, затронутые тесты, статус, ответственный). Подробные решения — `docs/implementation/decisions/ADR-xxx-*.md`.
- `docs/implementation/REQUIREMENTS_TRACEABILITY.md` и `CONTRACT_TRACEABILITY_MAP.md` — статусы покрытых требований и контрактов.
- `docs/implementation/KNOWN_GAPS.md` — новые/закрытые пробелы.
- `docs/implementation/DECISIONS_PENDING.md` — только вопросы, действительно требующие владельца/security owner.
- `docs/implementation/ECC_USAGE.md` — фактически использованные ECC agents/skills/commands, цель и результат; недоступные компетенции и компенсация.
- `docs/implementation/increments/{report}` — Increment Report по шаблону `docs/implementation/INCREMENT_REPORT_TEMPLATE.md`.
- Независимые review — `docs/implementation/reviews/{id}_*.md`."""

DOD_COMMON = """- Все пункты «Результаты» созданы; функциональность не замаскирована заглушками (test double допускается только по ADR-022 и с явной маркировкой).
- Все обязательные тесты этапа написаны до/вместе с кодом, проверяют реальное поведение (не импорт и не наличие файлов) и проходят; точные команды и результаты — в отчёте.
- Применимые пункты `.claude/rules/testing-and-verification.md` и `docs/implementation/QUALITY_GATES.md` (G1–G9) выполнены; неприменимые — с обоснованием.
- Миграции (если есть): upgrade from empty и from previous revision; drift = 0.
- Security/authorization negative tests этапа выполнены; секреты отсутствуют в коде, логах, трейсах, событиях, Temporal history.
- Observability: новые компоненты инструментированы (OTel, redaction).
- Независимое review (минимум `code-reviewer` + профильный агент) проведено, CRITICAL/HIGH устранены, отчёт review сохранён.
- Документы и статусы обновлены (раздел «Обновление документов»); Increment Report заполнен.
- Нет критических открытых дефектов; если runtime-проверка невозможна — статус не выше IMPLEMENTED и пометка `IMPLEMENTATION NOT VERIFIED`."""

FORBID = """- Не изменять файлы `docs/architecture/` и Registry; не выдавать предложение (PROPOSED/NCP) за утверждённое решение.
- Не расширять MVP (fine-tuning, GraphRAG/отдельный vector DB, runtime code generation, A2A brokers, A3/A4, OIDC adapter, write/bidirectional sync, shadow/canary, PagerDuty и др. — `.claude/rules/project-context.md`).
- Не изобретать значения WORKING-параметров (SLO, retention, пороги, lease/backoff как «утверждённые») — задавать как конфигурацию с пометкой WORKING или регистрировать решение с обоснованием.
- Не создавать endpoint/event без контракта; не делать generic `/execute` и PATCH защищённых статусов.
- Не ослаблять ACL, audit, Readiness Gate, fail-closed поведение; не отключать проверки ради зелёного CI.
- Не использовать `latest` теги; не хранить секреты в Git/образах/логах/промптах.
- Не выполнять `git commit`/`push`, PR, внешние публикации, destructive-операции с данными и изменение глобальных настроек без явного разрешения пользователя.
- Не отправлять код/документы/идентификаторы AI RES во внешние сервисы без согласия владельца (`/security-scan` — только с согласием: загружает npm-пакет; `/code-review` — только локальный режим)."""

STOP = """Остановись и сообщи (с discrepancy report / записью в DECISIONS_PENDING), если: зависимость не DONE; canonical документ отсутствует или противоречит другому BASELINED документу и противоречие нельзя устранить без изменения baseline; реализация требует изменить бизнес-цель, MVP, права пользователя или критические гарантии безопасности; невозможно получить runtime evidence для заявленного статуса."""

def li(xs): return "\n".join(f"- {x}" for x in xs) if xs else "- —"

def ecc_block(e):
    a = "\n".join(f"| agent | `{n}` | {p} |" for n, p in e["agents"])
    s = "\n".join(f"| skill | `{n}` | {p} |" for n, p in e["skills"])
    c = "\n".join(f"| command | `{n}` | {p} |" for n, p in e["cmds"])
    return "| Тип | Имя (установлено в `.claude/`) | Назначение на этапе |\n|---|---|---|\n" + "\n".join(x for x in (a, s, c) if x)

def prompt(s):
    st, allowed = eff(s)
    report = f"{s['id']}_{s['slug']}_REPORT.md"
    deps = ", ".join(f"{d} ({BY[d]['title']})" for d in s["deps"]) or "—"
    adrs = li([f"{a} — {ADR_T[a]}" for a in s["adrs"]])
    blk = li(s["blockers"]) if s["blockers"] else "- Нет блокирующих решений владельца."
    banner = ""
    if st.startswith("BLOCKED"):
        banner = f"\n> **СТАТУС ПРОМПТА: {st}.** Не исполнять, пока не сняты блокировки (см. «Зависимости и условия старта»).\n"
    elif st == "PENDING_DEPS":
        banner = "\n> **СТАТУС ПРОМПТА: PENDING_DEPS.** Исполнять только после перевода всех зависимостей в DONE.\n"
    elif st == "DONE":
        banner = "\n> **СТАТУС: DONE.** Промпт сохранён для истории; повторно не исполнять.\n"
    return f"""# {s['id']} — {s['title']}

**Фаза:** {s['phase']} · **Соответствие Spec:** {s['spec']} · **Roadmap:** `docs/implementation/IMPLEMENTATION_ROADMAP.md`
{banner}
## 1. Роль и полномочия

{ROLE}

## 2. Цель этапа

{s['goal']}

## 3. Нормативные источники (обязательно прочитать перед планом)

{li(s['refs'])}
- `{ "docs/architecture/AI_RES_Claude_Code_Implementation_Spec_v1.22.md" }` — §3 Non-negotiable constraints, §8 Test matrix/DoD, §9 Prohibited shortcuts, §10 Delivery report; Addendum v1.22 (приоритет Registry v4.1).
- `docs/architecture/AI_RES_Document_Registry_v4.1.md` — §2 (canonical версии и статусы); BASELINED ≠ реализовано, WORKING ≠ утверждено.

## 4. Зависимости и условия старта

- **Этапы-зависимости (должны быть DONE):** {deps}
- **Решения владельца:**
{blk}

Порядок старта:
{START}

## 5. Scope (входит)

{li(s['scope'])}

**Не входит:**
{li(s['out'])}

## 6. Обязательные решения (ACCEPTED) для этого этапа

{adrs}

**Решения, которые нужно принять и зарегистрировать на этапе:**
{li(s['decide'])}

## 7. Результаты реализации

{li(s['deliverables'])}

## 8. ECC: обязательные agents, skills, commands

{ecc_block(s['ecc'])}

Порядок применения: `planner` + `/plan` → реализация с тестами (TDD) → профильные reviewers → `code-reviewer`/`/code-review` → `silent-failure-hunter` → `architect` (соответствие архитектуре) → `verification-loop` + `/quality-gate`. ECC подчинён правилам AI RES (`.claude/rules/ecc-precedence.md`); ECC agents — инструменты разработки, не Runtime Workers AI RES. Если компетенции нет в ECC — выполнить самостоятельно с дополнительной проверкой и записать в `ECC_USAGE.md`.

## 9. Обязательные тесты

{li(s['tests'])}

Типы тестов и инструменты — `docs/implementation/TEST_STRATEGY.md`.

## 10. Quality gates

- `docs/implementation/QUALITY_GATES.md`: G1 Static, G2 Unit, G3 Integration (PostgreSQL/Temporal реальные), G4 Contract, G5 Security/Authorization, G6 Migration, G7 Independent review, G8 Documentation & traceability, G9 Evidence & report — все применимые.
- Этап-специфичные: все тесты раздела 9 зелёные; результаты воспроизводимы командой из отчёта.

## 11. Документирование решений

Каждое нетривиальное самостоятельное техническое/архитектурное решение регистрируется как ADR (`ACCEPTED`, ответственный — Implementation Lead) с полным набором полей. Противоречия не скрываются: discrepancy report в отчёте этапа. Изменения нормативных документов — только как NCP.

## 12. Обновление документов и статусов

{DOCS_COMMON.replace('{report}', report).replace('{id}', s['id'])}
{li(s['docs'])}

## 13. Definition of Done

{li(s['dod'])}
{DOD_COMMON}

## 14. Increment Report

Создать `docs/implementation/increments/{report}` по шаблону `docs/implementation/INCREMENT_REPORT_TEMPLATE.md` (все разделы обязательны).

## 15. Запреты

{FORBID}

## 16. Условия остановки

{STOP}

## 17. Покрываемые требования

{li(s['reqs'])}
"""

for s in STAGES:
    open(os.path.join(PR, fname(s)), "w").write(prompt(s))

# ---------------- index ----------------
rows = []
for s in STAGES:
    st, allowed = eff(s)
    rows.append(f"| {s['id']} | {s['title']} | [`{fname(s)}`]({fname(s)}) | {', '.join(s['deps']) or '—'} | {st} | {allowed} |")
open(os.path.join(PR, "README.md"), "w").write(f"""# Execution Prompts — индекс

Один этап — один самостоятельный промпт. Источник последовательности: `docs/implementation/IMPLEMENTATION_ROADMAP.md` (ADR-010). Общий шаблон отчёта: `docs/implementation/INCREMENT_REPORT_TEMPLATE.md`; отчёт этапа — `docs/implementation/increments/<ID>_<slug>_REPORT.md`.

Статусы готовности: **READY** — можно исполнять сейчас; **PENDING_DEPS** — промпт готов, ждёт DONE зависимостей; **BLOCKED** — требует решения владельца (DECISIONS_PENDING.md); **BLOCKED (транзитивно)** — зависит от BLOCKED этапа; **DONE** — выполнен.

| ID | Название | Промпт | Зависимости | Статус готовности | Разрешено начинать |
|---|---|---|---|---|---|
{chr(10).join(rows)}

Обновлять при изменении статуса этапа (вместе с `IMPLEMENTATION_STATUS.md`).
""")

# ---------------- roadmap ----------------
def mer():
    lines = ["```mermaid", "flowchart LR"]
    for s in STAGES:
        lines.append(f'  {s["id"]}["{s["id"]} {s["title"][:38].replace(chr(34), "")}"]')
    for s in STAGES:
        for d in s["deps"]: lines.append(f"  {d} --> {s['id']}")
    for s in STAGES:
        if s["gate"] == "BLOCKED": lines.append(f"  style {s['id']} fill:#f8d7da")
        if s["gate"] == "DONE": lines.append(f"  style {s['id']} fill:#d4edda")
        if s["gate"] == "READY": lines.append(f"  style {s['id']} fill:#fff3cd")
    lines.append("```")
    return "\n".join(lines)

rm = []
for s in STAGES:
    st, _ = eff(s)
    rm.append(f"| {s['id']} | {s['phase']} | {s['title']} | {s['spec']} | {', '.join(s['deps']) or '—'} | {'; '.join(s['reqs'])} | {st} | [{fname(s)}](increments/prompts/{fname(s)}) |")
det = []
for s in STAGES:
    det.append(f"""### {s['id']} — {s['title']}

- **Spec:** {s['spec']} · **Зависимости:** {', '.join(s['deps']) or '—'} · **Блокеры владельца:** {'; '.join(s['blockers']) or '—'}
- **Цель:** {s['goal']}
- **Нормативные источники:** {'; '.join(r.replace('`docs/architecture/', '`') for r in s['refs'])}
- **Обязательные тесты:** {' '.join(s['tests'])}
- **DoD (этап-специфичный):** {' '.join(s['dod'])} + общий DoD (QUALITY_GATES.md G1–G9).
- **Применяемые ADR:** {', '.join(s['adrs']) or '—'}
""")
open(os.path.join(IMP, "IMPLEMENTATION_ROADMAP.md"), "w").write(f"""# IMPLEMENTATION_ROADMAP — единая последовательность реализации AI RES

**Версия:** 2.0 · **Дата:** {D} · **Решение о последовательности:** ADR-010 (устранение циклических зависимостей Spec)

Последовательность покрывает все нормативные этапы Implementation Spec v1.22 (Inc. 0–9, Add. v1.1 Inc. 10–18, Add. v1.2, Add. v1.13–v1.20 Inc. 20–28), Persistence Blueprint §5/§14 и обязательные MVP-возможности, для которых в Spec нет этапа (Local Auth/Policy, Rules Registry, Requirements approvals, Web Workspace UI). Колонка «Spec» показывает соответствие. Каждый этап исполняется по своему промпту; общий DoD — `QUALITY_GATES.md`, тестовая стратегия — `TEST_STRATEGY.md`.

## 1. Устранённые циклы и разрывы (ADR-010)

| # | Проблема в порядке Spec | Решение |
|---|---|---|
| C1 | Inc.3 читает `agents.worker_runs`, Inc.5–6 создают таблицы; Blueprint §5 требует цепочку PDB-0001…0007 до RLS | Persistence выделен в S04–S06 до read slices (S08) |
| C2 | Inc.5 (Operation + Temporal start) требует Inc.7 (Temporal) и Inc.8 (Outbox dispatcher) | S10 Outbox → S11 Temporal foundation → S12 Operation API |
| C3 | Inc.13 Gate требует ContextPackageVersion (Inc.22), Tool Registry (Inc.23), правила (RULE-MVP) | S17 Tools, S18 Rules, S19 ContextPackage до S22 Gate |
| C4 | Inc.14 WorkerRun / Inc.11 Manager требуют LLMGatewayPort (Inc.20) | S15 port + test double (ADR-022) до S20; провайдер — S16 |
| C5 | Inc.7 LangGraph с WorkerRun до Gate (Inc.13) — риск обхода Gate | LangGraph/WorkerRun — только S23 после S22 |
| C6 | Inc.16 Source ingestion требует индексации (Inc.21) | S27 ingestion → S28 retrieval → S30 impact |
| C7 | Нет этапа Local Auth/Policy Engine, нужного для ACL в Inc.3 | S07 до S08 |
| C8 | Нет этапов Rules Registry (RULE-MVP), Requirements approvals (DOC-003), Web Workspace UI (WS-MVP/UX) | S18, S26, S35–S36 |
| C9 | createTask (201) vs `work.tasks.operation_id NOT NULL` | ADR-012 |
| C10 | Legacy backfill в greenfield | ADR-011 |

## 2. Карта зависимостей

{mer()}

## 3. Сводная таблица этапов

| ID | Фаза | Этап | Spec | Зависимости | Требования | Статус готовности | Промпт |
|---|---|---|---|---|---|---|---|
{chr(10).join(rm)}

## 4. Детали этапов

{chr(10).join(det)}
## 5. Правила перехода

- Этап стартует только после DONE всех зависимостей (ADR-032) и закрытия блокирующих решений владельца.
- Этапы без взаимной зависимости (например, S13 и S14; S17, S18, S19; S27 и S26) могут выполняться в любом порядке, но по одному за раз, если не принято иное решение.
- Изменение последовательности — новый ADR (SUPERSEDES ADR-010) и перегенерация промптов/индекса.
""")

# ---------------- status ----------------
st_rows = []
for s in STAGES:
    st, _ = eff(s)
    cur = {"DONE": "IMPLEMENTED (static evidence)", "READY": "NOT_STARTED"}.get(s["gate"], "BLOCKED" if st.startswith("BLOCKED") else "NOT_STARTED")
    rep = f"[report](increments/{s['id']}_{s['slug']}_REPORT.md)" if s["gate"] == "DONE" else "—"
    note = st if st != "DONE" else "Воспроизводимость проверок — в S01"
    st_rows.append(f"| {s['id']} | {s['title']} | {cur} | {note} | {rep} |")
_ST = os.path.join(IMP, "IMPLEMENTATION_STATUS.md")  # created once; afterwards maintained by hand (stage statuses)
open(os.devnull if os.path.exists(_ST) else _ST, "w").write(f"""# IMPLEMENTATION_STATUS

**Обновлено:** {D} (подготовительная фаза завершена — см. `reviews/PREP_PHASE_REPORT.md`)

Статусы реализации: NOT_STARTED · IN_PROGRESS · IMPLEMENTED · TESTED · VERIFIED · BLOCKED · DEFERRED. IMPLEMENTED ≠ TESTED ≠ VERIFIED. DONE (для старта зависимых этапов) — по ADR-032.

| ID | Этап | Статус реализации | Готовность / примечание | Отчёт |
|---|---|---|---|---|
{chr(10).join(st_rows)}

## Компоненты runtime

| Компонент | Статус | Этап |
|---|---|---|
| Contract toolchain | NOT_STARTED | S01 |
| Backend API | NOT_STARTED | S02, S07–S12 |
| PostgreSQL `ai_res_db` (миграции, роли, RLS) | NOT_STARTED | S04–S06 |
| Docker Compose / secrets / CI | NOT_STARTED | S03 |
| Outbox / Inbox | NOT_STARTED | S10 |
| Temporal, Manager Runtime, Worker Runtime | NOT_STARTED | S11, S20, S23 |
| LangGraph | NOT_STARTED | S23 |
| LLM Gateway (port / Bifrost) | NOT_STARTED / BLOCKED | S15 / S16 |
| Readiness Gate | NOT_STARTED | S22 |
| MinIO / ingestion / retrieval | NOT_STARTED | S03, S27, S28 |
| Observability stack | NOT_STARTED | S13 |
| Web Workspace UI | NOT_STARTED | S35–S36 |

**Runtime implementation: NOT VERIFIED.** Security / performance / production readiness: NOT APPROVED (Readiness Audit v2.2 §6).
""")

# ---------------- ADL ----------------
ent = []
for a in ADRS:
    ent.append(f"""## {a['id']} — {a['title']}

| Поле | Значение |
|---|---|
| Статус | {a['status']} |
| Дата | {a.get('date', D)} |
| Ответственный | {a['owner']} |
| Проблема и контекст | {a['context']} |
| Связанные требования | {a['reqs']} |
| Документы и разделы | {a['docs']} |
| Альтернативы | {a['alts']} |
| Решение | {a['decision']} |
| Обоснование | {a['why']} |
| Влияние на компоненты/контракты | {a['impact']} |
| Риски и компромиссы | {a['risks']} |
| Затронутые тесты | {a['tests']} |
""")
open(os.path.join(IMP, "ARCHITECTURE_DECISION_LOG.md"), "w").write(f"""# ARCHITECTURE_DECISION_LOG

Единый журнал архитектурных и технических решений реализации AI RES (ненормативный). Статусы: PROPOSED, ACCEPTED, REJECTED, SUPERSEDED. Решения в пределах полномочий Implementation Lead регистрируются как ACCEPTED. Решения, меняющие нормативные документы, оформляются как NCP в `decisions/NORMATIVE_CHANGE_PROPOSALS.md` и не считаются утверждёнными до решения владельца. Подробные материалы крупных решений — `decisions/`. `docs/adr/` не используется (`.claude/rules/ecc-precedence.md`).

Сводка: {len(ADRS)} записей; все ACCEPTED.

| ID | Решение | Статус |
|---|---|---|
{chr(10).join(f"| {a['id']} | {a['title']} | {a['status']} |" for a in ADRS)}

---

{chr(10).join(ent)}""")
print("generated", len(STAGES), "prompts")
