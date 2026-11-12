"""Test double of the Platform API port. It is a double of the PORT only (the real HTTP implementation is exercised against the internal API in the postgres
integration tests); it models the platform's idempotency so that Activity retries are observable."""
from collections import Counter

from ai_res.orchestration.contracts import OperationFailure, OperationRef, OperationState
from ai_res.orchestration.platform_port import PlatformPermanentError, PlatformTransientError


class FakePlatform:
    def __init__(self, *, transient_failures: int = 0, permanent: bool = False, cancel_wins_race: bool = False, preset: dict[str, str] | None = None) -> None:
        self.status: dict[str, str] = dict(preset or {})
        self._cancel_wins = cancel_wins_race  # a user cancel lands between the start acknowledgement and the skeleton failure
        self.calls: Counter[str] = Counter()
        self.transitions: list[tuple[str, str]] = []
        self._transient, self._permanent = transient_failures, permanent

    async def acknowledge_start(self, ref: OperationRef) -> OperationState:
        self.calls["ack"] += 1
        if self._permanent:
            raise PlatformPermanentError("denied")
        if self._transient > 0:
            self._transient -= 1
            raise PlatformTransientError("503")
        if self.status.get(ref.operation_id, "ACCEPTED") == "ACCEPTED":
            self.status[ref.operation_id] = "RUNNING"
            self.transitions.append((ref.operation_id, "RUNNING"))
        return OperationState(ref.operation_id, self.status[ref.operation_id])

    async def record_failure(self, failure: OperationFailure) -> OperationState:
        self.calls["fail"] += 1
        oid = failure.operation.operation_id
        if self.status.get(oid) == "RUNNING" and self._cancel_wins:
            self.status[oid] = "CANCEL_REQUESTED"
        elif self.status.get(oid) == "RUNNING":
            self.status[oid] = "FAILED"
            self.transitions.append((oid, "FAILED"))
        return OperationState(oid, self.status[oid])

    async def confirm_cancellation(self, ref: OperationRef) -> OperationState:
        self.calls["confirm_cancel"] += 1
        if self.status.get(ref.operation_id) == "CANCEL_REQUESTED":
            self.status[ref.operation_id] = "CANCELLED"
            self.transitions.append((ref.operation_id, "CANCELLED"))
        return OperationState(ref.operation_id, self.status.get(ref.operation_id, "ACCEPTED"))
