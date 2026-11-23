# ruff: noqa: E501  -- route tables and DTO mappers read best one entry per line
"""Controlled write commands of the Public API v1.3 (S09, ADR-078..083): createProject, updateProjectMetadata, createEpic, registerRequirementCandidate,
proposeRequirementVersion, createUploadIntent. S21 createTask resolves an exact, unique approved PlanItem in an active PLAN_EXECUTION (ADR-012).

Every command is ONE database transaction that holds: tenant context -> idempotency record -> domain write (+ aggregate event + outbox where AsyncAPI v1.6
defines a message) -> audit rows -> idempotency completion. Any failure rolls all of it back, so there is never a half-created object or an event without its
projection. Authorization is the Policy Engine, decided BEFORE a data connection is taken; browser CSRF, Origin and the session come from the shared
dependencies. Nothing here approves anything: requirement versions are CANDIDATE proposals.
"""
import logging
import re
from asyncio import timeout
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, replace
from datetime import timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Header, Request, Response
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError, field_validator
from pydantic.alias_generators import to_camel

from ai_res.api.identity import IdentityServices
from ai_res.api.locator import ObjectLocator
from ai_res.api.read_api import epic_dto, operation_dto, plan_version_dto, project_dto, requirement_dto, requirement_version_dto, task_dto
from ai_res.application.manager_intake import AuthorizedIntake, persist_manager_intake
from ai_res.application.plan_execution import RequestedTask, create_matching_approved_task
from ai_res.db.session import DbSession as AsyncSession
from ai_res.db.session import IntegrityViolation, UnitOfWork
from ai_res.modules.audit.writer import SqlAuditWriter, correlation_uuid
from ai_res.modules.epics.manager_interactions import ManagerMessage, ResponseMode
from ai_res.modules.epics.manager_proposals import HumanDecision, ManagerProposalRepository, ProposalVersionRef
from ai_res.modules.epics.repository import EpicRepository
from ai_res.modules.events.aggregate_events import EventSpec
from ai_res.modules.events.assigned_replay import QuarantinedStart, approve_quarantined_start, inspect_quarantined_start
from ai_res.modules.events.envelope import DOMAIN_DESTINATION
from ai_res.modules.iam.authority import lock_authenticated_session
from ai_res.modules.iam.sessions import AuthenticatedSession
from ai_res.modules.idempotency.repository import IdempotencyOutcome, IdempotencyRepository
from ai_res.modules.idempotency.service import IdempotencyService, load_keyring
from ai_res.modules.operations.cancellation import request_cancellation
from ai_res.modules.projects.repository import ProjectRepository, new_project_id
from ai_res.modules.readmodel.queries import ReadQueries
from ai_res.modules.requirements.repository import NewRequirementVersion, RequirementRepository
from ai_res.modules.sources.completion import complete_verified_upload
from ai_res.modules.sources.object_store import ObjectStore, ObjectStoreError, S3ObjectStore
from ai_res.modules.sources.presign import StorageCredentials, checksum_header, presign_url
from ai_res.modules.sources.repository import NewUpload, SourceRepository
from ai_res.modules.sources.version_metadata import SourceVersionMetadataReader
from ai_res.modules.tasks.plan_versions import PlanItemSpec, PlanProposalOrigin, PlanSnapshot, PlanVersionRepository
from ai_res.platform.boundary import read_bounded_body
from ai_res.platform.clock import utc_now
from ai_res.platform.concurrency import AggregateVersionConflict, format_etag, parse_if_match
from ai_res.platform.config import ConfigError, Settings, read_secret_file
from ai_res.platform.correlation import current_request_id
from ai_res.platform.ids import new_id
from ai_res.platform.ports import AuditOutcome, AuditRecord, PolicyDecision, PolicyRequest, Principal
from ai_res.platform.problems import ErrorCode, ProblemError

_log = logging.getLogger("ai_res.api.write")
PROJECT_TYPES = Literal["GREENFIELD", "BROWNFIELD", "HYBRID", "UNKNOWN"]
MAX_TEXT = 20_000  # WORKING technical bound on free text (no normative limit; ADR-078)
MAX_PLAN_DRAFT_BYTES = 1024 * 1024  # technical request allocation bound
WRITE_BODY_TIMEOUT_SECONDS = 10.0  # technical read deadline, not a product SLO
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


