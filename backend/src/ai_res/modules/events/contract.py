"""Runtime validation of an outbox envelope against the canonical AsyncAPI v1.6 messages (S10; fail-closed).

Every message of the contract whose `type` is a constant is indexed by that type. An envelope is accepted only if its `type` is one of them and its whole
shape validates against that message's schema (`additionalProperties: false`, so an unmodelled attribute is a rejection, not an extension). A type that
names a known event with another major version is `UNKNOWN_MAJOR_VERSION` (quarantine + alert, never a silent downgrade); any other type is
`UNKNOWN_EVENT_TYPE`. Event data must not carry secret- or content-looking keys (the same key rule as `append_event`).
The contract file is loaded once; a missing or malformed file is a startup error, never an empty (accept-everything) registry.
"""
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import jsonschema
import yaml
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from ai_res.modules.events import delivery
from ai_res.modules.events.envelope import event_type_name, subject_for
from ai_res.modules.events.outbox_repository import OutboxRow
from ai_res.platform.redaction import assert_no_sensitive_keys

_TYPE = re.compile(r"^(?P<name>.+)\.v(?P<major>[0-9]+)$")
_BASE = "urn:aires:asyncapi"


class EventContract:
    def __init__(self, document: Mapping[str, Any]) -> None:
        registry = Registry().with_resource(_BASE, Resource.from_contents(dict(document), default_specification=DRAFT202012))
        self._validators: dict[str, jsonschema.Draft202012Validator] = {}
        self._names: dict[str, set[str]] = {}
        for name, message in document.get("components", {}).get("messages", {}).items():
            const = message.get("payload", {}).get("properties", {}).get("type", {}).get("const")
            if not isinstance(const, str) or not (m := _TYPE.match(const)):
                continue
            self._validators[const] = jsonschema.Draft202012Validator(
                {"$ref": f"{_BASE}#/components/messages/{name}/payload"}, registry=registry, format_checker=jsonschema.FormatChecker())
            self._names.setdefault(m["name"], set()).add(m["major"])
        if not self._validators:
            raise ValueError("the event contract defines no canonical message: refusing to accept every event")

    @classmethod
    def from_file(cls, path: Path) -> "EventContract":
        return cls(yaml.safe_load(path.read_text(encoding="utf-8")))

    def check_row(self, row: "OutboxRow") -> None:
        """Contract check plus agreement of the envelope with the row's own columns (defense in depth next to the database trigger): a valid envelope that
        describes another event, type or aggregate is `ENVELOPE_MISMATCH`, never delivered under the row's identity."""
        self.check(row.envelope)
        env = row.envelope
        if (env.get("id") != str(row.event_id) or env.get("type") != event_type_name(row.event_type, row.schema_version, row.aggregate_type)
                or env.get("subject") != subject_for(row.aggregate_type, row.aggregate_id)):
            raise delivery.PermanentDeliveryError(delivery.ENVELOPE_MISMATCH)

    @property
    def event_types(self) -> frozenset[str]:
        return frozenset(self._validators)

    def check(self, envelope: Mapping[str, Any]) -> None:
        """Raises PermanentDeliveryError with a machine code; returns None when the envelope is a valid canonical event."""
        etype = envelope.get("type")
        if not isinstance(etype, str):
            raise delivery.PermanentDeliveryError(delivery.SCHEMA_REJECTED)
        validator = self._validators.get(etype)
        if validator is None:
            m = _TYPE.match(etype)
            known_name = m is not None and m["name"] in self._names
            raise delivery.PermanentDeliveryError(delivery.UNKNOWN_MAJOR_VERSION if known_name else delivery.UNKNOWN_EVENT_TYPE)
        if not validator.is_valid(dict(envelope)):
            raise delivery.PermanentDeliveryError(delivery.SCHEMA_REJECTED)
        try:
            assert_no_sensitive_keys(envelope.get("data", {}))
        except ValueError:
            raise delivery.PermanentDeliveryError(delivery.FORBIDDEN_CONTENT) from None
