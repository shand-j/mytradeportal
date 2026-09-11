"""LLM generation of quote line items from a job description.

Beta "AI quote creation": the model takes an electrician's free text plus any
structured intake and returns guide-priced line items (labour + materials) that
the electrician then reviews and edits. Supplier catalogue prices are provided
as an *optional* reference — they ground material prices when a good match
exists, but the model may price standard labour and common materials from its
own knowledge so a plausible job never comes back empty.

The chat call goes through LiteLLM against any OpenAI-compatible endpoint. To
use Kimi / Moonshot, point ``LLM_API_BASE`` at ``https://api.moonshot.ai/v1``,
set ``LLM_API_KEY`` and use an ``openai/``-prefixed ``LLM_MODEL`` (e.g.
``openai/kimi-k2.6``); no code change is required.
"""

import json
import re
import time
from typing import Any

import httpx
import structlog
from litellm import acompletion
from openai import APIError

from app.config import LLM_COST_PER_1K_TOKENS_USD, settings

logger = structlog.get_logger("api.rag")


def _extract_usage(response: Any) -> dict[str, int] | None:
    """Pull token counts off a LiteLLM response, when the provider reports them."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    prompt_tokens = getattr(usage, "prompt_tokens", None)
    completion_tokens = getattr(usage, "completion_tokens", None)
    if prompt_tokens is None and completion_tokens is None:
        return None
    return {
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
    }


def estimate_llm_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    """Estimate the USD cost of an LLM call from the per-1K-token price map.

    Returns ``None`` when the model is not in the pricing map — the caller
    still records the token counts, just without a cost estimate.
    """
    prices = next(
        (price for key, price in LLM_COST_PER_1K_TOKENS_USD.items() if key in model.lower()),
        None,
    )
    if prices is None:
        return None
    cost = (prompt_tokens * prices["prompt"] + completion_tokens * prices["completion"]) / 1000
    return round(cost, 6)


def _model_allows_custom_temperature(model: str) -> bool:
    """Kimi's kimi-k* models reject any temperature other than the default
    (1.0) with a 400 ``invalid temperature`` — omit the parameter for them
    rather than failing the whole generation."""
    return "kimi-k" not in model.lower()


SYSTEM_PROMPT = """You are an expert UK electrical estimator. Produce a clear, \
itemised GUIDE quote for the job described so a qualified electrician can review \
and adjust it before sending.

Rules:
- Return realistic guide prices in GBP, excluding VAT, for BOTH labour and \
materials. These are estimates the electrician will review and edit.
- Catalogue grounding is MANDATORY. For every MATERIAL line item you must \
decide one of two paths:
    (a) If a catalogue item below is a reasonable match for that material, \
set ``catalogue_ref`` to that item's number (the integer at the start of the \
catalogue line, e.g. ``3``) and use the catalogue's ``unit`` and ``unit_price`` \
(you may add a small markup per the business rules). Close matches on name, \
size, rating, or category count.
    (b) If NO catalogue item is a reasonable match, set ``catalogue_ref`` to \
null AND record why in the line item's ``reason`` field (e.g. \
"no matching catalogue item"). Only take path (b) when path (a) is genuinely \
impossible.
- Labour and callout lines do not need a ``catalogue_ref`` (leave it null).
- ``catalogue_ref`` is ALWAYS a small integer (1, 2, 3, ...) matching a \
catalogue line number — never a code string, never a description, never a URL. \
The server maps this number back to the real product code, so you do not need \
to copy any long code strings.
- Always include the labour required (installation, testing, \
certification/EICR where relevant) as separate line items. Price labour using \
the business hourly labour rate when one is provided; otherwise use a sensible \
UK domestic rate.
- Break the job into sensible line items. Each needs: a short description, a \
"kind" (one of labour, material, callout), a quantity, a unit (each, m, job, \
point, hour) and a unit_price (per-unit, ex-VAT, GBP). For unit "m" the \
unit_price is per metre and the quantity is the exact metreage.
- Prefer between 3 and 12 line items. Do not invent unrelated work. Never return \
an empty quote for a plausible electrical job — if the description is vague, \
return your best-effort minimal draft and record what you assumed.