class ManagerMessageBody(_Body):
    message: str = Field(min_length=1, max_length=MAX_TEXT)
    attachment_refs: tuple[UUID, ...] = ()
    expected_response_mode: ResponseMode | None = None

    @field_validator("message")
    @classmethod
    def valid_message(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("invalid text")
        return value

    @field_validator("expected_response_mode", mode="before")
    @classmethod
    def supplied_mode(cls, value: object) -> object:
        if value is None:
            raise ValueError("expected response mode must be omitted or an enum")
        return value


def _plan_text(value: str) -> str:
    if "\x00" in value:
        raise ValueError("invalid text")
    return value


PlanDraftText = Annotated[str, Field(max_length=MAX_TEXT), AfterValidator(_plan_text)]


class PlanItemDraftBody(PlanItemSpec):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=False)
    title: Annotated[str, Field(min_length=1, max_length=240), AfterValidator(_plan_text)]
    description: PlanDraftText | None = None
    rationale: PlanDraftText | None = None
    expected_output: PlanDraftText | None = None
    acceptance_criteria: tuple[PlanDraftText, ...] = ()


class PlanDraftBody(_Body):
    expected_version: int = Field(ge=0, le=2_147_483_647, strict=True)
    proposal_version_id: UUID | None = None
    goal: Annotated[PlanDraftText, Field(min_length=1), AfterValidator(_nonblank)]
    scope: PlanDraftText | None = None
    rationale: PlanDraftText | None = None
    entries: tuple[UUID, ...] = Field(min_length=1)
    items: tuple[PlanItemDraftBody, ...] = Field(min_length=1)

    @field_validator("entries")
    @classmethod
    def unique_entries(cls, ids: tuple[UUID, ...]) -> tuple[UUID, ...]:
        return PlanSnapshot.unique_entries(ids)

    @field_validator("proposal_version_id", mode="before")
    @classmethod
    def supplied_proposal(cls, value: object) -> object:
        if value is None:
            raise ValueError("proposalVersionId must be omitted or a UUID")
        return value


class ManagerProposalDecisionBody(_Body):
    decision: HumanDecision
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    comment: PlanDraftText | None = None


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


class CreateTaskBody(_Body):
    title: str = Field(min_length=1, max_length=240)
    description: str | None = None
    task_type: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    _title = field_validator("title")(_nonblank)


class PlanVersionDecisionBody(_Body):
    decision: Literal["APPROVE", "REJECT", "REQUEST_CHANGES"]
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved_item_ids: list[UUID] | None = None
    comment: str | None = None


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


class CompleteUploadBody(_Body):
    sha256: str

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


async def _read_command_body(request: Request, maximum: int) -> bytes:
    try:
        async with timeout(WRITE_BODY_TIMEOUT_SECONDS):
            return await read_bounded_body(request, maximum)
    except TimeoutError:
        raise ProblemError(ErrorCode.VALIDATION_ERROR, "Request body was not received within its time limit.") from None


