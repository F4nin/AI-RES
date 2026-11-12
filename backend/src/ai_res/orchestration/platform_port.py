"""Port from the runtimes to the domain Application Services (Contracts v1.10 §7.2: internal authenticated Platform API).

Runtimes hold no DB credentials; every domain change goes through these narrow operations. Failures are classified (Process v1.9 §13.1): a TRANSIENT one is
retried by Temporal within a bounded budget, a PERMANENT one (input, permission, integrity) is never retried automatically.
"""
from typing import Protocol

from ai_res.orchestration.contracts import OperationFailure, OperationRef, OperationState


class PlatformTransientError(Exception):
    """Network fault, 5xx, 429 or a retryable conflict: bounded retry is allowed."""


class PlatformPermanentError(Exception):
    """Rejected input, denied permission or integrity mismatch: retrying cannot help (fail closed)."""


class OperationPlatform(Protocol):
    async def acknowledge_start(self, ref: OperationRef) -> OperationState:
        """Idempotent: ACCEPTED -> QUEUED -> RUNNING; an Operation already past that (or terminal / cancel requested) is returned unchanged."""
        ...

    async def confirm_cancellation(self, ref: OperationRef) -> OperationState:
        """Idempotent reconciliation: CANCEL_REQUESTED -> CANCELLED only when no required branch is still active; a terminal fact that already exists wins
        (a completed side effect is never reported as cancelled); anything else is returned unchanged."""
        ...

    async def record_failure(self, failure: OperationFailure) -> OperationState:
        """Idempotent terminal FAILED with a machine code; a different terminal status already recorded is returned, never overwritten."""
        ...
