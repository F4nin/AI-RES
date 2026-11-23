"""Per-call fail-closed behavior independent of PostgreSQL integration."""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ai_res.application.tools import PROJECT_READ, project_tool_registry
from ai_res.modules.tools.contracts import ToolCall, ToolError, ToolErrorCode, ToolLimits, ToolSubject, ToolTarget
from ai_res.modules.tools.gateway import ToolGateway
from ai_res.platform.clock import utc_now
from ai_res.platform.ports import Effect, PolicyDecision, ServiceName


@pytest.fixture
def gateway_case():
    registry = project_tool_registry(ToolLimits(5, 256, 2048, 10), environment="test")
    project = uuid4()
    subject = ToolSubject(
        organization_id=uuid4(), project_id=project, epic_id=uuid4(), task_id=uuid4(), run_id=uuid4(),
        identity_id=uuid4(), worker_definition_version_id=uuid4(), service=ServiceName.WORKER_RUNTIME,
        worker_type="REQUIREMENTS", identity_expires_at=utc_now() + timedelta(minutes=1), environment="test",
    )
    call = ToolCall(
        ref=PROJECT_READ, contract_version="1.0", operation="read", grant_id=uuid4(),
        target=ToolTarget(resource_type="PROJECT", resource_id=project, classification="INTERNAL"),
    )
    policy = SimpleNamespace(decide=AsyncMock(return_value=PolicyDecision(effect=Effect.ALLOW, reason_code="fixture", policy_version="test")))
    audit = SimpleNamespace(write=AsyncMock())
    claim = AsyncMock(return_value=True)
    adapter = SimpleNamespace(available=True, execute=AsyncMock(return_value={
        "projectId": str(project), "name": "example", "projectType": "GREENFIELD", "status": "ACTIVE",
    }))
    gateway = ToolGateway(registry, policy, audit, claim, {PROJECT_READ.tool_id: adapter}, policy_timeout=1, audit_timeout=1)
    return gateway, subject, call, policy, audit, claim, adapter


@pytest.mark.parametrize(("failure", "expected"), [
    ("invalid_input", ToolErrorCode.VALIDATION),
    ("policy_unavailable", ToolErrorCode.UNAVAILABLE),
    ("audit_unavailable", ToolErrorCode.UNAVAILABLE),
    ("approval_required", ToolErrorCode.APPROVAL_REQUIRED),
])
async def test_invalid_or_unapproved_calls_do_not_reach_adapter(gateway_case, failure, expected):
    gateway, subject, call, policy, audit, claim, adapter = gateway_case
    arguments = {}
    if failure == "invalid_input":
        arguments = {"unexpected": "fixture-canary"}
    elif failure == "policy_unavailable":
        policy.decide.side_effect = RuntimeError("fixture-canary")
    elif failure == "audit_unavailable":
        audit.write.side_effect = RuntimeError("fixture-canary")
    else:
        policy.decide.return_value = PolicyDecision(effect=Effect.APPROVAL_REQUIRED, reason_code="fixture", policy_version="test")
    with pytest.raises(ToolError) as error:
        await gateway.invoke(subject, call, arguments)
    assert error.value.code is expected and "fixture-canary" not in str(error.value)
    adapter.execute.assert_not_awaited()
    if failure == "invalid_input":
        claim.assert_not_awaited()


async def test_invalid_output_is_rejected_with_correlated_metadata_only_audit(gateway_case):
    gateway, subject, call, _, audit, _, adapter = gateway_case
    adapter.execute.return_value = {"name": "fixture-canary"}
    with pytest.raises(ToolError) as error:
        await gateway.invoke(subject, call, {})
    assert error.value.code is ToolErrorCode.EXECUTION
    intent, outcome = [attempt.args[0] for attempt in audit.write.await_args_list]
    assert intent.request_id and intent.request_id == outcome.request_id
    assert "fixture-canary" not in repr((intent, outcome))
