"""Trusted deployment definitions, indexed by exact version and isolated from grant state."""
from collections.abc import Iterable
from dataclasses import dataclass

from jsonschema import Draft202012Validator

from ai_res.modules.tools.contracts import ToolDefinition, ToolRef, ToolStatus, compile_schema


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    definition: ToolDefinition
    input_validator: Draft202012Validator
    output_validator: Draft202012Validator


class ToolRegistry:
    def __init__(self, definitions: Iterable[ToolDefinition]) -> None:
        self._tools: dict[ToolRef, RegisteredTool] = {}
        for definition in definitions:
            if definition.ref in self._tools:
                raise ValueError("duplicate tool version")
            self._tools[definition.ref] = RegisteredTool(
                definition,
                compile_schema(definition.input_schema),
                compile_schema(definition.output_schema),
            )

    def active(self, ref: ToolRef) -> RegisteredTool | None:
        tool = self._tools.get(ref)
        if tool is None or tool.definition.status is not ToolStatus.ACTIVE:
            return None
        return tool
