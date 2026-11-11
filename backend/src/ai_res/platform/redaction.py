"""Log redaction (security.md: no passwords, cookies, tokens, prompts, source fragments in telemetry).

Defense in depth: key-based redaction of structured fields and value-pattern redaction of every string leaf (objects are
repr'd and redacted). Reserved log fields cannot be overwritten by `extra` values.
"""
import json
import logging
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

REDACTED = "[REDACTED]"
# Secret-class tokens: sensitive wherever they appear in a key. Content-class tokens (what a payload carries) are sensitive too, unless the key only names a
# reference to it (`source_id`, `SourceVersion`, `body_ref`): identifiers are allowed in logs and events (security.md), the content is not.
_SECRET_TOKENS = frozenset({
    "password", "passwd", "passphrase", "pwd", "secret", "token", "cookie", "authorization", "bearer", "apikey", "csrf", "session", "credential",
    "privatekey", "totp", "otp", "mfa", "seed", "recovery", "dsn", "jwt", "digest", "ciphertext", "hmac", "signature"})
_CONTENT_TOKENS = frozenset({"prompt", "payload", "body", "source", "content", "response", "args"})
_REFERENCE_SUFFIXES = frozenset({"id", "ids", "ref", "refs", "version", "versions", "hash", "code", "type", "uri", "count", "size", "length", "kind"})
_SENSITIVE_PAIRS = frozenset({
    ("api", "key"), ("private", "key"), ("signing", "key"), ("encryption", "key"), ("access", "key"), ("master", "key"), ("shared", "key"),
    ("connection", "string"), ("set", "cookie")})
# Run-together spellings (`accesstoken`, `clientsecret`): long, unambiguous words are also matched as substrings of the key without separators.
_RUN_TOGETHER = ("password", "passwd", "passphrase", "secret", "token", "authorization", "apikey", "privatekey", "credential", "cookie", "bearer")
_EXEMPT_KEYS = frozenset({"content_type", "content_length", "response_time", "response_size"})


def _is_token(part: str, tokens: frozenset[str]) -> bool:
    return part in tokens or (part.endswith("s") and part[:-1] in tokens)  # plural: tokens, secrets, cookies, credentials


def is_sensitive_key(key: str) -> bool:
    """Token-based match (split on non-alphanumerics and camelCase): `resource_id` is not sensitive, `source_text`, `api_key` and `accesstoken` are."""
    norm = re.sub(r"[^a-z0-9]+", "_", re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", key).lower()).strip("_")
    if norm in _EXEMPT_KEYS:
        return False
    parts = norm.split("_")
    if any(_is_token(p, _SECRET_TOKENS) for p in parts) or any(pair in _SENSITIVE_PAIRS for pair in zip(parts, parts[1:], strict=False)):
        return True
    if any(w in norm.replace("_", "") for w in _RUN_TOGETHER):
        return True
    return any(_is_token(p, _CONTENT_TOKENS) for p in parts) and parts[-1] not in _REFERENCE_SUFFIXES


def assert_no_sensitive_keys(value: Any, path: str = "data") -> None:
    """Persisted structured payloads (events, results, refs, snapshots) must not carry secret-looking KEYS: rejected, never silently redacted
    (a mutated payload would be a different record). Key-based only: a secret inside a free-text value is not detected (documented limitation)."""
    if isinstance(value, Mapping):
        for key, inner in value.items():
            if is_sensitive_key(str(key)):
                raise ValueError(f"payload must not contain sensitive key {path}.{key}")
            assert_no_sensitive_keys(inner, f"{path}.{key}")
    elif isinstance(value, list | tuple | set | frozenset):
        for i, inner in enumerate(value):
            assert_no_sensitive_keys(inner, f"{path}[{i}]")


_VALUE_PATTERNS = [
    re.compile(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{6,}"),
    re.compile(r"(?i)\b(ai_res_session|session)=[^;\s]+"),
    re.compile(r"(?i)(?<![A-Za-z0-9])[\"']?[A-Za-z0-9_-]{0,32}(password|passwd|secret|token|api[-_]?key|authorization)[A-Za-z0-9_-]{0,32}[\"']?\s*[=:]\s*"
               r"(\"[^\"]*\"|'[^']*'|[^\s,;]+)"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*"),  # JWT-like
    re.compile(r"(?i)\b[a-z][a-z0-9+.-]{0,15}://[^\s/@:]+:[^\s/@]+@[^\s]+"),  # URL with embedded credentials
    re.compile(r"(?i)\b(postgres(?:ql)?|redis|amqp|mongodb)://[^\s]+"),
    re.compile(r"-----BEGIN [A-Z ]{0,20}PRIVATE KEY-----[\s\S]{0,8192}?(-----END [A-Z ]{0,20}PRIVATE KEY-----|$)"),
    re.compile(r"\b(sk-[A-Za-z0-9]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})\b"),
]


MAX_LOG_TEXT = 8192  # bound regex work on attacker-controlled text (ReDoS); longer text is truncated before matching


def redact_text(text: str) -> str:
    if len(text) > MAX_LOG_TEXT:
        text = text[:MAX_LOG_TEXT] + "...[truncated]"
    for pat in _VALUE_PATTERNS:
        text = pat.sub(REDACTED, text)
    return text


def redact(value: Any, key: str | None = None) -> Any:
    if key is not None and is_sensitive_key(key):
        return REDACTED
    if isinstance(value, dict):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [redact(v) for v in value]
    if isinstance(value, (bytes, bytearray)):
        return REDACTED  # opaque binary is never logged
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return redact_text(value if isinstance(value, str) else _safe_repr(value))


def _safe_repr(value: Any) -> str:
    try:
        return repr(value)
    except Exception:
        return "<unrepresentable>"


_STD_ATTRS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class RedactingJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname, "logger": record.name, "msg": redact_text(record.getMessage()),
        }
        ctx = {k: redact(v, k) for k, v in record.__dict__.items() if k not in _STD_ATTRS}
        if ctx:
            entry["ctx"] = ctx  # extras live under "ctx": they cannot overwrite ts/level/logger/msg
        if record.exc_info and record.exc_info[0]:
            entry["exc_type"] = record.exc_info[0].__name__  # type only: no message, no traceback values
        return json.dumps(entry, default=lambda o: redact_text(_safe_repr(o)), ensure_ascii=False)


class _AccessLogFilter(logging.Filter):
    """uvicorn.access: drop query strings (may carry cursors/tokens) from logged request lines."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) >= 3 and isinstance(record.args[2], str):
            path: str = record.args[2]
            record.args = (*record.args[:2], path.split("?", 1)[0], *record.args[3:])
        return True


def configure_logging(level: str = "INFO", stream: Any = None) -> logging.Logger:
    """Configure ai_res and uvicorn loggers with the redacting formatter (uvicorn's own formatters would log raw text)."""
    handler = logging.StreamHandler(stream)
    handler.setFormatter(RedactingJsonFormatter())
    for name in ("ai_res", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.addHandler(handler)
        lg.setLevel(level)
        lg.propagate = False
    logging.getLogger("uvicorn.access").addFilter(_AccessLogFilter())
    return logging.getLogger("ai_res")
