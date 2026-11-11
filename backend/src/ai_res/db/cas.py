"""Compare-and-swap update by `row_version` (Blueprint §7.1, database-and-migrations.md: stale update -> 409 AGGREGATE_VERSION_CONFLICT).

Column names are interpolated into SQL, so they come ONLY from a caller-owned allowlist (`allowed`: column -> optional cast); values are always bound.
A missing row and an invisible row (other tenant, RLS) are indistinguishable by design: both report RESOURCE_NOT_FOUND (no existence leak).
"""
import json
from collections.abc import Mapping
from typing import Any, NoReturn, cast
from uuid import UUID

from sqlalchemy import CursorResult, Result, text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.platform.concurrency import AggregateVersionConflict
from ai_res.platform.problems import ErrorCode, ProblemError
from ai_res.platform.redaction import assert_no_sensitive_keys

JSONB = "jsonb"


def affected(result: Result[Any]) -> int:
    return int(cast("CursorResult[Any]", result).rowcount)


def canonical_json(value: Any) -> str:
    """The one JSON encoding for jsonb parameters and hashes: sorted, compact, no NaN, no implicit coercion of unknown types."""
    return json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False)


def bind_value(value: Any, sql_cast: str | None) -> Any:
    return canonical_json(value) if sql_cast == JSONB and value is not None else value


def set_clause(changes: Mapping[str, Any], allowed: Mapping[str, str | None], params: dict[str, Any]) -> list[str]:
    parts: list[str] = []
    for column, value in changes.items():
        if column not in allowed:
            raise ValueError(f"column {column!r} is not updatable through this repository")
        sql_cast = allowed[column]
        if sql_cast == JSONB and value is not None:
            assert_no_sensitive_keys(value, column)  # result_ref / problem_ref / snapshots are persisted and visible to other principals
        params[f"v_{column}"] = bind_value(value, sql_cast)
        parts.append(f"{column} = CAST(:v_{column} AS {sql_cast})" if sql_cast else f"{column} = :v_{column}")
    return parts


async def raise_conflict_or_not_found(session: AsyncSession, table: str, row_id: UUID) -> NoReturn:
    exists = (await session.execute(text(f"SELECT 1 FROM {table} WHERE id = :id"), {"id": row_id})).first()  # noqa: S608 - table is a frozen literal of the caller
    if exists is None:
        raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")
    raise AggregateVersionConflict


async def cas_update(session: AsyncSession, table: str, row_id: UUID, expected_version: int, changes: Mapping[str, Any],
                     allowed: Mapping[str, str | None]) -> int:
    """UPDATE ... SET <changes>, row_version = row_version + 1 WHERE id = :id AND row_version = :expected. Returns the new row_version."""
    if not changes:
        raise ValueError("a compare-and-swap update needs at least one change (a bare row_version bump would invalidate other writers' If-Match for nothing)")
    params: dict[str, Any] = {"id": row_id, "expected": expected_version}
    sets = [*set_clause(changes, allowed, params), "row_version = row_version + 1"]
    sql = f"UPDATE {table} SET {', '.join(sets)} WHERE id = :id AND row_version = :expected RETURNING row_version"  # noqa: S608 - table/columns from allowlists
    row = (await session.execute(text(sql), params)).first()
    if row is None:
        await raise_conflict_or_not_found(session, table, row_id)
    return int(row[0])
