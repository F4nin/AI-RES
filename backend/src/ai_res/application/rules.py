# ruff: noqa: E501 -- command and persistence arguments kept together
"""Trusted S18 application boundary; Rules results never grant access.

No transport or management grants are installed. Production activation requires
an independently configured human authority/separation policy. Context facts
are derived from the authorized immutable S19 manifest, never caller assertions.
"""
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid5

from opentelemetry import metrics, trace
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.db.cas import canonical_json
from ai_res.db.session import UnitOfWork
from ai_res.modules.audit.writer import SqlAuditWriter
from ai_res.modules.context.repository import ContextPackageSnapshot
from ai_res.modules.context.service import ContextApplicationService
from ai_res.modules.iam.authority import lock_authenticated_session
from ai_res.modules.iam.sessions import AuthenticatedSession
from ai_res.modules.idempotency.repository import IdempotencyOutcome
from ai_res.modules.idempotency.service import IdempotencyService
from ai_res.modules.rules.engine import ENGINE_VERSION, EvaluationResult, evaluate_rules
from ai_res.modules.rules.language import parse_definition
from ai_res.modules.rules.registry import RuleRegistry
from ai_res.modules.rules.repository import RulesRepository
from ai_res.modules.rules.types import (
    EvaluationScope,
    FactField,
    FactSchema,
    FactSnapshot,
    FactType,
    RuleException,
    RuleLevel,
    RuleSnapshot,
    canonical_hash,
)
from ai_res.modules.rules.validation import ValidationReport, validate_rule
from ai_res.platform.clock import require_utc, utc_now
from ai_res.platform.correlation import current_request_id
from ai_res.platform.ids import new_id
from ai_res.platform.ports import AuditOutcome, AuditRecord, PolicyRequest
from ai_res.platform.problems import ErrorCode, ProblemError
from ai_res.policy.enforcer import PolicyEnforcer

FACT_SCHEMA = FactSchema("1.0", (FactField("context_item_count", FactType.INT), FactField("context_has_source", FactType.BOOL),
                               FactField("context_has_artifact", FactType.BOOL), FactField("context_has_requirement", FactType.BOOL)))
_FACT_NS = UUID("ebd67931-84bf-4d40-ae41-85f26c156944")
_tracer = trace.get_tracer("ai_res.rules")
_counter = metrics.get_meter("ai_res.rules").create_counter("ai_res.rules.operations", description="Rules operations by fixed outcome")


def _not_found() -> ProblemError:
    return ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")


@dataclass(frozen=True, slots=True)
class RuleMutationResult:
    rule: RuleSnapshot
    parent_version: int
    validation_id: UUID | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"rule": self.rule.to_dict(), "parentVersion": self.parent_version,
                "validationRef": None if self.validation_id is None else str(self.validation_id)}

    @classmethod
    def from_dict(cls, body: dict[str, Any]) -> "RuleMutationResult":
        if body.keys() != {"rule", "parentVersion", "validationRef"} or type(body["parentVersion"]) is not int or body["parentVersion"] < 1:
            raise ValueError("invalid mutation receipt")
        return cls(RuleSnapshot.from_dict(body["rule"], FACT_SCHEMA), body["parentVersion"],
                   None if body["validationRef"] is None else UUID(body["validationRef"]))


@dataclass(frozen=True, slots=True)
class RuleEvaluationRecord:
    id: UUID
    context_id: UUID
    evaluated_at: datetime
    input_json: str
    result: EvaluationResult


Mutation = Callable[[RulesRepository, RuleRegistry, datetime, dict[str, Any] | None], Awaitable[RuleMutationResult]]


