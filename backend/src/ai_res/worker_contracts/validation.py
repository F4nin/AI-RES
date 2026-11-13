"""Fail-closed validation of Worker contracts in four points (S14, DOC-007 v1.1 WORKING, ADR-021).

Points: ENQUEUE and PRE_EXECUTION check the Envelope; RESULT_RECEIPT and DOWNSTREAM check the Result and the Notice. The order is fixed: an independent JSON
snapshot of the payload (so what is validated is exactly what a caller may store; NaN, lone surrogates and oversize payloads are refused), `contractVersion`
(unknown major or any version other than the implemented one is rejected, never downgraded), JSON Schema, evidence rule, secret-looking values. A violation
carries a machine reason and field paths only — never payload values (they may be secrets or source content).
The schema file is loaded once; a missing or incomplete file is a startup error, never an accept-everything validator."""
import json
import re
import unicodedata
from collections.abc import Iterator, Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

import jsonschema
from opentelemetry import metrics
from pydantic import BaseModel
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from ai_res.platform.redaction import redact_text
from ai_res.worker_contracts.models import WorkerNoticeModel, WorkerResultModel, WorkerRunEnvelopeModel

CONTRACT_VERSION: Final = "1.1"
CONTRACT_STATUS: Final = "WORKING"  # DOC-007 is not BASELINED (Registry v4.1); never present these fields as final
# WORKING (ADR-101): claims that must cite evidence; hypotheses, assumptions and unknowns may stand without it.
EVIDENCE_REQUIRED: Final = frozenset({"FACT", "SOURCE_ASSERTION", "CONCLUSION"})
MAX_ERRORS: Final = 20
MAX_PAYLOAD_BYTES: Final = 1_048_576  # WORKING (ADR-101): a bound against unbounded scanning, not a product limit; large data travels by reference
_REJECTED = metrics.get_meter("ai_res.worker_contracts").create_counter(
    "ai_res.worker_contracts.rejected", description="Worker contract payloads rejected (fail-closed); attributes are machine codes only")


class ValidationPoint(StrEnum):
    ENQUEUE = "ENQUEUE"
    PRE_EXECUTION = "PRE_EXECUTION"
    RESULT_RECEIPT = "RESULT_RECEIPT"
    DOWNSTREAM = "DOWNSTREAM"


class Reason(StrEnum):
    UNSUPPORTED_CONTRACT_VERSION = "UNSUPPORTED_CONTRACT_VERSION"
    SCHEMA_REJECTED = "SCHEMA_REJECTED"
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    FORBIDDEN_CONTENT = "FORBIDDEN_CONTENT"


class ContractViolation(Exception):
    """`errors` are `path: keyword` strings (no values)."""

    def __init__(self, kind: str, point: ValidationPoint, reason: Reason, errors: list[str] | None = None) -> None:
        super().__init__(f"{kind} rejected at {point.value}: {reason.value}")
        self.kind, self.point, self.reason, self.errors = kind, point, reason, errors or []


_DEFS: Final = {"envelope": "WorkerRunEnvelope", "result": "WorkerResult", "notice": "WorkerNotice"}
_POINTS: Final = {"envelope": (ValidationPoint.ENQUEUE, ValidationPoint.PRE_EXECUTION),
                  "result": (ValidationPoint.RESULT_RECEIPT, ValidationPoint.DOWNSTREAM),
                  "notice": (ValidationPoint.RESULT_RECEIPT, ValidationPoint.DOWNSTREAM)}
_MODELS: Final[dict[str, type[BaseModel]]] = {"envelope": WorkerRunEnvelopeModel, "result": WorkerResultModel, "notice": WorkerNoticeModel}


def _leaves(value: Any, path: str = "$") -> Iterator[tuple[str, str]]:
    """(field path, text) of every string in the payload, keys included. Paths hold property names and indexes only, never values."""
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, Mapping):
        for key, inner in value.items():
            yield f"{path}/{key}", str(key)
            yield from _leaves(inner, f"{path}/{key}")
    elif isinstance(value, list):
        for i, inner in enumerate(value):
            yield from _leaves(inner, f"{path}/{i}")


_WINDOW, _STEP = 8000, 7680  # below redact_text's 8192 cut-off (which would truncate and so always "differ"); 320 chars of overlap


# OD-20 / ADR-104 (owner decision): a secret word followed by a separator and ONE short plain word is prose about a rule ("Password: min 15 characters"), not a
# credential. Anything else after the separator (digits, symbols, quotes, a long or compound token) still counts as a value. The separator of such a descriptive
# pair is neutralised before the shared `redact_text` patterns run, so every other pattern (Bearer, JWT, PEM, URLs with credentials, known token formats) keeps
# working on the rest of the text. Accepted risk (G-140): `password: tiger` is indistinguishable from prose.
_DESCRIPTIVE_PAIR = re.compile(
    r"(?i)(?<![A-Za-z0-9])[\"']?[A-Za-z0-9_-]{0,32}(?:password|passwd|secret|token|api[-_]?key|authorization)[A-Za-z0-9_-]{0,32}[\"']?\s*([=:])\s*"
    r"(?=[A-Za-z]{1,12}(?![A-Za-z0-9_+/=@.-]))")