Respond with valid JSON in exactly this shape:
{
  "line_items": [
    {"description": "Consumer unit replacement (labour)", "kind": "labour", \
"quantity": 4, "unit": "hour", "unit_price": 80.00, "catalogue_ref": null, \
"reason": "brief justification"}
  ],
  "assumptions": ["Any assumptions you made"],
  "notes": "Any warnings or clarifications for the electrician"
}

Units must be real billing units: "hour" or "day" for labour, "ea" for \
individual items, "m" for cable/containment by length, "job" only for a \
genuine fixed-price whole-job line. Never default every line to "job".
"""


def _build_user_prompt(
    job_description: str,
    property_type: str | None,
    cost_items: list[dict[str, Any]],
    tenant_settings: dict[str, Any],
    site_survey: dict[str, Any] | None = None,
    knowledge_chunks: list[dict[str, Any]] | None = None,
) -> str:
    lines = [
        "Customer job description:",
        job_description,
        "",
    ]
    if property_type:
        lines.extend([f"Property type: {property_type}", ""])
    if site_survey:
        # Include captured intake answers (property profile, questionnaire,
        # budget context, access/parking notes) so the electrician does not need
        # to re-enter information the customer already provided.
        lines.extend(
            [
                "Site survey / captured intake (review and adjust if needed):",
                json.dumps(site_survey, indent=2, default=str),
                "",
            ]
        )

    min_charge = tenant_settings.get("minimum_charge", "not set")
    markup = tenant_settings.get("markup_percent", "not set")
    labour_rate = tenant_settings.get("hourly_labour_rate", "not set")
    lines.extend(
        [
            "Business pricing rules (apply where relevant):",
            f"- Minimum charge (GBP): {min_charge}",
            f"- Material markup percent: {markup}",
            f"- Hourly labour rate (GBP): {labour_rate}",
            "",
        ]
    )

    if knowledge_chunks:
        # Labour norms + KB guidance let the LLM anchor labour HOURS (a
        # different failure mode from labour RATES, which the validation
        # layer already snaps to the tenant setting).
        lines.append(
            "Guidance from the knowledge base and labour norms (use these "
            "as your default hours/assumptions unless the job description "
            "clearly contradicts them):"
        )
        for chunk in knowledge_chunks:
            text = str(chunk.get("text") or "").strip()
            if not text:
                continue
            lines.append(f"---\n{text}")
        lines.append("")

    if cost_items:
        lines.append(
            "Catalogue matches for this job. When a MATERIAL line matches one "
            "of the numbered items below, set that line's `catalogue_ref` to "
            "the item's number:"
        )
        for index, item in enumerate(cost_items, start=1):
            lines.append(
                f"  {index}. {item['description']} | "
                f"unit={item['unit']} | price={item['unit_price']} GBP"
            )
        lines.append(
            "`catalogue_ref` is ALWAYS a small integer matching a catalogue "
            f"line number (1-{len(cost_items)}) or null when nothing matches. "
            "Never invent codes or reference numbers outside that range."
        )
    else:
        lines.append(
            "No catalogue reference available — price materials from typical UK trade prices."
        )

    lines.append("\nReturn JSON only.")
    return "\n".join(lines)


def _resolve_catalogue_refs(
    parsed: dict[str, Any], cost_items: list[dict[str, Any]]
) -> dict[str, int]:
    """Map ``catalogue_ref`` integers back to catalogue codes on each line item.

    Copying long code strings (``DOM-screwfix-20967``) verbatim is unreliable
    for LLMs; asking for a small integer index and mapping it server-side is
    dramatically more compliant. Any pre-existing ``code`` the LLM emits is
    preserved as a fallback. Returns per-call counts for observability.
    """
    resolved = 0
    invalid = 0
    line_items = parsed.get("line_items") or []
    for line in line_items:
        if not isinstance(line, dict):
            continue
        ref = line.get("catalogue_ref")
        # Some models emit strings like "3." — coerce leniently.
        if isinstance(ref, str):
            digits = re.match(r"\s*(\d+)", ref)
            ref = int(digits.group(1)) if digits else None
        if isinstance(ref, int) and 1 <= ref <= len(cost_items):
            code = cost_items[ref - 1].get("code")
            if code:
                line["code"] = code
                resolved += 1
                continue
        if ref is not None:
            # Out-of-range or unparseable ref — drop it and mark invalid so we
            # can see in logs whether the LLM is inventing indices.
            line["catalogue_ref"] = None
            invalid += 1
    return {"resolved": resolved, "invalid": invalid}


def _parse_json_response(content: str) -> dict[str, Any]:
    """Parse JSON from an LLM response, allowing for markdown fences."""
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        content = content.strip()

    try:
        return json.loads(content)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        # Try to extract the first JSON object in the response.
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(content[start : end + 1])  # type: ignore[no-any-return]
            except json.JSONDecodeError:
                pass

    return {
        "line_items": [],
        "assumptions": [],
        "notes": f"Could not parse LLM response as JSON. Raw response: {content[:500]}",
    }


FOLLOWUP_SYSTEM_PROMPT = """You are a friendly, concise AI assistant for a UK electrician.

