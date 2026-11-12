# ruff: noqa: E501  -- route tables and DTO mappers read best one entry per line
"""Controlled write commands of the Public API v1.3 (S09, ADR-078..083): createProject, updateProjectMetadata, createEpic, registerRequirementCandidate,
proposeRequirementVersion, createUploadIntent. `createTask` is NOT here: ADR-012 (PREP review) moved it to S21 (NCP-08).

Every command is ONE database transaction that holds: tenant context -> idempotency record -> domain write (+ aggregate event + outbox where AsyncAPI v1.6
defines a message) -> audit rows -> idempotency completion. Any failure rolls all of it back, so there is never a half-created object or an event without its
projection. Authorization is the Policy Engine, decided BEFORE a data connection is taken; browser CSRF, Origin and the session come from the shared
dependencies. Nothing here approves anything: requirement versions are CANDIDATE proposals.
"""
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Header, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from ai_res.api.identity import IdentityServices
from ai_res.api.locator import ObjectLocator
from ai_res.api.read_api import epic_dto, project_dto, requirement_dto, requirement_version_dto
from ai_res.db.session import DbSession as AsyncSession
from ai_res.db.session import IntegrityViolation, UnitOfWork
from ai_res.modules.audit.writer import SqlAuditWriter, correlation_uuid
from ai_res.modules.epics.repository import EpicRepository
from ai_res.modules.events.aggregate_events import EventSpec
from ai_res.modules.events.envelope import DOMAIN_DESTINATION
from ai_res.modules.iam.sessions import AuthenticatedSession
from ai_res.modules.idempotency.repository import IdempotencyOutcome, IdempotencyRepository
from ai_res.modules.idempotency.service import IdempotencyService, load_keyring
from ai_res.modules.projects.repository import ProjectRepository, new_project_id
from ai_res.modules.readmodel.queries import ReadQueries
from ai_res.modules.requirements.repository import NewRequirementVersion, RequirementRepository
from ai_res.modules.sources.presign import StorageCredentials, checksum_header, presign_url
from ai_res.modules.sources.repository import NewUpload, SourceRepository
from ai_res.platform.clock import utc_now
from ai_res.platform.concurrency import AggregateVersionConflict, format_etag, parse_if_match
from ai_res.platform.config import ConfigError, Settings, read_secret_file
from ai_res.platform.correlation import current_request_id
from ai_res.platform.ids import new_id
from ai_res.platform.ports import AuditOutcome, AuditRecord, PolicyRequest
from ai_res.platform.problems import ErrorCode, ProblemError

_log = logging.getLogger("ai_res.api.write")
PROJECT_TYPES = Literal["GREENFIELD", "BROWNFIELD", "HYBRID", "UNKNOWN"]
MAX_TEXT = 20_000  # WORKING technical bound on free text (no normative limit; ADR-078)
MAX_EVIDENCE_REFS = 50  # WORKING
UNSPECIFIED_TYPE = "UNSPECIFIED"  # declared text kept for a requirement whose type was not given: it is stored as UNKNOWN, never guessed (ADR-056)
_SHA256 = re.compile(r"\A[0-9a-fA-F]{64}\Z")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


# -- request bodies (OAS schemas; unknown fields are rejected like `additionalProperties: false`) ------------------------------------------------------
class _Body(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=False, extra="forbid", str_strip_whitespace=False)


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


class CreateProjectBody(_Body):
    organization_id: UUID
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=MAX_TEXT)
    goal: str | None = Field(default=None, max_length=MAX_TEXT)
    project_type: PROJECT_TYPES = "UNKNOWN"
    _name = field_validator("name")(_nonblank)


class UpdateProjectBody(_Body):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=MAX_TEXT)
    goal: str | None = Field(default=None, max_length=MAX_TEXT)


class CreateEpicBody(_Body):
    title: str = Field(min_length=1, max_length=200)
    goal: str | None = Field(default=None, max_length=MAX_TEXT)
    scope: str | None = Field(default=None, max_length=MAX_TEXT)
    _title = field_validator("title")(_nonblank)


