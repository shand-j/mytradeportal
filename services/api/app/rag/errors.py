"""Sanitized public boundaries for LLM provider failures."""

from __future__ import annotations

import re
from typing import Any

LLM_AUTH_ERROR = "llm_authentication_failed"
LLM_TIMEOUT = "llm_timeout"
LLM_RATE_LIMIT = "llm_rate_limited"
LLM_CONNECTION = "llm_connection_failed"
LLM_UNAVAILABLE = "llm_unavailable"

PUBLIC_MESSAGES: dict[str, str] = {
    LLM_AUTH_ERROR: "The AI provider is not configured correctly. Please retry later.",
    LLM_TIMEOUT: "The AI service took too long to respond. Your existing data is unchanged; please try again.",
    LLM_RATE_LIMIT: "The AI service is busy. Please wait a moment and try again.",
    LLM_CONNECTION: "The AI service could not be reached. Please try again.",
    LLM_UNAVAILABLE: "The AI service is temporarily unavailable. Please try again.",
}


class LLMProviderError(RuntimeError):
    """Provider failure whose public text is safe and whose private detail is retained."""

    def __init__(self, code: str, provider_detail: str) -> None:
        self.code = code
        self.provider_detail = provider_detail
        super().__init__(PUBLIC_MESSAGES.get(code, PUBLIC_MESSAGES[LLM_UNAVAILABLE]))


def redact_provider_detail(detail: str) -> str:
    text = str(detail)
    text = re.sub(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[REDACTED]", text)
    text = re.sub(
        r"(?i)\b(api[_-]?key|authorization|token|secret|password)\b(\s*[=:]\s*)['\"]?[^'\"\s,;]+",
        r"\1\2[REDACTED]",
        text,
    )
    text = re.sub(r"\b(sk-[A-Za-z0-9_-]{8,})\b", "[REDACTED]", text)
    return text


def classify_llm_error(exc: BaseException) -> str:
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    status_code = getattr(exc, "status_code", None)

    if isinstance(exc, TimeoutError) or "timeout" in name or "timedout" in name:
        return LLM_TIMEOUT
    if status_code in (401, 403) or "authentication" in name or "permissiondenied" in name:
        return LLM_AUTH_ERROR
    if status_code == 429 or "rate" in name or "ratelimit" in name:
        return LLM_RATE_LIMIT
    if (
        isinstance(exc, (ConnectionError, OSError))
        or "connection" in name
        or "connect" in name
        or "api connection" in message
    ):
        return LLM_CONNECTION
    return LLM_UNAVAILABLE


def provider_error_from(exc: BaseException) -> LLMProviderError:
    if isinstance(exc, LLMProviderError):
        return exc
    return LLMProviderError(classify_llm_error(exc), redact_provider_detail(str(exc)))


def public_llm_error(exc: BaseException) -> dict[str, str]:
    provider_error = provider_error_from(exc)
    return {"code": provider_error.code, "reason": str(provider_error)}


def log_llm_provider_error(logger: Any, exc: BaseException, **context: Any) -> None:
    provider_error = provider_error_from(exc)
    logger.error(
        "llm_provider_failure",
        error_code=provider_error.code,
        error_type=type(exc).__name__,
        provider_detail=provider_error.provider_detail,
        **context,
    )
