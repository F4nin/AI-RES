"""Delivery vocabulary shared by the dispatcher and the consumers (Event Model v1.4 §9, §15).

A failure is either transient (the same event is tried again later: bounded retry with backoff) or permanent (the event is quarantined and kept for a
controlled replay, never dropped). The code is a machine code: it is stored and echoed in alerts, so it never carries an exception message.
"""
import re

ERROR_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}")

UNKNOWN_EVENT_TYPE = "UNKNOWN_EVENT_TYPE"
UNKNOWN_MAJOR_VERSION = "UNKNOWN_MAJOR_VERSION"
SCHEMA_REJECTED = "SCHEMA_REJECTED"
FORBIDDEN_CONTENT = "FORBIDDEN_CONTENT"
ENVELOPE_MISMATCH = "ENVELOPE_MISMATCH"
SEQUENCE_REGRESSION = "SEQUENCE_REGRESSION"
SEQUENCE_GAP = "SEQUENCE_GAP"
INBOX_STUCK = "INBOX_STUCK"
INBOX_QUARANTINED = "INBOX_QUARANTINED"
PUBLISH_TIMEOUT = "PUBLISH_TIMEOUT"
PUBLISH_FAILED = "PUBLISH_FAILED"
NO_CONSUMER = "NO_CONSUMER"


class DeliveryError(Exception):
    def __init__(self, code: str) -> None:
        if not ERROR_CODE.fullmatch(code):
            raise ValueError("error code must be an upper-case machine code")
        super().__init__(code)
        self.code = code


class TransientDeliveryError(DeliveryError):
    """Try again later (publisher down, sequence gap, consumer busy). Bounded by the attempt budget."""


class PermanentDeliveryError(DeliveryError):
    """Retrying cannot help (schema mismatch, unknown major version, poison payload): quarantine."""
