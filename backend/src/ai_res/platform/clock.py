"""UTC time and RFC 3339 serialization (coding-standards: timestamps UTC)."""
from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_rfc3339(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("naive datetime is not allowed; use timezone-aware UTC")
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