A homeowner has submitted a quote request. The summary below leads with the
"Customer's stated problem" — the job in the customer's own words — followed by
any known property facts. Review what is known and decide whether you are
confident enough (more than 80%) that an electrician can prepare an accurate
quote from it.

Rules:
- If this is your FIRST message in the conversation, explicitly acknowledge the
  customer's stated problem in your own words (e.g. "Sorry to hear your washer
  keeps tripping the fuse box") BEFORE asking anything.
- If you are more than 80% confident, set "complete": true and write a brief thank-you
  message confirming the electrician will review the request and the customer will be
  notified once the quote is ready.
- If you are 80% confident or less, set "complete": false and ask ONE short clarifying
  question that fills the biggest gap in the details. Reference the provided details.
- Ask about the HIGHEST-VALUE missing detail. In priority order:
    1. Job specifics — which room(s), how many items, what's there now, symptoms for
       faults, brand/finish preferences. These matter most because they change both
       the labour hours and material choices.
    2. Access / logistics — where the consumer unit / fuse box is, parking, best times.
    3. Property basics — type and bedroom count if not already known.
  Skip anything the summary already answers, and never chain two unrelated questions.
- Every question must be answerable by a non-engineer homeowner. Never ask about
  technical details they cannot reasonably know (circuit ratings, earthing
  arrangements, cable sizes) — ask about things they can see or count instead.
- When your question has natural choices, include "options": 2-4 short strings the
  customer can pick from (e.g. ["Fuse box under the stairs", "In the garage",
  "Not sure"]). Keep each option under 60 characters.
- When you close the conversation WITHOUT high confidence, also include
  "suggested_questions": 1-3 precise questions the electrician could ask the
  customer on a call.
- Never ask about information the customer has already provided in the request summary
  or earlier in the conversation — acknowledge what they told you instead.
- Keep the question conversational and under 2 sentences.
- Do not quote prices or promise availability.
- Confidence must be an integer from 0 to 100.
- In "extracted", record any facts the customer has EXPLICITLY stated that are useful for
  quoting, as flat string key→value pairs. Prefer these standard keys where they apply — \
using the same key names lets the quote engine credit the information without a human \
re-mapping it:
    Property: property_type, bedrooms, age, tenure
    Access: consumer_unit_location, fuse_box_location, parking, access_notes, \
preferred_time
    Job specifics: location (which room), quantity (how many), existing_setup \