class RegisterRequirementBody(_Body):
    statement: str = Field(min_length=1, max_length=MAX_TEXT)
    registration_kind: Literal["CANDIDATE", "PROJECT_REQUIREMENT_PROPOSAL"]
    requirement_type: str | None = Field(default=None, min_length=1, max_length=100)
    evidence_refs: list[UUID] = Field(default_factory=list, max_length=MAX_EVIDENCE_REFS)
    _statement = field_validator("statement")(_nonblank)


class ProposeVersionBody(_Body):
    statement: str = Field(min_length=1, max_length=MAX_TEXT)
    change_reason: str = Field(min_length=1, max_length=MAX_TEXT)
    rationale: str | None = Field(default=None, max_length=MAX_TEXT)
    _statement = field_validator("statement")(_nonblank)
    _reason = field_validator("change_reason")(_nonblank)


class CreateUploadBody(_Body):
    project_id: UUID
    file_name: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(ge=1)
    sha256: str
    _name = field_validator("file_name")(_nonblank)

    @field_validator("sha256")
    @classmethod
    def _hex(cls, value: str) -> str:
        if not _SHA256.match(value):
            raise ValueError("must be 64 hexadecimal characters")
        return value.lower()


@dataclass(frozen=True)
class Rendered:
    status: int
    body: dict[str, Any]
    headers: dict[str, str]


@dataclass(frozen=True)
class StorageConfig:
    endpoint: str
    bucket: str
    region: str
    credentials: StorageCredentials
    max_size: int
    content_types: frozenset[str]
    ttl_seconds: int


def load_storage(settings: Settings) -> StorageConfig | None:
    """None when upload is not (completely) configured: the command then answers 503 instead of issuing an unsafe or unsigned URL (fail closed)."""
    if (settings.upload_public_endpoint is None or settings.upload_bucket is None or settings.object_store_access_key_file is None
            or settings.object_store_secret_key_file is None or settings.upload_max_size_bytes is None):
        return None
    creds = StorageCredentials(read_secret_file(settings.object_store_access_key_file).decode(), read_secret_file(settings.object_store_secret_key_file).decode())
    return StorageConfig(settings.upload_public_endpoint.rstrip("/"), settings.upload_bucket, settings.object_store_region, creds, settings.upload_max_size_bytes,
                         frozenset(settings.upload_content_types), settings.upload_url_ttl_seconds)


def _clean_title(name: str) -> str:
    """A file name becomes a Source title: no path components, no control characters, bounded to the column limit. It is never part of an object key."""
    base = _CONTROL.sub("", name.replace("\\", "/").rsplit("/", 1)[-1]).strip()
    if not base:
        raise ProblemError(ErrorCode.VALIDATION_ERROR, "fileName is not usable.", errors=[{"field": "fileName", "reason": "invalid"}])
    return base[:240]


def _need_key(value: str | None) -> str:
    if value is None:
        raise ProblemError(ErrorCode.VALIDATION_ERROR, "Idempotency-Key header is required.", errors=[{"field": "Idempotency-Key", "reason": "required"}])
    return value


