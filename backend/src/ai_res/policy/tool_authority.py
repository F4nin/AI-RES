"""Independent, deny-by-default authorization for Worker tools (IAM v1.5 §6)."""
from collections.abc import Callable
from datetime import datetime

from ai_res.modules.tools.contracts import ToolCall, ToolDefinition, ToolSubject
from ai_res.modules.tools.grants import WorkerToolGrantSource
from ai_res.platform.clock import utc_now
from ai_res.platform.ports import Effect, PolicyDecision, ServiceName

POLICY_VERSION = "worker-tool-policy/1.0"


class WorkerToolPolicy:
    def __init__(self, grants: WorkerToolGrantSource, *, clock: Callable[[], datetime] = utc_now) -> None:
        self._grants = grants
        self._clock = clock

    async def decide(self, subject: ToolSubject, tool: ToolDefinition, call: ToolCall) -> PolicyDecision:
        deny = PolicyDecision(effect=Effect.DENY, reason_code="tool_scope_denied", policy_version=POLICY_VERSION)
        if (
            subject.service is not ServiceName.WORKER_RUNTIME
            or subject.identity_expires_at <= self._clock()
            or subject.worker_type not in tool.worker_types
            or subject.environment not in tool.environments
            or call.ref != tool.ref
            or call.contract_version != tool.contract_version
            or call.operation != tool.operation
            or call.target.resource_type != tool.resource_type
            or call.target.classification not in tool.classifications
        ):
            return deny
        grant = await self._grants.get(subject, call.grant_id)
        now = self._clock()
        if (
            grant is None
            or grant.id != call.grant_id
            or grant.revoked_at is not None
            or grant.expires_at <= now
            or subject.identity_expires_at <= now
            or grant.subject != subject
            or grant.tool != call.ref
            or grant.contract_version != call.contract_version
            or grant.operation != call.operation
            or grant.target != call.target
            or grant.permission_scope != tool.required_scope
        ):
            return deny
        effect = Effect.APPROVAL_REQUIRED if tool.requires_human_approval else Effect.ALLOW
        reason = "tool_approval_required" if tool.requires_human_approval else "tool_grant_allowed"
        return PolicyDecision(effect=effect, reason_code=reason, policy_version=POLICY_VERSION)
