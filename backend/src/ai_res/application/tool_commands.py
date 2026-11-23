"""Atomic execution of trusted local tool commands, with durable replay of exact result refs."""
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.modules.idempotency.repository import IdempotencyOutcome
from ai_res.modules.idempotency.service import IdempotencyService
from ai_res.modules.tools.contracts import JsonObject, ToolCall, ToolDefinition, ToolError, ToolErrorCode, ToolSubject
from ai_res.platform.problems import ErrorCode, ProblemError


@dataclass(frozen=True, slots=True)
class CommandResultRef:
    resource_id: UUID
    version_id: UUID

    def as_json(self) -> JsonObject:
        return {"resourceId": str(self.resource_id), "versionId": str(self.version_id)}


class LocalToolCommand(Protocol):
    """An application command bound to the caller's session. Implementations must use local ports only."""

    async def check_precondition(self, subject: ToolSubject, call: ToolCall, arguments: JsonObject) -> None: ...

    async def apply(self, subject: ToolSubject, call: ToolCall, arguments: JsonObject) -> CommandResultRef: ...

    async def verify_result(self, subject: ToolSubject, call: ToolCall, result: CommandResultRef) -> None:
        """Re-read the exact changed version. Must raise if the expected effect is absent."""


class SqlToolWriteExecutor:
    """Bind to the same UnitOfWork as the gateway audit and commit only after gateway completion."""

    def __init__(
        self, session: AsyncSession, idempotency: IdempotencyService, commands: Mapping[str, LocalToolCommand],
    ) -> None:
        self._session, self._idempotency, self._commands = session, idempotency, dict(commands)

    def supports(self, adapter_id: str) -> bool:
        return adapter_id in self._commands

    async def execute(
        self, subject: ToolSubject, call: ToolCall, definition: ToolDefinition, arguments: JsonObject,
        validate_output: Callable[[object], JsonObject], reauthorize: Callable[[], Awaitable[None]],
    ) -> JsonObject:
        command = self._commands.get(definition.adapter_id)
        if command is None:
            raise ToolError(ToolErrorCode.UNAVAILABLE)
        if call.idempotency_key is None:
            raise ToolError(ToolErrorCode.VALIDATION)
        try:
            async with self._session.begin_nested():
                record = await self._idempotency.begin(
                    self._session, organization_id=subject.organization_id, project_id=subject.project_id,
                    actor_type="WORKER_RUN", actor_id=subject.run_id,
                    command=f"tool:{call.ref.tool_id}:{call.ref.version}", key=call.idempotency_key,
                    payload={"grantId": str(call.grant_id), "resourceId": str(call.target.resource_id),
                             "contractVersion": call.contract_version, "operation": call.operation, "input": arguments},
                )
                if record.outcome is IdempotencyOutcome.IN_PROGRESS:
                    raise ToolError(ToolErrorCode.CONFLICT)
                if record.outcome is IdempotencyOutcome.REPLAY:
                    await reauthorize()
                    return validate_output(record.response_body_ref)
                await command.check_precondition(subject, call, arguments)
                await reauthorize()
                result = await command.apply(subject, call, arguments)
                await command.verify_result(subject, call, result)
                output = validate_output(result.as_json())
                await self._idempotency.complete(
                    self._session, record, status="COMPLETED", resource_type=definition.resource_type,
                    resource_id=result.resource_id, response_status=200, response_body_ref=result.as_json(),
                )
                return output
        except ProblemError as error:
            if error.code is ErrorCode.IDEMPOTENCY_KEY_REUSED:
                raise ToolError(ToolErrorCode.CONFLICT) from None
            if error.code is ErrorCode.VALIDATION_ERROR:
                raise ToolError(ToolErrorCode.VALIDATION) from None
            raise