def _neutralise_descriptive_pairs(text: str) -> str:
    return _DESCRIPTIVE_PAIR.sub(lambda m: m.group(0).replace(m.group(1), " ", 1), text)


def _looks_secret(text: str) -> bool:
    """Every part of a long string is scanned, in windows that `redact_text` does not truncate: a long benign text is not a false positive and a secret after
    the first 8192 characters is not missed. The text is NFKC-normalised and stripped of format characters (zero-width, bidi) first, so full-width or invisible
    characters do not hide a pattern. Pattern-based and best effort (G-138); descriptive pairs are allowed by the OD-20 compromise (see above)."""
    plain = _neutralise_descriptive_pairs("".join(ch for ch in unicodedata.normalize("NFKC", text) if unicodedata.category(ch) != "Cf"))
    return any(redact_text(window) != window for window in (plain[i:i + _WINDOW] for i in range(0, max(len(plain), 1), _STEP)))


def _snapshot(payload: Any) -> Any:
    """An independent deep copy through JSON, or None when the payload is not strict JSON (NaN/Infinity, non-JSON types, lone surrogates, too large)."""
    try:
        text = json.dumps(payload, allow_nan=False, ensure_ascii=False)
        if len(text.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            return None
        return json.loads(text)
    except (TypeError, ValueError, RecursionError, UnicodeEncodeError):  # UnicodeEncodeError: a lone surrogate cannot be written as UTF-8 (nor stored in jsonb)
        return None


class WorkerContracts:
    def __init__(self, document: Mapping[str, Any]) -> None:
        defs = document.get("$defs", {})
        missing = [name for name in _DEFS.values() if name not in defs]
        if missing or not isinstance(document.get("$id"), str):
            raise ValueError(f"the worker contract schema lacks {', '.join(missing) or '$id'}: refusing to accept every payload")
        registry = Registry().with_resource(document["$id"], Resource.from_contents(dict(document), default_specification=DRAFT202012))
        self._validators = {kind: jsonschema.Draft202012Validator({"$ref": f"{document['$id']}#/$defs/{name}"}, registry=registry,
                                                                  format_checker=jsonschema.FormatChecker()) for kind, name in _DEFS.items()}

    @classmethod
    def from_file(cls, path: Path) -> "WorkerContracts":
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def check(self, kind: str, payload: Any, point: ValidationPoint) -> Any:
        """Returns the typed model of a valid payload; raises ContractViolation otherwise. A wrong kind/point pair is a programming error (ValueError)."""
        return self.check_snapshot(kind, payload, point)[0]

    def check_snapshot(self, kind: str, payload: Any, point: ValidationPoint) -> tuple[Any, dict[str, Any]]:
        """Like `check`, plus the validated JSON snapshot: store THAT, not the caller's object (which may change between the check and the write)."""
        try:
            return self._check(kind, payload, point)
        except ContractViolation as violation:
            _REJECTED.add(1, {"kind": kind, "point": point.value, "reason": violation.reason.value})  # never payload values or ids (security.md)
            raise

    def _check(self, kind: str, payload: Any, point: ValidationPoint) -> tuple[Any, dict[str, Any]]:
        if kind not in _DEFS:
            raise ValueError(f"unknown contract kind {kind!r}")
        if point not in _POINTS[kind]:
            raise ValueError(f"a {kind} is not validated at point {point.value}")
        data = _snapshot(payload)
        if not isinstance(data, dict):
            raise ContractViolation(kind, point, Reason.SCHEMA_REJECTED, ["$: type"])
        if data.get("contractVersion") != CONTRACT_VERSION or not isinstance(data.get("contractVersion"), str):
            raise ContractViolation(kind, point, Reason.UNSUPPORTED_CONTRACT_VERSION)
        errors = sorted(self._validators[kind].iter_errors(data), key=lambda e: [str(p) for p in e.absolute_path])
        if errors:
            raise ContractViolation(kind, point, Reason.SCHEMA_REJECTED,
                                    [f"{'/'.join(str(p) for p in e.absolute_path) or '$'}: {e.validator}" for e in errors[:MAX_ERRORS]])
        if kind == "result":
            self._require_evidence(data, point)
        secret_paths = [f"{path}: forbidden_content" for path, text in _leaves(data) if _looks_secret(text)]
        if secret_paths:
            raise ContractViolation(kind, point, Reason.FORBIDDEN_CONTENT, secret_paths[:MAX_ERRORS])
        return _MODELS[kind].model_validate(data, by_alias=True), data

    @staticmethod
    def _require_evidence(result: Mapping[str, Any], point: ValidationPoint) -> None:
        bad = [f"findings/{i}/evidenceRefs: minItems" for i, f in enumerate(result["findings"])
               if f["classification"] in EVIDENCE_REQUIRED and not f["evidenceRefs"]]
        if bad:
            raise ContractViolation("result", point, Reason.EVIDENCE_MISSING, bad[:MAX_ERRORS])


def load_worker_contracts(schema_file: Path | None) -> WorkerContracts:
    """Startup helper for a process that validates Worker contracts: a missing setting or file stops the process (never an unvalidated Worker path)."""
    if schema_file is None:
        raise ValueError("worker_contract_schema_file is required: Worker payloads are validated against the contract (fail-closed)")
    return WorkerContracts.from_file(schema_file)