def register_write_api(app: FastAPI, services: IdentityServices, *, idempotency: IdempotencyService | None = None, storage: StorageConfig | None = None) -> None:
    settings, enforcer, factory = services.settings, services.enforcer, services.factory
    if services.current_session is None or services.origin_guard is None:
        raise RuntimeError("register_identity must run before register_write_api")
    config = enforcer.config
    actions = {"project.create": "PROJECT", "project.update": "PROJECT", "epic.create": "EPIC", "requirement.register": "REQUIREMENT",
               "requirement.propose_version": "REQUIREMENT", "source.upload_create": "SOURCE", "project.read": "PROJECT"}
    if config is None or any(a not in config.actions or config.actions[a].resource_type != t for a, t in actions.items()):
        raise RuntimeError("policy configuration lacks the write actions or their resource types; refusing to expose write endpoints")  # fail closed at start-up
    router = APIRouter(prefix="/api/v1", dependencies=[Depends(services.origin_guard)])
    Session = Annotated[AuthenticatedSession, Depends(services.current_session)]
    locator = ObjectLocator.from_policy(services)
    state: dict[str, Any] = {"idem": idempotency, "storage": storage, "storage_loaded": storage is not None}

    def idem() -> IdempotencyService:
        if state["idem"] is None:  # loaded lazily so read-only deployments and tests need no key ring; absent => every write is refused (503)
            try:
                state["idem"] = IdempotencyService(load_keyring(settings), timedelta(hours=settings.idempotency_ttl_hours))
            except ConfigError as exc:
                _log.error("idempotency key ring unavailable: %s", exc)
                raise ProblemError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Write commands are unavailable.") from exc
        return state["idem"]  # type: ignore[no-any-return]

    def store() -> StorageConfig:
        if not state["storage_loaded"]:
            try:
                state["storage"], state["storage_loaded"] = load_storage(settings), True
            except ConfigError as exc:
                _log.error("object store credentials unavailable: %s", exc)
                raise ProblemError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Uploads are unavailable.") from exc
        if state["storage"] is None:
            raise ProblemError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Uploads are unavailable.")
        return state["storage"]  # type: ignore[no-any-return]

    def policy_request(s: AuthenticatedSession, action: str, project_id: UUID | None, resource_id: UUID | None) -> PolicyRequest:
        return PolicyRequest(actor_id=str(s.user_id), action=action, resource_type=actions[action], resource_id=None if resource_id is None else str(resource_id),
                             organization_id=str(s.organization_id), project_id=None if project_id is None else str(project_id),
                             attributes={"mfa_verified": s.mfa_verified_at is not None})

    async def authorize(s: AuthenticatedSession, action: str, project_id: UUID | None, resource_id: UUID | None = None) -> Any:
        """Project-scoped commands first prove the caller may READ the project (a denial is the same 404 as a missing project), and only then ask for the write
        right (a refusal is an honest 403: the caller already sees the project). Both decisions are audited; neither holds a data connection."""
        if project_id is not None:
            await enforcer.decide(policy_request(s, "project.read", project_id, project_id), conceal=True)
        request = policy_request(s, action, project_id, resource_id)
        return request, await enforcer.decide(request)

    def audit(s: AuthenticatedSession, action: str, rtype: str, rid: UUID, project_id: UUID | None, details: dict[str, Any]) -> AuditRecord:
        return AuditRecord(action=action, outcome=AuditOutcome.SUCCEEDED, resource_type=rtype, resource_id=str(rid), actor_id=str(s.user_id),
                           organization_id=str(s.organization_id), project_id=None if project_id is None else str(project_id), request_id=current_request_id(),
                           details=details)

    def spec(s: AuthenticatedSession, event_type: str, data: dict[str, Any]) -> EventSpec:
        return EventSpec(event_type=event_type, schema_version=1, actor_type="USER", actor_id=s.user_id, correlation_id=correlation_uuid(current_request_id()),
                         destinations=(DOMAIN_DESTINATION,), data=data)

    async def run(s: AuthenticatedSession, *, command: str, key: str | None, payload: Any, project_id: UUID, decision: tuple[Any, Any], resource_type: str,
                  execute: Callable[[AsyncSession], Awaitable[UUID]], render: Callable[[AsyncSession, UUID], Awaitable[Rendered]]) -> Rendered:
        """The common transaction. A replay (same key + same fingerprint) re-renders the stored resource and writes nothing; the same key with another
        request is 409 IDEMPOTENCY_KEY_REUSED; a request still in progress is a retryable 409."""
        raw_key = _need_key(key)
        request, allowed = decision
        service = idem()
        async with UnitOfWork(factory) as uow:
            await uow.with_tenant(s.organization_id, project_id)
            record = await service.begin(uow.session, organization_id=s.organization_id, project_id=project_id, actor_type="USER", actor_id=s.user_id,
                                         command=command, key=raw_key, payload=payload)
            if record.outcome is IdempotencyOutcome.REPLAY and record.resource_id is not None:
                return await render(uow.session, record.resource_id)
            if record.outcome is not IdempotencyOutcome.NEW:
                raise ProblemError(ErrorCode.OPERATION_NOT_READY, "The same request is still being processed; retry shortly.")
            await enforcer.record_allow(request, allowed, session=uow.session)  # fail-closed: no audit row, no change
            rid = await execute(uow.session)
            await service.complete(uow.session, record, status="COMPLETED", resource_type=resource_type, resource_id=rid, response_status=201, response_body_ref=None)
            return await render(uow.session, rid)

    def out(response: Response, rendered: Rendered) -> dict[str, Any]:
        response.status_code = rendered.status
        for name, value in rendered.headers.items():
            response.headers[name] = value
        response.headers["Cache-Control"] = "no-store"
        return rendered.body

    async def _project_rendered(session: AsyncSession, project_id: UUID, status: int) -> Rendered:
        row = await ReadQueries(session).get_project(project_id)
        if row is None:
            raise ProblemError(ErrorCode.INTERNAL_ERROR, "Created resource is not visible.")
        return Rendered(status, project_dto(row), {"ETag": format_etag(row["row_version"])})

    # -- createProject: the project id (and therefore the tenant context of the new project's rows) is fixed before the creating transaction ---------------
    @router.post("/projects", status_code=201)
    async def create_project(body: CreateProjectBody, response: Response, s: Session, idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None) -> dict[str, Any]:
        if body.organization_id != s.organization_id:  # the organization is the session's, never the client's claim
            raise ProblemError(ErrorCode.ACCESS_DENIED, "Access denied.", errors=[{"field": "policy", "reason": "denied"}])
        raw_key = _need_key(idempotency_key)
        request, allowed = await authorize(s, "project.create", None)
        payload = body.model_dump(mode="json")
        service = idem()
        # (1) idempotency record in the ORGANIZATION context (its project column is NULL); a new request reserves the project id in the record.
        async with UnitOfWork(factory) as uow:
            await uow.with_tenant(s.organization_id)
            record = await service.begin(uow.session, organization_id=s.organization_id, project_id=None, actor_type="USER", actor_id=s.user_id,
                                         command="createProject", key=raw_key, payload=payload)
            if record.outcome is IdempotencyOutcome.NEW:
                project_id = new_project_id()
                await IdempotencyRepository(uow.session).reserve_resource(record.id, "PROJECT", project_id)
            elif record.resource_id is not None:
                project_id = record.resource_id
            else:
                raise ProblemError(ErrorCode.OPERATION_NOT_READY, "The same request is still being processed; retry shortly.")
        # (2) the project, its first administrator, ProjectCreated and the outbox row in ONE transaction under the new project's context. A retry (or a crash
        # after this commit) finds the project by the reserved id and creates nothing twice: the primary key is the arbiter.
        try:
            rendered = await _create_project_tx(s, request, allowed, body, project_id)
        except IntegrityViolation as exc:
            diag = getattr(exc.orig, "diag", None)
            constraint = getattr(diag, "constraint_name", None)
            if getattr(exc.orig, "sqlstate", None) != "23505" or constraint != "pk_projects":
                _log.error("createProject: integrity failure other than the primary-key race (constraint=%s)", constraint)
                raise
            rendered = None
        if rendered is None:
            async with UnitOfWork(factory) as uow:
                await uow.with_tenant(s.organization_id, project_id)
                rendered = await _project_rendered(uow.session, project_id, 201)  # lost the race to a concurrent identical request: its result is the result
        # (3) close the idempotency record (a concurrent finisher is fine)
        async with UnitOfWork(factory) as uow:
            await uow.with_tenant(s.organization_id)
            try:
                await service.complete(uow.session, record, status="COMPLETED", resource_type="PROJECT", resource_id=project_id, response_status=201, response_body_ref=None)
            except ProblemError as exc:
                if exc.code is not ErrorCode.AGGREGATE_VERSION_CONFLICT:
                    raise
                _log.warning("createProject: idempotency record %s was already closed by a concurrent request", record.id)
        return out(response, rendered)

    async def _create_project_tx(s: AuthenticatedSession, request: PolicyRequest, allowed: Any, body: CreateProjectBody, project_id: UUID) -> Rendered:
        async with UnitOfWork(factory) as uow:
            await uow.with_tenant(s.organization_id, project_id)
            repo = ProjectRepository(uow.session)
            if not await repo.exists(project_id):
                await enforcer.record_allow(request, allowed, session=uow.session)
                await repo.create(project_id, s.organization_id, name=body.name, description=body.description, goal=body.goal, project_type=body.project_type,
                                        creator=s.user_id, created=spec(s, "project.created", {}))
                writer = SqlAuditWriter(uow.session)
                await writer.write(audit(s, "PROJECT_CREATE", "PROJECT", project_id, project_id, {"projectType": body.project_type}))
                await writer.write(audit(s, "PROJECT_MEMBERSHIP_INITIAL_GRANT", "PROJECT", project_id, project_id, {"roleCode": "PROJECT_ADMIN", "userId": str(s.user_id)}))
            existing = await repo.get(project_id)
            if existing is None:
                raise ProblemError(ErrorCode.INTERNAL_ERROR, "Created resource is not visible.")
            return Rendered(201, project_dto(asdict(existing)), {"ETag": format_etag(existing.row_version)})

    # -- updateProjectMetadata ------------------------------------------------------------------------------------------------------------------------
    @router.patch("/projects/{project_id}")
    async def update_project(project_id: UUID, body: UpdateProjectBody, response: Response, s: Session, if_match: Annotated[str | None, Header(alias="If-Match")] = None) -> dict[str, Any]:
        sent = body.model_fields_set
        if not sent or (("name" in sent) and body.name is None):
            raise ProblemError(ErrorCode.VALIDATION_ERROR, "Nothing to change, or name is null.", errors=[{"field": "body", "reason": "no_change_or_null_name"}])
        expected = parse_if_match(if_match)  # missing -> 428, malformed -> 412, before any lookup
        request, allowed = await authorize(s, "project.update", project_id, project_id)
        changes: dict[str, Any] = {field: getattr(body, field) for field in ("name", "description", "goal") if field in sent}
        async with UnitOfWork(factory) as uow:
            await uow.with_tenant(s.organization_id, project_id)
            await enforcer.record_allow(request, allowed, session=uow.session)
            repo = ProjectRepository(uow.session)
            current = await repo.get(project_id)
            if current is None:
                raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")
            if current.row_version != expected:
                raise ProblemError(ErrorCode.VERSION_CONFLICT, "The resource was modified; reload and retry.")
            try:
                row = await repo.update_metadata(project_id, expected, changes)
            except AggregateVersionConflict:  # a concurrent writer won between the check and the compare-and-swap: still a stale If-Match (412)
                raise ProblemError(ErrorCode.VERSION_CONFLICT, "The resource was modified; reload and retry.") from None
            await SqlAuditWriter(uow.session).write(audit(s, "PROJECT_UPDATE", "PROJECT", project_id, project_id, {"changedFields": sorted(changes)}))
            rendered = Rendered(200, project_dto(asdict(row)), {"ETag": format_etag(row.row_version)})
        return out(response, rendered)

    # -- createEpic -----------------------------------------------------------------------------------------------------------------------------------
    @router.post("/projects/{project_id}/epics", status_code=201)
    async def create_epic(project_id: UUID, body: CreateEpicBody, response: Response, s: Session, idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None) -> dict[str, Any]:
        decision = await authorize(s, "epic.create", project_id)

        async def execute(session: AsyncSession) -> UUID:
            epic_id = await EpicRepository(session).create(s.organization_id, project_id, title=body.title, goal=body.goal, scope=body.scope, created_by=s.user_id,
                                                           make_spec=lambda eid: spec(s, "epic.created", {"epicId": str(eid)}))
            await SqlAuditWriter(session).write(audit(s, "EPIC_CREATE", "EPIC", epic_id, project_id, {}))
            return epic_id

        async def render(session: AsyncSession, epic_id: UUID) -> Rendered:
            row = await ReadQueries(session).get_epic(epic_id)
            if row is None:
                raise ProblemError(ErrorCode.INTERNAL_ERROR, "Created resource is not visible.")
            return Rendered(201, epic_dto(row), {})

        return out(response, await run(s, command="createEpic", key=idempotency_key, payload={"projectId": str(project_id), **body.model_dump(mode="json")},
                                       project_id=project_id, decision=decision, resource_type="EPIC", execute=execute, render=render))

    # -- registerRequirementCandidate -----------------------------------------------------------------------------------------------------------------
    @router.post("/projects/{project_id}/requirements", status_code=201)
    async def register_requirement(project_id: UUID, body: RegisterRequirementBody, response: Response, s: Session, idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None) -> dict[str, Any]:
        decision = await authorize(s, "requirement.register", project_id)
        provenance = tuple({"type": "EVIDENCE_REF", "id": str(ref), "verified": False} for ref in body.evidence_refs)  # references are NOT resolved here (unverified, DOC-007 WORKING)

        async def execute(session: AsyncSession) -> UUID:
            first = NewRequirementVersion(statement=body.statement, author_type="USER", author_id=s.user_id, declared_type=body.requirement_type or UNSPECIFIED_TYPE,
                                          provenance_refs=provenance)
            row = await RequirementRepository(session).register(
                s.organization_id, project_id, first, lambda rid, vid, number: spec(s, "requirement.version.created", {
                    "requirementId": str(rid), "requirementVersionId": str(vid), "versionNumber": number}), s.user_id)
            await SqlAuditWriter(session).write(audit(s, "REQUIREMENT_REGISTER", "REQUIREMENT", row.id, project_id, {"registrationKind": body.registration_kind, "evidenceRefCount": len(provenance)}))
            return row.id

        async def render(session: AsyncSession, requirement_id: UUID) -> Rendered:
            row = await ReadQueries(session).get_requirement(requirement_id)
            if row is None:
                raise ProblemError(ErrorCode.INTERNAL_ERROR, "Created resource is not visible.")
            return Rendered(201, requirement_dto(row), {"ETag": format_etag(row["row_version"])})  # the OAS names no source for the requirement ETag: G-91

        return out(response, await run(s, command="registerRequirementCandidate", key=idempotency_key, payload={"projectId": str(project_id), **body.model_dump(mode="json")},
                                       project_id=project_id, decision=decision, resource_type="REQUIREMENT", execute=execute, render=render))

    # -- proposeRequirementVersion --------------------------------------------------------------------------------------------------------------------
    @router.post("/requirements/{requirement_id}/versions", status_code=201)
    async def propose_version(requirement_id: UUID, body: ProposeVersionBody, response: Response, s: Session,
                              idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None, if_match: Annotated[str | None, Header(alias="If-Match")] = None) -> dict[str, Any]:
        expected = parse_if_match(if_match)
        project_id = await locator.locate(s, "requirements.requirements", requirement_id)
        if project_id is None:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")
        decision = await authorize(s, "requirement.propose_version", project_id, requirement_id)
        created: dict[str, Any] = {}

        async def execute(session: AsyncSession) -> UUID:
            declared = await RequirementRepository(session).current_type(requirement_id)
            if declared is None:
                raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")
            version = NewRequirementVersion(statement=body.statement, author_type="USER", author_id=s.user_id, declared_type=declared, rationale=body.rationale,
                                            change_reason=body.change_reason)  # the type of the previous version carries over; changing a type is not part of this command
            vid, number, row_version = await RequirementRepository(session).propose_version(
                s.organization_id, project_id, requirement_id, expected, version, lambda vid, number: spec(s, "requirement.version.created", {
                    "requirementId": str(requirement_id), "requirementVersionId": str(vid), "versionNumber": number}), s.user_id)
            created["row_version"] = row_version
            await SqlAuditWriter(session).write(audit(s, "REQUIREMENT_VERSION_PROPOSE", "REQUIREMENT", requirement_id, project_id, {"versionNumber": number, "versionId": str(vid)}))
            return vid

        async def render(session: AsyncSession, version_id: UUID) -> Rendered:
            queries = ReadQueries(session)
            row = await queries.get_requirement_version(version_id)
            parent = None if row is None else await queries.get_requirement(row["requirement_id"])
            if row is None or parent is None:
                raise ProblemError(ErrorCode.INTERNAL_ERROR, "Created resource is not visible.")
            return Rendered(201, requirement_version_dto(row), {"ETag": format_etag(parent["row_version"])})

        return out(response, await run(s, command="proposeRequirementVersion", key=idempotency_key,
                                       payload={"requirementId": str(requirement_id), "ifMatch": expected, **body.model_dump(mode="json")},
                                       project_id=project_id, decision=decision, resource_type="REQUIREMENT_VERSION", execute=execute, render=render))

    # -- createUploadIntent ---------------------------------------------------------------------------------------------------------------------------
    @router.post("/uploads", status_code=201)
    async def create_upload(body: CreateUploadBody, response: Response, s: Session, idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None) -> dict[str, Any]:
        decision = await authorize(s, "source.upload_create", body.project_id)
        cfg = store()  # unconfigured => 503 before any row is written
        if body.size_bytes > cfg.max_size:
            raise ProblemError(ErrorCode.VALIDATION_ERROR, "sizeBytes exceeds the allowed maximum.", errors=[{"field": "sizeBytes", "reason": "too_large"}])
        if body.content_type not in cfg.content_types:
            raise ProblemError(ErrorCode.VALIDATION_ERROR, "contentType is not allowed.", errors=[{"field": "contentType", "reason": "not_allowed"}])
        title = _clean_title(body.file_name)

        async def execute(session: AsyncSession) -> UUID:
            upload_id = new_id()
            repo = SourceRepository(session)
            source_id = await repo.create_source(s.organization_id, body.project_id, "FILE", title, s.user_id)
            await repo.register_upload(NewUpload(
                organization_id=s.organization_id, project_id=body.project_id, source_id=source_id, object_key=f"{s.organization_id}/{body.project_id}/{upload_id}",
                declared_media_type=body.content_type, declared_size_bytes=body.size_bytes, declared_sha256=bytes.fromhex(body.sha256),
                expires_at=utc_now() + timedelta(seconds=cfg.ttl_seconds), created_by=s.user_id, upload_id=upload_id))
            await SqlAuditWriter(session).write(audit(s, "UPLOAD_INTENT_CREATE", "SOURCE", source_id, body.project_id, {"uploadId": str(upload_id), "sizeBytes": body.size_bytes, "contentType": body.content_type}))
            return upload_id

        async def render(session: AsyncSession, upload_id: UUID) -> Rendered:
            row = await SourceRepository(session).get_intent(upload_id)
            if row is None:
                raise ProblemError(ErrorCode.INTERNAL_ERROR, "Created resource is not visible.")
            now = utc_now()
            remaining = int((row.expires_at - now).total_seconds())
            if row.status != "PENDING" or remaining < 1:  # the intent was used or has lapsed: the same key cannot mint a fresh URL (a new intent needs a new key)
                raise ProblemError(ErrorCode.IDEMPOTENCY_KEY_REUSED, "The upload intent is no longer usable; create a new one.")
            headers = {"content-type": row.media_type, "content-length": str(row.size_bytes), "x-amz-checksum-sha256": checksum_header(row.sha256.hex())}
            url = presign_url("PUT", cfg.endpoint, f"/{cfg.bucket}/{row.object_key}", headers, cfg.credentials, region=cfg.region, now=now, expires_seconds=remaining)
            return Rendered(201, {"uploadId": str(upload_id), "uploadUrl": url, "expiresAt": row.expires_at.isoformat().replace("+00:00", "Z"), "requiredHeaders": headers},
                            {"Cache-Control": "no-store"})

        return out(response, await run(s, command="createUploadIntent", key=idempotency_key, payload=body.model_dump(mode="json"), project_id=body.project_id,
                                       decision=decision, resource_type="UPLOAD", execute=execute, render=render))

    app.include_router(router)

