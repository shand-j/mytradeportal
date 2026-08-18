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
from typing import Any

import httpx
from litellm import acompletion
from openai import APIError

from app.config import settings

SYSTEM_PROMPT = """You are an expert UK electrical estimator. Produce a clear, \
itemised GUIDE quote for the job described so a qualified electrician can review \
and adjust it before sending.

Rules:
- Return realistic guide prices in GBP, excluding VAT, for BOTH labour and \
materials. These are estimates the electrician will review and edit.
- Use the supplier catalogue prices provided below as your reference for \
materials whenever an item matches; set that item's "code" so the price can be \
grounded. When a required item is not in the catalogue, price it from typical UK \
trade prices.
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
"quantity": 1, "unit": "job", "unit_price": 320.00, "code": null, \
"reason": "brief justification"}
  ],
  "assumptions": ["Any assumptions you made"],
  "notes": "Any warnings or clarifications for the electrician"
}
"""


def _build_user_prompt(
    job_description: str,
    property_type: str | None,
    cost_items: list[dict[str, Any]],
    tenant_settings: dict[str, Any],
) -> str:
    lines = [
        "Customer job description:",
        job_description,
        "",
    ]
    if property_type:
        lines.extend([f"Property type: {property_type}", ""])

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

    if cost_items:
        lines.append(
            "Catalogue price reference (use a matching item's code to ground its "
            "material price; not exhaustive — price anything missing yourself):"
        )
        for item in cost_items:
            lines.append(
                f"- code={item['code']} | {item['description']} | "
                f"unit={item['unit']} | price={item['unit_price']} GBP"
            )
    else:
        lines.append(
            "No catalogue reference available — price materials from typical UK trade prices."
        )

    lines.append("\nReturn JSON only.")
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


async def generate_quote_from_prompt(
    job_description: str,
    cost_items: list[dict[str, Any]],
    tenant_settings: dict[str, Any],
    property_type: str | None = None,
) -> dict[str, Any]:
    """Call the configured LLM and return parsed guide-priced line items."""
    if not settings.resolved_llm_api_key:
        raise RuntimeError("LLM API key is not configured")

    prompt = _build_user_prompt(job_description, property_type, cost_items, tenant_settings)
    completion_kwargs: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "api_key": settings.resolved_llm_api_key,
        "response_format": {"type": "json_object"},
    }
    # Kimi's kimi-k* models reject a custom temperature; omit it when unset.
    if settings.llm_temperature is not None:
        completion_kwargs["temperature"] = settings.llm_temperature
    # Route to any OpenAI-compatible endpoint (e.g. Kimi/Moonshot) when set.
    if settings.llm_api_base:
        completion_kwargs["api_base"] = settings.llm_api_base

    try:
        response = await acompletion(**completion_kwargs)
    except APIError as exc:
        raise RuntimeError(f"LLM generation failed: {exc.message}") from exc
    except (httpx.HTTPError, ConnectionError, OSError) as exc:
        raise RuntimeError(f"LLM service unavailable: {exc}") from exc

    content = response.choices[0].message.content
    if not content:
        return {"line_items": [], "assumptions": [], "notes": "LLM returned empty content"}

    return _parse_json_response(content)
