"""Builds the gateway for the configured profile (ADR-022, ADR-110). The only module that may load the test double, and only for environment=test."""
import importlib
from collections.abc import Callable
from typing import Any

from ai_res.llm.budget import BudgetLedgerPort
from ai_res.llm.gateway import GatewayPolicy
from ai_res.llm.port import LLMGatewayPort, UnconfiguredLLMGateway
from ai_res.llm.registry import ModelRegistry
from ai_res.llm.types import ContractCatalogPort
from ai_res.platform.config import ConfigError, Settings

_TEST_DOUBLE_MODULE = "ai_res_testkit.deterministic_llm"  # a string, not an import: no static dependency on the test package


def build_llm_gateway(settings: Settings, *, registry: Callable[[], ModelRegistry] | None = None, ledger: BudgetLedgerPort | None = None,
                      catalog: ContractCatalogPort | None = None, **extra: Any) -> LLMGatewayPort:
    """`unconfigured` -> a gateway that refuses every call. `deterministic-test-double` -> only when environment=test (re-checked here although Settings already
    validates it: the factory must not trust that a Settings object was built through validation) and only if the test package is importable."""
    if settings.llm_gateway == "unconfigured":
        return UnconfiguredLLMGateway()
    if settings.llm_gateway == "deterministic-test-double":
        if settings.environment != "test":
            raise ConfigError("deterministic LLM test double is allowed only when environment=test (ADR-022)")
        try:
            module = importlib.import_module(_TEST_DOUBLE_MODULE)
        except ImportError as exc:
            raise ConfigError("the deterministic LLM test double is not available in this image") from exc
        empty = ModelRegistry()
        extra.setdefault("policy", GatewayPolicy.from_settings(settings))
        gateway: LLMGatewayPort = module.DeterministicLLMGateway(settings, registry=registry or (lambda: empty), ledger=ledger, catalog=catalog, **extra)
        return gateway
    raise ConfigError("unknown llm_gateway setting")
