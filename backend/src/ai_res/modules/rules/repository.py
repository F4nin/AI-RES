# ruff: noqa: E501 -- SQL predicates and typed write columns kept together for review
"""Rules-owned persistence. The authorized caller owns the transaction and audit.

Every mutation serializes the tenant's registry before locking an aggregate.
Version allocation uses the parent counter and expected row_version, never MAX.
JSON columns are typed engine snapshots, not alternate mutable domain state.
"""
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.db.cas import canonical_json
from ai_res.modules.rules.engine import ENGINE_VERSION, EvaluationResult, evaluate_rules
from ai_res.modules.rules.types import EvaluationScope, FactSchema, FactSnapshot, RuleException, RuleSnapshot, canonical_hash
from ai_res.modules.rules.validation import ValidationReport, validation_basis_fingerprint
from ai_res.platform.clock import require_utc
from ai_res.platform.ids import new_id
from ai_res.platform.problems import ErrorCode, ProblemError
from ai_res.platform.redaction import assert_no_sensitive_keys, is_sensitive_key

_VERSION_SQL = """
SELECT v.id,v.rule_id,v.level,v.organization_id,v.project_id,v.version_number,v.condition,v.action,v.applicability,v.rationale,
       v.author_type,v.author_id,v.status,v.approver_user_id,v.approved_at,v.valid_from,v.valid_to,
       r.rule_key,r.applies_to_object_type,r.row_version AS parent_row_version,
       coalesce(c.action='SUSPEND',false) AS suspended
FROM governance.rule_versions v JOIN governance.rules r ON r.id=v.rule_id
LEFT JOIN LATERAL (SELECT action FROM governance.rule_runtime_controls c WHERE c.rule_version_id=v.id ORDER BY sequence DESC LIMIT 1) c ON true
"""


def _missing() -> ProblemError:
    return ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")


def _state() -> ProblemError:
    return ProblemError(ErrorCode.STATE_TRANSITION_NOT_ALLOWED, "The rule lifecycle does not permit this action.")


def _payload(value: Mapping[str, Any]) -> str:
    if not isinstance(value, dict):
        value = dict(value)
    assert_no_sensitive_keys(value, "snapshot")
    return canonical_json(value)


def _digest(value: str) -> bytes:
    if not isinstance(value, str) or len(value) != 64 or value.lower() != value:
        raise ValueError("a canonical SHA-256 hash is required")
    try:
        result = bytes.fromhex(value)
    except ValueError:
        raise ValueError("a canonical SHA-256 hash is required") from None
    if len(result) != 32:
        raise ValueError("a canonical SHA-256 hash is required")
    return result


def _evaluation_keys(value: object, path: tuple[str, ...] = ()) -> None:
    """Typed Boolean presence metadata is allowed at its exact fact path only.

    This never edits the persisted snapshot or changes the global detector.
    Names denoting actual source content or any credential remain forbidden.
    """
    if isinstance(value, dict):
        for key, inner in value.items():
            presence = (path == ("facts", "values") and key in {"context_has_source", "context_has_artifact", "context_has_requirement"}
                        and type(inner) is bool)
            if is_sensitive_key(str(key)) and not presence:
                raise ValueError("evaluation snapshot contains a forbidden key")
            _evaluation_keys(inner, (*path, str(key)))
    elif isinstance(value, list):
        for item in value:
            _evaluation_keys(item, (*path, "[]"))


