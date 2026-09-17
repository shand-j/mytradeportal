"""AI call telemetry: the single writer for ``ai_call_events``.

Every LLM/embedding call and every AI-funnel outcome is recorded here — one
writer, one table, so cost, latency, quality and outcome funnels all join off
``ai_call_events``. Design discipline mirrors ``app.audit.write_audit_log``:

* **Fail-open always.** Telemetry must never break a customer-facing flow.
  Every failure is logged at ``warning`` and swallowed; ``record_ai_event``
  returns ``None`` instead of raising. When a request session is supplied the
  insert runs inside a SAVEPOINT (``begin_nested``) so a failed telemetry
  write rolls back only itself and never poisons the business transaction.
* **Cheap.** A single indexed INSERT; the writer-latency test holds p95 under
  50ms over 100 writes.
* **Prompt text never lands in Postgres.** It is mirrored to Langfuse only,
  when Langfuse is configured (guarded optional import, no-op when
  ``LANGFUSE_PUBLIC_KEY`` is unset — the Resend optional-integration idiom).

Trace model: ``trace_id`` is minted on a quote's first AI generation and
stored on the previously-unused ``Quote.ai_metadata`` JSONB column
(``ai_metadata.trace_id`` — nothing else reads or writes that column today).
Refines/requotes link back via ``parent_event_id`` (the previous generation's
event id, also cached in ``ai_metadata.last_event_id``) and outcomes carry the
same ``trace_id`` so cost↔outcome joins run off one table.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import structlog

from app.ai_pricing import estimate_cost
from app.config import settings
from app.fx import get_usd_gbp_rate
from app.models import AiCallEvent

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models import Quote

logger = structlog.get_logger("api.ai_telemetry")

# Feature vocabulary (AiCallEvent.feature).
FEATURE_QUOTE_DRAFT = "quote_draft"
FEATURE_QUOTE_REFINE = "quote_refine"
FEATURE_TRIAGE_FOLLOWUP = "triage_followup"
FEATURE_REMINDER_DRAFT = "reminder_draft"
FEATURE_EMBEDDING = "embedding"
FEATURE_DEMO_QUOTE = "demo_quote"
FEATURE_OUTCOME = "outcome"

# Status vocabulary (AiCallEvent.status).
STATUS_SUCCESS = "success"
STATUS_TIMEOUT = "timeout"
STATUS_ERROR = "error"
STATUS_ABANDONED = "abandoned"

# Actor vocabulary (AiCallEvent.actor_type): who/what initiated the call.
ACTOR_STAFF = "staff"
ACTOR_CUSTOMER = "customer"
ACTOR_SYSTEM = "system"

_GBP_QUANTUM = Decimal("0.0001")


@dataclass
class AiCallContext:
    """Caller-supplied context for one tracked AI call.

    Routers/workers build one of these and pass it down to the generation /
    retrieval layer, which wraps the provider call in an :class:`AiCallTracker`.
    ``event_id`` is populated by the tracker once the event row is written so
    the caller can persist the linkage (``ai_metadata.last_event_id``).
    """

    feature: str
    db: AsyncSession | None = None
    tenant_id: UUID | None = None
    user_id: UUID | None = None
    actor_type: str = ACTOR_STAFF
    entry_channel: str | None = None
    trace_id: str | None = None
    parent_event_id: UUID | None = None
    attempt_no: int = 1
    prompt_version: str | None = None
    quote_id: UUID | None = None
    quote_request_id: UUID | None = None
    extra_payload: dict[str, Any] = field(default_factory=dict)
    event_id: UUID | None = None


def new_trace_id() -> str:
    """Mint a new quote-level funnel trace id."""
    return uuid4().hex


def get_or_create_trace_id(quote: Quote) -> str:
    """Return the quote's trace id, minting + persisting it on first use.

    Stored in the previously-dead ``Quote.ai_metadata`` JSONB column; the
    caller flushes the quote as part of its normal flow.
    """
    metadata = dict(quote.ai_metadata or {})
    trace_id = metadata.get("trace_id")
    if not trace_id:
        trace_id = new_trace_id()
        metadata["trace_id"] = trace_id
        quote.ai_metadata = metadata
    return str(trace_id)


def set_last_event_id(quote: Quote, event_id: UUID | None) -> None:
    """Cache the latest generation event id on the quote for parent linkage."""
    if event_id is None:
        return
    metadata = dict(quote.ai_metadata or {})
    metadata["last_event_id"] = str(event_id)
    quote.ai_metadata = metadata


def get_last_event_id(quote: Quote) -> UUID | None:
    """Return the cached last generation event id, if any."""
    raw = (quote.ai_metadata or {}).get("last_event_id")
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except ValueError:
        return None


def next_attempt_no(quote: Quote) -> int:
    """Increment and return the quote's AI generation attempt counter."""
    metadata = dict(quote.ai_metadata or {})
    attempt = int(metadata.get("attempts") or 0) + 1
    metadata["attempts"] = attempt
    quote.ai_metadata = metadata
    return attempt


