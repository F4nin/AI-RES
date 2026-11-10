# RELEASE_AND_VERSIONING

Основание: DOC-015 §12–§14; DOC-006 §15; DOC-072 §10–§11; ADR-009.

| Объект | Правило |
|---|---|
| Приложение AI RES | SemVer `MAJOR.MINOR.PATCH`; релиз связан с Release Manifest |
| Release Manifest | Версии всех сервисов, image tag + **immutable digest**, конфигурация, schema versions (Alembic head, LangGraph checkpoint, Temporal), source commit, подписи (DOC-015 §12) |
| Контейнеры | Только digest-pinned; `latest` запрещён; собственные образы — SBOM, сканирование, Cosign подпись (S37) |
| Зависимости | `uv.lock`, `package-lock.json`; обновления — Renovate PR (DOC-015 §13), решение о включении — контролируемое |
| Public API | Base path `/api/v1`; additive optional = non-breaking; breaking → новая major версия; `contracts/CHANGELOG.md` |
| Domain events | Additive optional в пределах major; breaking → новый major event type; unknown major → quarantine |
| Worker contracts | `contractVersion` major; unknown → fail closed (ADR-021) |
| Alembic revisions | Immutable после применения; expand → backfill → validate → contract; destructive — только с backup/PITR evidence и решением владельца |
| Нормативные документы | Только через владельца (NCP → Registry); `contracts/` — зеркало (ADR-009) |
| Откат | Возврат к предыдущим digests и Release Manifest; БД — forward-fix или restore (DOC-072 §11) |

Git: commit/push/tag — только по явному разрешению пользователя.
