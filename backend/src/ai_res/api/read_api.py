# ruff: noqa: E501  -- route tables and DTO mappers read best one entry per line
"""Read-only Public API v1.3 GET operations (S08, ADR-074..077): listProjects, getProject, listEpics, getEpic, listTasks, getTask, listRequirements,
listRequirementVersions, listSources, listArtifacts, listArtifactVersions, getWorkerRun. Thin handlers: authentication is the shared session dependency,
authorization is the Policy Engine (a denial is the SAME 404 as a missing object), data comes from ReadQueries and leaves through explicit DTO mappers.

Project-scoped tables are protected by RLS keyed on (organization, project), so a by-id GET first has to learn the object's project. It does that by
probing only the projects the caller may read (one short transaction each, in the caller's own tenant context): an id that is missing, belongs to another
project the caller cannot read, or to another organization yields the identical 404 and no cross-project row is ever visible to the session.
"""
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Annotated, Any, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Query, Request, Response

from ai_res.api.identity import IdentityServices
from ai_res.api.locator import ObjectLocator
from ai_res.db.session import UnitOfWork
from ai_res.modules.iam.sessions import AuthenticatedSession
from ai_res.modules.readmodel.queries import ReadQueries, Row, Slice, parse_num_keyset, parse_ts_keyset
from ai_res.platform.concurrency import format_etag
from ai_res.platform.pagination import InvalidCursor, decode_cursor, encode_cursor, validate_limit
from ai_res.platform.ports import PolicyRequest
from ai_res.platform.problems import ErrorCode, ProblemError

DEFAULT_LIMIT, OAS_MAX_LIMIT = 25, 100  # Public API v1.3 `Limit` parameter
MAX_TEXT = 200  # cap for free-text fields copied out of JSON references (worker run problem / result)
READ_ACTIONS = {"project.read": "PROJECT", "epic.read": "EPIC", "task.read": "TASK", "requirement.read": "REQUIREMENT", "source.read": "SOURCE",
                "artifact.read": "ARTIFACT", "worker_run.read": "WORKER_RUN", "operation.read": "OPERATION"}
_log = logging.getLogger("ai_res.api.read")
T = TypeVar("T")


def _not_found() -> ProblemError:
    return ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _opt(value: Any) -> str | None:
    return None if value is None else str(value)


# -- DTO mappers (explicit; nothing from a row is passed through unnamed) ---------------------------------------------------------------------------
def project_dto(r: Row) -> dict[str, Any]:
    return {"id": str(r["id"]), "organizationId": str(r["organization_id"]), "name": r["name"], "description": r["description"], "goal": r["goal"],
            "projectType": r["project_type"], "status": r["status"], "createdAt": _iso(r["created_at"]), "updatedAt": _iso(r["updated_at"])}


def epic_dto(r: Row) -> dict[str, Any]:
    return {"id": str(r["id"]), "projectId": str(r["project_id"]), "title": r["title"], "goal": r["goal"], "status": r["status"]}


def task_dto(r: Row) -> dict[str, Any]:
    return {"id": str(r["id"]), "epicId": str(r["epic_id"]), "title": r["title"], "status": r["status"], "priority": r["priority"]}


def requirement_dto(r: Row) -> dict[str, Any]:
    return {"id": str(r["id"]), "projectId": str(r["project_id"]), "displayId": f"REQ-{r['display_number']:06d}",
            "lifecycleStatus": r["lifecycle_status"], "currentVersionId": str(r["current_version_id"])}


def requirement_version_dto(r: Row) -> dict[str, Any]:
    return {"id": str(r["id"]), "requirementId": str(r["requirement_id"]), "versionNumber": r["version_number"], "statement": r["statement"],
            "changeReason": r["change_reason"]}


def source_dto(r: Row) -> dict[str, Any]:
    return {"id": str(r["id"]), "projectId": str(r["project_id"]), "name": r["title"], "sourceType": r["source_kind"], "latestVersionId": _opt(r["current_version_id"])}


def artifact_dto(r: Row) -> dict[str, Any]:
    return {"id": str(r["id"]), "projectId": str(r["project_id"]), "title": r["title"], "artifactType": r["artifact_type"], "currentVersionId": _opt(r["current_version_id"])}


def artifact_version_dto(r: Row) -> dict[str, Any]:
    return {"id": str(r["id"]), "artifactId": str(r["artifact_id"]), "versionNumber": r["version_number"], "lifecycleStatus": r["lifecycle_status"]}


_PROBLEM_KEYS = ("type", "title", "status", "code")
# the store vocabulary (operations.operations.initiator_type) differs from the OAS enum (HUMAN|SYSTEM|MANAGER|SCHEDULED): mapped, not passed through (G-112)
_INITIATOR_TYPE = {"USER": "HUMAN", "SYSTEM": "SYSTEM", "MANAGER": "MANAGER", "SERVICE": "SYSTEM"}


