# ruff: noqa: E501 -- fixed SQL keeps scope predicates reviewable
"""Internal ContextApplicationService (DOC-006 §6), explicit-ref slice.

Called by trusted application code with a server-authenticated human session.
No browser route, runtime credential, retrieval, text materialization or Gate is
introduced here. Future calling commands must authorize their own domain action;
the read checks here only authorize inclusion and access to derived metadata. Existing read grants authorize this derived ref-only snapshot;
they do not grant a new domain action. All dereferences are reauthorized.
"""
from collections.abc import Callable, Mapping
from uuid import UUID

from opentelemetry import metrics, trace
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.db.session import UnitOfWork
from ai_res.modules.audit.writer import SqlAuditWriter
from ai_res.modules.context.manifest import BUILDER_VERSION, SCHEMA_VERSION, ContextManifest
from ai_res.modules.context.repository import ContextPackageSnapshot, ContextRepository, not_found
from ai_res.modules.context.types import ContextItemKind, ContextRef, ResolvedRef
from ai_res.modules.iam.authority import lock_authenticated_session
from ai_res.modules.iam.sessions import AuthenticatedSession
from ai_res.modules.idempotency.repository import IdempotencyOutcome
from ai_res.modules.idempotency.service import IdempotencyService
from ai_res.platform.correlation import current_request_id
from ai_res.platform.ports import AuditOutcome, AuditRecord, PolicyRequest
from ai_res.platform.problems import ErrorCode, ProblemError
from ai_res.platform.version_metadata import VersionMetadataPort
from ai_res.policy.enforcer import PolicyEnforcer

_ACTIONS = {"REQUIREMENT_VERSION": ("requirement.read", "REQUIREMENT"), "SOURCE_VERSION": ("source.read", "SOURCE"),
            "ARTIFACT_VERSION": ("artifact.read", "ARTIFACT")}
_tracer = trace.get_tracer("ai_res.context")
_counter = metrics.get_meter("ai_res.context").create_counter("ai_res.context.operations", description="Context operations by fixed result")