def _validate_evaluation(*, organization_id: UUID, project_id: UUID, context_version_id: UUID, evaluated_at: datetime,
                         engine_version: str, schema_version: str, input_snapshot: dict[str, Any], result: dict[str, Any]) -> None:
    required = {"engineVersion", "schemaVersion", "schema", "scope", "asOf", "facts", "rules", "exceptions"}
    if (not isinstance(input_snapshot, dict) or set(input_snapshot) != required or input_snapshot["engineVersion"] != engine_version
            or engine_version != ENGINE_VERSION or input_snapshot["schemaVersion"] != schema_version):
        raise ValueError("invalid rule evaluation input version or fields")
    schema = FactSchema.from_dict(input_snapshot["schema"])
    facts = FactSnapshot.from_dict(input_snapshot["facts"])
    schema.validate(facts)
    scope = EvaluationScope.from_dict(input_snapshot["scope"])
    if not isinstance(input_snapshot["asOf"], str) or not isinstance(input_snapshot["rules"], list) or not isinstance(input_snapshot["exceptions"], list):
        raise ValueError("invalid rule evaluation input shape")
    at = require_utc(datetime.fromisoformat(input_snapshot["asOf"]))
    if (at != require_utc(evaluated_at) or schema.version != schema_version or facts.context_id != context_version_id
            or facts.provider_version != "context-metadata-v1" or scope.organization_id != organization_id or scope.project_id != project_id
            or scope.object_type != "CONTEXT_PACKAGE_VERSION" or scope.object_id != context_version_id or scope.operation != "CONTEXT_ASSESSMENT"):
        raise ValueError("rule evaluation input scope or provenance mismatch")
    rules = tuple(RuleSnapshot.from_dict(r, schema) for r in input_snapshot["rules"])
    exceptions = tuple(RuleException.from_dict(e) for e in input_snapshot["exceptions"])
    parsed_result = EvaluationResult.from_dict(result)
    if evaluate_rules(rules, facts, scope, at, exceptions) != parsed_result:
        raise ValueError("evaluation result does not reproduce its typed inputs")
    _evaluation_keys(input_snapshot)
    assert_no_sensitive_keys(result, "result")


def _validate_report(proposal_hash: str, basis_hash: str, basis: dict[str, Any], result: dict[str, Any]) -> None:
    parsed = ValidationReport.from_dict(result)
    if not isinstance(basis, dict) or set(basis) != {"schema", "rules"} or not isinstance(basis["rules"], list):
        raise ValueError("invalid rule validation basis shape")
    schema = FactSchema.from_dict(basis["schema"])
    rules = tuple(RuleSnapshot.from_dict(r, schema) for r in basis["rules"])
    if (parsed.proposal_content_hash != proposal_hash or parsed.basis_fingerprint != basis_hash or parsed.schema_content_hash != schema.content_hash
            or validation_basis_fingerprint(schema, rules) != basis_hash):
        raise ValueError("validation report does not match the typed proposal or basis")


class RulesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def lock_registry(self) -> None:
        org = (await self._s.execute(text("SELECT NULLIF(current_setting('app.organization_id',true),'')"))).scalar_one()
        if org is None:
            raise _missing()
        await self._s.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('rules-registry:' || :o,0))"), {"o": org})

    async def get_rule(self, rule_id: UUID) -> dict[str, Any]:
        row = (await self._s.execute(text("SELECT id,level,organization_id,project_id,rule_key,title,applies_to_object_type,created_by,row_version,"
                                          "last_version_number,row_version AS parent_row_version FROM governance.rules WHERE id=:i"),
                                    {"i": rule_id})).mappings().first()
        if row is None:
            raise _missing()
        return dict(row)

    async def get_version(self, version_id: UUID) -> dict[str, Any]:
        row = (await self._s.execute(text(_VERSION_SQL + " WHERE v.id=:v"), {"v": version_id})).mappings().first()
        if row is None:
            raise _missing()
        return dict(row)

    async def version_rows(self, *, all_statuses: bool = False) -> tuple[dict[str, Any], ...]:
        sql = _VERSION_SQL + ("" if all_statuses else " WHERE v.status='APPROVED'") + " ORDER BY v.id"
        return tuple(dict(r) for r in (await self._s.execute(text(sql))).mappings().all())

    async def _parent(self, rule_id: UUID, expected: int) -> dict[str, Any]:
        if type(expected) is not int or expected < 1:
            raise ProblemError(ErrorCode.PRECONDITION_REQUIRED, "A positive expected rule version is required.")
        await self.lock_registry()
        row = (await self._s.execute(text("SELECT id,level,organization_id,project_id,last_version_number,row_version FROM governance.rules WHERE id=:r FOR UPDATE"),
                                    {"r": rule_id})).mappings().first()
        if row is None:
            raise _missing()
        if row["level"] == "SYSTEM":
            raise ProblemError(ErrorCode.ACCESS_DENIED, "System rules are read-only.")
        if row["row_version"] != expected:
            raise ProblemError(ErrorCode.VERSION_CONFLICT, "The resource was modified; reload and retry.")
        return dict(row)

    async def _locked_version(self, version_id: UUID, expected: int) -> dict[str, Any]:
        row = await self.get_version(version_id)
        await self._parent(row["rule_id"], expected)
        return await self.get_version(version_id)

    async def _advance(self, rule_id: UUID, expected: int) -> int:
        row = (await self._s.execute(text("UPDATE governance.rules SET row_version=row_version+1 WHERE id=:r AND row_version=:e RETURNING row_version"),
                                    {"r": rule_id,"e": expected})).first()
        if row is None:
            raise ProblemError(ErrorCode.VERSION_CONFLICT, "The resource was modified; reload and retry.")
        return int(row[0])

    async def create_rule(self, organization_id: UUID, project_id: UUID | None, *, rule_key: str, title: str, level: str, created_by: UUID | None,
                          applies_to_object_type: str | None = None) -> UUID:
        if level not in ("ORGANIZATION", "PROJECT") or (level == "PROJECT") != (project_id is not None):
            raise ValueError("runtime rules require an organization or project scope")
        await self.lock_registry()
        rid = new_id()
        await self._s.execute(text("INSERT INTO governance.rules (id,level,organization_id,project_id,rule_key,title,created_by,applies_to_object_type) "
                                   "VALUES (:i,:l,:o,:p,:k,:t,:a,:ot)"),
                              {"i": rid,"l": level,"o": organization_id,"p": project_id,"k": rule_key,"t": title,"a": created_by,"ot": applies_to_object_type})
        return rid

    async def create_version(self, rule_id: UUID, expected_parent_version: int, *, condition: dict[str, Any], action: dict[str, Any],
                             applicability: dict[str, Any] | None = None, rationale: str | None = None, author_type: str = "USER", author_id: UUID | None = None) -> dict[str, Any]:
        if author_type not in ("USER", "MANAGER", "WORKER_RUN", "IMPORT"):
            raise ValueError("unsupported rule author type")
        condition_json, action_json, applicability_json = _payload(condition), _payload(action), _payload(applicability or {})
        parent = await self._parent(rule_id, expected_parent_version)
        version_id = new_id()
        number = int(parent["last_version_number"]) + 1
        await self._s.execute(text("UPDATE governance.rules SET last_version_number=:n,row_version=row_version+1 WHERE id=:r"), {"n": number,"r": rule_id})
        await self._s.execute(text("INSERT INTO governance.rule_versions (id,rule_id,level,organization_id,project_id,version_number,condition,action,applicability,rationale,author_type,author_id) "
                                   "VALUES (:i,:r,:l,:o,:p,:n,CAST(:c AS jsonb),CAST(:a AS jsonb),CAST(:ap AS jsonb),:ra,:at,:ai)"),
                              {"i": version_id,"r": rule_id,"l": parent["level"],"o": parent["organization_id"],"p": parent["project_id"],"n": number,
                               "c": condition_json,"a": action_json,"ap": applicability_json,"ra": rationale,"at": author_type,"ai": author_id})
        return await self.get_version(version_id)

    async def submit(self, version_id: UUID, expected_parent_version: int) -> int:
        row = await self._locked_version(version_id, expected_parent_version)
        if row["status"] != "DRAFT":
            raise _state()
        await self._s.execute(text("UPDATE governance.rule_versions SET status='PROPOSED' WHERE id=:v"), {"v": version_id})
        return await self._advance(row["rule_id"], expected_parent_version)

    async def schedule_approval(self, version_id: UUID, expected_parent_version: int, *, approver_user_id: UUID, approved_at: datetime,
                                valid_from: datetime, valid_to: datetime | None) -> int:
        row = await self._locked_version(version_id, expected_parent_version)
        if row["status"] != "PROPOSED" or row["approved_at"] is not None:
            raise _state()
        approved_at, valid_from = require_utc(approved_at), require_utc(valid_from)
        if valid_to is not None and require_utc(valid_to) <= valid_from:
            raise ValueError("rule validity must have a positive interval")
        await self._s.execute(text("UPDATE governance.rule_versions SET approver_user_id=:a,approved_at=:t,valid_from=:f,valid_to=:u WHERE id=:v"),
                              {"a": approver_user_id,"t": approved_at,"f": valid_from,"u": valid_to,"v": version_id})
        return await self._advance(row["rule_id"], expected_parent_version)

    async def _control(self, row: Mapping[str, Any], sequence: int, action: str, actor_id: UUID, at: datetime) -> None:
        await self._s.execute(text("INSERT INTO governance.rule_runtime_controls (id,rule_version_id,level,organization_id,project_id,sequence,action,actor_id,occurred_at) "
                                   "VALUES (:i,:v,:l,:o,:p,:n,:a,:by,:at)"),
                              {"i": new_id(),"v": row["id"],"l": row["level"],"o": row["organization_id"],"p": row["project_id"],"n": sequence,
                               "a": action,"by": actor_id,"at": require_utc(at)})

    async def publish(self, version_id: UUID, expected_parent_version: int, *, at: datetime, actor_id: UUID) -> int:
        row = await self._locked_version(version_id, expected_parent_version)
        at = require_utc(at)
        if (row["status"] != "PROPOSED" or row["approved_at"] is None or row["approved_at"] > at or row["valid_from"] > at
                or row["valid_to"] is not None and row["valid_to"] <= at):
            raise _state()
        await self._s.execute(text("UPDATE governance.rule_versions SET status='RETIRED' WHERE rule_id=:r AND status='APPROVED'"), {"r": row["rule_id"]})
        await self._s.execute(text("UPDATE governance.rule_versions SET status='APPROVED' WHERE id=:v"), {"v": version_id})
        rv = await self._advance(row["rule_id"], expected_parent_version)
        await self._control(row, rv, "PUBLISH", actor_id, at)
        return rv

    async def _change_control(self, version_id: UUID, expected_parent_version: int, *, action: str, at: datetime, actor_id: UUID) -> int:
        at = require_utc(at)
        row = await self._locked_version(version_id, expected_parent_version)
        if row["status"] != "APPROVED" or action == "SUSPEND" and row["suspended"] or action == "RESUME" and not row["suspended"]:
            raise _state()
        if action == "RETIRE":
            await self._s.execute(text("UPDATE governance.rule_versions SET status='RETIRED' WHERE id=:v"), {"v": version_id})
        rv = await self._advance(row["rule_id"], expected_parent_version)
        await self._control(row, rv, action, actor_id, at)
        return rv

    async def suspend(self, version_id: UUID, expected_parent_version: int, *, at: datetime, actor_id: UUID) -> int:
        return await self._change_control(version_id, expected_parent_version, action="SUSPEND", at=at, actor_id=actor_id)

    async def resume(self, version_id: UUID, expected_parent_version: int, *, at: datetime, actor_id: UUID) -> int:
        return await self._change_control(version_id, expected_parent_version, action="RESUME", at=at, actor_id=actor_id)

    async def retire(self, version_id: UUID, expected_parent_version: int, *, at: datetime, actor_id: UUID) -> int:
        return await self._change_control(version_id, expected_parent_version, action="RETIRE", at=at, actor_id=actor_id)

    async def reject(self, version_id: UUID, expected_parent_version: int) -> int:
        row = await self._locked_version(version_id, expected_parent_version)
        if row["status"] not in ("DRAFT", "PROPOSED"):
            raise _state()
        await self._s.execute(text("UPDATE governance.rule_versions SET status='REJECTED' WHERE id=:v"), {"v": version_id})
        return await self._advance(row["rule_id"], expected_parent_version)

    async def save_validation(self, *, organization_id: UUID, project_id: UUID | None, proposal_version_id: UUID, proposal_hash: str, basis_hash: str,
                              basis: dict[str, Any], result: dict[str, Any], actor_id: UUID, at: datetime, record_id: UUID | None = None) -> UUID:
        _validate_report(proposal_hash,basis_hash,basis,result)
        vid = record_id or new_id()
        await self._s.execute(text("INSERT INTO governance.rule_validation_reports (id,organization_id,project_id,proposal_version_id,proposal_hash,basis_hash,basis,result,result_hash,actor_id,evaluated_at) "
                                   "VALUES (:i,:o,:p,:v,:ph,:bh,CAST(:b AS jsonb),CAST(:r AS jsonb),:rh,:a,:at)"),
                              {"i": vid,"o": organization_id,"p": project_id,"v": proposal_version_id,"ph": _digest(proposal_hash),"bh": _digest(basis_hash),
                               "b": _payload(basis),"r": _payload(result),"rh": _digest(canonical_hash(result)),"a": actor_id,"at": require_utc(at)})
        return vid

    async def get_validation(self, record_id: UUID) -> dict[str, Any]:
        row = (await self._s.execute(text("SELECT id,organization_id,project_id,proposal_version_id,proposal_hash,basis_hash,basis,result,result_hash,actor_id,evaluated_at "
                                           "FROM governance.rule_validation_reports WHERE id=:i"), {"i": record_id})).mappings().first()
        if row is None:
            raise _missing()
        if _digest(canonical_hash(row["result"])) != bytes(row["result_hash"]):
            raise _state()
        try:
            _validate_report(bytes(row["proposal_hash"]).hex(),bytes(row["basis_hash"]).hex(),row["basis"],row["result"])
        except (KeyError,ValueError,TypeError,AttributeError):
            raise _state() from None
        return dict(row)

    async def save_evaluation(self, *, organization_id: UUID, project_id: UUID, context_version_id: UUID, actor_id: UUID, evaluated_at: datetime,
                              engine_version: str, schema_version: str, input_snapshot: dict[str, Any], result: dict[str, Any],
                              previous_evaluation_id: UUID | None = None, record_id: UUID | None = None) -> UUID:
        _validate_evaluation(organization_id=organization_id,project_id=project_id,context_version_id=context_version_id,evaluated_at=evaluated_at,
                             engine_version=engine_version,schema_version=schema_version,input_snapshot=input_snapshot,result=result)
        eid = record_id or new_id()
        await self._s.execute(text("INSERT INTO governance.rule_evaluations (id,organization_id,project_id,context_version_id,actor_id,evaluated_at,engine_version,schema_version,"
                                   "input_snapshot,input_hash,result,result_hash,previous_evaluation_id) VALUES (:i,:o,:p,:c,:a,:at,:e,:s,CAST(:inp AS jsonb),:ih,CAST(:r AS jsonb),:rh,:prev)"),
                              {"i": eid,"o": organization_id,"p": project_id,"c": context_version_id,"a": actor_id,"at": require_utc(evaluated_at),"e": engine_version,"s": schema_version,
                               "inp": canonical_json(input_snapshot),"ih": _digest(canonical_hash(input_snapshot)),"r": _payload(result),"rh": _digest(canonical_hash(result)),"prev": previous_evaluation_id})
        return eid

    async def get_evaluation(self, evaluation_id: UUID) -> dict[str, Any]:
        row = (await self._s.execute(text("SELECT id,organization_id,project_id,context_version_id,actor_id,evaluated_at,engine_version,schema_version,input_snapshot,input_hash,result,result_hash,previous_evaluation_id "
                                           "FROM governance.rule_evaluations WHERE id=:i"), {"i": evaluation_id})).mappings().first()
        if row is None:
            raise _missing()
        if _digest(canonical_hash(row["input_snapshot"])) != bytes(row["input_hash"]) or _digest(canonical_hash(row["result"])) != bytes(row["result_hash"]):
            raise _state()
        try:
            _validate_evaluation(organization_id=row["organization_id"],project_id=row["project_id"],context_version_id=row["context_version_id"],
                                 evaluated_at=row["evaluated_at"],engine_version=row["engine_version"],schema_version=row["schema_version"],
                                 input_snapshot=row["input_snapshot"],result=row["result"])
        except (KeyError,ValueError,TypeError,AttributeError):
            raise _state() from None
        return dict(row)

    async def save_exception(self, exception: RuleException) -> UUID:
        if not isinstance(exception, RuleException) or exception.revoked_at is not None:
            raise ValueError("a new exception must be an unrevoked typed snapshot")
        await self.lock_registry()
        e, scope = exception, exception.scope
        payload = e.to_dict()
        await self._s.execute(text("INSERT INTO governance.rule_exceptions (id,organization_id,project_id,target_version_id,target_content_hash,target_effect_hash,permission_version_id,"
                                   "object_type,object_id,operation,approved_by,approved_at,valid_from,valid_to,reason_code,risk_refs,compensation_refs,snapshot,snapshot_hash) "
                                   "VALUES (:i,:o,:p,:tv,:th,:eh,:pv,:ot,:oi,:op,:a,:at,:f,:u,:r,:risk,:comp,CAST(:s AS jsonb),:h)"),
                              {"i": e.id,"o": scope.organization_id,"p": scope.project_id,"tv": e.target_version_id,"th": _digest(e.target_content_hash),"eh": _digest(e.target_effect_hash),
                               "pv": e.permission_version_id,"ot": scope.object_type,"oi": scope.object_id,"op": scope.operation,"a": e.approved_by,"at": e.approved_at,
                               "f": e.valid_from,"u": e.valid_to,"r": e.reason_code,"risk": list(e.risk_refs),"comp": list(e.compensation_refs),"s": _payload(payload),"h": _digest(canonical_hash(payload))})
        return e.id

    async def exception_rows(self) -> tuple[dict[str, Any], ...]:
        rows = (await self._s.execute(text("SELECT e.id,e.organization_id,e.project_id,e.target_version_id,e.target_content_hash,e.target_effect_hash,e.permission_version_id,"
                                            "e.object_type,e.object_id,e.operation,e.approved_by,e.approved_at,e.valid_from,e.valid_to,e.reason_code,e.risk_refs,e.compensation_refs,e.snapshot,e.snapshot_hash,r.revoked_at "
                                            "FROM governance.rule_exceptions e LEFT JOIN governance.rule_exception_revocations r ON r.exception_id=e.id ORDER BY e.id"))).mappings().all()
        return tuple(dict(r) for r in rows)

    async def revoke_exception(self, exception_id: UUID, *, actor_id: UUID, at: datetime) -> UUID:
        await self.lock_registry()
        row = (await self._s.execute(text("SELECT organization_id,project_id,approved_at FROM governance.rule_exceptions WHERE id=:i"), {"i": exception_id})).mappings().first()
        if row is None:
            raise _missing()
        at = require_utc(at)
        if at < row["approved_at"]:
            raise _state()
        existing = (await self._s.execute(text("SELECT id FROM governance.rule_exception_revocations WHERE exception_id=:i"), {"i": exception_id})).first()
        if existing is not None:
            return UUID(str(existing[0]))
        rid = new_id()
        await self._s.execute(text("INSERT INTO governance.rule_exception_revocations (id,organization_id,project_id,exception_id,actor_id,revoked_at) VALUES (:i,:o,:p,:e,:a,:at)"),
                              {"i": rid,"o": row["organization_id"],"p": row["project_id"],"e": exception_id,"a": actor_id,"at": at})
        return rid