def _bounded(value: Any) -> str | int | None:
    if isinstance(value, bool):
        return None
    return value[:MAX_TEXT] if isinstance(value, str) else value if isinstance(value, int) else None


def worker_run_dto(r: Row) -> dict[str, Any]:
    result, problem = r["result_ref"], r["problem_ref"]
    return {
        "id": str(r["id"]), "taskId": str(r["task_id"]), "workerRole": "UNKNOWN",  # no worker definition table exists yet (G-85): marked, not invented
        "status": r["status"], "contextPackageVersionId": str(r["context_package_version_id"]), "createdAt": _iso(r["created_at"]),
        "operationId": str(r["operation_id"]), "rowVersion": r["row_version"], "derivedFromWorkerRunId": _opt(r["derived_from_worker_run_id"]),
        "derivationReason": r["derivation_reason"], "attemptNumber": r["attempt_number"], "latestReadinessEvaluationId": _opt(r["latest_readiness_evaluation_id"]),
        "startedWithReadinessEvaluationId": _opt(r["started_with_readiness_evaluation_id"]),
        "startedAt": None if r["started_at"] is None else _iso(r["started_at"]), "finishedAt": None if r["finished_at"] is None else _iso(r["finished_at"]),
        "resultRef": result["id"][:MAX_TEXT] if isinstance(result, dict) and isinstance(result.get("id"), str) else None,  # opaque reference only, never the stored object
        "problem": None if not isinstance(problem, dict) else {k: _bounded(problem[k]) for k in _PROBLEM_KEYS if _bounded(problem.get(k)) is not None},
    }


def operation_dto(r: Row) -> dict[str, Any]:
    result, problem = r["result_ref"], r["problem_ref"]
    return {
        "id": str(r["id"]), "status": r["status"], "submittedAt": _iso(r["created_at"]), "acceptedAt": _iso(r["created_at"]),
        "startedAt": None if r["started_at"] is None else _iso(r["started_at"]), "completedAt": None if r["completed_at"] is None else _iso(r["completed_at"]),
        "lastProgressAt": None,  # no progress timestamp is stored (progress_snapshot is opaque and WORKING): marked, not invented
        "resultRef": result["id"][:MAX_TEXT] if isinstance(result, dict) and isinstance(result.get("id"), str) else None,
        "correlationId": str(r["correlation_id"]), "organizationId": str(r["organization_id"]), "projectId": str(r["project_id"]), "epicId": None,
        "operationType": r["operation_type"], "initiatorType": _INITIATOR_TYPE.get(r["initiator_type"], "SYSTEM"), "initiatorId": _opt(r["initiator_id"]),
        "subjectRef": None, "problem": None if not isinstance(problem, dict) else {k: _bounded(problem[k]) for k in _PROBLEM_KEYS if _bounded(problem.get(k)) is not None},
        "rowVersion": r["row_version"], "aggregateVersion": r["row_version"], "parentOperationId": _opt(r["parent_operation_id"]),
        "rootOperationId": str(r["root_operation_id"] or r["id"]),
    }


def _ts_key(r: Row) -> list[Any]:
    return [r["created_at"].isoformat(), str(r["id"])]


def _num_key(field: str) -> Callable[[Row], list[Any]]:
    return lambda r: [r[field], str(r["id"])]


