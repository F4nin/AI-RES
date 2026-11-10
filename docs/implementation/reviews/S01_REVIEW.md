# S01 — независимые review (2026-11-11)

Ревьюеры (ECC, read-only): `code-reviewer`, `silent-failure-hunter`. Оба — ИИ той же модели; S01 не P0-этап (ADR-037 не требуется).

| ID | Sev | Замечание | Решение |
|---|---|---|---|
| S1 | HIGH | Spectral lint fail-open: сбой/пустой stdout → `[ok]` | ИСПРАВЛЕНО: returncode∈{0,1}, непустой JSON, иначе ошибка; любое исключение команды = FAIL; тест `test_lint_gate_fails_closed_when_spectral_breaks` |
| CR-2 | HIGH | JSON Schema breaking не смотрит `$defs`/oneOf/anyOf/additionalProperties | ИСПРАВЛЕНО: рекурсия по `$defs`, ветвям, if/then/else; тесты на реальной Worker-схеме |
| S2 | HIGH | Lint только базового OAS, не merged | ИСПРАВЛЕНО: lint merged base+overlay |
| S3/CR-5 | HIGH/MED | Merged AsyncAPI не валидируется | ИСПРАВЛЕНО: `validate_asyncapi_doc` на merged |
| S4/S5 | HIGH | Overlay: отсутствующий каталог, чужие файлы, пустой YAML, ослабление через security | ИСПРАВЛЕНО: каталог обязателен, stray files и empty → ошибка, корневые ключи allowlist, `x-source` обязателен; тест |
| M1/CR-6 | MED | Молчаливый пропуск файлов без `$schema` | ИСПРАВЛЕНО: явный allowlist (State Machine), остальное — ошибка |
| M2 | MED | Дубль `$id` в registry | ИСПРАВЛЕНО: ValueError |
| M4 | MED | Удалённые/частичные схемы baseline | ИСПРАВЛЕНО: сравнение наборов файлов, проверка полноты baseline |
| CR-3 | MED | Baseline можно принять в том же PR | ЧАСТИЧНО: шаг CI `git diff` против base ref; обязательное owner-approval — настройка репозитория (CODEOWNERS), вне S01; атомарный swap в Makefile |
| CR-4 | MED | Направления enum/типов/removed requestBody | ИСПРАВЛЕНО частично; остальное (security, headers, schema параметров) — G-20 |
| CR-7 | MED | Вакуозный тест jsonschema | ИСПРАВЛЕНО: positive control без `$id` |
| CR-8 | MED | CI: непинованные uv/actions | ОТЛОЖЕНО в S03 (THR-017), TODO в workflow, G-21 |
| M8 | MED | Baseline без severity | ИСПРАВЛЕНО: ключ (code,path,severity) |
| L1/L2/L3 | LOW | Отсутствие источника, пустой glob, unknown command | ИСПРАВЛЕНО |
| M3, M5–M7 | MED | URL `$ref` не резолвятся в OAS/AsyncAPI; breaking не покрывает headers/security/operations AsyncAPI | ПРИНЯТО как ограничение, G-20, COMPATIBILITY.md |
| Spectral rules | LOW | Регистр заголовков | ИСПРАВЛЕНО (case-insensitive); path-level параметры и `default` responses — G-20 |
