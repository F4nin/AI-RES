"""Builds the gateway for the configured profile (ADR-022, ADR-110). The only module that may load the test double, and only for environment=test."""
import importlib
from collections.abc import Callable
from typing import Any

from ai_res.llm.adapters.bifrost import BifrostTransport
from ai_res.llm.admission import ObservedAdmissionPort
from ai_res.llm.budget import BudgetLedgerPort
from ai_res.llm.gateway import GatewayPolicy, GovernedLLMGateway
from ai_res.llm.port import LLMGatewayPort, UnconfiguredLLMGateway
from ai_res.llm.registry import ModelRegistry
from ai_res.llm.types import ContractCatalogPort
from ai_res.platform.config import ConfigError, Settings

_TEST_DOUBLE_MODULE = "ai_res_testkit.deterministic_llm"  # a string, not an import: no static dependency on the test package


def build_llm_gateway(settings: Settings, *, registry: Callable[[], ModelRegistry] | None = None, ledger: BudgetLedgerPort | None = None,
                      catalog: ContractCatalogPort | None = None, transport: BifrostTransport | None = None,
                      admission: ObservedAdmissionPort | None = None, **extra: Any) -> LLMGatewayPort:
    """Default refuses every call. Observed Bifrost needs explicit trusted ports;
    deterministic-test-double needs environment=test and the separate test package.
    Recheck test environment even for Settings objects built without validation.
    """
    if settings.llm_gateway == "unconfigured":
        return UnconfiguredLLMGateway()
    if settings.llm_gateway == "bifrost-observed":
        # Explicit trusted composition only. A setting/credential is not model,
        # Bifrost, caller or budget approval; those authorities remain injected.
        if registry is None or ledger is None or transport is None or admission is None:
            raise ConfigError("observed Bifrost needs an explicit registry, budget ledger, transport and admission authority")
        extra.setdefault("policy", GatewayPolicy.from_settings(settings))
        return GovernedLLMGateway(registry=registry, ledger=ledger, transport=transport, admission=admission, catalog=catalog, **extra)
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
