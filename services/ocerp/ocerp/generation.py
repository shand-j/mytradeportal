"""LLM generation of Bills of Quantities from retrieved cost data."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from decimal import Decimal
from typing import Any

from litellm import acompletion
from openai import APIError

from ocerp.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert UK electrical estimator producing a detailed Bill of Quantities (BoQ).

Decompose the customer's job description into a **brandless, generic list of material requirements** and a labour estimate. Do NOT use supplier SKU codes or prices. The downstream engine will resolve each requirement to a live Screwfix catalogue item and price it automatically.

Rules:
1. NEVER use generic package items such as "full rewire of a X-bedroom house". Always break the job into individual components.
2. Be granular. For a rewire include: cable by the metre, back boxes, accessories, consumer unit, circuit breakers/RCBOs, smoke/heat detectors, SPD, testing per circuit, certification, and labour.
3. Mandatory items by job type (include them even if the customer did not explicitly list them):
   - Full rewire or consumer-unit upgrade: a metal consumer unit with SPD, main switch, and RCD protection.
   - Full rewire: mains-powered interlinked smoke alarms (at least one per floor/level) and a heat detector in the kitchen.
   - EV charger circuit: dedicated 32A MCB, Type A RCD, SWA cable, weatherproof isolator, and earth rod.
   - Detached garage/outbuilding: separate garage consumer unit, SWA cable supply, and weatherproof isolator.
   - TT earthing system (customer mentions TT or old Victorian terrace): earth rod, main equipotential bonding clamps, and supplementary bonding cable.
   - HMO or AFDD requested: AFDD protection on socket circuits.
   - Underfloor heating: UFH mat, thermostat, dedicated MCB, and 4mm cable per room.
4. Estimate quantities from the description:
   - Cable: 40-60m of 1.5mm lighting cable and 50-80m of 2.5mm socket cable per room; 6.0mm/10mm for cooker/shower/EV circuits.
   - Back boxes: one per switch/socket.
   - Circuit protection: one MCB or RCBO per final electrical circuit only (lights, sockets, cooker, shower, EV, UFH). TV, data and smoke-alarm points do NOT need their own MCB/RCBO.
   - Use standard sockets unless the description explicitly asks for USB sockets.
   - Include main earth bonding for any full rewire or consumer-unit upgrade.
   - Testing: one per-circuit test plus an installation certificate for rewires/new circuits.
   - Labour: small jobs in hours; full rewires in electrician days. A 1-bed flat is 4-5 days, a 3-bed house 6-8 days, a 4-bed house 8-10 days, plus 2-4 mate days for larger properties.
5. Return requirements as brandless concepts with attributes (see below). Do not invent codes or prices.
6. If the description is vague, make reasonable assumptions and state them in the notes.

Return valid JSON only. The top-level object MUST include:

1. `analysis` object:
   - job_summary: a one-sentence summary of the job
   - room_count: number of bedrooms/rooms if inferable, otherwise null
   - spec_level: one of budget / mid_range / premium based on the fittings named
   - regulatory_flags: list of relevant flags from [spd_required, afdd_required, smoke_alarms_required, metal_cu_required, rcd_protection]
   - Do NOT include estimated costs or labour hours; the downstream pricing engine computes those deterministically from the resolved catalogue items and tenant labour rates.

2. `requirements` array. Each requirement has:
   - concept: a short generic identifier, e.g. "double_socket", "consumer_unit", "smoke_alarm", "1.5mm_twin_earth_cable", "rcbo", "swa_cable"
   - category: one of Cable, Switches & Sockets, Consumer Units, Circuit Protection, Lighting, Security & Fire, Wiring Accessories, Conduit & Trunking, Heating & Cooling
   - attributes: object of filters for the resolver, e.g. {"gang": 2, "usb": false, "finish": "white", "outdoor": false, "brand": "hager", "mm": "1.5", "swa": true, "type": "rcbo"}
   - quantity: number
   - notes: brief justification

3. `labour_estimate` object:
   - electrician_days: number (or 0)
   - mate_days: number (or 0)
   - electrician_hours: number (or 0)
   - notes: brief justification

4. `notes`: any assumptions or caveats.

Example requirement:
{"concept": "double_socket", "category": "Switches & Sockets", "attributes": {"gang": 2, "usb": false, "finish": "white"}, "quantity": 24, "notes": "Standard white double sockets for 3-bed rewire"}
"""


def _is_ollama_model(model: str) -> bool:
    return model.startswith("ollama/")


