"""Application Service: finish a verified upload (coding-standards: domain writes go through a service, not a router).

One transaction: upload UPLOADED -> VERIFIED, the SourceVersion, and the SOURCE_INGESTION Operation with its accepted event. The object-store check happened
BEFORE this transaction (no network call is made while it is open); here the verified facts are only recorded. The ingestion pipeline is S27, so no start
command is queued (G-107, G-116) and the completion policy is a WORKING placeholder.
"""
import hashlib
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.modules.events.aggregate_events import EventSpec
from ai_res.modules.events.envelope import DOMAIN_DESTINATION
from ai_res.modules.operations.repository import NewOperation, OperationRepository
from ai_res.modules.sources.object_store import ObservedObject
from ai_res.modules.sources.repository import SourceRepository
from ai_res.platform.clock import utc_now
from ai_res.platform.ids import new_id
from ai_res.platform.problems import ErrorCode, ProblemError

COMPLETION_POLICY_VERSION = "wip-1"  # WORKING: SOURCE_INGESTION completion policy arrives with S21/S27


@dataclass(frozen=True)
class CompletedUpload:
    operation_id: UUID
    source_id: UUID
    source_version_id: UUID


async def complete_verified_upload(session: AsyncSession, *, organization_id: UUID, project_id: UUID, upload_id: UUID, actor_id: UUID, correlation_id: UUID,
                                   observed: ObservedObject | None) -> CompletedUpload:
    sources = SourceRepository(session)
    upload = await sources.get_upload(upload_id)
    if upload is None:
        raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")
    if upload.status not in ("PENDING", "UPLOADED") or observed is None:
        raise ProblemError(ErrorCode.STATE_TRANSITION_NOT_ALLOWED, "The upload was already completed.")
    if observed.sha256 is None:  # explicit, not an assert (stripped under -O): an unverifiable object is never recorded as verified
        raise ProblemError(ErrorCode.INTERNAL_ERROR, "Unverified object reached finalization.")
    if upload.status == "PENDING":
        upload = await sources.mark_uploaded(upload)
    upload = await sources.verify_upload(upload, observed.size_bytes, observed.sha256)
    version = await sources.finalize_version(organization_id, project_id, upload, received_at=utc_now(),
                                             provenance={"uploadId": str(upload_id), "via": "completeUpload"}, created_by=actor_id)
    operation_id = new_id()
    await OperationRepository(session).create(
        NewOperation(id=operation_id, organization_id=organization_id, project_id=project_id, operation_type="SOURCE_INGESTION", initiator_type="USER",
                     initiator_id=actor_id, idempotency_scope=f"complete-upload:{upload_id}", request_fingerprint=hashlib.sha256(upload_id.bytes).digest(),
                     completion_policy_version=COMPLETION_POLICY_VERSION, completion_policy_snapshot={}, correlation_id=correlation_id, created_by=actor_id),
        EventSpec(event_type="operation.accepted", schema_version=1, actor_type="USER", actor_id=actor_id, correlation_id=correlation_id,
                  destinations=(DOMAIN_DESTINATION,), data={"sourceVersionId": str(version.id)}))
    return CompletedUpload(operation_id, upload.source_id, version.id)
