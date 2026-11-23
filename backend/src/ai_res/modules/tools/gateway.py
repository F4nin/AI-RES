"""Internal gateway. Application composition supplies authenticated scope and trusted adapters."""
import asyncio
from collections.abc import Awaitable, Callable, Iterable
from time import perf_counter
from typing import Protocol
from uuid import uuid4

from opentelemetry import metrics, trace

from ai_res.modules.tools.contracts import (
    JsonObject,
    SideEffect,
    ToolCall,
    ToolDefinition,
    ToolError,
    ToolErrorCode,
    ToolRef,
    ToolSubject,
    validated_object,
)
from ai_res.modules.tools.registry import ToolRegistry
from ai_res.platform.correlation import current_request_id
from ai_res.platform.export import process_tracer
from ai_res.platform.ports import AuditOutcome, AuditRecord, AuditWriterPort, Effect, PolicyDecision

_tracer = trace.get_tracer("ai_res.tools")
_duration = metrics.get_meter("ai_res.tools").create_histogram("ai_res.tool.gateway.duration", unit="s")


class ToolPolicy(Protocol):
    async def decide(self, subject: ToolSubject, tool: ToolDefinition, call: ToolCall) -> PolicyDecision: ...


class ToolAdapter(Protocol):
    @property
    def available(self) -> bool: ...

    async def execute(self, subject: ToolSubject, call: ToolCall, arguments: JsonObject) -> object:
        """Trusted adapter. Local writes require a transactional precondition, idempotency and verified effect."""


class ToolWriteExecutor(Protocol):
    def supports(self, adapter_id: str) -> bool: ...

    async def execute(
        self, subject: ToolSubject, call: ToolCall, definition: ToolDefinition, arguments: JsonObject,
        validate_output: Callable[[object], JsonObject], reauthorize: Callable[[], Awaitable[None]],
    ) -> JsonObject: ...


