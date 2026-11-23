"""Default-off and exact MCP tool admission."""
from dataclasses import replace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ai_res.modules.tools.contracts import ToolCall, ToolError, ToolErrorCode, ToolRef, ToolTarget
from ai_res.modules.tools.mcp import McpAdapter, McpBinding


@pytest.mark.parametrize("enabled,matching", [(False, True), (True, False)])
async def test_disabled_or_unlisted_mcp_binding_cannot_call_transport(enabled, matching):
    binding = McpBinding(ToolRef("fixture.read", "1.0"), "fixture", "read", "pinned-configuration")
    allowed = binding if matching else replace(binding, server_id="unlisted")
    transport = AsyncMock()
    adapter = McpAdapter(binding, frozenset({allowed}), transport, enabled=enabled)
    call = ToolCall(
        ref=binding.ref, contract_version="1.0", operation="read", grant_id=uuid4(),
        target=ToolTarget(resource_type="PROJECT", resource_id=uuid4(), classification="INTERNAL"),
    )
    with pytest.raises(ToolError) as error:
        await adapter.execute(None, call, {})
    assert error.value.code is ToolErrorCode.AUTHORIZATION
    transport.call.assert_not_called()
