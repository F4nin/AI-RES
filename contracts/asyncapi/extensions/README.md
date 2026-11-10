# AsyncAPI overlay (WORKING)

События, отсутствующие в canonical `AI_RES_Domain_Events_AsyncAPI_v1.6.yaml`, проектируются здесь по ADR-009/ADR-038 (решение владельца OD-09).

Правила те же, что для OpenAPI (`../../openapi/extensions/README.md`): корень — AsyncAPI-фрагмент (`channels`, `operations`, `components`) с `x-status: WORKING` и `x-source`; только additive; CloudEvents 1.0 envelope; новое событие → запись в `docs/implementation/CONTRACT_TRACEABILITY_MAP.md`; формализация — NCP-06.
