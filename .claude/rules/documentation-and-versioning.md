# documentation-and-versioning.md — Документация, версионирование и Registry

**Нормативные источники:** `AI_RES_Document_Registry_v4.1.md` · `AI_RES_Claude_Code_Implementation_Spec_v1.22.md` (Addendum v1.22) · `AI_RES_Domain_Model_and_Data_Architecture_v1.9.md` §6,§9 · `AI_RES_Requirements_Lifecycle_v2.7.md`

---

## Правила обновления нормативных документов

**Нормативные документы `docs/architecture/` не изменяются без явного указания владельца проекта.**

При изменении требований, контрактов или архитектурных решений обязательная последовательность:

1. Получить явное решение владельца проекта.
2. Обновить все затронутые нормативные документы в рамках **одного изменения**.
3. Обновить `AI_RES_Document_Registry_v4.1.md` §2: версию, статус, canonical path.
4. При необходимости зафиксировать в `AI_RES_Decisions_Assumptions_Risks_Uncertainty_v1.2.md`.
5. Обновить `AI_RES_Architecture_Baseline_Manifest_v1.2.json` (SHA-256 manifest) если изменение затрагивает BASELINED файлы.
6. Выпустить discrepancy report при обнаружении расхождения кода и документации.

**Запрещено:**
- Обновлять Registry как побочный эффект реализации без владельца.
- Менять статус документа с WORKING на BASELINED в коде без синхронизации Registry.
- Создавать новые версии документов без обновления Registry.

---

## Версионирование доменных объектов (BASELINED)

### Иммутабельные снимки
Следующие сущности **никогда не перезаписываются** после создания:

| Сущность | Schema |
|---|---|
| `RequirementVersion` | `requirements` |
| `SourceVersion` | `sources` |
| `PlanVersion` | `work` |
| `ArtifactVersion` | `artifacts` |
| `ContextPackageVersion` | `context` |
| `WorkerResult` | `agents` |
| `ReadinessEvaluation` | `execution` |
| `Baseline` | `governance` |

Изменение содержания = новая версия. Rework = новый WorkerRun с новым WorkerResult.

### Текущая версия
- Определяется контролируемой ссылкой в родительском объекте (`Requirement.current_version_id` и т.п.).
- Переключение `current_version` — транзакционная операция с audit event.
- Включение версии в Baseline — отдельная операция, не автоматическое следствие approval.

### Change Control
Изменение Baseline — только через:
1. Change Request (CR) с обоснованием.
2. Impact Assessment (ChangeSet → ImpactAssessment → ImpactItem[]).
3. Required Approvals уполномоченных лиц.
4. Создание новой Baseline (не изменение существующей).

---

## Требования и их жизненный цикл (BASELINED — DOC-003)

### Статусы RequirementVersion

| Статус | Значение |
|---|---|
| `EXTRACTED / CANDIDATE` | Извлечено или предложено; не подтверждено аналитиком |
| `CONFIRMED` | Аналитик подтвердил существование; не обязательно business-approval |
| `APPROVED` | Уполномоченное лицо приняло решение |
| `IN_BASELINE` | Включено в утверждённый Baseline |
| `SUPERSEDED` | Заменено новой версией |
| `REJECTED` | Отклонено |

Переход `CANDIDATE → CONFIRMED → APPROVED → IN_BASELINE` — контролируемый; каждый шаг требует соответствующего права. Worker Result не переводит требование в APPROVED или IN_BASELINE автоматически.

### Классификация типов
Поддерживаемые типы требований: BR, StR, UR, FR, NFR, SyR, IR, DR, IntR, CON, TR и расширяемый registry. Неизвестный тип не превращается автоматически в ближайший знакомый тип; фиксировать как UNKNOWN и запрашивать решение.

---

## Traceability (WORKING — DOC-012, инварианты из DOC-005 BASELINED)

### TraceabilityLink
- Типизированная таблица с полями: `source_object_type`, `source_object_id`, `target_object_type`, `target_object_id`, `link_type`, `status`, `origin`, `evidence_refs`, `rationale`.
- Статусы: PROPOSED / CONFIRMED / REJECTED / SUPERSEDED.
- Origin: HUMAN / AGENT / IMPORT / RULE.
- Критичные бизнес-связи (Task–Requirement, ArtifactVersion–ValidationReport, Approval–target version) — специализированные таблицы с FK, не только universal TraceabilityLink.
- `object_type` и `link_type` из пользовательского/agent ввода — валидировать по registry допустимых типов перед сохранением.

### Impact Analysis lifecycle
1. `ChangeSet` — исходное изменение или набор изменённых версий.
2. `ImpactAssessment` — запуск анализа: версии графа/правил, автор/метод, deterministic + semantic results.
3. `ImpactItem[]` — затронутый объект, путь, категория I0–I4, evidence, статус, рекомендуемое действие.

Детерминированные проверки (прямые связи, baseline membership, обязательные gates) выполняются **до/параллельно** с семантическим анализом. Категория I0–I4 — рекомендация AI RES, не confidence score; не понижать обязательную детерминированную категорию семантической оценкой.

---

## Артефакты и публикация (BASELINED)

### Lifecycle артефакта
```
DRAFT → PROPOSED → UNDER_REVIEW → APPROVED → PUBLISHED → SUPERSEDED
```

- Validation, Review, Approval, Publication — разные события с разными actor/rights.
- WorkerResult не переводит артефакт в APPROVED или PUBLISHED автоматически.
- DOCX/PDF-экспорт — обычно `ArtifactRepresentation`, не canonical content.
- OpenAPI/JSON Schema/diagram-as-code могут быть canonical content в зависимости от `artifact_type`.

### GenerationJob
- Фиксирует каждую попытку генерации/обновления/импорта: pipeline version, model/tool version, timestamp, status, errors, input version refs.
- `ValidationReport` привязан к точной `ArtifactVersion` и набору валидаторов/версий.

---

## Решения и неопределённость (BASELINED — DOC-051)

Отдельные типизированные объекты с lifecycle:

| Тип | Ключевые поля сверх общих |
|---|---|
| Decision | question, alternatives, chosen, rationale, consequences, approver, review trigger |
| Assumption | statement, owner, invalidation consequences, verification method/criteria, TTL/trigger |
| Risk | cause, event, consequences, probability/impact, owner, triggers, mitigation, contingency, residual |
| Issue | discovered problem, actual impact, owner, status, resolution |
| Unknown | specific information gap, affected decisions/tasks, closing condition |
| Hypothesis | testable statement, grounds, test method, result |
| Conflict | conflicting objects/assertions, evidence, classification, resolution approach |

Нельзя сводить все типы в одну таблицу заметок с нестрогим JSON.

**WORKING:** quantitative risk calibration и organization-specific authority matrix — не утверждены; не изобретать числовые пороги.

---

## Discrepancy report

Выпускать при обнаружении любого из условий:
- Файл из Registry §2 отсутствует в `docs/architecture/`.
- Версия файла в репозитории не совпадает с версией в Registry.
- Контракт в коде ссылается на версию документа, не совпадающую с Registry.
- Код реализует поведение, противоречащее BASELINED решению.
- Код реализует WORKING-параметр как finalised без обновления Registry.

Discrepancy report содержит: файл/документ, ожидаемое состояние из Registry, фактическое состояние, блокирует ли increment, предлагаемые варианты решения. Не выбирать трактовку молча.