def _build_user_prompt(
    job_description: str,
    property_type: str | None,
    cost_items: list[dict[str, Any]] | None,
    tenant_settings: dict[str, Any],
    standard: str | None,
    *,
    compliance_context: str = "",
) -> str:
    lines = [
        "Customer job description:",
        job_description,
        "",
    ]
    if property_type:
        lines.extend([f"Property type: {property_type}", ""])
    if standard:
        lines.extend([f"Estimating standard: {standard}", ""])

    if compliance_context:
        lines.extend(
            [
                "AUTHORITATIVE REGULATORY CONTEXT (UK domestic electrical):",
                "Use these excerpts to decide which mandatory items the BoQ must contain.",
                "Do NOT invent regulations that are not in this context.",
                compliance_context,
                "",
            ]
        )

    unset = "not set"
    min_charge = tenant_settings.get("minimum_charge", unset)
    markup = tenant_settings.get("markup_percent", unset)
    labour_rate = tenant_settings.get("hourly_labour_rate", unset)
    lines.extend(
        [
            "Business pricing rules:",
            f"- Minimum charge: {min_charge}",
            f"- Markup percent: {markup}",
            f"- Default hourly labour rate: {labour_rate}",
        ]
    )

    if cost_items:
        lines.extend(
            [
                "",
                "Example catalogue items available for resolution (do NOT use these codes in your output; output generic requirements instead):",
            ]
        )

        for item in cost_items:
            lines.append(
                f"- code={item['code']} | {item['description']} | "
                f"unit={item['unit']} | listed_price={item['unit_price']} GBP"
            )

    lines.append(
        "\nReturn JSON only with top-level keys: analysis, requirements, labour_estimate, notes."
    )
    return "\n".join(lines)


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
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(content[start : end + 1])  # type: ignore[no-any-return]
            except json.JSONDecodeError:
                pass

    return {
        "requirements": [],
        "notes": f"Could not parse LLM response as JSON. Raw response: {content[:500]}",
    }


async def generate_boq_from_prompt(
    job_description: str,
    cost_items: list[dict[str, Any]] | None,
    tenant_settings: dict[str, Any],
    property_type: str | None = None,
    standard: str | None = None,
    *,
    compliance_context: str = "",
) -> dict[str, Any]:
    """Call the configured LLM and return parsed JSON BoQ requirements."""
    is_ollama = _is_ollama_model(settings.llm_model)
    if not is_ollama and not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    prompt = _build_user_prompt(
        job_description,
        property_type,
        cost_items,
        tenant_settings,
        standard,
        compliance_context=compliance_context,
    )
    completion_kwargs: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        # temperature=0 makes the same input produce the same output so a
        # regenerated quote is reproducible. Increase only when explicitly
        # opting in to creative quote exploration.
        "temperature": 0.0,
        "seed": 0,
    }

    # Hash the prompt + model so we can attribute a generated BoQ to a
    # specific prompt revision in audit logs and quote metadata.
    prompt_hash = hashlib.sha256(
        (settings.llm_model + "\n" + SYSTEM_PROMPT + "\n" + prompt).encode("utf-8")
    ).hexdigest()
    logger.info(
        "llm.boq.request",
        extra={
            "model": settings.llm_model,
            "prompt_hash": prompt_hash,
            "prompt_chars": len(prompt),
        },
    )

    if is_ollama:
        completion_kwargs["api_base"] = settings.ollama_api_base
    elif settings.openai_api_key:
        completion_kwargs["api_key"] = settings.openai_api_key
        completion_kwargs["response_format"] = {"type": "json_object"}

    try:
        response = await asyncio.wait_for(
            acompletion(**completion_kwargs), timeout=settings.llm_timeout_seconds
        )
    except TimeoutError:
        logger.warning("LLM generation timed out after %ss", settings.llm_timeout_seconds)
        return {
            "requirements": [],
            "notes": f"LLM generation timed out after {settings.llm_timeout_seconds}s",
        }
    except APIError as exc:
        raise RuntimeError(f"LLM generation failed: {exc.message}") from exc

    content = response.choices[0].message.content
    if not content:
        return {"requirements": [], "notes": "LLM returned empty content", "_meta": {"prompt_hash": prompt_hash, "model": settings.llm_model}}

    parsed = _parse_json_response(content)
    # Attach generation metadata so callers can persist it on the quote for
    # reproducibility / audit purposes.
    parsed["_meta"] = {
        "prompt_hash": prompt_hash,
        "model": settings.llm_model,
    }
    return parsed


def to_decimal(value: Any) -> Decimal:
    """Coerce a value to Decimal safely."""
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value))