(what's there now), symptoms (for faults), timeline, preference, brand, finish, budget
  Add other keys as needed but keep values short. Only include facts explicitly stated \
by the customer; use an empty object when there are none.

Respond with valid JSON in exactly this shape ("options" and "suggested_questions"
are optional — omit them when they do not apply):
{"confidence": 0-100, "complete": true|false, "message": "Your question or thank-you message", "options": ["choice 1", "choice 2"], "suggested_questions": ["question for the electrician to ask on a call"], "extracted": {"fact_name": "value"}}
"""


def _build_followup_prompt(
    job_description: str,
    prior_messages: list[dict[str, str]],
    final_turn: bool = False,
) -> str:
    """Legacy flat-string prompt kept for compatibility.

    Superseded by :func:`_build_followup_messages`, which shapes the same
    context as a role-tagged messages array so Kimi (and any OpenAI-compatible
    endpoint) can reuse prompt caching across turns and respect its
    instruction-tuned multi-turn behaviour. Retained because it is imported by
    tests and downstream callers.
    """
    lines = ["Quote request summary:", job_description, ""]
    if prior_messages:
        lines.append("Conversation so far:")
        for msg in prior_messages:
            role_label = {"customer": "Customer", "business": "Electrician", "ai": "Assistant"}.get(
                msg["role"], "Assistant"
            )
            lines.append(f"{role_label}: {msg['text']}")
    else:
        lines.append("Conversation so far: (none — this is your first message)")
    if final_turn:
        lines.extend(
            [
                "",
                "Note: this is the LAST question you may ask. If you still cannot reach "
                'high confidence, close politely and include "suggested_questions" with '
                "1-3 precise questions the electrician could ask the customer on a call.",
            ]
        )
    lines.append("\nRespond with JSON only.")
    return "\n".join(lines)


# Kimi (like all OpenAI-compatible endpoints) is stateless — every call must
# resend the whole conversation. We cap the tail so long threads cannot grow
# the prompt without bound. Each triage turn is one user + one assistant
# message, so 20 = ~10 turns of safety on top of the configured cap.
_MAX_FOLLOWUP_HISTORY_MESSAGES = 20

_FINAL_TURN_HINT = (
    "This is your LAST question. If you still cannot reach high confidence, "
    'close politely and include "suggested_questions" with 1-3 precise '
    "questions the electrician could ask the customer on a call."
)


def _build_followup_messages(
    job_description: str,
    prior_messages: list[dict[str, str]],
    final_turn: bool = False,
) -> list[dict[str, str]]:
    """Shape the triage chat as a role-tagged messages array for the LLM.

    Layout mirrors Kimi's multi-turn docs so prompt-prefix caching kicks in
    across turns: system rules → anchoring user summary → alternating
    ``user``/``assistant`` turns from the DB → optional final-turn user hint.
    """
    role_map = {"customer": "user", "business": "user", "ai": "assistant"}
    if len(prior_messages) > _MAX_FOLLOWUP_HISTORY_MESSAGES:
        logger.warning(
            "followup_history_truncated",
            total=len(prior_messages),
            kept=_MAX_FOLLOWUP_HISTORY_MESSAGES,
        )
    tail = prior_messages[-_MAX_FOLLOWUP_HISTORY_MESSAGES:]

    messages: list[dict[str, str]] = [
        {"role": "system", "content": FOLLOWUP_SYSTEM_PROMPT},
        {"role": "user", "content": f"Quote request summary:\n{job_description}"},
    ]
    for msg in tail:
        role = role_map.get(msg.get("role", ""), "user")
        text = (msg.get("text") or "").strip()
        if not text:
            continue
        messages.append({"role": role, "content": text})

    # If the last DB message is from the AI (empty turn or dedupe race), append
    # an explicit nudge so the LLM's next output is another assistant turn
    # rather than parroting the last one.
    if messages[-1]["role"] == "assistant":
        messages.append(
            {
                "role": "user",
                "content": "Continue the triage. Respond with JSON only.",
            }
        )

    if final_turn:
        messages.append({"role": "user", "content": _FINAL_TURN_HINT})

    return messages


FOLLOWUP_FALLBACK = {
    "confidence": 50,
    "complete": False,
    "message": "Could you share any other details that might help with the quote?",
    "extracted": {},
}


def _sanitize_extracted(value: Any) -> dict[str, str]:
    """Keep only flat str→str scalar facts from the LLM's ``extracted`` object."""
    if not isinstance(value, dict):
        return {}
    return {
        str(key): str(val)
        for key, val in value.items()
        if isinstance(val, (str, int, float, bool)) and str(key).strip()
    }


def _sanitize_string_list(value: Any, *, max_items: int, max_length: int) -> list[str]:
    """Keep only non-empty strings, trimmed and truncated, capped in count.

    Used for the LLM's ``options`` (quick-reply choices for the customer) and
    ``suggested_questions`` (call script for the electrician) so malformed or
    oversized model output never reaches the app.
    """
    if not isinstance(value, list):
        return []
    sanitized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text:
            continue
        sanitized.append(text[:max_length])
        if len(sanitized) >= max_items:
            break
    return sanitized


async def generate_followup(
    job_description: str,
    prior_messages: list[dict[str, str]],
    final_turn: bool = False,
) -> dict[str, Any]:
    """Call the configured LLM to produce the next chat turn for the homeowner.

    Returns a dict with ``confidence`` (int 0-100), ``complete`` (bool),
    ``message`` (the clarifying question or thank-you closure) and
    ``extracted`` (flat str→str facts the customer has explicitly stated).
    When the model offers them, ``options`` (≤4 short customer quick-reply
    choices, ≤60 chars each) and ``suggested_questions`` (≤3 questions the
    electrician could ask on a call, ≤60 chars each) are included too.
    ``final_turn`` tells the model this is its last question, so it should
    close with ``suggested_questions`` when confidence stays low.
    """
    if not settings.resolved_llm_api_key:
        raise RuntimeError("LLM API key is not configured")

    messages = _build_followup_messages(job_description, prior_messages, final_turn=final_turn)
    completion_kwargs: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
        "api_key": settings.resolved_llm_api_key,
        "response_format": {"type": "json_object"},
        "timeout": settings.llm_timeout_seconds,
        "num_retries": settings.llm_max_retries,
        "max_tokens": settings.llm_followup_max_tokens,
    }
    if settings.llm_temperature is not None and _model_allows_custom_temperature(
        settings.llm_model
    ):
        completion_kwargs["temperature"] = settings.llm_temperature
    if settings.llm_api_base:
        completion_kwargs["api_base"] = settings.llm_api_base

    try:
        started = time.perf_counter()
        response = await acompletion(**completion_kwargs)
    except APIError as exc:
        logger.error(
            "llm_error",
            phase="followup",
            model=settings.llm_model,
            error_type=type(exc).__name__,
        )
        raise RuntimeError(f"LLM generation failed: {exc.message}") from exc
    except (httpx.HTTPError, ConnectionError, OSError) as exc:
        logger.error(
            "llm_error",
            phase="followup",
            model=settings.llm_model,
            error_type=type(exc).__name__,
        )
        raise RuntimeError(f"LLM service unavailable: {exc}") from exc

    content = response.choices[0].message.content
    if not content:
        logger.warning(
            "llm_followup_empty",
            model=settings.llm_model,
            finish_reason=getattr(response.choices[0], "finish_reason", None),
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return FOLLOWUP_FALLBACK

    parsed = _parse_json_response(content)
    confidence_raw: Any = parsed.get("confidence")
    try:
        confidence = int(confidence_raw)
    except (TypeError, ValueError):
        confidence = 50
    confidence = max(0, min(100, confidence))

    complete = bool(parsed.get("complete"))
    # Force completion once confidence is high enough.
    if confidence >= 80:
        complete = True

    message = parsed.get("message") or FOLLOWUP_FALLBACK["message"]
    extracted = _sanitize_extracted(parsed.get("extracted"))
    options = _sanitize_string_list(parsed.get("options"), max_items=4, max_length=60)
    suggested_questions = _sanitize_string_list(
        parsed.get("suggested_questions"), max_items=3, max_length=60
    )
    logger.info(
        "llm_followup_generated",
        model=settings.llm_model,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
        prior_message_count=len(prior_messages),
        message_count=len(messages),
        prompt_chars=sum(len(m["content"]) for m in messages),
        final_turn=final_turn,
        confidence=confidence,
        complete=complete,
        extracted_count=len(extracted),
        options_count=len(options),
        suggested_questions_count=len(suggested_questions),
    )
    return {
        "confidence": confidence,
        "complete": complete,
        "message": message,
        "extracted": extracted,
        "options": options,
        "suggested_questions": suggested_questions,
        "usage": _extract_usage(response),
    }


async def generate_quote_from_prompt(
    job_description: str,
    cost_items: list[dict[str, Any]],
    tenant_settings: dict[str, Any],
    property_type: str | None = None,
    site_survey: dict[str, Any] | None = None,
    knowledge_chunks: list[dict[str, Any]] | None = None,
    model: str | None = None,
    api_base: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Call the configured LLM and return parsed guide-priced line items.

    ``knowledge_chunks`` (labour norms + KB guidance) are rendered into the
    prompt when supplied. Callers that don't pass anything trigger a live
    knowledge-collection lookup so this stays a one-line wiring for the
    existing quote router while the eval harness / tests can pass an empty
    list to skip retrieval.

    ``model`` / ``api_base`` / ``api_key`` optionally override the configured
    provider for a single call (the public demo uses them to route to a fast,
    reliable model regardless of the production ``LLM_MODEL``). All default to
    ``None`` → the configured pipeline is used unchanged. Pass ``api_base=""``
    to suppress a configured non-OpenAI base (e.g. Kimi) and hit the
    OpenAI defaults instead.
    """
    resolved_model = model or settings.llm_model
    resolved_api_key = api_key or settings.resolved_llm_api_key
    if not resolved_api_key:
        raise RuntimeError("LLM API key is not configured")

    if knowledge_chunks is None:
        # Local import: retrieval imports generation for the followup prompts.
        from app.rag.retrieval import search_knowledge_chunks

        knowledge_chunks = await search_knowledge_chunks(job_description, top_k=3)

    prompt = _build_user_prompt(
        job_description,
        property_type,
        cost_items,
        tenant_settings,
        site_survey,
        knowledge_chunks=knowledge_chunks,
    )
    completion_kwargs: dict[str, Any] = {
        "model": resolved_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "api_key": resolved_api_key,
        "response_format": {"type": "json_object"},
        "timeout": settings.llm_timeout_seconds,
        "num_retries": settings.llm_max_retries,
    }
    # Kimi's kimi-k* models reject a custom temperature; omit it for them.
    if settings.llm_temperature is not None and _model_allows_custom_temperature(resolved_model):
        completion_kwargs["temperature"] = settings.llm_temperature
    # Route to any OpenAI-compatible endpoint (e.g. Kimi/Moonshot) when set.
    # An explicit empty override suppresses the configured base (OpenAI path).
    resolved_api_base = settings.llm_api_base if api_base is None else api_base
    if resolved_api_base:
        completion_kwargs["api_base"] = resolved_api_base

    try:
        started = time.perf_counter()
        response = await acompletion(**completion_kwargs)
    except APIError as exc:
        logger.error(
            "llm_error",
            phase="quote_generation",
            model=resolved_model,
            error_type=type(exc).__name__,
        )
        raise RuntimeError(f"LLM generation failed: {exc.message}") from exc
    except (httpx.HTTPError, ConnectionError, OSError) as exc:
        logger.error(
            "llm_error",
            phase="quote_generation",
            model=resolved_model,
            error_type=type(exc).__name__,
        )
        raise RuntimeError(f"LLM service unavailable: {exc}") from exc

    content = response.choices[0].message.content
    if not content:
        logger.warning(
            "llm_quote_empty",
            model=resolved_model,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return {"line_items": [], "assumptions": [], "notes": "LLM returned empty content"}

    parsed = _parse_json_response(content)
    parsed["usage"] = _extract_usage(response)
    ref_stats = _resolve_catalogue_refs(parsed, cost_items)
    logger.info(
        "llm_quote_generated",
        model=resolved_model,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
        prompt_chars=len(prompt),
        catalogue_items=len(cost_items),
        line_items=len(parsed.get("line_items") or []),
        assumption_count=len(parsed.get("assumptions") or []),
        catalogue_refs_resolved=ref_stats["resolved"],
        catalogue_refs_invalid=ref_stats["invalid"],
    )
    return parsed
