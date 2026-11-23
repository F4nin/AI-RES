"""MCP adapter with exact trusted bindings and no discovery."""
from dataclasses import dataclass
from typing import Protocol

from ai_res.modules.tools.contracts import JsonObject, ToolCall, ToolError, ToolErrorCode, ToolRef, ToolSubject


@dataclass(frozen=True, slots=True)
class McpBinding:
    ref: ToolRef
    server_id: str
    tool_name: str
    configuration_digest: str


class McpTransport(Protocol):
    async def call(self, binding: McpBinding, arguments: JsonObject) -> object:
        """Transport with isolated credentials and egress, resolving server_id against pinned configuration."""


class McpAdapter:
    def __init__(
        self, binding: McpBinding, allowlist: frozenset[McpBinding], transport: McpTransport, *, enabled: bool = False,
    ) -> None:
        self._binding, self._allowlist, self._transport = binding, allowlist, transport
        self._enabled = enabled

    @property
    def available(self) -> bool:
        return self._enabled and self._binding in self._allowlist

    async def execute(self, subject: ToolSubject, call: ToolCall, arguments: JsonObject) -> object:
        if not self.available or call.ref != self._binding.ref:
            raise ToolError(ToolErrorCode.AUTHORIZATION)
        return await self._transport.call(self._binding, arguments)
