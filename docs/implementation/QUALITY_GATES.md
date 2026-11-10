# QUALITY_GATES

Gates этапа (применимые обязательны; неприменимость обосновывается в отчёте). Основание: Spec v1.22 §8, §10; `.claude/rules/testing-and-verification.md`; DOC-078 (release gates).

| Gate | Название | Критерий прохождения | Evidence |
|---|---|---|---|
| G1 | Static | ruff, mypy --strict, architecture/import tests, валидаторы контрактов — 0 ошибок | Команда + вывод |
| G2 | Unit | Все unit тесты зелёные; state machines покрыты (включая недопустимые переходы) | junit |
| G3 | Integration | Тесты на реальном PostgreSQL 16 / Temporal / MinIO зелёные | junit + версии образов |
| G4 | Contract | Handler ↔ OpenAPI/AsyncAPI/JSON Schema; breaking-change check; зеркало контрактов = manifest | отчёты schemathesis/oasdiff |
| G5 | Security & authorization | Negative suites этапа; нет секретов в логах/трейсах/событиях; dependency audit без HIGH/CRITICAL | отчёты |
| G6 | Migration | Upgrade from empty и previous; drift = 0; RLS coverage 100%; grants audit | вывод |
| G7 | Independent review | `code-reviewer` + профильный агент (+ `security-reviewer` для security-кода); CRITICAL/HIGH устранены | `reviews/<ID>_*.md` |
| G8 | Documentation & traceability | STATUS, ADL, REQUIREMENTS_TRACEABILITY, CONTRACT_TRACEABILITY_MAP, KNOWN_GAPS, ECC_USAGE обновлены | diff |
| G9 | Evidence & report | Increment Report по шаблону; статус соответствует evidence (IMPLEMENTED/TESTED/VERIFIED) | отчёт |

## Release gates (S33, S37–S39)

Все SEC P0 (DOC-020 §3); evaluation gates DOC-078 §5 (пороги — OD-02); LLM judge не единственный gate; restore drill выполнен; SBOM, подписи, сканирование образов; UI acceptance владельцем. Production readiness не заявляется без всех release gates.

## Блокирующие условия

CRITICAL/HIGH дефект, проваленный G3–G6, отсутствующий evidence, обход Gate/ACL, секрет в артефактах → этап не DONE.
