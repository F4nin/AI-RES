"""Authoritative Rules Registry: complete tenant-visible live snapshots.

No caller-selected rule list or rule IDs determine the basis. Only APPROVED
versions are live; the engine itself applies validity/suspension/scope checks.
Malformed approved legacy definitions fail closed, never become empty rules.
"""
from collections.abc import Mapping
from dataclasses import replace
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.modules.rules.language import parse_definition
from ai_res.modules.rules.repository import RulesRepository
from ai_res.modules.rules.types import FactSchema, RuleException, RuleLevel, RuleScope, RuleSnapshot, RuleStatus, canonical_hash
from ai_res.platform.problems import ErrorCode, ProblemError


class RuleRegistry:
    def __init__(self, session: AsyncSession, schema: FactSchema) -> None:
        if not isinstance(schema, FactSchema):
            raise ValueError("a configured fact schema is required")
        self._repo, self._schema = RulesRepository(session), schema

    def snapshot_from_row(self, row: Mapping[str, Any]) -> RuleSnapshot:
        try:
            applicability = row["applicability"]
            if not isinstance(applicability, dict) or set(applicability) - {"objectType", "objectId", "operation"}:
                raise ValueError("unsupported rule applicability")
            action = row["action"]
            if not isinstance(action, dict) or set(action) != {"schemaVersion", "effects"}:
                raise ValueError("unsupported rule action version")
            definition = parse_definition({"schemaVersion": action["schemaVersion"], "condition": row["condition"], "effects": action["effects"]}, self._schema)
            scope = RuleScope(RuleLevel[row["level"]], row["organization_id"], row["project_id"], applicability.get("objectType"),
                              None if applicability.get("objectId") is None else UUID(applicability["objectId"]), applicability.get("operation"))
            return RuleSnapshot(row["rule_id"], row["id"], int(row["version_number"]), row["rule_key"], scope, definition.condition, definition.effects,
                                RuleStatus(row["status"]), row["author_type"], row["author_id"], row["approver_user_id"], row["approved_at"],
                                row["valid_from"], row["valid_to"],
                                row["suspended"], row["applies_to_object_type"])
        except (KeyError, ValueError, TypeError, AttributeError):
            raise ProblemError(ErrorCode.STATE_TRANSITION_NOT_ALLOWED, "Rule snapshot is unavailable or invalid.") from None

    async def get(self, version_id: UUID) -> RuleSnapshot:
        return self.snapshot_from_row(await self._repo.get_version(version_id))

    async def snapshots(self) -> tuple[RuleSnapshot, ...]:
        return tuple(self.snapshot_from_row(row) for row in await self._repo.version_rows())

    @staticmethod
    def _exception_from_row(row: Mapping[str, Any]) -> RuleException:
        try:
            payload = row["snapshot"]
            parsed = RuleException.from_dict(payload)
            if canonical_hash(payload) != bytes(row["snapshot_hash"]).hex() or parsed.revoked_at is not None:
                raise ValueError("exception snapshot integrity mismatch")
            checks = (
                (parsed.id, row["id"]), (parsed.scope.organization_id, row["organization_id"]), (parsed.scope.project_id, row["project_id"]),
                (parsed.target_version_id, row["target_version_id"]), (parsed.target_content_hash, bytes(row["target_content_hash"]).hex()),
                (parsed.target_effect_hash, bytes(row["target_effect_hash"]).hex()), (parsed.permission_version_id, row["permission_version_id"]),
                (parsed.scope.object_type, row["object_type"]), (parsed.scope.object_id, row["object_id"]), (parsed.scope.operation, row["operation"]),
                (parsed.approved_by, row["approved_by"]), (parsed.approved_at, row["approved_at"]),
                (parsed.valid_from, row["valid_from"]), (parsed.valid_to, row["valid_to"]),
                (parsed.reason_code, row["reason_code"]), (parsed.risk_refs, tuple(row["risk_refs"])),
                (parsed.compensation_refs, tuple(row["compensation_refs"])),
            )
            if any(a != b for a, b in checks):
                raise ValueError("exception columns do not match the immutable snapshot")
            return replace(parsed, revoked_at=row["revoked_at"])
        except (KeyError, ValueError, TypeError, AttributeError):
            raise ProblemError(ErrorCode.STATE_TRANSITION_NOT_ALLOWED, "Rule exception snapshot is unavailable or invalid.") from None

    async def exceptions(self) -> tuple[RuleException, ...]:
        return tuple(self._exception_from_row(row) for row in await self._repo.exception_rows())

    async def get_exception(self, exception_id: UUID) -> RuleException:
        for exception in await self.exceptions():
            if exception.id == exception_id:
                return exception
        raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")
