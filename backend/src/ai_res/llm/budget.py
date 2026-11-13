# ruff: noqa: E501  -- long prose lines in the module docstring
"""Budget enforcement OUTSIDE the model (DOC-076 §5, Security v1.2, ADR-108): a model can neither raise nor ignore its own budget.

The ledger reserves the worst case BEFORE a provider call and settles with the provider-reported usage afterwards. A call without an established budget is refused
(fail closed). Exhaustion is a typed, non-retryable error: another attempt cannot create budget.

`InMemoryBudgetLedger` is process-local: it proves the semantics but is NOT durable across restarts and not shared by processes (G-145). The WorkerRun grant that sets
a scope's budget arrives in S22/S23; budget numbers are never invented here.
"""
import asyncio
from dataclasses import dataclass
from decimal import Decimal
from itertools import count
from typing import Protocol

from ai_res.llm.errors import BudgetExhausted, BudgetNotEstablished, BudgetUnenforceable
from ai_res.llm.registry import CostRates


@dataclass(frozen=True, slots=True)
class Budget:
    max_total_tokens: int | None = None
    max_cost: Decimal | None = None
    currency: str | None = None  # required with max_cost

    def __post_init__(self) -> None:
        if self.max_total_tokens is None and self.max_cost is None:
            raise ValueError("a budget limits tokens, cost or both")
        if (self.max_total_tokens is not None and self.max_total_tokens < 0) or (self.max_cost is not None and (self.max_cost < 0 or not self.currency)):
            raise ValueError("budget limits are non-negative and a cost limit names its currency")


@dataclass(frozen=True, slots=True)
class Reservation:
    scope: str
    token: int
    tokens: int
    cost: Decimal


class BudgetLedgerPort(Protocol):
    async def reserve(self, scope: str, *, tokens: int, cost: Decimal | None, currency: str | None) -> Reservation:
        """Hold the worst case or raise BudgetNotEstablished / BudgetExhausted / BudgetUnenforceable."""

    async def settle(self, reservation: Reservation, *, tokens: int, cost: Decimal | None) -> None: ...

    async def release(self, reservation: Reservation) -> None:
        """Give a reservation back when no usage is known to have occurred."""


@dataclass(slots=True)
class _Account:
    budget: Budget
    used_tokens: int = 0
    used_cost: Decimal = Decimal(0)
    held_tokens: int = 0
    held_cost: Decimal = Decimal(0)


class InMemoryBudgetLedger:
    def __init__(self) -> None:
        self._accounts: dict[str, _Account] = {}
        self._ids = count(1)
        self._open: set[int] = set()
        self._lock = asyncio.Lock()

    def establish(self, scope: str, budget: Budget) -> None:
        """Called by the trusted platform (never by a caller of the gateway). Re-establishing a scope is refused: a budget is not silently reset."""
        if scope in self._accounts:
            raise ValueError("budget scope already established")
        self._accounts[scope] = _Account(budget)

    def usage(self, scope: str) -> tuple[int, Decimal]:
        a = self._accounts[scope]
        return a.used_tokens, a.used_cost

    async def reserve(self, scope: str, *, tokens: int, cost: Decimal | None, currency: str | None) -> Reservation:
        async with self._lock:
            account = self._accounts.get(scope)
            if account is None:
                raise BudgetNotEstablished("no budget is established for this scope")
            b = account.budget
            if b.max_total_tokens is not None and account.used_tokens + account.held_tokens + tokens > b.max_total_tokens:
                raise BudgetExhausted("token budget exhausted")
            hold = Decimal(0)
            if b.max_cost is not None:
                if cost is None or currency != b.currency:
                    raise BudgetUnenforceable("a cost budget needs the profile's cost rates in the same currency")
                if account.used_cost + account.held_cost + cost > b.max_cost:
                    raise BudgetExhausted("cost budget exhausted")
                hold = cost
            account.held_tokens += tokens
            account.held_cost += hold
            rid = next(self._ids)
            self._open.add(rid)
            return Reservation(scope, rid, tokens, hold)

    async def settle(self, reservation: Reservation, *, tokens: int, cost: Decimal | None) -> None:
        async with self._lock:
            account = self._release_hold(reservation)
            account.used_tokens += tokens  # actual usage is charged even when it exceeds the hold: the next reserve then refuses
            account.used_cost += cost if cost is not None else Decimal(0)

    async def release(self, reservation: Reservation) -> None:
        async with self._lock:
            self._release_hold(reservation)

    def _release_hold(self, reservation: Reservation) -> _Account:
        if reservation.token not in self._open:
            raise ValueError("reservation already settled or unknown")
        self._open.discard(reservation.token)
        account = self._accounts[reservation.scope]
        account.held_tokens -= reservation.tokens
        account.held_cost -= reservation.cost
        return account


def worst_case_cost(rates: CostRates | None, input_tokens: int, max_output_tokens: int) -> Decimal | None:
    return None if rates is None else rates.cost(input_tokens, max_output_tokens)
