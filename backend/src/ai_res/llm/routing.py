"""Deterministic routing and fallback policy (DOC-076 §4, Completion Decisions §3.1).

Routing is a pure function of (rules, registry snapshot, route input): the same inputs always give the same profile, and a model never selects its own
route. Rules are DATA supplied by the owner (WORKING, ADR-107); none are built in, so without rules every route is refused.

Fallback is only to a profile of the SAME `fallback_group` that is itself approved, supports every required capability, accepts the data classification and has
equal-or-stricter data handling than the profile it replaces: no higher egress, no region the primary did not allow. A fallback never widens egress, data access
or tool grants, and an outage never reaches an unapproved or public model.
"""
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from ai_res.llm.errors import RouteNotFound
from ai_res.llm.registry import ModelProfile, ModelRegistry
from ai_res.llm.types import Capability


@dataclass(frozen=True, slots=True, kw_only=True)
class RouteInput:
    worker_role: str
    task_class: str
    data_classification: str
    required_capabilities: frozenset[Capability]
    context_tokens: int
    environment: str
    max_output_tokens: int = 1


@dataclass(frozen=True, slots=True, kw_only=True)
class RoutingRule:
    profile_key: str
    worker_role: str | None = None  # None = any
    task_class: str | None = None

    def matches(self, route: RouteInput) -> bool:
        return self.worker_role in (None, route.worker_role) and self.task_class in (None, route.task_class)


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    primary: ModelProfile
    fallbacks: tuple[ModelProfile, ...]


def can_serve(profile: ModelProfile, *, now: datetime, data_classification: str, required: frozenset[Capability], context_tokens: int,
              max_output_tokens: int = 1) -> bool:
    return (profile.usable_at(now) and required <= profile.capabilities and data_classification in profile.data_classifications
            and context_tokens + max_output_tokens <= profile.context_window_tokens and max_output_tokens <= profile.max_output_tokens)


def is_equal_or_stricter(candidate: ModelProfile, primary: ModelProfile) -> bool:
    """The candidate handles data no less strictly than the primary: egress not higher, regions a subset of the primary's."""
    return candidate.egress.rank <= primary.egress.rank and candidate.allowed_regions <= primary.allowed_regions


def fallback_candidates(registry: ModelRegistry, primary: ModelProfile, *, now: datetime, data_classification: str,
                        required: frozenset[Capability], context_tokens: int, max_output_tokens: int = 1) -> tuple[ModelProfile, ...]:
    """Approved, compatible, equal-or-stricter profiles of the primary's fallback group, in a fixed order (profile_key, newest version first)."""
    if primary.fallback_group is None:
        return ()
    return tuple(p for p in registry.all()
                 if p.id != primary.id and p.fallback_group == primary.fallback_group and is_equal_or_stricter(p, primary)
                 and can_serve(p, now=now, data_classification=data_classification, required=required, context_tokens=context_tokens,
                               max_output_tokens=max_output_tokens))


class RoutingPolicy:
    def __init__(self, rules: Sequence[RoutingRule]) -> None:
        self._rules = tuple(rules)

    def route(self, registry: ModelRegistry, route: RouteInput, now: datetime) -> RoutingDecision:
        """First matching rule whose alias has a serving profile wins (newest approved version of the alias); no match -> ROUTE_NOT_FOUND."""
        for rule in self._rules:
            if not rule.matches(route):
                continue
            serving = [p for p in registry.all() if p.profile_key == rule.profile_key
                       and can_serve(p, now=now, data_classification=route.data_classification, required=route.required_capabilities,
                                     context_tokens=route.context_tokens, max_output_tokens=route.max_output_tokens)]
            if serving:
                primary = max(serving, key=lambda p: p.profile_version)
                return RoutingDecision(primary, fallback_candidates(registry, primary, now=now, data_classification=route.data_classification,
                                                                    required=route.required_capabilities, context_tokens=route.context_tokens,
                                                                    max_output_tokens=route.max_output_tokens))
        raise RouteNotFound("no routing rule yields an approved profile for this request")