def register_read_api(app: FastAPI, services: IdentityServices) -> None:
    settings, enforcer, factory = services.settings, services.enforcer, services.factory
    router = APIRouter(prefix="/api/v1")
    Session = Annotated[AuthenticatedSession, Depends(services.current_session)]
    if services.current_session is None:
        raise RuntimeError("register_identity must run before register_read_api")  # Depends(None) would turn request parameters into an identity
    config = enforcer.config
    if config is None or any(a not in config.actions or config.actions[a].resource_type != t for a, t in READ_ACTIONS.items()):
        raise RuntimeError("policy configuration lacks the read actions or their resource types; refusing to expose read endpoints")  # fail closed at start-up
    rule = config.actions["project.read"]
    if any(config.actions[a].project_roles != rule.project_roles or config.actions[a].org_roles != rule.org_roles for a in READ_ACTIONS):
        raise RuntimeError("read actions grant different roles; the project visibility filter assumes one shared grant")
    plain = sorted(rule.project_roles - config.privileged_roles)
    priv = sorted(rule.project_roles & config.privileged_roles)
    org_roles = sorted(rule.org_roles)

    def ring(request: Request) -> Any:
        found = getattr(request.app.state, "cursor_key_ring", None)
        if found is None:
            raise ProblemError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Pagination is not configured.")
        return found

    def limit_of(limit: int | None) -> int:
        value = validate_limit(limit, DEFAULT_LIMIT)
        if value > OAS_MAX_LIMIT:
            raise ProblemError(ErrorCode.VALIDATION_ERROR, "limit out of range.", errors=[{"field": "limit", "reason": "range"}])
        return value

    def request_of(s: AuthenticatedSession, action: str, rtype: str, project_id: UUID, resource_id: UUID | None) -> PolicyRequest:
        return PolicyRequest(actor_id=str(s.user_id), action=action, resource_type=rtype, resource_id=None if resource_id is None else str(resource_id),
                             organization_id=str(s.organization_id), project_id=str(project_id), attributes={"mfa_verified": s.mfa_verified_at is not None})

    async def in_project(s: AuthenticatedSession, project_id: UUID, action: str, rtype: str, resource_id: UUID | None,
                         fn: Callable[[ReadQueries], Awaitable[T]]) -> T:
        """Project id known from the path: authorize (denial == not found) inside the project's tenant context, then read."""
        policy_request = request_of(s, action, rtype, project_id, resource_id)
        decision = await enforcer.decide(policy_request, conceal=True)  # before any data connection is taken: a request never holds two (pool starvation)
        async with UnitOfWork(factory) as uow:
            await uow.with_tenant(s.organization_id, project_id)
            await enforcer.record_allow(policy_request, decision, session=uow.session)  # fail-closed: no audit row, no data
            return await fn(ReadQueries(uow.session))

    locator = ObjectLocator(services, plain=plain, priv=priv, org_roles=org_roles)

    async def by_id(s: AuthenticatedSession, table: str, object_id: UUID, action: str, rtype: str,
                    fn: Callable[[ReadQueries, UUID], Awaitable[T]]) -> T:
        """Find the object among projects the caller can read, authorize against the owning project, then run `fn`."""
        project_id = await locator.locate(s, table, object_id)
        if project_id is not None:
            async def run(q: ReadQueries) -> T:
                return await fn(q, project_id)
            return await in_project(s, project_id, action, rtype, object_id, run)
        raise _not_found()

    def paged(request: Request, s: AuthenticatedSession, audience: str, scope: UUID, data: Slice, dto: Callable[[Row], dict[str, Any]],
              key: Callable[[Row], list[Any]]) -> dict[str, Any]:
        nxt = None
        if data.has_more and data.items:
            nxt = encode_cursor(ring(request), subject=str(s.user_id), audience=audience, filters=_filters(s, scope), keyset=key(data.items[-1]),
                                ttl_seconds=settings.cursor_ttl_seconds)
        return {"data": [dto(r) for r in data.items], "page": {"nextCursor": nxt, "hasMore": data.has_more}}

    def _filters(s: AuthenticatedSession, scope: UUID | None) -> dict[str, Any]:
        return {"org": str(s.organization_id), "scope": None if scope is None else str(scope)}

    def keyset_of(request: Request, s: AuthenticatedSession, audience: str, scope: UUID | None, cursor: str | None, kind: str) -> list[Any] | None:
        """Decode and shape-check the cursor BEFORE any transaction: a bad cursor is a 400 that never touches the database or the audit trail."""
        if not cursor:  # absent or empty (`?cursor=` is schema-valid in the OAS): first page
            return None
        keyset = decode_cursor(ring(request), cursor, subject=str(s.user_id), audience=audience, filters=_filters(s, scope))
        try:
            (parse_ts_keyset if kind == "ts" else parse_num_keyset)(keyset)
        except (ValueError, TypeError) as exc:
            raise InvalidCursor from exc
        return keyset

    def no_store(response: Response) -> None:
        response.headers["Cache-Control"] = "no-store"

    Limit = Annotated[int | None, Query()]
    Cursor = Annotated[str | None, Query()]

    @router.get("/projects")
    async def list_projects(request: Request, response: Response, s: Session, limit: Limit = None, cursor: Cursor = None) -> dict[str, Any]:
        size, after = limit_of(limit), keyset_of(request, s, "listProjects", s.organization_id, cursor, "ts")
        async with UnitOfWork(factory) as uow:
            await uow.with_tenant(s.organization_id)
            data = await ReadQueries(uow.session).visible_projects(
                s.organization_id, s.user_id, plain_roles=plain, privileged_roles=priv, org_roles=org_roles, mfa_verified=s.mfa_verified_at is not None,
                limit=size, after=after)
        no_store(response)
        return paged(request, s, "listProjects", s.organization_id, data, project_dto, _ts_key)

    @router.get("/projects/{project_id}")
    async def get_project(project_id: UUID, response: Response, s: Session) -> dict[str, Any]:
        async def read(q: ReadQueries) -> Row:
            row = await q.get_project(project_id)
            if row is None:
                raise _not_found()
            return row
        row = await in_project(s, project_id, "project.read", "PROJECT", project_id, read)
        response.headers["ETag"] = format_etag(row["row_version"])
        no_store(response)
        return project_dto(row)

    def project_list(path: str, op: str, action: str, rtype: str, dto: Callable[[Row], dict[str, Any]], key: Callable[[Row], list[Any]], kind: str,
                     query: Callable[[ReadQueries, UUID, int, list[Any] | None], Awaitable[Slice]]) -> None:
        @router.get(path, name=op)
        async def handler(project_id: UUID, request: Request, response: Response, s: Session, limit: Limit = None, cursor: Cursor = None) -> dict[str, Any]:
            size, after = limit_of(limit), keyset_of(request, s, op, project_id, cursor, kind)
            data = await in_project(s, project_id, action, rtype, None, lambda q: query(q, project_id, size, after))
            no_store(response)
            return paged(request, s, op, project_id, data, dto, key)

    project_list("/projects/{project_id}/epics", "listEpics", "epic.read", "EPIC", epic_dto, _ts_key, "ts", lambda q, p, n, a: q.list_epics(p, n, a))
    project_list("/projects/{project_id}/requirements", "listRequirements", "requirement.read", "REQUIREMENT", requirement_dto, _num_key("display_number"), "num",
                 lambda q, p, n, a: q.list_requirements(p, n, a))
    project_list("/projects/{project_id}/sources", "listSources", "source.read", "SOURCE", source_dto, _ts_key, "ts", lambda q, p, n, a: q.list_sources(p, n, a))
    project_list("/projects/{project_id}/artifacts", "listArtifacts", "artifact.read", "ARTIFACT", artifact_dto, _ts_key, "ts", lambda q, p, n, a: q.list_artifacts(p, n, a))

    def child_list(path: str, op: str, table: str, action: str, rtype: str, dto: Callable[[Row], dict[str, Any]], key: Callable[[Row], list[Any]], kind: str,
                   query: Callable[[ReadQueries, UUID, int, list[Any] | None], Awaitable[Slice]]) -> None:
        @router.get(path, name=op)
        async def handler(parent_id: UUID, request: Request, response: Response, s: Session, limit: Limit = None, cursor: Cursor = None) -> dict[str, Any]:
            size, after = limit_of(limit), keyset_of(request, s, op, parent_id, cursor, kind)
            data = await by_id(s, table, parent_id, action, rtype, lambda q, _p: query(q, parent_id, size, after))
            no_store(response)
            return paged(request, s, op, parent_id, data, dto, key)

    child_list("/epics/{parent_id}/tasks", "listTasks", "work.epics", "task.read", "TASK", task_dto, _ts_key, "ts", lambda q, e, n, a: q.list_tasks(e, n, a))
    child_list("/requirements/{parent_id}/versions", "listRequirementVersions", "requirements.requirements", "requirement.read", "REQUIREMENT",
               requirement_version_dto, _num_key("version_number"), "num", lambda q, r, n, a: q.list_requirement_versions(r, n, a))
    child_list("/artifacts/{parent_id}/versions", "listArtifactVersions", "artifacts.artifacts", "artifact.read", "ARTIFACT", artifact_version_dto,
               _num_key("version_number"), "num", lambda q, r, n, a: q.list_artifact_versions(r, n, a))

    def single(path: str, op: str, table: str, action: str, rtype: str, fetch: Callable[[ReadQueries, UUID], Awaitable[Row | None]],
               dto: Callable[[Row], dict[str, Any]], etag: bool) -> None:
        @router.get(path, name=op)
        async def handler(object_id: UUID, response: Response, s: Session) -> dict[str, Any]:
            async def read(q: ReadQueries, project: UUID) -> Row:
                row = await fetch(q, object_id)
                if row is None or row["project_id"] != project:  # defense in depth next to RLS: the row must belong to the project that was authorized
                    raise _not_found()
                return row
            row = await by_id(s, table, object_id, action, rtype, read)
            if etag:
                response.headers["ETag"] = format_etag(row["row_version"])
            no_store(response)
            return dto(row)

    single("/epics/{object_id}", "getEpic", "work.epics", "epic.read", "EPIC", lambda q, i: q.get_epic(i), epic_dto, False)
    single("/tasks/{object_id}", "getTask", "work.tasks", "task.read", "TASK", lambda q, i: q.get_task(i), task_dto, True)
    single("/worker-runs/{object_id}", "getWorkerRun", "agents.worker_runs", "worker_run.read", "WORKER_RUN", lambda q, i: q.get_worker_run(i), worker_run_dto, False)

    single("/operations/{object_id}", "getOperation", "operations.operations", "operation.read", "OPERATION", lambda q, i: q.get_operation(i), operation_dto, True)

    app.include_router(router)