def _provider_for_model(model: str | None) -> str | None:
    """Derive the OpenTelemetry ``gen_ai_provider_name`` from the model id."""
    if not model:
        return None
    if "/" in model:
        return model.split("/", 1)[0]
    # Bare model ids route through LiteLLM's OpenAI-compatible handler.
    return "openai"


def _is_timeout(exc: BaseException) -> bool:
    """Best-effort timeout classification across httpx/openai/litellm wrappers."""
    if isinstance(exc, TimeoutError):
        return True
    return "timeout" in type(exc).__name__.lower()


# --- Langfuse (optional, guarded) ------------------------------------------

_langfuse_client: Any = None
_langfuse_unavailable = False


def _get_langfuse() -> Any:
    """Return a cached Langfuse client, or ``None`` when not configured.

    Follows the optional-integration idiom: empty-string settings + truthiness
    guard + ``try: import``. Any construction failure disables emission for
    the process rather than raising into a request path.
    """
    global _langfuse_client, _langfuse_unavailable
    if _langfuse_unavailable or not settings.langfuse_public_key:
        return None
    if _langfuse_client is not None:
        return _langfuse_client
    try:
        from langfuse import Langfuse

        _langfuse_client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host or None,
        )
    except Exception as exc:
        _langfuse_unavailable = True
        logger.warning(
            "ai_telemetry.langfuse_disabled",
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
        return None
    return _langfuse_client


def _emit_langfuse(event: AiCallEvent, prompt_text: str | None) -> None:
    """Mirror one tracked AI call to Langfuse. Never raises.

    The trace carries prompt text + prompt_version + model + tokens. Prompt
    text goes to Langfuse ONLY — it is never written to ``ai_call_events``.
    """
    client = _get_langfuse()
    if client is None:
        return
    try:
        tags = [f"actor_type:{event.actor_type}"]
        if event.entry_channel:
            tags.append(f"entry_channel:{event.entry_channel}")
        trace = client.trace(
            name=event.feature,
            tags=tags,
            metadata={
                "trace_id": event.trace_id,
                "tenant_id": str(event.tenant_id) if event.tenant_id else None,
                "prompt_version": event.prompt_version,
                "status": event.status,
            },
        )
        trace.generation(
            name=event.feature,
            model=event.gen_ai_request_model,
            input=prompt_text,
            metadata={"prompt_version": event.prompt_version, "status": event.status},
            usage={
                "input": event.gen_ai_usage_input_tokens,
                "output": event.gen_ai_usage_output_tokens,
            },
        )
    except Exception as exc:
        logger.warning(
            "ai_telemetry.langfuse_emit_failed",
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )


# --- The single writer ------------------------------------------------------


async def record_ai_event(
    db: AsyncSession | None = None,
    *,
    feature: str,
    status: str = STATUS_SUCCESS,
    tenant_id: UUID | None = None,
    user_id: UUID | None = None,
    actor_type: str = ACTOR_STAFF,
    entry_channel: str | None = None,
    model: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cached_input_tokens: int | None = None,
    latency_seconds: float | None = None,
    attempt_no: int = 1,
    parent_event_id: UUID | None = None,
    trace_id: str | None = None,
    prompt_version: str | None = None,
    confidence: float | None = None,
    completeness: float | None = None,
    retrieval_status: str | None = None,
    quote_id: UUID | None = None,
    quote_request_id: UUID | None = None,
    raw_payload: dict[str, Any] | None = None,
    prompt_text: str | None = None,
) -> UUID | None:
    """Insert one ``ai_call_events`` row. Fail-open: returns ``None`` on failure.

    Cost fields are derived here so every call site stays dumb:
    ``est_cost_usd`` from :func:`app.ai_pricing.estimate_cost` (None for
    unknown models), ``cost_gbp`` = ``est_cost_usd x fx_rate`` stamped with
    today's :func:`app.fx.get_usd_gbp_rate`.

    With ``db`` the row is written through a SAVEPOINT on the caller's
    transaction (committed by the caller); without it the writer opens its own
    session and commits independently — used by call sites that have no
    request session (embeddings) and by paths whose business transaction may
    legitimately roll back after the AI spend was incurred.
    """
    try:
        est_cost_usd: Decimal | None = None
        if model and input_tokens is not None:
            est_cost_usd = estimate_cost(
                model,
                input_tokens,
                output_tokens or 0,
                cached_input_tokens or 0,
                at_date=date.today(),
            )

        event = AiCallEvent(
            id=uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            feature=feature,
            actor_type=actor_type,
            entry_channel=entry_channel,
            gen_ai_provider_name=_provider_for_model(model),
            gen_ai_request_model=model,
            gen_ai_usage_input_tokens=input_tokens,
            gen_ai_usage_output_tokens=output_tokens,
            gen_ai_usage_cached_input_tokens=cached_input_tokens,
            est_cost_usd=est_cost_usd,
            latency_seconds=latency_seconds,
            status=status,
            attempt_no=attempt_no,
            parent_event_id=parent_event_id,
            trace_id=trace_id,
            prompt_version=prompt_version,
            confidence=confidence,
            completeness=completeness,
            retrieval_status=retrieval_status,
            quote_id=quote_id,
            quote_request_id=quote_request_id,
            raw_payload=raw_payload or {},
        )

        if db is not None:
            if est_cost_usd is not None:
                fx_rate, fx_date = await get_usd_gbp_rate(db)
                event.fx_rate = fx_rate
                event.fx_rate_date = fx_date
                event.cost_gbp = (est_cost_usd * fx_rate).quantize(_GBP_QUANTUM)
            # SAVEPOINT: a failed telemetry insert rolls back only itself, so
            # the caller's business transaction can still commit.
            async with db.begin_nested():
                db.add(event)
                await db.flush()
        else:
            # Local import: app.database imports app.models; keeping this
            # lazy avoids an import cycle at module load.
            from app.database import get_db_session

            async with get_db_session() as session:
                if est_cost_usd is not None:
                    fx_rate, fx_date = await get_usd_gbp_rate(session)
                    event.fx_rate = fx_rate
                    event.fx_rate_date = fx_date
                    event.cost_gbp = (est_cost_usd * fx_rate).quantize(_GBP_QUANTUM)
                session.add(event)
                await session.commit()

        if model is not None:
            _emit_langfuse(event, prompt_text)
        return event.id
    except Exception as exc:  # fail-open, mirrors write_audit_log discipline
        logger.warning(
            "ai_telemetry.write_failed",
            feature=feature,
            status=status,
            tenant_id=str(tenant_id) if tenant_id else None,
            trace_id=trace_id,
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
        return None


async def record_quote_outcome(
    db: AsyncSession | None,
    *,
    outcome: str,
    tenant_id: UUID | None,
    quote: Quote,
    user_id: UUID | None = None,
    extra_payload: dict[str, Any] | None = None,
) -> UUID | None:
    """Emit a lightweight ``feature="outcome"`` row for an AI-traced quote.

    Outcome rows (``quote_sent`` / ``quote_accepted`` / ``invoice_paid``)
    carry no model/token/cost fields — they exist so cost↔outcome joins run
    off ``ai_call_events`` via ``trace_id``. No-op (returns ``None``) when the
    quote has no trace id: manual quotes have no AI funnel to join against,
    so recording them would only pollute the funnel.
    """
    trace_id = (quote.ai_metadata or {}).get("trace_id")
    if not trace_id:
        return None
    return await record_ai_event(
        db,
        feature=FEATURE_OUTCOME,
        tenant_id=tenant_id,
        user_id=user_id,
        trace_id=str(trace_id),
        quote_id=quote.id,
        quote_request_id=quote.quote_request_id,
        raw_payload={"outcome": outcome, **(extra_payload or {})},
    )


class AiCallTracker:
    """Async context manager that times one provider call and records it.

    Usage::

        tracker = AiCallTracker(ctx, model=resolved_model, prompt_text=prompt)
        async with tracker:
            response = await acompletion(**kwargs)
            tracker.set_usage(_extract_usage(response))

    On exit — success or exception — exactly one ``ai_call_events`` row is
    written (fail-open). Exceptions are NEVER swallowed: ``__aexit__`` records
    a ``status=error|timeout`` row and re-raises, so the caller still sees the
    original failure. When ``ctx`` is ``None`` the tracker still times and
    collects usage but writes nothing (call sites without telemetry wiring
    pay no cost).
    """

    def __init__(
        self,
        ctx: AiCallContext | None,
        *,
        model: str | None,
        prompt_version: str | None = None,
        prompt_text: str | None = None,
    ) -> None:
        self.ctx = ctx
        self.model = model
        self.prompt_version = prompt_version
        self.prompt_text = prompt_text
        self.input_tokens: int | None = None
        self.output_tokens: int | None = None
        self.cached_input_tokens: int | None = None
        self._started = 0.0

    def set_usage(self, usage: dict[str, Any] | None) -> None:
        """Record token counts extracted from the provider response."""
        if not usage:
            return
        prompt = usage.get("prompt_tokens")
        completion = usage.get("completion_tokens")
        cached = usage.get("cached_tokens")
        self.input_tokens = int(prompt) if prompt is not None else None
        self.output_tokens = int(completion) if completion is not None else None
        self.cached_input_tokens = int(cached) if cached is not None else None

    async def __aenter__(self) -> AiCallTracker:
        self._started = time.perf_counter()
        return self

    async def __aexit__(self, exc_type: Any, exc: BaseException | None, tb: Any) -> bool:
        latency = round(time.perf_counter() - self._started, 4)
        if exc is None:
            status = STATUS_SUCCESS
        elif _is_timeout(exc):
            status = STATUS_TIMEOUT
        else:
            status = STATUS_ERROR
        if self.ctx is not None:
            self.ctx.event_id = await record_ai_event(
                self.ctx.db,
                feature=self.ctx.feature,
                status=status,
                tenant_id=self.ctx.tenant_id,
                user_id=self.ctx.user_id,
                actor_type=self.ctx.actor_type,
                entry_channel=self.ctx.entry_channel,
                model=self.model,
                input_tokens=self.input_tokens,
                output_tokens=self.output_tokens,
                cached_input_tokens=self.cached_input_tokens,
                latency_seconds=latency,
                attempt_no=self.ctx.attempt_no,
                parent_event_id=self.ctx.parent_event_id,
                trace_id=self.ctx.trace_id,
                prompt_version=self.ctx.prompt_version or self.prompt_version,
                quote_id=self.ctx.quote_id,
                quote_request_id=self.ctx.quote_request_id,
                raw_payload=self.ctx.extra_payload,
                prompt_text=self.prompt_text,
            )
        return False  # never suppress — the caller still sees the error


__all__ = [
    "ACTOR_CUSTOMER",
    "ACTOR_STAFF",
    "ACTOR_SYSTEM",
    "FEATURE_DEMO_QUOTE",
    "FEATURE_EMBEDDING",
    "FEATURE_OUTCOME",
    "FEATURE_QUOTE_DRAFT",
    "FEATURE_QUOTE_REFINE",
    "FEATURE_REMINDER_DRAFT",
    "FEATURE_TRIAGE_FOLLOWUP",
    "STATUS_ABANDONED",
    "STATUS_ERROR",
    "STATUS_SUCCESS",
    "STATUS_TIMEOUT",
    "AiCallContext",
    "AiCallTracker",
    "get_last_event_id",
    "get_or_create_trace_id",
    "new_trace_id",
    "next_attempt_no",
    "record_ai_event",
    "record_quote_outcome",
    "set_last_event_id",
]
