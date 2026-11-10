# OpenAPI overlay (WORKING)

Endpoints, отсутствующие в canonical `AI_RES_Public_API_v1.3.yaml`, проектируются здесь по ADR-009/ADR-038 (решение владельца OD-09).

Правила:
- файл `*.yaml` с корнем OpenAPI-фрагмента (`paths`, `components`) и обязательными `x-status: WORKING`, `x-source: [<документы и разделы>]`;
- overlay только добавляет ключи; переопределение существующего ключа — ошибка CI;
- CI собирает base+overlay, валидирует, проверяет Spectral-правила AI RES и отсутствие breaking-изменений относительно `contracts/baseline/`;
- handler не пишется до появления overlay-описания, contract tests и записи в `docs/implementation/CONTRACT_TRACEABILITY_MAP.md`;
- формализация в нормативную версию — NCP-06 (`docs/implementation/decisions/NORMATIVE_CHANGE_PROPOSALS.md`).
