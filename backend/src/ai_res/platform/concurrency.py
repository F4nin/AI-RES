"""ETag / If-Match primitives and the row_version contract (api-and-contracts.md). No database here (S05+)."""
import re
from typing import Protocol

from ai_res.platform.problems import ErrorCode, ProblemError

_ETAG_RE = re.compile(r'^"v([1-9][0-9]{0,17})"$')


class Versioned(Protocol):
    @property
    def row_version(self) -> int: ...


def format_etag(row_version: int) -> str:
    if row_version < 1:
        raise ValueError("row_version starts at 1")
    return f'"v{row_version}"'


def parse_if_match(header: str | None) -> int:
    """Missing -> 428 PRECONDITION_REQUIRED; malformed or wildcard -> 412 VERSION_CONFLICT (no last-write-wins).
    Only strong ETags "v<N>" (N >= 1, no leading zeros) are accepted."""
    if header is None or not header.strip():
        raise ProblemError(ErrorCode.PRECONDITION_REQUIRED, "If-Match header is required.")
    m = _ETAG_RE.match(header.strip())
    if not m:
        raise ProblemError(ErrorCode.VERSION_CONFLICT, "If-Match does not identify a supported version.")
    return int(m.group(1))


def check_if_match(header: str | None, current_row_version: int) -> None:
    if parse_if_match(header) != current_row_version:
        raise ProblemError(ErrorCode.VERSION_CONFLICT, "The resource was modified; reload and retry.")


class AggregateVersionConflict(ProblemError):
    """Storage-level optimistic concurrency failure (expected row_version no longer current)."""

    def __init__(self) -> None:
        super().__init__(ErrorCode.AGGREGATE_VERSION_CONFLICT, "Aggregate version conflict.")
