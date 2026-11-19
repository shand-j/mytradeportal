"""AI-drafted personalised reminder copy for the chase scheduler (F2).

Each due quote/invoice reminder gets a short, warm, personalised message
drafted by the configured LLM, rendered into the static reminder template.
The whole path is fail-open: a missing API key, an LLM error/timeout or a
draft that fails the sanity gate all fall back to the existing static
template — the reminder email still goes out. Every attempt is timed and
recorded through :class:`app.ai_telemetry.AiCallTracker` under
``feature="reminder_draft"`` so cost rollups see the feature independently.

Latency budget: reminder drafting runs inline with an email send, so the
call uses a hard per-call timeout far below the pipeline default and no
retries — a slow provider must never hold up the sweep.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import httpx
import structlog
from litellm import acompletion
from openai import APIError

from app.ai_telemetry import (
    ACTOR_SYSTEM,
    FEATURE_REMINDER_DRAFT,
    AiCallContext,
    AiCallTracker,
)
from app.config import settings
from app.rag.generation import _extract_usage

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger("api.reminder_draft")

# Prompt version recorded on every ai_call_events row; bump when the prompt
# changes materially so quality/cost can be compared across iterations.
REMINDER_DRAFT_PROMPT_VERSION = "reminder-draft.v1"

# Hard latency bound for the inline draft (seconds) — well under the pipeline's
# 180s default, because this call holds up a customer email mid-sweep.
_REMINDER_DRAFT_TIMEOUT_SECONDS = 10
_REMINDER_DRAFT_MAX_TOKENS = 300
# Cheap sanity gate: drafts longer than this, or carrying markdown/placeholder
# artefacts, fall back to the static template.
_MAX_DRAFT_CHARS = 800

SYSTEM_PROMPT = """You write short, friendly reminder emails for a UK trade business.

Rules:
- Write 2-3 warm, professional sentences, in plain text. No markdown, no \
headings, no bullet points, no placeholders like [name] or {{business}}.
- Do not invent prices, dates or promises — only use the facts given.
- Do not be pushy or apologetic; sound like a helpful local tradesperson.
- Output ONLY the reminder message text, nothing else."""


def _build_user_prompt(
    *,
    business_name: str,
    customer_first_name: str | None,
    kind: str,
    document_label: str,
    total: str,
    status_line: str,
) -> str:
    who = customer_first_name or "there"
    lines = [
        f"Business name: {business_name}",
        f"Customer first name: {who}",
        f"Document type: {kind} ({document_label})",
        f"Total: {total}",
        f"Status: {status_line}",
        "",
        f"Draft a short personalised message to {who} reminding them about this "
        f"{kind} from {business_name}. Mention the total naturally. Plain text only.",
    ]
    return "\n".join(lines)


def _passes_sanity_gate(message: str) -> bool:
    """Cheap quality gate: non-empty, bounded, free of markdown/placeholders."""
    text = message.strip()
    if not text or len(text) > _MAX_DRAFT_CHARS:
        return False
    lowered = text.lower()
    if "```" in text or "{{" in text or "[insert" in lowered:
        return False
    return not text.lstrip().startswith(("#", "{", "["))


async def draft_reminder_message(
    db: AsyncSession,
    *,
    tenant_id: UUID | None,
    business_name: str,
    customer_name: str | None,
    kind: str,
    document_label: str,
    total: str,
    status_line: str,
) -> str | None:
    """Draft one personalised reminder message. Returns ``None`` on any failure.

    Fail-open by contract: no API key, provider error/timeout or a sanity-gate
    rejection all return ``None`` and the caller sends the static template
    instead. Telemetry rows (success and failure) are written through
    :class:`AiCallTracker` regardless, so spend rollups stay complete.
    """
    if not settings.resolved_llm_api_key:
        return None

    first_name = None
    if customer_name:
        first_name = customer_name.split()[0] or None

    prompt = _build_user_prompt(
        business_name=business_name,
        customer_first_name=first_name,
        kind=kind,
        document_label=document_label,
        total=total,
        status_line=status_line,
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    completion_kwargs: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
        "api_key": settings.resolved_llm_api_key,
        "timeout": min(settings.llm_timeout_seconds, _REMINDER_DRAFT_TIMEOUT_SECONDS),
        "num_retries": 1,
        "max_tokens": _REMINDER_DRAFT_MAX_TOKENS,
    }
    if settings.llm_temperature is not None and "kimi-k" not in settings.llm_model.lower():
        completion_kwargs["temperature"] = settings.llm_temperature
    if settings.llm_api_base:
        completion_kwargs["api_base"] = settings.llm_api_base

    tracker = AiCallTracker(
        AiCallContext(
            feature=FEATURE_REMINDER_DRAFT,
            db=db,
            tenant_id=tenant_id,
            actor_type=ACTOR_SYSTEM,
        ),
        model=settings.llm_model,
        prompt_version=REMINDER_DRAFT_PROMPT_VERSION,
        prompt_text=prompt,
    )
    try:
        started = time.perf_counter()
        async with tracker:
            response = await acompletion(**completion_kwargs)
            tracker.set_usage(_extract_usage(response))
    except (APIError, httpx.HTTPError, ConnectionError, OSError) as exc:
        logger.warning(
            "reminder_draft_llm_failed",
            model=settings.llm_model,
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
        return None

    content: str | None = response.choices[0].message.content
    if not content or not _passes_sanity_gate(content):
        logger.warning(
            "reminder_draft_rejected",
            model=settings.llm_model,
            reason="empty_or_sanity_gate",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return None

    draft = content.strip()
    logger.info(
        "reminder_draft_generated",
        model=settings.llm_model,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
        prompt_chars=len(prompt),
        draft_chars=len(draft),
    )
    return draft
