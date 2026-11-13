"""Typed, immutable views of the DOC-007 v1.1 contracts (WORKING). The JSON Schema is authoritative; a parity test keeps these field sets equal to it.
Nested objects stay as validated plain data: the schema already checked their shape, and a second hand-written copy of every nested type would only drift."""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _Contract(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=False, extra="forbid", frozen=True)


class WorkerRunEnvelopeModel(_Contract):
    contract_version: str
    worker_run_id: UUID
    organization_id: UUID
    project_id: UUID
    epic_id: UUID
    task_id: UUID
    worker_definition_id: UUID
    worker_role: str
    runtime_profile_version: str | None = None
    plan_version_id: UUID | None = None
    context_package_version_id: UUID
    context_checksum: str
    goal: str
    scope: dict[str, Any]
    constraints: list[str] = []
    assumptions: list[str] = []
    dependency_refs: list[UUID] = []
    input_refs: list[dict[str, Any]] = []
    expected_output_schema: dict[str, Any]
    acceptance_criteria: list[dict[str, Any]]
    allowed_tools: list[dict[str, Any]]
    budget: dict[str, Any] | None = None
    correlation_id: UUID
    traceparent: str | None = None
    attempt: int
    idempotency_key: str
    run_purpose: str
    parent_worker_run_id: UUID | None = None
    coordination_request_id: UUID | None = None
    review_id: UUID | None = None


class WorkerResultModel(_Contract):
    contract_version: str
    worker_run_id: UUID
    task_id: UUID
    worker_role: str
    result_status: str
    summary: str
    outcome: str | None = None
    findings: list[dict[str, Any]]
    proposed_changes: list[dict[str, Any]]
    artifact_refs: list[dict[str, Any]]
    questions: list[str]
    blockers: list[str]
    risks: list[str] = []
    limitations: list[str]
    validation: dict[str, Any]
    tool_execution_refs: list[UUID] = []
    metrics: dict[str, Any] | None = None
    completed_at: datetime


class WorkerNoticeModel(_Contract):
    contract_version: str
    worker_run_id: UUID
    notice_id: UUID
    notice_type: str
    severity: str
    message: str
    evidence_refs: list[dict[str, Any]] = []
    proposed_next_action: str | None = None
    created_at: datetime
    coordination_request: dict[str, Any] | None = None