def register_write_api(app: FastAPI, services: IdentityServices, *, idempotency: IdempotencyService | None = None, storage: StorageConfig | None = None,
                       object_store: ObjectStore | None = None, manager_dispatch_namespace: str | None = None) -> None:
    settings, enforcer, factory = services.settings, services.enforcer, services.factory
    current_session = services.current_session
    if current_session is None or services.origin_guard is None:
        raise RuntimeError("register_identity must run before register_write_api")
    manager_body_limit = settings.manager_message_max_body_bytes
    if manager_dispatch_namespace is not None and manager_body_limit is None:
        raise ConfigError("Manager dispatch requires a request body limit")
    config = enforcer.config
    actions = {"project.create": "PROJECT", "project.update": "PROJECT", "epic.create": "EPIC", "requirement.register": "REQUIREMENT",
               "requirement.propose_version": "REQUIREMENT", "source.upload_create": "SOURCE", "project.read": "PROJECT", "operation.cancel": "OPERATION",
               "source.upload_complete": "SOURCE", "task.create": "EPIC", "epic.read": "EPIC", "plan.propose": "EPIC", "plan.decide": "PLAN_VERSION",
               "manager.send_message": "EPIC", "source.read": "SOURCE", "manager.proposal.read": "MANAGER_PROPOSAL_VERSION",
               "manager.proposal.decide": "MANAGER_PROPOSAL_VERSION", "operation.approve_start_replay": "OPERATION"}
    if config is None or any(a not in config.actions or config.actions[a].resource_type != t for a, t in actions.items()):
        raise RuntimeError("policy configuration lacks the write actions or their resource types; refusing to expose write endpoints")  # fail closed at start-up
    router = APIRouter(prefix="/api/v1", dependencies=[Depends(services.origin_guard)])
    Session = Annotated[AuthenticatedSession, Depends(current_session)]
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

    async def authorize(s: AuthenticatedSession, action: str, project_id: UUID | None, resource_id: UUID | None = None) -> tuple[PolicyRequest, PolicyDecision]:
        """Project-scoped commands first prove the caller may READ the project (a denial is the same 404 as a missing project), and only then ask for the write
        right (a refusal is an honest 403: the caller already sees the project). Both decisions are audited; neither holds a data connection."""
        if project_id is not None:
            await enforcer.decide(policy_request(s, "project.read", project_id, project_id), conceal=True)
        request = policy_request(s, action, project_id, resource_id)
        return request, await enforcer.decide(request)

    async def current_write_authority(session: AsyncSession, s: AuthenticatedSession, project_id: UUID, action: PolicyRequest,
                                      *, reads: tuple[PolicyRequest, ...] = ()) -> tuple[bool, list[tuple[PolicyRequest, PolicyDecision]]]:
        await enforcer.lock_subject_grants(session, s.user_id, s.organization_id, project_id)
        mfa_verified = await lock_authenticated_session(session, s)
        attributes = {"mfa_verified": mfa_verified}
        project_read = policy_request(s, "project.read", project_id, project_id)
        checks = []
        for read in (project_read, *reads):
            current = replace(read, attributes=attributes)
            checks.append((current, await enforcer.decide(current, conceal=True)))
        current = replace(action, attributes=attributes)
        checks.append((current, await enforcer.decide(current)))
        return mfa_verified, checks

    def audit(s: AuthenticatedSession, action: str, rtype: str, rid: UUID, project_id: UUID | None, details: dict[str, Any]) -> AuditRecord:
        return AuditRecord(action=action, outcome=AuditOutcome.SUCCEEDED, resource_type=rtype, resource_id=str(rid), actor_id=str(s.user_id),
                           organization_id=str(s.organization_id), project_id=None if project_id is None else str(project_id), request_id=current_request_id(),
                           details=details)

    def spec(s: AuthenticatedSession, event_type: str, data: dict[str, Any]) -> EventSpec:
        return EventSpec(event_type=event_type, schema_version=1, actor_type="USER", actor_id=s.user_id, correlation_id=correlation_uuid(current_request_id()),
                         destinations=(DOMAIN_DESTINATION,), data=data)

    async def run(s: AuthenticatedSession, *, command: str, key: str | None, payload: Any, project_id: UUID,
                  decision: tuple[PolicyRequest, PolicyDecision], resource_type: str, execute: Callable[[AsyncSession], Awaitable[UUID]],
                  render: Callable[[AsyncSession, UUID], Awaitable[Rendered]], response_status: int = 201,
                  refresh_authority: Callable[[AsyncSession], Awaitable[list[tuple[PolicyRequest, PolicyDecision]]]] | None = None) -> Rendered:
        """The common transaction. A replay (same key + same fingerprint) re-renders the stored resource and writes nothing; the same key with another
        request is 409 IDEMPOTENCY_KEY_REUSED; a request still in progress is a retryable 409."""
        raw_key = _need_key(key)
        service = idem()
        async with UnitOfWork(factory) as uow:
            await uow.with_tenant(s.organization_id, project_id)
            authorization = [decision] if refresh_authority is None else await refresh_authority(uow.session)
            record = await service.begin(uow.session, organization_id=s.organization_id, project_id=project_id, actor_type="USER", actor_id=s.user_id,
                                         command=command, key=raw_key, payload=payload)
            if record.outcome is IdempotencyOutcome.REPLAY and record.resource_id is not None:
                return await render(uow.session, record.resource_id)
            if record.outcome is not IdempotencyOutcome.NEW:
                raise ProblemError(ErrorCode.OPERATION_NOT_READY, "The same request is still being processed; retry shortly.")
            for request, allowed in authorization:
                await enforcer.record_allow(request, allowed, session=uow.session)  # fail-closed: no audit row, no change
            rid = await execute(uow.session)
            await service.complete(uow.session, record, status="COMPLETED", resource_type=resource_type, resource_id=rid, response_status=response_status, response_body_ref=None)
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

    @router.post("/epics/{epic_id}/manager-messages", status_code=202, operation_id="sendManagerMessage")
    async def send_manager_message(epic_id: UUID, incoming: Request, response: Response, s: Session,
                                   idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None) -> dict[str, Any]:
        project_id = await locator.locate(s, "work.epics", epic_id)
        if project_id is None:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Epic not found.")
        request, _ = await authorize(s, "manager.send_message", project_id, epic_id)
        if manager_dispatch_namespace is None or manager_body_limit is None:
            raise ProblemError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Manager dispatch is unavailable.")
        raw_key = _need_key(idempotency_key)
        raw = await _read_command_body(incoming, manager_body_limit)
        try:
            body = ManagerMessageBody.model_validate_json(raw)
        except ValidationError:
            raise ProblemError(ErrorCode.VALIDATION_ERROR, "Invalid Manager message.") from None
        async with UnitOfWork(factory) as uow:
            await uow.with_tenant(s.organization_id, project_id)
            # The request stream is client-paced. Revalidate authority under the write transaction's locks.
            await enforcer.lock_subject_grants(uow.session, s.user_id, s.organization_id, project_id)
            attributes = {"mfa_verified": await lock_authenticated_session(uow.session, s)}
            project_read = policy_request(s, "project.read", project_id, project_id)
            await enforcer.decide(replace(project_read, attributes=attributes), conceal=True)
            await enforcer.authorize(replace(request, attributes=attributes), session=uow.session)
            if body.attachment_refs:
                sources = SourceVersionMetadataReader(uow.session)
                metadata = await sources.resolve_all(body.attachment_refs, s.organization_id, project_id)
                for source_id in dict.fromkeys(item.object_id for item in metadata):
                    lookup = policy_request(s, "source.read", project_id, source_id)
                    await enforcer.authorize(replace(lookup, attributes=attributes), session=uow.session, conceal=True)
            correlation = correlation_uuid(current_request_id())
            scope = AuthorizedIntake(s.organization_id, project_id, epic_id, s.user_id, correlation)
            rid = await persist_manager_intake(
                uow.session, idem(), scope, ManagerMessage(body.message, body.attachment_refs, body.expected_response_mode),
                idempotency_key=raw_key, dispatch_namespace=manager_dispatch_namespace,
            )
            row = await ReadQueries(uow.session).get_operation(rid)
            if row is None:
                raise ProblemError(ErrorCode.INTERNAL_ERROR, "Manager Operation is not visible.")
            rendered = Rendered(202, operation_dto(row), {"Location": f"/api/v1/operations/{rid}", "ETag": format_etag(row["row_version"])})
        return out(response, rendered)

    @router.post("/epics/{epic_id}/tasks", status_code=201, operation_id="createTask")
    async def create_task(epic_id: UUID, body: CreateTaskBody, response: Response, s: Session,
                          idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None) -> dict[str, Any]:
        project_id = await locator.locate(s, "work.epics", epic_id)
        if project_id is None:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Epic not found.")
        allowed = await authorize(s, "task.create", project_id, epic_id)
        requested = RequestedTask(body.title, body.task_type, body.description, tuple(body.acceptance_criteria))

        async def execute(session: AsyncSession) -> UUID:
            task_id = await create_matching_approved_task(
                session, epic_id, requested, actor_id=s.user_id, correlation_id=correlation_uuid(current_request_id()),
            )
            await SqlAuditWriter(session).write(audit(s, "TASK_REGISTERED_IN_APPROVED_PLAN", "TASK", task_id, project_id, {}))
            return task_id

        async def render(session: AsyncSession, task_id: UUID) -> Rendered:
            row = await ReadQueries(session).get_task(task_id)
            if row is None:
                raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Task not found.")
            return Rendered(201, task_dto(row), {})

        rendered = await run(s, command="createTask", key=idempotency_key,
                             payload={"epicId": str(epic_id), **body.model_dump(mode="json")}, project_id=project_id, decision=allowed,
                             resource_type="TASK", execute=execute, render=render)
        return out(response, rendered)

    @router.post("/epics/{epic_id}/plans", status_code=201, operation_id="proposePlanVersion")
    async def propose_plan(epic_id: UUID, incoming: Request, response: Response, _authenticated: Session,
                           idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None) -> dict[str, Any]:
        raw_key = _need_key(idempotency_key)
        raw = await _read_command_body(incoming, MAX_PLAN_DRAFT_BYTES)
        # The byte stream is client-paced. Recheck the session and exact scope afterwards.
        s: AuthenticatedSession = await current_session(incoming)
        project_id = await locator.locate(s, "work.epics", epic_id)
        if project_id is None:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Epic not found.")
        read_checks = [policy_request(s, "epic.read", project_id, epic_id)]
        await enforcer.decide(policy_request(s, "project.read", project_id, project_id), conceal=True)
        await enforcer.decide(read_checks[0], conceal=True)
        request = policy_request(s, "plan.propose", project_id, epic_id)
        allowed = request, await enforcer.decide(request)
        try:
            body = PlanDraftBody.model_validate_json(raw)
        except ValidationError:
            raise ProblemError(ErrorCode.VALIDATION_ERROR, "Invalid plan draft.") from None
        if body.proposal_version_id is not None:
            check = policy_request(s, "manager.proposal.read", project_id, body.proposal_version_id)
            await enforcer.decide(check, conceal=True)
            read_checks.append(check)
        snapshot = PlanSnapshot(goal=body.goal, scope=body.scope, rationale=body.rationale, items=body.items, entries=body.entries)
        payload = {"epicId": str(epic_id), "expectedVersion": body.expected_version, **snapshot.model_dump(mode="json", exclude={"proposal_origin"})}
        if body.proposal_version_id is not None:
            payload["proposalVersionId"] = str(body.proposal_version_id)

        async def refresh(session: AsyncSession) -> list[tuple[PolicyRequest, PolicyDecision]]:
            _, checks = await current_write_authority(session, s, project_id, request, reads=tuple(read_checks))
            return checks

        async def execute(session: AsyncSession) -> UUID:
            proposed = snapshot
            details = {"epicId": str(epic_id)}
            if body.proposal_version_id is not None:
                decision_id, digest = await ManagerProposalRepository(session).approved_plan_origin(
                    body.proposal_version_id, epic_id, goal=body.goal, scope=body.scope,
                )
                origin = PlanProposalOrigin(proposal_version_id=body.proposal_version_id, decision_id=decision_id, content_hash=digest)
                proposed = snapshot.model_copy(update={"proposal_origin": origin})
                details.update(proposalVersionId=str(body.proposal_version_id), proposalDecisionId=str(decision_id))
            version, _digest = await PlanVersionRepository(session).propose(
                s.organization_id, project_id, epic_id, proposed, correlation_id=correlation_uuid(current_request_id()), actor_id=s.user_id,
                expected_version=body.expected_version,
            )
            await SqlAuditWriter(session).write(audit(s, "PLAN_VERSION_PROPOSE", "PLAN_VERSION", version, project_id, details))
            return version

        async def render(session: AsyncSession, version: UUID) -> Rendered:
            row = await ReadQueries(session).get_plan_version(version)
            if row is None or row["epic_id"] != epic_id:
                raise ProblemError(ErrorCode.INTERNAL_ERROR, "Created PlanVersion is not visible.")
            return Rendered(201, plan_version_dto(row), {"ETag": format_etag(row["row_version"])})

        rendered = await run(s, command="proposePlanVersion", key=raw_key, payload=payload,
                             project_id=project_id, decision=allowed, resource_type="PLAN_VERSION", execute=execute, render=render,
                             refresh_authority=refresh)
        return out(response, rendered)

    @router.post("/manager-proposal-versions/{proposal_version_id}/decision", status_code=201, operation_id="decideManagerProposalVersion")
    async def decide_proposal(proposal_version_id: UUID, incoming: Request, response: Response, _authenticated: Session,
                              if_match: Annotated[str | None, Header(alias="If-Match")] = None,
                              idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None) -> dict[str, Any]:
        if parse_if_match(if_match) != 1:
            raise ProblemError(ErrorCode.VERSION_CONFLICT, "Proposal version changed.")
        raw_key = _need_key(idempotency_key)
        raw = await _read_command_body(incoming, MAX_PLAN_DRAFT_BYTES)
        s: AuthenticatedSession = await current_session(incoming)
        project_id = await locator.locate(s, "work.manager_proposal_versions", proposal_version_id)
        if project_id is None:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Proposal not found.")
        check = policy_request(s, "manager.proposal.read", project_id, proposal_version_id)
        await enforcer.decide(check, conceal=True)
        allowed = await authorize(s, "manager.proposal.decide", project_id, proposal_version_id)
        try:
            body = ManagerProposalDecisionBody.model_validate_json(raw)
        except ValidationError:
            raise ProblemError(ErrorCode.VALIDATION_ERROR, "Invalid Proposal decision.") from None
        version = ProposalVersionRef(proposal_version_id, bytes.fromhex(body.content_hash))
        actor = Principal(user_id=str(s.user_id), session_id=str(s.session_id),
                          mfa_verified=s.mfa_verified_at is not None, expires_at=min(s.idle_expires_at, s.absolute_expires_at))
        decision = allowed[1]

        async def refresh(session: AsyncSession) -> list[tuple[PolicyRequest, PolicyDecision]]:
            nonlocal actor, decision
            mfa_verified, checks = await current_write_authority(session, s, project_id, allowed[0], reads=(check,))
            actor = replace(actor, mfa_verified=mfa_verified)
            decision = checks[-1][1]
            return checks

        async def execute(session: AsyncSession) -> UUID:
            return await ManagerProposalRepository(session).record_human_decision(
                s.organization_id, project_id, version, body.decision, actor, decision, require_separation=True,
                comment=body.comment, correlation_id=correlation_uuid(current_request_id()),
            )

        async def render(_session: AsyncSession, decision_id: UUID) -> Rendered:
            return Rendered(201, {"decisionId": str(decision_id), "proposalVersionId": str(version.id), "decision": body.decision.value}, {})

        rendered = await run(s, command="decideManagerProposalVersion", key=raw_key,
                             payload={"proposalVersionId": str(version.id), **body.model_dump(mode="json")}, project_id=project_id,
                             decision=allowed, resource_type="MANAGER_PROPOSAL_DECISION", execute=execute, render=render,
                             refresh_authority=refresh)
        return out(response, rendered)

    @router.post("/plan-versions/{plan_version_id}/decision", status_code=201, operation_id="decidePlanVersion")
    async def decide_plan(plan_version_id: UUID, body: PlanVersionDecisionBody, response: Response, s: Session,
                          if_match: Annotated[str | None, Header(alias="If-Match")] = None,
                          idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None) -> dict[str, Any]:
        expected = parse_if_match(if_match)
        project_id = await locator.locate(s, "work.plan_versions", plan_version_id)
        if project_id is None:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Plan version not found.")
        allowed = await authorize(s, "plan.decide", project_id, plan_version_id)
        items = frozenset(body.approved_item_ids or ())
        if (body.decision == "APPROVE" and (not items or len(items) != len(body.approved_item_ids or ()))) or (
            body.decision != "APPROVE" and "approved_item_ids" in body.model_fields_set
        ):
            raise ProblemError(ErrorCode.VALIDATION_ERROR, "Invalid approved item set.")
        actor = Principal(user_id=str(s.user_id), session_id=str(s.session_id),
                          mfa_verified=s.mfa_verified_at is not None, expires_at=min(s.idle_expires_at, s.absolute_expires_at))
        decision = allowed[1]

        async def refresh(session: AsyncSession) -> list[tuple[PolicyRequest, PolicyDecision]]:
            nonlocal actor, decision
            mfa_verified, checks = await current_write_authority(session, s, project_id, allowed[0])
            actor = replace(actor, mfa_verified=mfa_verified)
            decision = checks[-1][1]
            return checks

        async def execute(session: AsyncSession) -> UUID:
            return await PlanVersionRepository(session).decide(
                s.organization_id, project_id, plan_version_id, bytes.fromhex(body.content_hash), actor, decision,
                decision=body.decision, approved=items, comment=body.comment, expected_version=expected, correlation_id=correlation_uuid(current_request_id()),
            )

        async def render(_session: AsyncSession, decision_id: UUID) -> Rendered:
            return Rendered(201, {"decisionId": str(decision_id), "planVersionId": str(plan_version_id), "decision": body.decision}, {})

        rendered = await run(s, command="decidePlanVersion", key=idempotency_key,
                             payload={"planVersionId": str(plan_version_id), "version": expected, **body.model_dump(mode="json")},
                             project_id=project_id, decision=allowed, resource_type="PLAN_VERSION_DECISION",
                             execute=execute, render=render, refresh_authority=refresh)
        return out(response, rendered)

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

    # -- completeUpload: the STORE'S view of the object (size + store-verified SHA-256) decides, never the client's claim -----------------------------------
    shared: list[ObjectStore] = []  # one lightweight store object per app; each stat opens and closes its own connection (no lifecycle to leak)

    def objects() -> ObjectStore:
        if object_store is not None:
            return object_store
        if not shared:
            cfg = store()
            shared.append(S3ObjectStore(cfg.endpoint, cfg.bucket, cfg.region, cfg.credentials))
        return shared[0]

    async def reject_upload(s: AuthenticatedSession, project_id: UUID, upload_id: UUID, status: str, code: str | None, reason: str) -> ProblemError:
        """Persists the verdict in its OWN committed transaction, then hands back the problem (raised by the caller): a rejection must outlive the failed request."""
        async with UnitOfWork(factory) as uow:
            await uow.with_tenant(s.organization_id, project_id)
            row = await SourceRepository(uow.session).get_upload(upload_id)
            if row is not None and row.status in ("PENDING", "UPLOADED"):
                if not await SourceRepository(uow.session).reject_upload(upload_id, status, code):  # lost a race: decide from the real state, not the stale read
                    return ProblemError(ErrorCode.STATE_TRANSITION_NOT_ALLOWED, "The upload was decided concurrently.")
                await SqlAuditWriter(uow.session).write(audit(s, "UPLOAD_" + status, "SOURCE", row.source_id, project_id, {"uploadId": str(upload_id), "reason": reason}))
        return ProblemError(ErrorCode.VALIDATION_ERROR, "The uploaded object failed verification.", errors=[{"field": "object", "reason": reason}])

    @router.post("/uploads/{upload_id}/complete", status_code=202)
    async def complete_upload(upload_id: UUID, body: CompleteUploadBody, response: Response, s: Session,
                              idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None) -> dict[str, Any]:
        project_id = await locator.locate(s, "sources.uploads", upload_id)
        if project_id is None:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")
        decision = await authorize(s, "source.upload_complete", project_id, upload_id)
        _need_key(idempotency_key)
        async with UnitOfWork(factory) as uow:  # a short read transaction: no network call is made while it is open
            await uow.with_tenant(s.organization_id, project_id)
            intent = await SourceRepository(uow.session).get_intent(upload_id)
        if intent is None:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")
        if intent.status == "VERIFIED":  # completed before: only the SAME key may replay it (handled by the idempotent command below)
            observed = None
        else:
            if intent.status not in ("PENDING", "UPLOADED"):
                raise ProblemError(ErrorCode.STATE_TRANSITION_NOT_ALLOWED, "The upload can no longer be completed.")
            if body.sha256 != intent.sha256.hex():
                raise ProblemError(ErrorCode.VALIDATION_ERROR, "sha256 does not match the declared checksum.", errors=[{"field": "sha256", "reason": "checksum_mismatch"}])
            if utc_now() > intent.expires_at:
                raise await reject_upload(s, project_id, upload_id, "EXPIRED", None, "expired")
            try:
                observed = await objects().stat(intent.object_key)
            except ObjectStoreError as exc:
                _log.error("object store did not answer: %s", exc)
                raise ProblemError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Upload verification is unavailable; retry.") from exc
            if observed is None:
                raise ProblemError(ErrorCode.OPERATION_NOT_READY, "The object has not been uploaded yet.")
            if observed.size_bytes != intent.size_bytes:
                raise await reject_upload(s, project_id, upload_id, "REJECTED", "SIZE_MISMATCH", "size_mismatch")
            if observed.sha256 is None or observed.sha256 != intent.sha256:  # an unverifiable object is rejected, never accepted on declared values
                raise await reject_upload(s, project_id, upload_id, "REJECTED", "CHECKSUM_MISMATCH", "checksum_mismatch")

        async def execute(session: AsyncSession) -> UUID:
            done = await complete_verified_upload(session, organization_id=s.organization_id, project_id=project_id, upload_id=upload_id, actor_id=s.user_id,
                                                  correlation_id=correlation_uuid(current_request_id()), observed=observed)
            await SqlAuditWriter(session).write(audit(s, "UPLOAD_COMPLETE", "SOURCE", done.source_id, project_id,
                                                      {"uploadId": str(upload_id), "sourceVersionId": str(done.source_version_id)}))
            return done.operation_id

        async def render(session: AsyncSession, rid: UUID) -> Rendered:
            row = await ReadQueries(session).get_operation(rid)
            if row is None:
                raise ProblemError(ErrorCode.INTERNAL_ERROR, "Resource is not visible.")
            return Rendered(202, operation_dto(row), {"Location": f"/api/v1/operations/{rid}", "ETag": format_etag(row["row_version"])})

        return out(response, await run(s, command="completeUpload", key=idempotency_key, payload={"uploadId": str(upload_id), "sha256": body.sha256}, project_id=project_id,
                                       decision=decision, resource_type="OPERATION", execute=execute, render=render, response_status=202))

    # -- requestOperationCancellation: 202 = the REQUEST was recorded; CANCELLED comes only after the orchestrator reconciled (S12) ------------------------
    @router.post("/operations/{operation_id}/cancel", status_code=202)
    async def cancel_operation(operation_id: UUID, response: Response, s: Session, idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None) -> dict[str, Any]:
        project_id = await locator.locate(s, "operations.operations", operation_id)
        if project_id is None:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")  # missing, foreign and unreadable are indistinguishable
        decision = await authorize(s, "operation.cancel", project_id, operation_id)

        async def execute(session: AsyncSession) -> UUID:
            await request_cancellation(session, operation_id, actor_id=s.user_id, correlation_id=correlation_uuid(current_request_id()))
            await SqlAuditWriter(session).write(audit(s, "OPERATION_CANCEL_REQUESTED", "OPERATION", operation_id, project_id, {}))
            return operation_id

        async def render(session: AsyncSession, rid: UUID) -> Rendered:
            row = await ReadQueries(session).get_operation(rid)
            if row is None:
                raise ProblemError(ErrorCode.INTERNAL_ERROR, "Resource is not visible.")
            return Rendered(202, operation_dto(row), {"Location": f"/api/v1/operations/{rid}", "ETag": format_etag(row["row_version"])})

        return out(response, await run(s, command="requestOperationCancellation", key=idempotency_key, payload={"operationId": str(operation_id)}, project_id=project_id,
                                       decision=decision, resource_type="OPERATION", execute=execute, render=render, response_status=202))

    @router.get("/operations/{operation_id}/start-replay")
    async def read_start_replay(operation_id: UUID, response: Response, s: Session) -> dict[str, Any]:
        project_id = await locator.locate(s, "operations.operations", operation_id)
        if project_id is None:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")
        request, allowed = await authorize(s, "operation.approve_start_replay", project_id, operation_id)
        async with UnitOfWork(factory) as uow:
            await uow.with_tenant(s.organization_id, project_id)
            await enforcer.record_allow(request, allowed, session=uow.session)
            target = await inspect_quarantined_start(uow.session, operation_id)
        if target is None:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Replay candidate not found.")
        response.headers["ETag"] = format_etag(target.replay_count + 1)
        response.headers["Cache-Control"] = "no-store"
        return {"operationId": str(operation_id), "eventId": str(target.event_id)}

    @router.post("/operations/{operation_id}/start-replay/{event_id}", status_code=202)
    async def approve_start_replay(
        operation_id: UUID, event_id: UUID, response: Response, s: Session,
        if_match: Annotated[str | None, Header(alias="If-Match")] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> dict[str, Any]:
        project_id = await locator.locate(s, "operations.operations", operation_id)
        if project_id is None:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")
        decision = await authorize(s, "operation.approve_start_replay", project_id, operation_id)
        generation = parse_if_match(if_match)
        if generation > 2_147_483_647:
            raise ProblemError(ErrorCode.VERSION_CONFLICT, "Replay version changed.")

        async def execute(session: AsyncSession) -> UUID:
            if not await approve_quarantined_start(
                session, operation_id, QuarantinedStart(event_id, generation - 1),
                actor_id=s.user_id, session_id=s.session_id, correlation_id=correlation_uuid(current_request_id()),
            ):
                raise ProblemError(ErrorCode.VERSION_CONFLICT, "Replay candidate has changed.")
            return operation_id

        async def render(_session: AsyncSession, rid: UUID) -> Rendered:
            return Rendered(202, {"operationId": str(rid), "eventId": str(event_id)}, {"Location": f"/api/v1/operations/{rid}"})

        return out(response, await run(
            s, command="approveAssignedStartReplay", key=idempotency_key,
            payload={"operationId": str(operation_id), "eventId": str(event_id), "generation": generation},
            project_id=project_id, decision=decision, resource_type="OPERATION", execute=execute, render=render, response_status=202,
        ))

    app.include_router(router)

