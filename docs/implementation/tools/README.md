# tools/ — генерация и проверка системы реализации

Единый источник данных этапов и решений: `stages.py` (этапы S00–S39) и `adrs.py` (ADR). Из них генерируются `IMPLEMENTATION_ROADMAP.md`, `IMPLEMENTATION_STATUS.md`, `ARCHITECTURE_DECISION_LOG.md`, `increments/prompts/*.md` и `increments/prompts/README.md`. Ручная правка сгенерированных файлов будет потеряна при перегенерации — меняйте данные.

| Команда (из корня репозитория) | Назначение |
|---|---|
| `python3 docs/implementation/tools/gen.py .` | Перегенерировать roadmap/status/ADL/prompts (проверяет циклы, порядок, ссылки на ADR) |
| `python3 docs/implementation/tools/reqs.py .` | Перегенерировать индекс `REQUIREMENTS_TRACEABILITY.md` из canonical документов |
| `python3 docs/implementation/tools/check_prompts.py` | Проверить промпты: canonical документы Registry, ADR, имена ECC, обязательные разделы, индексацию |

Внимание: `gen.py` перезаписывает `IMPLEMENTATION_STATUS.md` статусами из `stages.py` — при смене статуса этапа обновляйте поле `gate` в `stages.py`.
