"""Synchronous quick AI check on public quote-request intake.

When the portal submits with ``sync_check=true`` the endpoint awaits ONE
bounded cheap-model call that decides whether a single follow-up question
would materially improve quote accuracy. The full 60-120s draft still runs in
the background; this check only powers the "submitting… quick AI check" view
and the inline guest thread.

Hard guarantees:

* **Never blocks the submission.** The LLM call is wrapped in
  ``asyncio.wait_for`` (``INTAKE_TRIAGE_TIMEOUT_SECONDS``, default 12s) and
  LiteLLM retries are disabled so the budget cannot be blown by backoff.
* **Fail-open always.** Timeout, provider error, missing API key or
  unparseable output all return ``status="unavailable"`` — this function
  never raises.
* **Cheap.** A single call on ``INTAKE_TRIAGE_MODEL`` (default
  ``gpt-4o-mini``, a known model in ``app.ai_pricing`` so spend is costed)
  with a small ``max_tokens`` cap. Bare model ids route to OpenAI with any
  configured non-OpenAI base suppressed (the demo-route idiom); LiteLLM-style
  ``provider/model`` ids route through the configured LLM provider instead.

Every attempt — success, timeout or error — is recorded via
``record_ai_event`` with ``feature="intake_triage"``,
``actor_type="customer"`` and the request's entry channel.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import structlog
from litellm import acompletion
from sqlalchemy.ext.asyncio import AsyncSession

from app import config
from app.ai_telemetry import (
    ACTOR_CUSTOMER,
    STATUS_ERROR,
    STATUS_SUCCESS,
    STATUS_TIMEOUT,
    record_ai_event,
)
from app.config import settings
from app.models import QuoteRequest, Tenant
from app.quote_automation import build_triage_description
from app.rag.generation import (
    _extract_usage,
    _model_allows_custom_temperature,
    _parse_json_response,
)

logger = structlog.get_logger("api.intake_triage")

FEATURE_INTAKE_TRIAGE = "intake_triage"
INTAKE_TRIAGE_PROMPT_VERSION = "intake_triage_v1"
_MAX_QUESTION_CHARS = 240
_MAX_OUTPUT_TOKENS = 300

_SYSTEM_PROMPT = """You are the intake assistant for a UK electrician's quoting system.

Given a customer's job request, decide whether ONE short follow-up question
would MATERIALLY improve the accuracy of a guide-priced quote. Ask only when
a missing detail would change the price or the materials (e.g. number of
rooms, consumer unit location, whether cabling routes are accessible). Do not
ask for anything the customer has already provided, do not ask for contact
details, and never ask more than one question.

Respond with strict JSON only:
{"needs_followup": true, "question": "<one short plain-English question, 20 words max>"}
or
{"needs_followup": false, "question": null}"""


@dataclass
class IntakeCheckResult:
    """Outcome of the quick intake check. ``status`` is one of:

    * ``questions`` — the AI has a follow-up question (``question`` set);
    * ``ok`` — the AI has everything it needs;
    * ``unavailable`` — timeout/error/misconfigured; the caller proceeds as
      if no check ran.
    """

    status: str
    question: str | None = None


def _resolve_route() -> tuple[str, str, str]:
    """Return (model, api_key, api_base) for the cheap intake call."""
    model = config.INTAKE_TRIAGE_MODEL
    if "/" in model:
        # LiteLLM-style "provider/model": the configured provider (e.g. Kimi).
        return model, settings.resolved_llm_api_key, settings.llm_api_base
    # Bare OpenAI-style id: prefer the OpenAI key and suppress any configured
    # non-OpenAI base so a production Kimi base is not inherited (demo idiom).
    return model, settings.openai_api_key or settings.resolved_llm_api_key, ""


def _sanitize_question(value: Any) -> str | None:
    """Keep the model's question short, single-line and bounded."""
    if not isinstance(value, str):
        return None
    question = " ".join(value.split()).strip()
    if not question:
        return None
    return question[:_MAX_QUESTION_CHARS]


async def run_intake_check(
    db: AsyncSession,
    quote_request: QuoteRequest,
    tenant: Tenant,
    entry_channel: str | None = None,
) -> IntakeCheckResult:
    """Run the bounded quick check for a freshly submitted quote request.

    Never raises: every failure mode is recorded in telemetry and reported
    back as ``status="unavailable"``.
    """
    started = time.perf_counter()
    model, api_key, api_base = _resolve_route()

    async def _record(status: str, usage: dict[str, int] | None = None) -> None:
        await record_ai_event(
            db,
            feature=FEATURE_INTAKE_TRIAGE,
            status=status,
            tenant_id=tenant.id,
            actor_type=ACTOR_CUSTOMER,
            entry_channel=entry_channel,
            model=model,
            input_tokens=usage.get("prompt_tokens") if usage else None,
            output_tokens=usage.get("completion_tokens") if usage else None,
            cached_input_tokens=usage.get("cached_tokens") if usage else None,
            latency_seconds=round(time.perf_counter() - started, 4),
            prompt_version=INTAKE_TRIAGE_PROMPT_VERSION,
            quote_request_id=quote_request.id,
        )

    if not api_key:
        logger.warning("intake_triage_unavailable", reason="no_api_key", model=model)
        await _record(STATUS_ERROR)
        return IntakeCheckResult(status="unavailable")

    description = build_triage_description(quote_request)
    completion_kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": description},
        ],
        "api_key": api_key,
        "response_format": {"type": "json_object"},
        "timeout": config.INTAKE_TRIAGE_TIMEOUT_SECONDS,
        # No retries: backoff would blow the hard latency budget the public
        # submission is waiting on.
        "num_retries": 0,
        "max_tokens": _MAX_OUTPUT_TOKENS,
    }
    if _model_allows_custom_temperature(model):
        completion_kwargs["temperature"] = 0
    if api_base:
        completion_kwargs["api_base"] = api_base

    try:
        response = await asyncio.wait_for(
            acompletion(**completion_kwargs),
            timeout=config.INTAKE_TRIAGE_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        logger.warning(
            "intake_triage_timeout",
            model=model,
            timeout_seconds=config.INTAKE_TRIAGE_TIMEOUT_SECONDS,
            quote_request_id=str(quote_request.id),
        )
        await _record(STATUS_TIMEOUT)
        return IntakeCheckResult(status="unavailable")
    except Exception as exc:
        logger.warning(
            "intake_triage_error",
            model=model,
            error_type=type(exc).__name__,
            error=str(exc)[:200],
            quote_request_id=str(quote_request.id),
        )
        await _record(STATUS_ERROR)
        return IntakeCheckResult(status="unavailable")

    usage = _extract_usage(response)
    await _record(STATUS_SUCCESS, usage)

    content = response.choices[0].message.content
    if not content:
        logger.warning("intake_triage_empty", model=model)
        return IntakeCheckResult(status="unavailable")
    parsed = _parse_json_response(content)
    if "needs_followup" not in parsed:
        # _parse_json_response's quote-shaped fallback means the model output
        # was not JSON — treat as a failed check, not as "no question".
        logger.warning("intake_triage_unparseable", model=model, content=content[:200])
        return IntakeCheckResult(status="unavailable")

    question = _sanitize_question(parsed.get("question"))
    if bool(parsed.get("needs_followup")) and question:
        logger.info(
            "intake_triage_question",
            model=model,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            quote_request_id=str(quote_request.id),
        )
        return IntakeCheckResult(status="questions", question=question)
    return IntakeCheckResult(status="ok")
