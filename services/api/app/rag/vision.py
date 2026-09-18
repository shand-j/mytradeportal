"""Photo-observation step for the AI quote pipeline.

Customer photos attached to a quote request (``MediaAsset`` rows) previously
never reached the LLM: generation was text-only, so the model's assumptions
could contradict what a photo plainly showed (e.g. assuming no RCBOs when the
photo shows a rewireable-fuse consumer unit). This module captions each image
with one vision call through the same provider-agnostic LiteLLM setup used for
quote generation and returns short factual observations, which
:func:`app.rag.generation.generate_quote_from_prompt` renders into the draft
prompt as confirmed site facts.

Everything here is fail-open: a missing key, an unreadable object or a failed
vision call logs and drops that image so quote generation proceeds exactly as
it did before photos were wired in.
"""

import base64
import time
from dataclasses import dataclass
from typing import Any

import structlog
from litellm import acompletion

from app.ai_telemetry import AiCallContext, AiCallTracker
from app.config import settings
from app.rag.generation import _extract_usage, _model_allows_custom_temperature

logger = structlog.get_logger("api.rag")

# Prompt version recorded on every ai_call_events row; bump when the
# observation instructions change materially.
MEDIA_OBSERVATION_PROMPT_VERSION = "media-observation.v1"

# Bound per-quote vision cost: caption at most this many photos, and skip
# images whose base64 payload would swamp the prompt.
MAX_OBSERVED_IMAGES = 5
_MAX_IMAGE_BYTES = 8 * 1024 * 1024
# Kimi's kimi-k* reasoning models spend tokens reasoning before emitting
# content, so a tight cap can truncate the caption to empty.
_MAX_OBSERVATION_TOKENS = 2000

_OBSERVATION_INSTRUCTIONS = """You are assisting a UK electrical estimator.
Describe this customer photo in 2-4 short factual sentences covering only what
is relevant to quoting the electrical work: identify the equipment shown (for
a consumer unit, say whether it uses rewireable fuses, MCBs or RCBOs, and
whether surge protection is fitted), its visible condition, and anything that
changes the labour or materials. State only what is visible — never speculate
about anything outside the frame."""


@dataclass
class ImageRef:
    """One photo resolved to a form an LLM provider can consume.

    ``url`` is either an absolute http(s) URL the provider can fetch or a
    base64 ``data:`` URL (MinIO is private-network-only, so its objects are
    read server-side and inlined by the caller).
    """

    url: str
    mime_type: str = "image/jpeg"


def build_data_url(content: bytes, mime_type: str) -> str | None:
    """Inline image bytes as a base64 data URL, capped for prompt size."""
    if not content or len(content) > _MAX_IMAGE_BYTES:
        return None
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime_type or 'image/jpeg'};base64,{encoded}"


async def caption_images(
    images: list[ImageRef],
    *,
    model: str | None = None,
    api_base: str | None = None,
    api_key: str | None = None,
    telemetry: AiCallContext | None = None,
) -> list[str]:
    """Caption each photo with one vision call per image; fail-open per image.

    Returns one observation string per successfully captioned image, in input
    order, capped at ``MAX_OBSERVED_IMAGES``. An empty list means there were no
    usable photos or every call failed — callers treat that as "no photo
    evidence" and generate exactly as before.

    ``model`` / ``api_base`` / ``api_key`` mirror the override semantics of
    :func:`app.rag.generation.generate_quote_from_prompt`; the default model is
    ``llm_vision_model`` when configured, otherwise the quote pipeline's
    ``llm_model``.
    """
    resolved_api_key = api_key or settings.resolved_llm_api_key
    if not resolved_api_key:
        logger.warning("media_observation_skipped", reason="no_api_key")
        return []
    resolved_model = model or settings.llm_vision_model or settings.llm_model
    resolved_api_base = settings.llm_api_base if api_base is None else api_base

    observations: list[str] = []
    for image in images[:MAX_OBSERVED_IMAGES]:
        observation = await _caption_one(
            image,
            model=resolved_model,
            api_key=resolved_api_key,
            api_base=resolved_api_base,
            telemetry=telemetry,
        )
        if observation:
            observations.append(observation)
    if images and not observations:
        logger.warning("media_observation_all_failed", image_count=len(images))
    return observations


async def _caption_one(
    image: ImageRef,
    *,
    model: str,
    api_key: str,
    api_base: str,
    telemetry: AiCallContext | None,
) -> str | None:
    """Run one vision call for one photo; ``None`` on any failure."""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": _OBSERVATION_INSTRUCTIONS},
                {"type": "image_url", "image_url": {"url": image.url}},
            ],
        }
    ]
    completion_kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "api_key": api_key,
        "timeout": settings.llm_timeout_seconds,
        "num_retries": settings.llm_max_retries,
        "max_tokens": _MAX_OBSERVATION_TOKENS,
    }
    # Kimi's kimi-k* models reject a custom temperature; omit it for them.
    if settings.llm_temperature is not None and _model_allows_custom_temperature(model):
        completion_kwargs["temperature"] = settings.llm_temperature
    if api_base:
        completion_kwargs["api_base"] = api_base

    tracker = AiCallTracker(
        telemetry,
        model=model,
        prompt_version=MEDIA_OBSERVATION_PROMPT_VERSION,
        prompt_text=_OBSERVATION_INSTRUCTIONS if telemetry is not None else None,
    )
    try:
        started = time.perf_counter()
        async with tracker:
            response = await acompletion(**completion_kwargs)
            tracker.set_usage(_extract_usage(response))
    except Exception as exc:
        # Fail-open: a bad photo or a non-vision model must never break quote
        # generation — the draft is simply produced without photo evidence.
        logger.warning(
            "media_observation_failed",
            model=model,
            error_type=type(exc).__name__,
            error=str(exc)[:200],
        )
        return None

    content = response.choices[0].message.content
    observation = (content or "").strip()
    logger.info(
        "media_observation_generated",
        model=model,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
        mime_type=image.mime_type,
        observation_chars=len(observation),
    )
    return observation or None
