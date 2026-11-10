"""UUIDv7 identifiers (ADR-027). Library generator only; no home-made implementation."""
import uuid

import uuid_utils


def new_id() -> uuid.UUID:
    return uuid.UUID(bytes=uuid_utils.uuid7().bytes)


def is_uuid7(value: uuid.UUID) -> bool:
    return value.version == 7
