# ruff: noqa: E501  -- SQL statements stay on one line per clause for review
"""Immutable ReadinessEvaluation + check results (ADR-052). Both are written in ONE call/transaction; the database refuses later additions and any update.
`GateResult` is only an API projection over this table (ADR-023): there is no second table."""
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.db.cas import canonical_json
from ai_res.platform.clock import require_utc
from ai_res.platform.ids import new_id
from ai_res.platform.redaction import assert_no_sensitive_keys


@dataclass(frozen=True)
class NewCheck:
    check_code: str
    result: str
    severity: str
    reason_code: str | None = None
    evidence_refs: Sequence[Any] = ()
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NewEvaluation:
    worker_run_id: UUID
    evaluation_number: int
    evaluation_status: str
    gate_outcome: str | None
    snapshot_hash: bytes
    task_version: int
    worker_definition_version_id: UUID
    context_package_version_id: UUID
    ruleset_version: str
    policy_engine_version: str
    grant_snapshot_ref: Mapping[str, Any]
    tool_allowlist_snapshot: Sequence[Any]
    output_contract_version: str
    budget_profile_version: str
    dependency_snapshot: Mapping[str, Any]
    evaluator_version: str
    evaluated_at: datetime | None
    blockers: Sequence[Any] = ()
    limitations: Sequence[Any] = ()
    evidence_refs: Sequence[Any] = ()
    plan_version_id: UUID | None = None


def _j(value: Any) -> str:
    assert_no_sensitive_keys(value, "readiness")  # snapshots, blockers and check details are immutable and readable by auditors: no secret-looking keys
    return canonical_json(value)


class ReadinessRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def record(self, ev: NewEvaluation, checks: Sequence[NewCheck]) -> UUID:
        check_params = [(c, _j(c.evidence_refs), _j(c.details)) for c in checks]  # every guard runs before the first SQL: a rejected check leaves no half-written evaluation
        eid = new_id()
        await self._s.execute(text(
            "INSERT INTO execution.readiness_evaluations (id, worker_run_id, evaluation_number, evaluation_status, gate_outcome, snapshot_hash, task_version, plan_version_id, "
            "worker_definition_version_id, context_package_version_id, ruleset_version, policy_engine_version, grant_snapshot_ref, tool_allowlist_snapshot, output_contract_version, "
            "budget_profile_version, dependency_snapshot, evaluator_version, blockers, limitations, evidence_refs, evaluated_at) VALUES (:id, :run, :n, :st, :outcome, :hash, :tv, :plan, "
            ":wdv, :cpv, :rules, :pev, CAST(:grants AS jsonb), CAST(:tools AS jsonb), :ocv, :bpv, CAST(:deps AS jsonb), :evv, CAST(:blockers AS jsonb), CAST(:lims AS jsonb), "
            "CAST(:evid AS jsonb), :at)"),
            {"id": eid, "run": ev.worker_run_id, "n": ev.evaluation_number, "st": ev.evaluation_status, "outcome": ev.gate_outcome, "hash": ev.snapshot_hash,
             "tv": ev.task_version, "plan": ev.plan_version_id, "wdv": ev.worker_definition_version_id, "cpv": ev.context_package_version_id, "rules": ev.ruleset_version,
             "pev": ev.policy_engine_version, "grants": _j(ev.grant_snapshot_ref), "tools": _j(ev.tool_allowlist_snapshot), "ocv": ev.output_contract_version,
             "bpv": ev.budget_profile_version, "deps": _j(ev.dependency_snapshot), "evv": ev.evaluator_version, "blockers": _j(ev.blockers), "lims": _j(ev.limitations),
             "evid": _j(ev.evidence_refs), "at": None if ev.evaluated_at is None else require_utc(ev.evaluated_at)})
        for c, evidence_json, details_json in check_params:
            await self._s.execute(text(
                "INSERT INTO execution.readiness_check_results (id, worker_run_id, readiness_evaluation_id, check_code, result, severity, reason_code, evidence_refs, details) "
                "VALUES (:id, :run, :ev, :code, :res, :sev, :reason, CAST(:evid AS jsonb), CAST(:det AS jsonb))"),
                {"id": new_id(), "run": ev.worker_run_id, "ev": eid, "code": c.check_code, "res": c.result, "sev": c.severity, "reason": c.reason_code,
                 "evid": evidence_json, "det": details_json})
        return eid

    async def outcome(self, evaluation_id: UUID) -> tuple[str, str | None] | None:
        r = (await self._s.execute(text("SELECT evaluation_status, gate_outcome FROM execution.readiness_evaluations WHERE id = :id"), {"id": evaluation_id})).first()
        return None if r is None else (r[0], r[1])
