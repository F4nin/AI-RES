"""Outbound prompt guard (DOC-076 §5: redaction before the provider; Security v1.2: no secrets in prompts).

High-confidence credential shapes (private keys, JWTs, URLs with credentials, connection strings, well-known key prefixes) BLOCK the call: such a value means a
secret really reached the context, which is a defect to surface, not to paper over. Low-confidence shapes (`password: x`, `Bearer authentication`) also match
ordinary requirements prose, so they are REDACTED and counted. Neither the value nor the message text ever appears in an error or a log (ADR-105).
"""
from collections.abc import Sequence
from dataclasses import replace

from ai_res.llm.errors import SecretInPrompt
from ai_res.llm.types import Message
from ai_res.platform.redaction import scan_secrets


def guard_text(text: str) -> tuple[str, int]:
    scan = scan_secrets(text)
    if scan.high_confidence_kinds:
        raise SecretInPrompt("a credential-shaped value was found in the prompt input; the call was not sent")
    return scan.redacted, (1 if scan.kinds else 0)


def guard_messages(messages: Sequence[Message]) -> tuple[tuple[Message, ...], int]:
    joined = scan_secrets("".join(m.content for m in messages))
    # a credential cut in the middle by message chunking is whole in the plain concatenation (high confidence only: no false redactions)
    if joined.high_confidence_kinds:
        raise SecretInPrompt("a credential-shaped value was found in the prompt input; the call was not sent")
    out: list[Message] = []
    redactions = 0
    for m in messages:
        text, n = guard_text(m.content)
        redactions += n
        out.append(replace(m, content=text) if n else m)
    return tuple(out), redactions


def guard_inputs(inputs: Sequence[str]) -> tuple[tuple[str, ...], int]:
    pairs = [guard_text(i) for i in inputs]
    return tuple(p[0] for p in pairs), sum(p[1] for p in pairs)
