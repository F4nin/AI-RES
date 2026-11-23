"""PlanVersion dependency and approval rules (Process v1.9 §§6.2–6.3)."""
from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class PlanGraphCode(StrEnum):
    DUPLICATE_ITEM = "DUPLICATE_ITEM"
    MISSING_PREDECESSOR = "MISSING_PREDECESSOR"
    INVALID_ENTRY = "INVALID_ENTRY"
    CYCLE = "CYCLE"
    UNREACHABLE_ITEM = "UNREACHABLE_ITEM"
    INVALID_APPROVED_SET = "INVALID_APPROVED_SET"
    UNAPPROVED_PREDECESSOR = "UNAPPROVED_PREDECESSOR"


class PlanGraphError(ValueError):
    def __init__(self, code: PlanGraphCode) -> None:
        super().__init__(code.value)
        self.code = code


@dataclass(frozen=True, slots=True)
class PlanDependency:
    item: UUID
    predecessors: frozenset[UUID] = frozenset()


@dataclass(frozen=True, slots=True)
class PlanGraph:
    items: tuple[PlanDependency, ...]
    entries: frozenset[UUID]

    def order(self) -> tuple[UUID, ...]:
        by_id = {item.item: item.predecessors for item in self.items}
        if len(by_id) != len(self.items):
            raise PlanGraphError(PlanGraphCode.DUPLICATE_ITEM)
        successors: dict[UUID, list[UUID]] = {item: [] for item in by_id}
        remaining = {item: len(dependencies) for item, dependencies in by_id.items()}
        for item, predecessors in by_id.items():
            for predecessor in predecessors:
                if predecessor not in by_id:
                    raise PlanGraphError(PlanGraphCode.MISSING_PREDECESSOR)
                successors[predecessor].append(item)

        roots = frozenset(item for item, count in remaining.items() if count == 0)
        if not self.entries <= roots:
            raise PlanGraphError(PlanGraphCode.INVALID_ENTRY)
        ready = deque(sorted(roots))
        ordered: list[UUID] = []
        while ready:
            item = ready.popleft()
            ordered.append(item)
            for successor in sorted(successors[item]):
                remaining[successor] -= 1
                if remaining[successor] == 0:
                    ready.append(successor)
        if len(ordered) != len(by_id):
            raise PlanGraphError(PlanGraphCode.CYCLE)
        if self.entries != roots or not roots:
            raise PlanGraphError(PlanGraphCode.UNREACHABLE_ITEM)
        return tuple(ordered)

    def validate_approval(self, approved: frozenset[UUID], *, completed: frozenset[UUID] = frozenset()) -> None:
        ids = frozenset(self.order())
        if not approved or not approved <= ids or not completed <= ids:
            raise PlanGraphError(PlanGraphCode.INVALID_APPROVED_SET)
        available = approved | completed
        if any(item.item in approved and not item.predecessors <= available for item in self.items):
            raise PlanGraphError(PlanGraphCode.UNAPPROVED_PREDECESSOR)

    def ready(self, approved: frozenset[UUID], completed: frozenset[UUID]) -> tuple[UUID, ...]:
        self.validate_approval(approved, completed=completed)
        return tuple(sorted(item.item for item in self.items
                            if item.item in approved - completed and item.predecessors <= completed))