class ContextApplicationService:
    def __init__(self, factory: async_sessionmaker[AsyncSession], enforcer: PolicyEnforcer, idempotency: IdempotencyService,
                 resolvers: Callable[[AsyncSession], Mapping[ContextItemKind, VersionMetadataPort]]) -> None:
        self._factory, self._policy, self.idempotency, self._resolvers = factory, enforcer, idempotency, resolvers

    def _request(self, actor: AuthenticatedSession, project: UUID, action: str, kind: str, object_id: UUID, *, mfa: bool | None = None) -> PolicyRequest:
        return PolicyRequest(actor_id=str(actor.user_id), organization_id=str(actor.organization_id), project_id=str(project), action=action,
                             resource_type=kind, resource_id=str(object_id),
                             attributes={"actor_type": "USER", "mfa_verified": actor.mfa_verified_at is not None if mfa is None else mfa})

    async def _lock_authority(self, s: AsyncSession, actor: AuthenticatedSession, project: UUID) -> bool:
        await self._policy.lock_subject_grants(s, actor.user_id, actor.organization_id, project)
        return await lock_authenticated_session(s, actor)

    async def _resolve(self, s: AsyncSession, org: UUID, project: UUID, ref: ContextRef) -> ResolvedRef:
        metadata = await self._resolvers(s)[ref.kind].resolve(ref.version_id, org, project)
        return ResolvedRef(ref, metadata.object_id, metadata.version_number, metadata.content_digest)

    async def _authorize_manifest(self, s: AsyncSession, actor: AuthenticatedSession, project: UUID, manifest: ContextManifest, mfa: bool) -> None:
        await self._policy.authorize(self._request(actor, project, "project.read", "PROJECT", project, mfa=mfa), session=s, conceal=True)
        for item in manifest.items:
            # Exact metadata comes from the server. No caller-supplied owner, checksum, provenance or ACL fact is trusted.
            actual = await self._resolve(s, actor.organization_id, project, item.ref)
            if actual != item:
                raise ProblemError(ErrorCode.STATE_TRANSITION_NOT_ALLOWED, "Context integrity check failed.")
            action, kind = _ACTIONS[item.ref.kind.value]
            await self._policy.authorize(self._request(actor, project, action, kind, item.object_id, mfa=mfa), session=s, conceal=True)

    async def build(self, actor: AuthenticatedSession, project: UUID, refs: tuple[ContextRef, ...], *, key: str,
                    package_id: UUID | None = None, expected_version: int | None = None) -> ContextPackageSnapshot:
        try:
            return await self._build(actor, project, refs, key=key, package_id=package_id, expected_version=expected_version)
        except Exception as exc:
            reason = exc.code.value if isinstance(exc, ProblemError) else "BUILD_FAILED"
            # The protected UoW is already rolled back. Audit failure must never
            # convert a refusal into success; no raw exception/source data leaves it.
            try:
                async with UnitOfWork(self._factory) as uow:
                    await uow.with_tenant(actor.organization_id)
                    safe_refs = [{"kind": r.kind.value, "versionId": str(r.version_id)} for r in refs if isinstance(r, ContextRef)] if isinstance(refs, tuple) else []
                    await SqlAuditWriter(uow.session).write(AuditRecord(
                        action="CONTEXT_PACKAGE_BUILD_FAILED", outcome=AuditOutcome.FAILED, resource_type="PROJECT",
                        actor_id=str(actor.user_id), organization_id=str(actor.organization_id), request_id=current_request_id(), reason_code=reason,
                        details={"projectRef": str(project), "requestedRefs": safe_refs, "builderVersion": BUILDER_VERSION,
                                 "schemaVersion": SCHEMA_VERSION, "reasonCode": reason}))
            except Exception as audit_exc:
                raise ProblemError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Audit unavailable; action not performed.") from audit_exc
            _counter.add(1, {"operation": "build", "outcome": "failed"})
            raise

    async def _build(self, actor: AuthenticatedSession, project: UUID, refs: tuple[ContextRef, ...], *, key: str,
                    package_id: UUID | None = None, expected_version: int | None = None) -> ContextPackageSnapshot:
        if not isinstance(refs, tuple) or not refs or any(not isinstance(r, ContextRef) for r in refs) or len(set(refs)) != len(refs):
            raise ValueError("a nonempty tuple of unique exact refs is required")
        if package_id is not None and (type(expected_version) is not int or expected_version < 1):
            raise ProblemError(ErrorCode.PRECONDITION_REQUIRED, "The package's expected version is required.")
        if package_id is None and expected_version is not None:
            raise ValueError("expected_version requires package_id")
        # Initial project authorization needs no caller connection. Final local policy revalidation occurs under authority locks.
        await self._policy.decide(self._request(actor, project, "project.read", "PROJECT", project), conceal=True)
        with _tracer.start_as_current_span("context.build", record_exception=False, set_status_on_exception=False):
            async with UnitOfWork(self._factory) as uow:
                await uow.with_tenant(actor.organization_id, project)
                s = uow.session
                mfa = await self._lock_authority(s, actor, project)
                repo = ContextRepository(s)
                manifest = ContextManifest(actor.organization_id, project, tuple([await self._resolve(s, actor.organization_id, project, r) for r in refs]))
                await self._authorize_manifest(s, actor, project, manifest, mfa)
                payload = {"manifest": manifest.to_dict(), "packageId": str(package_id) if package_id else None, "expectedVersion": expected_version}
                record = await self.idempotency.begin(s, organization_id=actor.organization_id, project_id=project, actor_type="USER", actor_id=actor.user_id,
                                                      command="context.build", key=key, payload=payload)
                if record.outcome is not IdempotencyOutcome.NEW:
                    if record.outcome is not IdempotencyOutcome.REPLAY or record.resource_id is None:
                        raise ProblemError(ErrorCode.AGGREGATE_VERSION_CONFLICT, "Context build is in progress.")
                    result = await repo.load(actor.organization_id, project, record.resource_id)
                    await self._authorize_manifest(s, actor, project, result.manifest, mfa)
                    return result
                result = await repo.save(manifest, actor.user_id, package_id=package_id, expected_version=expected_version)
                await SqlAuditWriter(s).write(AuditRecord(action="CONTEXT_PACKAGE_BUILT", outcome=AuditOutcome.SUCCEEDED, resource_type="CONTEXT_PACKAGE_VERSION",
                                                        resource_id=str(result.version_id), organization_id=str(actor.organization_id), project_id=str(project),
                                                        actor_id=str(actor.user_id), request_id=current_request_id(),
                                                        details={"packageId": str(result.package_id), "versionNumber": result.version_number,
                                                                 "snapshotHash": result.content_hash, "itemCount": len(manifest.items),
                                                                 "builderVersion": BUILDER_VERSION, "schemaVersion": SCHEMA_VERSION,
                                                                 "manifestRef": str(result.version_id), "exclusionReasonCodes": []}))
                await self.idempotency.complete(s, record, status="COMPLETED", resource_type="CONTEXT_PACKAGE_VERSION", resource_id=result.version_id,
                                                response_status=201, response_body_ref={"versionId": str(result.version_id)})
            _counter.add(1, {"operation": "build", "outcome": "success"})
            return result

    async def retrieve(self, actor: AuthenticatedSession, project: UUID, version_id: UUID) -> ContextPackageSnapshot:
        await self._policy.decide(self._request(actor, project, "project.read", "PROJECT", project), conceal=True)
        with _tracer.start_as_current_span("context.retrieve", record_exception=False, set_status_on_exception=False):
            async with UnitOfWork(self._factory) as uow:
                await uow.with_tenant(actor.organization_id, project)
                mfa = await self._lock_authority(uow.session, actor, project)
                result = await ContextRepository(uow.session).load(actor.organization_id, project, version_id)
                if result.manifest.project_id != project:
                    raise not_found()
                await self._authorize_manifest(uow.session, actor, project, result.manifest, mfa)
            _counter.add(1, {"operation": "retrieve", "outcome": "success"})
            return result
