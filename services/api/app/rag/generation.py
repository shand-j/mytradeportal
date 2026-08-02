"""LLM generation of quote line items from retrieved cost data."""

import json
import re
from typing import Any

import httpx
from litellm import acompletion
from openai import APIError

from app.config import settings

SYSTEM_PROMPT = """You are an expert electrical estimator for UK residential and small-commercial work.
Your task is to produce a quote from a customer's job description using ONLY the cost items provided below.
These are real supplier catalogue prices. Do not invent prices or items that are not listed.
For cable and any item with unit="m", the listed price is per metre and the quantity must be the exact metreage required.
If the job description is unclear or no suitable cost items are available, respond with an empty line_items array and explain why in the notes field.

Respond with valid JSON in the following format:
{
  "line_items": [
    {"code": "ITEM-CODE", "quantity": 1, "reason": "Brief justification"}
  ],
  "notes": "Any assumptions or warnings"
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
            "Business pricing rules:",
            f"- Minimum charge: {min_charge}",
            f"- Markup percent: {markup}",
            f"- Hourly labour rate: {labour_rate}",
            "",
            "Available cost items (use ONLY these):",
        ]
    )

    for item in cost_items:
        lines.append(
            f"- code={item['code']} | {item['description']} | "
            f"unit={item['unit']} | price={item['unit_price']} GBP"
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
        "notes": f"Could not parse LLM response as JSON. Raw response: {content[:500]}",
    }


async def generate_quote_from_prompt(
    job_description: str,
    cost_items: list[dict[str, Any]],
    tenant_settings: dict[str, Any],
    property_type: str | None = None,
) -> dict[str, Any]:
    """Call the configured LLM and return parsed JSON line items."""
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    prompt = _build_user_prompt(job_description, property_type, cost_items, tenant_settings)
    completion_kwargs: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "api_key": settings.openai_api_key,
        "response_format": {"type": "json_object"},
    }

    try:
        response = await acompletion(**completion_kwargs)
    except APIError as exc:
        raise RuntimeError(f"LLM generation failed: {exc.message}") from exc
    except (httpx.HTTPError, ConnectionError, OSError) as exc:
        raise RuntimeError(f"LLM service unavailable: {exc}") from exc

    content = response.choices[0].message.content
    if not content:
        return {"line_items": [], "notes": "LLM returned empty content"}

    return _parse_json_response(content)