class RulesApplicationService:
    def __init__(self, factory: async_sessionmaker[AsyncSession], enforcer: PolicyEnforcer, idempotency: IdempotencyService,
                 context: ContextApplicationService, *, separation_required: bool | None = None,
                 clock: Callable[[], datetime] = utc_now) -> None:
        if separation_required is not None and type(separation_required) is not bool:
            raise ValueError("separation policy must be explicit or unconfigured")
        self._factory, self._policy, self._idem, self._context = factory, enforcer, idempotency, context
        self._separation, self._clock = separation_required, clock

    @staticmethod
    def _human(actor: AuthenticatedSession) -> None:
        if not isinstance(actor, AuthenticatedSession):
            raise ProblemError(ErrorCode.AUTHENTICATION_REQUIRED, "A human session is required.")

    def _request(self, actor: AuthenticatedSession, project: UUID | None, action: str, resource: str,
                 resource_id: UUID | None, mfa: bool) -> PolicyRequest:
        return PolicyRequest(actor_id=str(actor.user_id), organization_id=str(actor.organization_id),
                             project_id=None if project is None else str(project), action=action, resource_type=resource,
                             resource_id=None if resource_id is None else str(resource_id), attributes={"actor_type": "USER", "mfa_verified": mfa})

    async def _authority(self, s: AsyncSession, actor: AuthenticatedSession, project: UUID | None) -> bool:
        await self._policy.lock_subject_grants(s, actor.user_id, actor.organization_id, project)
        return await lock_authenticated_session(s, actor)

    def _approval_binding(self, actor: AuthenticatedSession, rule: RuleSnapshot) -> None:
        if self._separation is None:
            raise ProblemError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Rule approval authority is not configured.")
        if self._separation and actor.user_id == rule.author_id:
            raise ProblemError(ErrorCode.ACCESS_DENIED, "Independent human approval is required.")

    async def _failure_audit(self, actor: AuthenticatedSession, project: UUID | None, operation: str, error: Exception) -> None:
        reason = error.code.value if isinstance(error, ProblemError) else "RULES_OPERATION_FAILED"
        try:
            async with UnitOfWork(self._factory) as uow:
                await uow.with_tenant(actor.organization_id)
                await SqlAuditWriter(uow.session).write(AuditRecord(
                    action="RULES_OPERATION_FAILED", outcome=AuditOutcome.FAILED, resource_type="RULE",
                    organization_id=str(actor.organization_id), actor_id=str(actor.user_id), request_id=current_request_id(), reason_code=reason,
                    details={"operation": operation, "projectRef": None if project is None else str(project), "reasonCode": reason}))
        except Exception as exc:
            raise ProblemError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Audit unavailable; action not performed.") from exc

    async def _mutate(self, actor: AuthenticatedSession, project: UUID | None, operation: str, key: str, payload: dict[str, Any],
                      mutation: Mutation, *, version_id: UUID | None = None, level: RuleLevel = RuleLevel.PROJECT) -> RuleMutationResult:
        self._human(actor)
        try:
            with _tracer.start_as_current_span("rules.manage", record_exception=False, set_status_on_exception=False):
                async with UnitOfWork(self._factory) as uow:
                    await uow.with_tenant(actor.organization_id, project)
                    s = uow.session
                    repo, registry = RulesRepository(s), RuleRegistry(s, FACT_SCHEMA)
                    await repo.lock_registry()
                    mfa = await self._authority(s, actor, project)
                    row = await repo.get_version(version_id) if version_id is not None else None
                    if row is not None:
                        level = RuleLevel[row["level"]]
                    if level is RuleLevel.SYSTEM:
                        raise ProblemError(ErrorCode.ACCESS_DENIED, "System rules require the platform release process.")
                    if (level is RuleLevel.ORGANIZATION) != (project is None):
                        raise _not_found()
                    action = f"rules.{operation}" if project is not None else f"rules.organization.{operation}"
                    await self._policy.authorize(self._request(actor, project, action, "RULE" if project else "ORGANIZATION_RULE", version_id, mfa),
                                                 session=s, conceal=True)
                    record = await self._idem.begin(s, organization_id=actor.organization_id, project_id=project, actor_type="USER", actor_id=actor.user_id,
                                                    command=action, key=key, payload=payload)
                    if record.outcome is not IdempotencyOutcome.NEW:
                        if record.outcome is not IdempotencyOutcome.REPLAY or record.response_body_ref is None:
                            raise ProblemError(ErrorCode.AGGREGATE_VERSION_CONFLICT, "Rule command is in progress.")
                        return RuleMutationResult.from_dict(record.response_body_ref)
                    result = await mutation(repo, registry, require_utc(self._clock()), row)
                    await SqlAuditWriter(s).write(AuditRecord(
                        action=f"RULE_{operation.upper()}", outcome=AuditOutcome.SUCCEEDED, resource_type="RULE_VERSION", resource_id=str(result.rule.version_id),
                        organization_id=str(actor.organization_id), project_id=None if project is None else str(project), actor_id=str(actor.user_id),
                        request_id=current_request_id(), details={"ruleRef": str(result.rule.rule_id), "versionNumber": result.rule.version_number,
                                                                 "parentVersion": result.parent_version, "definitionHash": result.rule.definition_hash,
                                                                 "validationRef": None if result.validation_id is None else str(result.validation_id)}))
                    await self._idem.complete(s, record, status="COMPLETED", resource_type="RULE_VERSION", resource_id=result.rule.version_id,
                                              response_status=200, response_body_ref=result.to_dict())
                _counter.add(1, {"operation": "manage", "outcome": "success"})
                return result
        except Exception as exc:
            await self._failure_audit(actor, project, "manage", exc)
            raise

    async def _validation(self, repo: RulesRepository, registry: RuleRegistry, actor: AuthenticatedSession, project: UUID | None,
                          rule: RuleSnapshot, at: datetime, *, require_valid: bool = True) -> UUID:
        basis = await registry.snapshots()
        report = validate_rule(rule, FACT_SCHEMA, basis)
        rid = await repo.save_validation(organization_id=actor.organization_id, project_id=project, proposal_version_id=rule.version_id,
                                         proposal_hash=rule.content_hash, basis_hash=report.basis_fingerprint,
                                         basis={"schema": FACT_SCHEMA.to_dict(), "rules": [r.to_dict() for r in basis]}, result=report.to_dict(), actor_id=actor.user_id, at=at)
        if require_valid and not report.valid:
            raise ProblemError(ErrorCode.STATE_TRANSITION_NOT_ALLOWED, "Rule validation failed; inspect a dry-run validation report.")
        return rid

    async def propose(self, actor: AuthenticatedSession, project: UUID | None, *, rule_key: str, definition: dict[str, Any], key: str,
                      level: RuleLevel = RuleLevel.PROJECT, rule_id: UUID | None = None, expected_parent_version: int | None = None) -> RuleMutationResult:
        self._human(actor)
        parsed = parse_definition(definition, FACT_SCHEMA)
        if not isinstance(level, RuleLevel) or (level is RuleLevel.PROJECT and project is None):
            raise ValueError("invalid rule scope")
        async def write(repo: RulesRepository, registry: RuleRegistry, at: datetime, row: dict[str, Any] | None) -> RuleMutationResult:
            parent = rule_id
            expected = expected_parent_version
            if parent is None:
                parent = await repo.create_rule(actor.organization_id, project, rule_key=rule_key, title=rule_key, level=level.name,
                                                created_by=actor.user_id)
                expected = 1
            else:
                parent_row = await repo.get_rule(parent)
                if parent_row["level"] != level.name or parent_row["project_id"] != project or parent_row["rule_key"] != rule_key:
                    raise _not_found()
                if type(expected) is not int or expected < 1:
                    raise ProblemError(ErrorCode.PRECONDITION_REQUIRED, "The expected parent version is required.")
            raw = await repo.create_version(parent, expected, condition=parsed.condition.to_dict(),
                                             action={"schemaVersion": "1.0", "effects": [e.to_dict() for e in parsed.effects]},
                                             applicability={}, author_type="USER", author_id=actor.user_id)
            return RuleMutationResult(registry.snapshot_from_row(raw), int(raw["parent_row_version"]))
        return await self._mutate(actor, project, "propose", key, {"level": level.name, "ruleKey": rule_key, "definition": parsed.to_dict(),
                                                                   "ruleRef": None if rule_id is None else str(rule_id), "expectedVersion": expected_parent_version}, write, level=level)

    async def _transition(self, actor: AuthenticatedSession, project: UUID | None, version_id: UUID, *, expected_parent_version: int,
                          expected_hash: str, key: str, operation: str, valid_from: datetime | None = None, valid_to: datetime | None = None) -> RuleMutationResult:
        async def write(repo: RulesRepository, registry: RuleRegistry, at: datetime, row: dict[str, Any] | None) -> RuleMutationResult:
            if row is None:
                raise _not_found()
            rule = registry.snapshot_from_row(row)
            if rule.content_hash != expected_hash:
                raise ProblemError(ErrorCode.VERSION_CONFLICT, "The rule content changed.")
            validation = None
            if operation in {"validate", "submit", "approve", "publish"}:
                validation = await self._validation(repo, registry, actor, project, rule, at, require_valid=operation != "validate")
            if operation == "validate":
                if row["parent_row_version"] != expected_parent_version:
                    raise ProblemError(ErrorCode.VERSION_CONFLICT, "The resource was modified; reload and retry.")
                number = expected_parent_version
            elif operation == "approve":
                self._approval_binding(actor, rule)
                if valid_from is None:
                    raise ValueError("valid_from is required")
                number = await repo.schedule_approval(version_id, expected_parent_version, approver_user_id=actor.user_id, approved_at=at,
                                                       valid_from=require_utc(valid_from), valid_to=None if valid_to is None else require_utc(valid_to))
            elif operation == "submit":
                number = await repo.submit(version_id, expected_parent_version)
            elif operation == "publish":
                if self._separation is None or rule.approved_by is None or (self._separation and rule.approved_by == rule.author_id):
                    raise ProblemError(ErrorCode.ACCESS_DENIED, "Rule publication authority is not configured.")
                number = await repo.publish(version_id, expected_parent_version, at=at, actor_id=actor.user_id)
            elif operation == "retire":
                number = await repo.retire(version_id, expected_parent_version, at=at, actor_id=actor.user_id)
            elif operation == "suspend":
                number = await repo.suspend(version_id, expected_parent_version, at=at, actor_id=actor.user_id)
            elif operation == "resume":
                number = await repo.resume(version_id, expected_parent_version, at=at, actor_id=actor.user_id)
            else:
                raise ValueError("unknown rule transition")
            return RuleMutationResult(await registry.get(version_id), number, validation)
        return await self._mutate(actor, project, operation, key, {"versionRef": str(version_id), "expectedVersion": expected_parent_version,
                                  "expectedHash": expected_hash, "validFrom": None if valid_from is None else valid_from.isoformat(),
                                  "validTo": None if valid_to is None else valid_to.isoformat()}, write, version_id=version_id)

    async def validate(self, actor: AuthenticatedSession, project: UUID | None, version_id: UUID, **kwargs: Any) -> RuleMutationResult:
        return await self._transition(actor, project, version_id, operation="validate", **kwargs)

    async def validation_report(self, actor: AuthenticatedSession, project: UUID | None, report_id: UUID) -> ValidationReport:
        self._human(actor)
        async with UnitOfWork(self._factory) as uow:
            await uow.with_tenant(actor.organization_id, project)
            mfa = await self._authority(uow.session, actor, project)
            action = "rules.validate" if project else "rules.organization.validate"
            await self._policy.authorize(self._request(actor, project, action, "RULE" if project else "ORGANIZATION_RULE", report_id, mfa), session=uow.session, conceal=True)
            row = await RulesRepository(uow.session).get_validation(report_id)
            if row["organization_id"] != actor.organization_id or row["project_id"] != project:
                raise _not_found()
            return ValidationReport.from_dict(row["result"])

    async def submit(self, actor: AuthenticatedSession, project: UUID | None, version_id: UUID, **kwargs: Any) -> RuleMutationResult:
        return await self._transition(actor, project, version_id, operation="submit", **kwargs)

    async def approve(self, actor: AuthenticatedSession, project: UUID | None, version_id: UUID, **kwargs: Any) -> RuleMutationResult:
        return await self._transition(actor, project, version_id, operation="approve", **kwargs)

    async def publish(self, actor: AuthenticatedSession, project: UUID | None, version_id: UUID, **kwargs: Any) -> RuleMutationResult:
        return await self._transition(actor, project, version_id, operation="publish", **kwargs)

    async def retire(self, actor: AuthenticatedSession, project: UUID | None, version_id: UUID, **kwargs: Any) -> RuleMutationResult:
        return await self._transition(actor, project, version_id, operation="retire", **kwargs)

    async def suspend(self, actor: AuthenticatedSession, project: UUID | None, version_id: UUID, **kwargs: Any) -> RuleMutationResult:
        return await self._transition(actor, project, version_id, operation="suspend", **kwargs)

    async def resume(self, actor: AuthenticatedSession, project: UUID | None, version_id: UUID, **kwargs: Any) -> RuleMutationResult:
        return await self._transition(actor, project, version_id, operation="resume", **kwargs)

    async def approve_exception(self, actor: AuthenticatedSession, project: UUID, context_version_id: UUID, target_version_id: UUID, *,
                                expected_hash: str, effect_hash: str, permission_version_id: UUID, valid_to: datetime, reason_code: str,
                                risk_refs: tuple[UUID, ...], compensation_refs: tuple[UUID, ...], key: str) -> RuleException:
        self._human(actor)
        context = await self._context.retrieve(actor, project, context_version_id)
        # Human-designated evidence must be exact immutable refs in an authorized package.
        allowed = {item.ref.version_id for item in context.manifest.items}
        if not set(risk_refs + compensation_refs) <= allowed:
            raise _not_found()
        return await self._exception_command(actor, project, key, "approve", {
            "contextRef": str(context_version_id), "targetRef": str(target_version_id), "targetHash": expected_hash,
            "effectHash": effect_hash, "permissionRef": str(permission_version_id), "validTo": require_utc(valid_to).isoformat(),
            "reasonCode": reason_code, "riskRefs": [str(x) for x in risk_refs], "compensationRefs": [str(x) for x in compensation_refs]},
            context=context)

    async def revoke_exception(self, actor: AuthenticatedSession, project: UUID, exception_id: UUID, *, key: str) -> RuleException:
        self._human(actor)
        return await self._exception_command(actor, project, key, "revoke", {"exceptionRef": str(exception_id)})

    async def _exception_command(self, actor: AuthenticatedSession, project: UUID, key: str, operation: str,
                                 payload: dict[str, Any], *, context: ContextPackageSnapshot | None = None) -> RuleException:
        try:
            with _tracer.start_as_current_span("rules.exception", record_exception=False, set_status_on_exception=False):
                async with UnitOfWork(self._factory) as uow:
                    await uow.with_tenant(actor.organization_id, project)
                    s = uow.session
                    repo, registry = RulesRepository(s), RuleRegistry(s, FACT_SCHEMA)
                    await repo.lock_registry()
                    mfa = await self._authority(s, actor, project)
                    action = f"rules.exception.{operation}"
                    await self._policy.authorize(self._request(actor, project, action, "RULE", None, mfa), session=s, conceal=True)
                    record = await self._idem.begin(s, organization_id=actor.organization_id, project_id=project, actor_type="USER", actor_id=actor.user_id,
                                                    command=action, key=key, payload=payload)
                    if record.outcome is not IdempotencyOutcome.NEW:
                        if record.outcome is not IdempotencyOutcome.REPLAY or record.response_body_ref is None:
                            raise ProblemError(ErrorCode.AGGREGATE_VERSION_CONFLICT, "Exception command is in progress.")
                        return RuleException.from_dict(record.response_body_ref)
                    at = require_utc(self._clock())
                    if operation == "approve":
                        if context is None:
                            raise ValueError("exception context is required")
                        await self._context.revalidate(s, actor, project, context, mfa=mfa)
                        target = await registry.get(UUID(payload["targetRef"]))
                        self._approval_binding(actor, target)
                        if target.content_hash != payload["targetHash"] or target.scope.level is RuleLevel.SYSTEM:
                            raise ProblemError(ErrorCode.ACCESS_DENIED, "The exception target cannot be overridden.")
                        scope = EvaluationScope(actor.organization_id, project, "CONTEXT_PACKAGE_VERSION", context.version_id, "CONTEXT_ASSESSMENT")
                        result = RuleException(new_id(), target.version_id, target.content_hash, payload["effectHash"], UUID(payload["permissionRef"]), scope,
                            at, require_utc(datetime.fromisoformat(payload["validTo"])), actor.user_id, at, payload["reasonCode"],
                            tuple(UUID(x) for x in payload["riskRefs"]), tuple(UUID(x) for x in payload["compensationRefs"]))
                        evaluated = evaluate_rules(await registry.snapshots(), self._facts(context), scope, at, (result,))
                        if not any(item.exception_id == result.id for item in evaluated.waived):
                            raise ProblemError(ErrorCode.ACCESS_DENIED, "No active higher-level rule permits this exact exception.")
                        await repo.save_exception(result)
                    else:
                        result = await registry.get_exception(UUID(payload["exceptionRef"]))
                        await repo.revoke_exception(result.id, actor_id=actor.user_id, at=at)
                        result = await registry.get_exception(result.id)
                    await SqlAuditWriter(s).write(AuditRecord(action=f"RULE_EXCEPTION_{operation.upper()}", outcome=AuditOutcome.SUCCEEDED,
                        resource_type="RULE_EXCEPTION", resource_id=str(result.id), organization_id=str(actor.organization_id), project_id=str(project),
                        actor_id=str(actor.user_id), request_id=current_request_id(), details={"targetVersionRef": str(result.target_version_id),
                        "targetContentHash": result.target_content_hash, "permissionVersionRef": str(result.permission_version_id)}))
                    await self._idem.complete(s, record, status="COMPLETED", resource_type="RULE_EXCEPTION", resource_id=result.id,
                                              response_status=200, response_body_ref=result.to_dict())
                _counter.add(1, {"operation": "exception", "outcome": "success"})
                return result
        except Exception as exc:
            await self._failure_audit(actor, project, "exception", exc)
            raise

    @staticmethod
    def _facts(context: ContextPackageSnapshot) -> FactSnapshot:
        kinds = {item.ref.kind.value for item in context.manifest.items}
        facts = FactSnapshot(uuid5(_FACT_NS, str(context.version_id)), context.version_number, context.version_id,
            (("context_item_count", len(context.manifest.items)), ("context_has_source", "SOURCE_VERSION" in kinds),
             ("context_has_artifact", "ARTIFACT_VERSION" in kinds), ("context_has_requirement", "REQUIREMENT_VERSION" in kinds)), context.content_hash)
        FACT_SCHEMA.validate(facts)
        return facts

    def _evaluation_record(self, row: Mapping[str, Any]) -> RuleEvaluationRecord:
        inputs = row["input_snapshot"]
        if inputs.get("engineVersion") != ENGINE_VERSION or inputs.get("schemaVersion") != "1.0":
            raise ProblemError(ErrorCode.STATE_TRANSITION_NOT_ALLOWED, "Unsupported evaluation version.")
        return RuleEvaluationRecord(row["id"], row["context_version_id"], row["evaluated_at"], canonical_json(inputs), EvaluationResult.from_dict(row["result"]))

    async def evaluate(self, actor: AuthenticatedSession, project: UUID, context_version_id: UUID, *, key: str,
                       previous_evaluation_id: UUID | None = None) -> RuleEvaluationRecord:
        self._human(actor)
        context = await self._context.retrieve(actor, project, context_version_id)
        facts = self._facts(context)
        scope = EvaluationScope(actor.organization_id, project, "CONTEXT_PACKAGE_VERSION", context_version_id, "CONTEXT_ASSESSMENT")
        try:
            with _tracer.start_as_current_span("rules.evaluate", record_exception=False, set_status_on_exception=False):
                async with UnitOfWork(self._factory) as uow:
                    await uow.with_tenant(actor.organization_id, project)
                    s = uow.session
                    repo, registry = RulesRepository(s), RuleRegistry(s, FACT_SCHEMA)
                    await repo.lock_registry()
                    mfa = await self._authority(s, actor, project)
                    await self._policy.authorize(self._request(actor, project, "project.read", "PROJECT", project, mfa), session=s, conceal=True)
                    await self._context.revalidate(s, actor, project, context, mfa=mfa)
                    record = await self._idem.begin(s, organization_id=actor.organization_id, project_id=project, actor_type="USER", actor_id=actor.user_id,
                                                    command="rules.evaluate", key=key, payload={"contextRef": str(context_version_id), "previousRef": None if previous_evaluation_id is None else str(previous_evaluation_id)})
                    if record.outcome is not IdempotencyOutcome.NEW:
                        if record.outcome is not IdempotencyOutcome.REPLAY or record.resource_id is None:
                            raise ProblemError(ErrorCode.AGGREGATE_VERSION_CONFLICT, "Evaluation is in progress.")
                        return self._evaluation_record(await repo.get_evaluation(record.resource_id))
                    if previous_evaluation_id is not None:
                        await repo.get_evaluation(previous_evaluation_id)
                    at = require_utc(self._clock())
                    rules, exceptions = await registry.snapshots(), await registry.exceptions()
                    result = evaluate_rules(rules, facts, scope, at, exceptions)
                    inputs = {"schemaVersion": "1.0", "engineVersion": ENGINE_VERSION, "schema": FACT_SCHEMA.to_dict(), "facts": facts.to_dict(),
                              "scope": scope.to_dict(), "asOf": at.isoformat(), "rules": [r.to_dict() for r in rules], "exceptions": [e.to_dict() for e in exceptions]}
                    eid = await repo.save_evaluation(organization_id=actor.organization_id, project_id=project, context_version_id=context_version_id,
                                                     actor_id=actor.user_id, evaluated_at=at, engine_version=ENGINE_VERSION, schema_version="1.0",
                                                     input_snapshot=inputs, result=result.to_dict(), previous_evaluation_id=previous_evaluation_id)
                    await SqlAuditWriter(s).write(AuditRecord(action="RULES_EVALUATED", outcome=AuditOutcome.SUCCEEDED, resource_type="RULE_EVALUATION", resource_id=str(eid),
                        organization_id=str(actor.organization_id), project_id=str(project), actor_id=str(actor.user_id), request_id=current_request_id(),
                        details={"engineVersion": ENGINE_VERSION, "contextVersionRef": str(context_version_id), "resultCode": result.status.value,
                                 "rulesetHash": canonical_hash([r.to_dict() for r in rules])}))
                    await self._idem.complete(s, record, status="COMPLETED", resource_type="RULE_EVALUATION", resource_id=eid, response_status=201,
                                              response_body_ref={"evaluationRef": str(eid)})
                _counter.add(1, {"operation": "evaluate", "outcome": result.status.value})
                return RuleEvaluationRecord(eid, context_version_id, at, canonical_json(inputs), result)
        except Exception as exc:
            await self._failure_audit(actor, project, "evaluate", exc)
            raise

    async def retrieve(self, actor: AuthenticatedSession, project: UUID, evaluation_id: UUID) -> RuleEvaluationRecord:
        self._human(actor)
        await self._policy.decide(self._request(actor, project, "project.read", "PROJECT", project, actor.mfa_verified_at is not None), conceal=True)
        async with UnitOfWork(self._factory) as uow:
            await uow.with_tenant(actor.organization_id, project)
            mfa = await self._authority(uow.session, actor, project)
            await self._policy.authorize(self._request(actor, project, "project.read", "PROJECT", project, mfa), session=uow.session, conceal=True)
            result = self._evaluation_record(await RulesRepository(uow.session).get_evaluation(evaluation_id))
        await self._context.retrieve(actor, project, result.context_id)
        return result

    async def replay(self, actor: AuthenticatedSession, project: UUID, evaluation_id: UUID) -> EvaluationResult:
        stored = await self.retrieve(actor, project, evaluation_id)
        data = json.loads(stored.input_json)
        schema = FactSchema.from_dict(data["schema"])
        facts = FactSnapshot.from_dict(data["facts"])
        schema.validate(facts)
        result = evaluate_rules(tuple(RuleSnapshot.from_dict(x, schema) for x in data["rules"]), facts, EvaluationScope.from_dict(data["scope"]),
                                require_utc(datetime.fromisoformat(data["asOf"])), tuple(RuleException.from_dict(x) for x in data["exceptions"]))
        if result != stored.result:
            raise ProblemError(ErrorCode.STATE_TRANSITION_NOT_ALLOWED, "Evaluation integrity check failed.")
        _counter.add(1, {"operation": "replay", "outcome": "success"})
        return result