class ToolGateway:
    def __init__(
        self, registry: ToolRegistry, policy: ToolPolicy, audit: AuditWriterPort,
        claim_rate: Callable[[ToolSubject, ToolCall, int], Awaitable[bool]],
        adapters: dict[str, ToolAdapter], *, policy_timeout: float, audit_timeout: float,
        writes: ToolWriteExecutor | None = None,
    ) -> None:
        if not (0 < policy_timeout < float("inf") and 0 < audit_timeout < float("inf")):
            raise ValueError("tool control timeouts must be finite and positive")
        self._registry, self._policy, self._audit = registry, policy, audit
        self._claim_rate = claim_rate
        self._adapters = dict(adapters)
        self._writes = writes
        self._policy_timeout, self._audit_timeout = policy_timeout, audit_timeout

    async def _decision(self, subject: ToolSubject, tool: ToolDefinition, call: ToolCall) -> PolicyDecision:
        try:
            async with asyncio.timeout(self._policy_timeout):
                decision = await self._policy.decide(subject, tool, call)
            if not isinstance(decision, PolicyDecision):
                raise TypeError("invalid tool policy decision")
        except Exception:
            raise ToolError(ToolErrorCode.UNAVAILABLE) from None
        return decision

    async def catalogue(self, subject: ToolSubject, candidates: Iterable[ToolCall]) -> tuple[ToolDefinition, ...]:
        """Callers supply backend-derived candidates for the current task. Visibility is not authority."""
        visible: dict[ToolRef, ToolDefinition] = {}
        for call in candidates:
            tool = self._registry.active(call.ref)
            if tool is None or not self._adapter_available(tool.definition):
                continue
            decision = await self._decision(subject, tool.definition, call)
            if decision.effect is Effect.ALLOW:
                visible[call.ref] = tool.definition
        return tuple(visible.values())

    def _adapter_available(self, definition: ToolDefinition) -> bool:
        if definition.side_effect is SideEffect.DOMAIN_WRITE:
            return self._writes is not None and self._writes.supports(definition.adapter_id)
        adapter = self._adapters.get(definition.adapter_id)
        return adapter is not None and adapter.available

    async def invoke(self, subject: ToolSubject, call: ToolCall, arguments: object) -> JsonObject:
        started = perf_counter()
        outcome = "aborted"
        request_id = current_request_id() or str(uuid4())
        tracer = process_tracer("ai_res.tools") or _tracer
        with tracer.start_as_current_span("tool.invoke", record_exception=False, set_status_on_exception=False) as span:
            try:
                result = await self._invoke(subject, call, arguments, started, request_id)
                outcome = "success"
                return result
            except ToolError as error:
                outcome = error.code.value
                raise
            finally:
                span.set_attribute("tool.outcome", outcome)
                _duration.record(perf_counter() - started, {"outcome": outcome})

    async def _invoke(self, subject: ToolSubject, call: ToolCall, arguments: object, started: float, request_id: str) -> JsonObject:
        tool = self._registry.active(call.ref)
        if tool is None:
            await self._record(subject, call, None, None, ToolErrorCode.NOT_FOUND, started, request_id)
            raise ToolError(ToolErrorCode.NOT_FOUND)

        definition = tool.definition
        decision = None
        try:
            snapshot = validated_object(arguments, tool.input_validator, definition.limits.input_bytes,
                                        ToolErrorCode.VALIDATION)
            if definition.side_effect is SideEffect.DOMAIN_WRITE and not call.idempotency_key:
                raise ToolError(ToolErrorCode.VALIDATION)
            decision = await self._decision(subject, definition, call)
            _require_allow(decision)
            if not self._adapter_available(definition):
                raise ToolError(ToolErrorCode.UNAVAILABLE)
            async with asyncio.timeout(definition.limits.timeout_seconds):
                claimed = await self._claim_rate(subject, call, definition.limits.calls_per_minute)
                decision = await self._decision(subject, definition, call)
                _require_allow(decision)
                if not claimed:
                    raise ToolError(ToolErrorCode.RATE_LIMIT)
                await self._record(subject, call, definition, decision, None, started, request_id, intent=True)
                async def reauthorize() -> None:
                    nonlocal decision
                    decision = await self._decision(subject, definition, call)
                    _require_allow(decision)

                def validate_output(value: object) -> JsonObject:
                    return validated_object(value, tool.output_validator, definition.limits.output_bytes,
                                            ToolErrorCode.EXECUTION)

                if definition.side_effect is SideEffect.DOMAIN_WRITE:
                    if self._writes is None:
                        raise ToolError(ToolErrorCode.UNAVAILABLE)
                    validated = await self._writes.execute(subject, call, definition, snapshot, validate_output, reauthorize)
                else:
                    await reauthorize()
                    result = await self._adapters[definition.adapter_id].execute(subject, call, snapshot)
                    validated = validate_output(result)
        except ToolError as error:
            await self._record(subject, call, definition, decision, error.code, started, request_id)
            raise
        except TimeoutError:
            await self._record(subject, call, definition, decision, ToolErrorCode.TIMEOUT, started, request_id)
            raise ToolError(ToolErrorCode.TIMEOUT) from None
        except Exception:
            await self._record(subject, call, definition, decision, ToolErrorCode.EXECUTION, started, request_id)
            raise ToolError(ToolErrorCode.EXECUTION) from None
        await self._record(subject, call, definition, decision, None, started, request_id)
        return validated

    async def _record(
        self, subject: ToolSubject, call: ToolCall, definition: ToolDefinition | None,
        decision: PolicyDecision | None, error: ToolErrorCode | None, started: float, request_id: str, *, intent: bool = False,
    ) -> None:
        if error in {ToolErrorCode.AUTHORIZATION, ToolErrorCode.APPROVAL_REQUIRED}:
            outcome = AuditOutcome.DENIED
        elif error is not None:
            outcome = AuditOutcome.FAILED
        else:
            outcome = AuditOutcome.ALLOWED if intent else AuditOutcome.SUCCEEDED
        # Use registered metadata only. Raw args, returned text, key and dependency exceptions never enter audit.
        details = {
            "epicId": str(subject.epic_id),
            "taskId": str(subject.task_id),
            "environment": subject.environment,
            "durationMs": int((perf_counter() - started) * 1000),
            "effect": None if decision is None else decision.effect.value,
        }
        if definition is not None:
            details.update({"toolId": definition.ref.tool_id, "toolVersion": definition.ref.version,
                            "operation": definition.operation, "sideEffect": definition.side_effect.value})
        try:
            async with asyncio.timeout(self._audit_timeout):
                await self._audit.write(AuditRecord(
                    action="TOOL_CALL_AUTHORIZED" if intent else "TOOL_CALL_FINISHED",
                    outcome=outcome, resource_type="TOOL_GRANT", actor_type="WORKER_RUN",
                    actor_id=str(subject.run_id), resource_id=str(call.grant_id),
                    organization_id=str(subject.organization_id), project_id=str(subject.project_id),
                    reason_code=None if error is None else error.value,
                    policy_version=None if decision is None else decision.policy_version,
                    request_id=request_id, details=details,
                ))
        except Exception:
            raise ToolError(ToolErrorCode.UNAVAILABLE) from None


def _require_allow(decision: PolicyDecision) -> None:
    if decision.effect is Effect.APPROVAL_REQUIRED:
        raise ToolError(ToolErrorCode.APPROVAL_REQUIRED)
    if decision.effect is not Effect.ALLOW:
        raise ToolError(ToolErrorCode.AUTHORIZATION)
