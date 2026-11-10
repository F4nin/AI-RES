# Contract compatibility policy

Основание: DOC-006 §15, `.claude/rules/api-and-contracts.md`, ADR-004, ADR-009, ADR-038.

| Изменение | Класс |
|---|---|
| Новый endpoint / operation / событие; новый optional request-параметр; новое optional поле ответа | non-breaking (additive) |
| Удаление endpoint, operation, response code, поля ответа, enum-значения | **breaking** |
| Новый required параметр/поле запроса; optional → required; смена типа | **breaking** |
| Новое событие с новым major | breaking → новый major event type; unknown major → quarantine |
| Worker contracts: major `contractVersion` | unknown major → fail closed |

Проверки (`make contracts-check`): validate-openapi / validate-asyncapi / validate-jsonschema, lint-openapi (Spectral + AI RES правила; baseline `spectral-baseline.json`, новые findings запрещены), breaking (против `contracts/baseline/`), verify-mirror (SHA-256 против Baseline Manifest).

Breaking-изменение запрещено без версионного решения владельца. Обновление `contracts/baseline/` — отдельным шагом после принятого релиза контракта (`make contracts-baseline`).

## Ограничения проверок (честно)
- `verify-mirror` — проверка согласованности с Baseline Manifest в том же репозитории, не защита от подмены (манифест лежит рядом).
- Breaking-diff собственный (ADR-039): не сравнивает security schemes, response headers, schema параметров, `$ref` вне `#`; расхождения с oasdiff — G-20.
- `contracts/baseline/` в PR не должен меняться вместе с контрактом (CI-шаг); обновление — решение владельца.
- Overlay может расширять только `paths|components|tags` (OpenAPI) и `channels|operations|components` (AsyncAPI).
