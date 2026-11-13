# ruff: noqa: E501  -- long prose lines in the module docstring
"""Typed LLM gateway errors (DOC-076 §6, API Contracts v1.10 §11 "normalized error").

Messages are fixed text and never carry prompt content, provider payloads or secret values: an error is safe to log, to put in an audit record and to hand
to the caller. `retryable` says whether repeating the SAME call can succeed (bounded retry applies only then); `fallback_eligible` says whether the failure is
about the provider's availability, so that an explicitly approved fallback profile may be tried. Policy refusals are neither: they are not "fixed" by another model.
"""
from enum import StrEnum

from ai_res.platform.redaction import redact_text


class LLMErrorCode(StrEnum):
    GATEWAY_UNCONFIGURED = "GATEWAY_UNCONFIGURED"
    INVALID_REQUEST = "INVALID_REQUEST"
    MODEL_PROFILE_NOT_FOUND = "MODEL_PROFILE_NOT_FOUND"
    MODEL_PROFILE_NOT_APPROVED = "MODEL_PROFILE_NOT_APPROVED"
    CAPABILITY_NOT_SUPPORTED = "CAPABILITY_NOT_SUPPORTED"
    DATA_CLASSIFICATION_NOT_ALLOWED = "DATA_CLASSIFICATION_NOT_ALLOWED"
    INPUT_EXCEEDS_CONTEXT_WINDOW = "INPUT_EXCEEDS_CONTEXT_WINDOW"
    ROUTE_NOT_FOUND = "ROUTE_NOT_FOUND"
    CREDENTIAL_IN_PROMPT = "CREDENTIAL_IN_PROMPT"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    BUDGET_NOT_ESTABLISHED = "BUDGET_NOT_ESTABLISHED"
    BUDGET_UNENFORCEABLE = "BUDGET_UNENFORCEABLE"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_RATE_LIMITED = "PROVIDER_RATE_LIMITED"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_REJECTED = "PROVIDER_REJECTED"
    INVALID_PROVIDER_OUTPUT = "INVALID_PROVIDER_OUTPUT"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"


class LLMError(Exception):
    code: LLMErrorCode = LLMErrorCode.INVALID_REQUEST
    retryable: bool = False
    fallback_eligible: bool = False

    def __init__(self, detail: str | None = None, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(self.code.value)
        # `detail` may come from a transport: redact secret-shaped text and bound it, so an error is safe to log, trace and return
        self.detail = redact_text(detail)[:300] if detail else self.code.value.replace("_", " ").capitalize()
        self.retry_after_seconds = retry_after_seconds if retry_after_seconds is None or retry_after_seconds >= 0 else None

    def __str__(self) -> str:
        return f"{self.code.value}: {self.detail}"




class GatewayUnconfigured(LLMError):
    code = LLMErrorCode.GATEWAY_UNCONFIGURED


class InvalidRequest(LLMError):
    code = LLMErrorCode.INVALID_REQUEST


class ModelProfileNotFound(LLMError):
    code = LLMErrorCode.MODEL_PROFILE_NOT_FOUND


class ModelProfileNotApproved(LLMError):
    code = LLMErrorCode.MODEL_PROFILE_NOT_APPROVED


class CapabilityNotSupported(LLMError):
    code = LLMErrorCode.CAPABILITY_NOT_SUPPORTED


class DataClassificationNotAllowed(LLMError):
    code = LLMErrorCode.DATA_CLASSIFICATION_NOT_ALLOWED


class InputExceedsContextWindow(LLMError):
    code = LLMErrorCode.INPUT_EXCEEDS_CONTEXT_WINDOW


class RouteNotFound(LLMError):
    code = LLMErrorCode.ROUTE_NOT_FOUND


class SecretInPrompt(LLMError):
    code = LLMErrorCode.CREDENTIAL_IN_PROMPT


class BudgetExhausted(LLMError):
    # never retried: another attempt cannot create budget
    code = LLMErrorCode.BUDGET_EXHAUSTED


class BudgetNotEstablished(LLMError):
    code = LLMErrorCode.BUDGET_NOT_ESTABLISHED


class BudgetUnenforceable(LLMError):
    code = LLMErrorCode.BUDGET_UNENFORCEABLE


class ProviderUnavailable(LLMError):
    code = LLMErrorCode.PROVIDER_UNAVAILABLE
    retryable = True
    fallback_eligible = True


class ProviderRateLimited(LLMError):
    code = LLMErrorCode.PROVIDER_RATE_LIMITED
    retryable = True
    fallback_eligible = True


class ProviderTimeout(LLMError):
    code = LLMErrorCode.PROVIDER_TIMEOUT
    retryable = True
    fallback_eligible = True


class ProviderRejected(LLMError):
    # bad request, authentication, content policy: repeating does not help
    code = LLMErrorCode.PROVIDER_REJECTED


class InvalidProviderOutput(LLMError):
    code = LLMErrorCode.INVALID_PROVIDER_OUTPUT


class CircuitOpen(LLMError):
    code = LLMErrorCode.CIRCUIT_OPEN
    fallback_eligible = True
