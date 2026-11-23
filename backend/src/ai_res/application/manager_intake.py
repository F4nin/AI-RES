"""Transactional persistence for an authorized Manager message."""
import hashlib
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.modules.audit.writer import SqlAuditWriter
from ai_res.modules.epics.manager_interactions import ManagerInteractionRepository, ManagerMessage
from ai_res.modules.events.aggregate_events import EventSpec
from ai_res.modules.events.envelope import DOMAIN_DESTINATION, EventRef
from ai_res.modules.iam.platform_credentials import PlatformAction
from ai_res.modules.idempotency.repository import IdempotencyOutcome
from ai_res.modules.idempotency.service import IdempotencyService
from ai_res.modules.operations.execution_authority import OperationAssignments
from ai_res.modules.operations.repository import NewOperation, OperationRepository
from ai_res.modules.sources.version_metadata import SourceVersionMetadataReader
from ai_res.orchestration.contracts import EXECUTION_ASSIGNMENT_REF, START_DESTINATION
from ai_res.platform.ids import new_id
from ai_res.platform.ports import AuditOutcome, AuditRecord
from ai_res.platform.problems import ErrorCode, ProblemError


@dataclass(frozen=True, slots=True)
class AuthorizedIntake:
    """Trusted caller supplies checked user, Epic scope and attachment authorization."""
    organization_id: UUID
    project_id: UUID
    epic_id: UUID
    user_id: UUID
    correlation_id: UUID


async def persist_manager_intake(
    session: AsyncSession, idempotency: IdempotencyService, scope: AuthorizedIntake,
    message: ManagerMessage, *, idempotency_key: str, dispatch_namespace: str | None = None,
) -> UUID:
    """Use the caller's tenant transaction and return the accepted Operation id.

    Attachment permissions are rechecked by the calling policy boundary.
    The transaction verifies exact same-project versions before storing refs.
    Transport dispatch is attached by the caller only after ADR-129/G-107 admission.
    """
    record = await idempotency.begin(
        session, organization_id=scope.organization_id, project_id=scope.project_id, actor_type="USER",
        actor_id=scope.user_id, command="sendManagerMessage", key=idempotency_key, payload={
            "epicId": str(scope.epic_id), "message": message.text,
            "attachmentRefs": [str(ref) for ref in message.attachment_versions],
            "expectedResponseMode": message.expected_response_mode,
        },
    )
    if record.outcome is IdempotencyOutcome.IN_PROGRESS:
        raise ProblemError(ErrorCode.AGGREGATE_VERSION_CONFLICT, "Manager message is already in progress.")

    references = SourceVersionMetadataReader(session)
    await references.resolve_all(message.attachment_versions, scope.organization_id, scope.project_id)
    if record.outcome is IdempotencyOutcome.REPLAY:
        if record.resource_type != "OPERATION" or record.resource_id is None:
            raise ProblemError(ErrorCode.INTERNAL_ERROR, "Missing Manager intake receipt.")
        return record.resource_id
    operation_id = new_id()
    assignment = new_id() if dispatch_namespace is not None else None
    destinations = (DOMAIN_DESTINATION, START_DESTINATION) if assignment is not None else (DOMAIN_DESTINATION,)
    refs = (EventRef(EXECUTION_ASSIGNMENT_REF, assignment),) if assignment is not None else ()
    operation = NewOperation(
        id=operation_id, organization_id=scope.organization_id, project_id=scope.project_id,
        operation_type="MANAGER_MESSAGE", initiator_type="USER", initiator_id=scope.user_id,
        idempotency_scope=f"manager-message:{record.id}", request_fingerprint=hashlib.sha256(record.id.bytes).digest(),
        completion_policy_version="wip-1", completion_policy_snapshot={}, correlation_id=scope.correlation_id,
        created_by=scope.user_id,
    )
    _, accepted = await OperationRepository(session).create(
        operation, EventSpec("operation.accepted", 1, "USER", scope.correlation_id,
                             destinations, actor_id=scope.user_id, refs=refs, data={"operationType": operation.operation_type},
                             dispatch_namespace=dispatch_namespace),
    )
    if assignment is not None and dispatch_namespace is not None:
        await OperationAssignments(session).register(
            operation_id, namespace=dispatch_namespace, assignment_id=assignment,
            actions=frozenset({PlatformAction.ACKNOWLEDGE_START, PlatformAction.RECORD_FAILURE, PlatformAction.CONFIRM_CANCELLATION,
                               PlatformAction.READ_MANAGER_INPUT, PlatformAction.RECORD_MANAGER_DRAFT}),
        )
    interaction = await ManagerInteractionRepository(session).append(
        organization_id=scope.organization_id, project_id=scope.project_id, epic_id=scope.epic_id,
        operation_id=operation_id, author_id=scope.user_id, message=message, correlation_id=scope.correlation_id, causation_id=accepted.event_id,
    )
    await SqlAuditWriter(session).write(AuditRecord(
        action="MANAGER_INTERACTION_RECEIVED", outcome=AuditOutcome.SUCCEEDED, resource_type="MANAGER_INTERACTION",
        actor_id=str(scope.user_id), organization_id=str(scope.organization_id), project_id=str(scope.project_id),
        resource_id=str(interaction), request_id=str(scope.correlation_id), details={"operationId": str(operation_id)},
    ))
    await idempotency.complete(session, record, status="COMPLETED", resource_type="OPERATION", resource_id=operation_id,
                               response_status=202, response_body_ref={"operationId": str(operation_id)})
    return operation_id
