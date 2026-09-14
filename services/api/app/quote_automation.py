"""Background quote automation for the lead → triage → quote loop.

Two workers, both scheduled via FastAPI ``BackgroundTasks`` so customer-facing
endpoints never wait on the LLM:

* :func:`auto_draft_quote_for_request` — when a public quote request is
  submitted, generate the same AI draft quote an electrician would get from
  ``POST /quotes/generate``.
* :func:`requote_after_triage_close` — when the AI triage chat closes,
  regenerate the linked draft quote's AI line items from the enriched request
  data (ai_extracted facts + full chat transcript), provided the electrician
  has not touched the quote yet.

Both workers open their own DB session (the request session is not committed
yet when background tasks run), use the decorator-free internal pipeline so
slowapi does not debit the tenant's rate-limit bucket, write the audit log
with a system actor (``None`` — the ``AuditLog.actor_id`` column allows it),
and swallow + log every failure so the scheduling request is never affected.
"""

import re
import time
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai_quality import capture_draft_feedback
from app.ai_telemetry import (
    ACTOR_SYSTEM,
    FEATURE_QUOTE_REFINE,
    FEATURE_TRIAGE_FOLLOWUP,
    AiCallContext,
    get_last_event_id,
    get_or_create_trace_id,
    next_attempt_no,
    set_last_event_id,
)
from app.audit import Actions, write_audit_log
from app.calculations import apply_quote_rounding, calculate_quote_totals
from app.database import get_db_session
from app.models import Quote, QuoteLineItem, QuoteRequest, Tenant
from app.push import notify_customer, notify_staff
from app.rls import set_tenant_in_session
from app.routers import quotes as quotes_router
from app.schemas import QuoteGenerateRequest, QuoteRead

logger = structlog.get_logger("api.quote_automation")


async def _notify_quote_ready(
    db: AsyncSession,
    tenant_id: UUID,
    quote: QuoteRead,
    quote_request_id: UUID | None,
) -> None:
    """Record quote_ready notifications and push to staff + customer devices."""
    await set_tenant_in_session(db, tenant_id)
    link = f"/quotes/{quote.id}"
    # recipient_id=None addresses every staff user of the tenant.
    await notify_staff(
        db,
        tenant_id,
        kind="quote_ready",
        title="Quote ready for review",
        body=f"AI draft quote '{quote.title}' is ready for your review.",
        link=link,
    )

    # The homeowner gets their own notification AND push when the lead is
    # linked to a customer account.
    if quote_request_id is not None:
        quote_request = await db.get(QuoteRequest, quote_request_id)
        if quote_request is not None and quote_request.customer_id is not None:
            await notify_customer(
                db,
                tenant_id,
                quote_request.customer_id,
                kind="quote_ready",
                title="Your quote is ready",
                body=f"Your quote '{quote.title}' is ready to view.",
                link=link,
            )


async def _notify_quote_failed(db: AsyncSession, tenant_id: UUID) -> None:
    """Record and push a quote_failed notification for the tenant's staff."""
    await set_tenant_in_session(db, tenant_id)
    await notify_staff(
        db,
        tenant_id,
        kind="quote_failed",
        title="Quote generation failed",
        body="Quote generation failed — please build it manually or retry.",
        link=None,
    )


async def generate_quote_async_worker(tenant_id: UUID, data: QuoteGenerateRequest) -> None:
    """Background worker behind ``POST /quotes/generate-async``.

    Runs the identical generation pipeline as the synchronous endpoint (via
    the decorator-free :func:`app.routers.quotes._generate_quote_impl`, with a
    system ``None`` audit actor), then records the outcome as persistent
    notifications: ``quote_ready`` for the tenant's staff — plus the linked
    customer when the lead has a customer account — on success, or
    ``quote_failed`` on error. Every failure is logged and swallowed.
    """
    try:
        async with get_db_session() as db:
            tenant = await db.get(Tenant, tenant_id)
            if tenant is None:
                logger.warning(
                    "async_generate_skipped", reason="tenant_not_found", tenant_id=str(tenant_id)
                )
                return
            quote = await quotes_router._generate_quote_impl(data, tenant, None, db)
            await _notify_quote_ready(db, tenant_id, quote, data.quote_request_id)
            await db.commit()
            logger.info(
                "async_generate_completed",
                tenant_id=str(tenant_id),
                quote_id=str(quote.id),
                total=str(quote.total),
            )
    except Exception as exc:
        logger.error(
            "async_generate_failed",
            tenant_id=str(tenant_id),
            quote_request_id=str(data.quote_request_id) if data.quote_request_id else None,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        try:
            async with get_db_session() as db:
                await _notify_quote_failed(db, tenant_id)
                await db.commit()
        except Exception as notify_exc:
            logger.error(
                "async_generate_failure_notification_failed",
                tenant_id=str(tenant_id),
                error=str(notify_exc),
                error_type=type(notify_exc).__name__,
            )


async def auto_draft_quote_for_request(tenant_id: UUID, quote_request_id: UUID) -> None:
    """Generate an AI draft quote for a freshly submitted public quote request.

    Reuses :func:`app.routers.quotes._generate_quote_impl` so the resulting
    quote is identical in shape to an electrician-generated one (linked
    ``quote_request_id``, AI flags, rag metadata, title from the lead).
    Low-confidence drafts automatically open AI triage with the customer.
    """
    try:
        async with get_db_session() as db:
            tenant = await db.get(Tenant, tenant_id)
            if tenant is None:
                logger.warning(
                    "auto_draft_skipped", reason="tenant_not_found", tenant_id=str(tenant_id)
                )
                return
            data = QuoteGenerateRequest(quote_request_id=quote_request_id)
            quote = await quotes_router._generate_quote_impl(data, tenant, None, db)
            logger.info(
                "auto_draft_quote_created",
                tenant_id=str(tenant_id),
                quote_request_id=str(quote_request_id),
                quote_id=str(quote.id),
                total=str(quote.total),
            )
            if quote.ai_confidence is not None and quote.ai_confidence < 0.8:
                await start_ai_triage(db, tenant, quote_request_id, float(quote.ai_confidence))
    except Exception as exc:
        logger.error(
            "auto_draft_quote_failed",
            tenant_id=str(tenant_id),
            quote_request_id=str(quote_request_id),
            error=str(exc),
            error_type=type(exc).__name__,
        )


async def email_triage_question(
    db: AsyncSession,
    tenant: Tenant,
    quote_request: QuoteRequest,
    question: str,
) -> None:
    """Email the customer an outstanding AI triage question (best-effort).

    Shared by the low-confidence auto-triage trigger and the ai-followup
    endpoint: in-app + push only reach customers with an account and the app
    installed, so the question also goes out by email. Customer-facing comm,
    so it is tenant-branded with the tenant's address as Reply-To. The wrapper
    logs a warning instead of dropping silently when the lead's contact has no
    email address.
    """
    from app.config import settings
    from app.email import send_customer_email
    from app.email_templates import triage_question as triage_question_template
    from app.models import Contact

    contact = (
        await db.get(Contact, quote_request.contact_id)
        if quote_request.contact_id is not None
        else None
    )
    app_origin = settings.app_public_url.rstrip("/") if settings.app_public_url else ""
    chat_url = f"{app_origin}/customer/chat/{quote_request.id}" if app_origin else None
    subject, html, text = triage_question_template(
        customer_name=contact.name.split()[0] if contact is not None and contact.name else "there",
        business_name=tenant.name,
        question=question,
        chat_url=chat_url,
    )
    await send_customer_email(
        db,
        tenant_id=tenant.id,
        contact_id=contact.id if contact is not None else None,
        purpose="triage question",
        to_email=contact.email if contact is not None else None,
        subject=subject,
        html_body=html,
        text_body=text,
        event="ai_followup_needed",
        template="triage_question",
        from_name=tenant.name,
        reply_to=tenant.email if tenant.email else None,
        context={
            "quote_request_id": str(quote_request.id),
            "contact_id": str(quote_request.contact_id),
            "customer_id": (str(quote_request.customer_id) if quote_request.customer_id else None),
            "tenant_id": str(tenant.id),
        },
    )


async def start_ai_triage(
    db: AsyncSession,
    tenant: Tenant,
    quote_request_id: UUID,
    quote_confidence: float,
) -> None:
    """Open AI triage with the customer when the first draft is low confidence.

    Generates the first clarifying message, persists it to the chat thread and
    notifies the customer with a link into the chat. Event-triggered from
    ``auto_draft_quote_for_request`` so the customer does not have to find the
    chat themselves.
    """
    from app.models import Communication
    from app.rag import generate_followup

    quote_request = await db.get(QuoteRequest, quote_request_id)
    if quote_request is None:
        return

    description = build_triage_description(quote_request)
    # Join the quote-level trace when the triage follows an AI draft so the
    # follow-up call lands in the same funnel.
    triage_trace_id: str | None = None
    if quote_request.quote_id is not None:
        linked_quote = await db.get(Quote, quote_request.quote_id)
        if linked_quote is not None:
            triage_trace_id = get_or_create_trace_id(linked_quote)
    telemetry = AiCallContext(
        feature=FEATURE_TRIAGE_FOLLOWUP,
        db=db,
        tenant_id=tenant.id,
        actor_type=ACTOR_SYSTEM,
        trace_id=triage_trace_id,
        quote_id=quote_request.quote_id,
        quote_request_id=quote_request_id,
    )
    try:
        result = await generate_followup(description, [], telemetry=telemetry)
    except RuntimeError as exc:
        logger.warning(
            "auto_triage_followup_failed",
            tenant_id=str(tenant.id),
            quote_request_id=str(quote_request_id),
            error=str(exc)[:200],
        )
        return

    confidence = int(result.get("confidence", 0))
    complete = bool(result.get("complete", False)) or confidence >= 80
    if complete:
        # First turn already confident — nothing to ask, no reason to notify.
        return

    body = result.get("message") or (
        "Could you share any other details that might help with the quote?"
    )
    ai_metadata: dict[str, Any] = {"complete": False, "confidence": confidence}
    options = result.get("options") or []
    if options:
        ai_metadata["options"] = options

    db.add(
        Communication(
            tenant_id=tenant.id,
            contact_id=quote_request.contact_id,
            quote_request_id=quote_request_id,
            channel="in_app_chat",
            direction="outbound",
            sender_role="ai",
            body=body,
            status="sent",
            ai_metadata=ai_metadata,
        )
    )

    if quote_request.customer_id is not None:
        await notify_customer(
            db,
            tenant.id,
            quote_request.customer_id,
            kind="chat_reply",
            title=f"{tenant.name} has a question about your quote request",
            body=body[:120] + ("…" if len(body) > 120 else ""),
            link=f"/chat/{quote_request_id}",
        )
    await email_triage_question(db, tenant, quote_request, body)
    await db.commit()
    logger.info(
        "auto_triage_started",
        tenant_id=str(tenant.id),
        quote_request_id=str(quote_request_id),
        quote_confidence=quote_confidence,
        triage_confidence=confidence,
    )


def _humanize_key(key: str) -> str:
    """Turn a camelCase/snake_case payload key into a readable label."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", key).replace("_", " ")
    return spaced.strip().lower()


def _format_answer(value: Any) -> str | None:
    """Render one captured answer as human-readable text; None means skip it."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (list, tuple)):
        items = [text for item in value if (text := _format_answer(item)) is not None]
        return ", ".join(items) if items else None
    return None


def _render_answers(label: str, answers: dict[str, Any]) -> str | None:
    """Render a dict of captured answers as ``label: key: value, ...``."""
    parts = []
    for key, value in answers.items():
        text = _format_answer(value)
        if text is not None:
            parts.append(f"{_humanize_key(str(key))}: {text}")
    if not parts:
        return None
    return f"{label}: " + ", ".join(parts)


# structured_data keys rendered by dedicated sections below (or internal-only),
# so the generic catch-all loop skips them.
_HANDLED_STRUCTURED_KEYS = frozenset(
    {
        "title",
        "category",
        "property",
        "questionnaire",
        "ai_extracted",
        "budgetContext",
        "preferredContact",
        "bestTimeToCall",
        "marketing_consent",
    }
)


def build_triage_description(quote_request: QuoteRequest) -> str:
    """Assemble the LLM triage context from a quote request (shared by the
    ai-followup endpoint and the low-confidence auto-triage trigger).

    Every fact the customer has already given — request detail, property
    profile, questionnaire answers, contact preferences, photos and anything
    confirmed earlier in the triage chat — is rendered under an explicit
    "already provided" banner. The follow-up question must acknowledge that
    information and ask only for what is missing: the original defect was the
    first follow-up re-asking for symptoms stated in the request and looping
    when the customer replied "no".
    """
    sd = quote_request.structured_data or {}

    problem_parts: list[str] = []
    title = sd.get("title") or ""
    category = sd.get("category")
    if title:
        problem_parts.append(str(title))
    if category and category != title:
        problem_parts.append(f"[{_humanize_key(str(category))}]")
    problem = " ".join(problem_parts)
    if quote_request.raw_text:
        problem = f"{problem} — {quote_request.raw_text}" if problem else quote_request.raw_text

    provided: list[str] = []

    property_profile = sd.get("property")
    if isinstance(property_profile, dict):
        rendered = _render_answers("Property", property_profile)
        if rendered:
            provided.append(rendered)

    questionnaire = sd.get("questionnaire")
    if isinstance(questionnaire, dict):
        for section, answers in questionnaire.items():
            label = _humanize_key(str(section))
            if isinstance(answers, dict):
                rendered = _render_answers(label.capitalize(), answers)
                if rendered:
                    provided.append(rendered)
            else:
                # Flat questionnaire shape (e.g. fault-finding's free-text
                # other_description, or the shared notes field) — the key is
                # the question label.
                text = _format_answer(answers)
                if text is not None:
                    provided.append(f"{label.capitalize()}: {text}")

    budget = sd.get("budgetContext")
    if isinstance(budget, dict):
        rendered = _render_answers("Budget context", budget)
        if rendered:
            provided.append(rendered)

    contact_pref = _format_answer(sd.get("preferredContact"))
    best_time = _format_answer(sd.get("bestTimeToCall"))
    pref_parts = []
    if contact_pref:
        pref_parts.append(f"preferred contact: {contact_pref}")
    if best_time:
        pref_parts.append(f"best time to call: {best_time}")
    if pref_parts:
        provided.append("Contact preferences: " + ", ".join(pref_parts))

    # Facts the customer confirmed in earlier triage turns (persisted by the
    # ai-followup endpoint) — re-feeding them is what stops the assistant
    # asking the same question twice.
    ai_extracted = sd.get("ai_extracted")
    if isinstance(ai_extracted, dict):
        rendered = _render_answers("Already confirmed during triage", ai_extracted)
        if rendered:
            provided.append(rendered)

    # Catch-all for keys added by new intake versions, so future answers are
    # never silently dropped from the triage context.
    for key, value in sd.items():
        if key in _HANDLED_STRUCTURED_KEYS:
            continue
        if isinstance(value, dict):
            rendered = _render_answers(_humanize_key(str(key)).capitalize(), value)
            if rendered:
                provided.append(rendered)
        else:
            text = _format_answer(value)
            if text is not None:
                provided.append(f"{_humanize_key(str(key)).capitalize()}: {text}")

    if quote_request.urgency:
        provided.append(f"Urgency: {_humanize_key(quote_request.urgency)}")

    dates = [
        str(entry["date"])
        for entry in quote_request.preferred_dates or []
        if isinstance(entry, dict) and entry.get("date")
    ]
    if dates:
        provided.append("Preferred visit dates: " + ", ".join(dates))

    photo_count = len(quote_request.media_urls or [])
    if photo_count:
        provided.append(f"Photos attached: {photo_count}")

    if not problem and not provided:
        return "Electrical work requested by a customer."

    parts: list[str] = []
    if problem:
        parts.append(f"Customer's stated problem: {problem}")
    if provided:
        parts.append(
            "The customer has ALREADY PROVIDED everything below — never ask for it "
            "again. Acknowledge it (especially in your first message) and only ask "
            "about details that are still missing:\n" + "\n".join(provided)
        )
    parts.append(
        "If the customer declines or cannot answer a question, do NOT repeat it — "
        "move on to the next most valuable missing detail, or close the conversation."
    )

    return "\n\n".join(parts) or "Electrical work requested by a customer."


async def requote_after_triage_close(tenant_id: UUID, quote_request_id: UUID) -> None:
    """Regenerate the linked draft quote's AI line items after triage closes.

    Skipped (and logged) when there is no linked quote, the quote is no longer
    a draft, or any line item is no longer ``ai_generated`` — i.e. the
    electrician has taken over the draft.
    """
    try:
        async with get_db_session() as db:
            await set_tenant_in_session(db, tenant_id)
            tenant = await db.get(Tenant, tenant_id)
            if tenant is None:
                logger.warning(
                    "requote_skipped", reason="tenant_not_found", tenant_id=str(tenant_id)
                )
                return

            quote_request = await db.get(QuoteRequest, quote_request_id)
            if (
                quote_request is None
                or quote_request.tenant_id != tenant_id
                or quote_request.quote_id is None
            ):
                logger.info(
                    "requote_skipped",
                    reason="no_linked_quote",
                    quote_request_id=str(quote_request_id),
                )
                return

            quote = await db.scalar(
                select(Quote)
                .options(selectinload(Quote.line_items))
                .where(Quote.id == quote_request.quote_id, Quote.tenant_id == tenant_id)
            )
            if quote is None:
                logger.info(
                    "requote_skipped",
                    reason="quote_not_found",
                    quote_request_id=str(quote_request_id),
                )
                return
            if quote.status != "draft":
                logger.info(
                    "requote_skipped",
                    reason="status",
                    quote_id=str(quote.id),
                    status=quote.status,
                )
                return
            if any(not item.ai_generated for item in quote.line_items):
                logger.info("requote_skipped", reason="manual_edits", quote_id=str(quote.id))
                return

            # Same description the generate path builds: lead data (now with
            # ai_extracted facts) plus the full triage chat transcript.
            description = quotes_router._build_lead_description(quote_request)
            description = await quotes_router._append_chat_context(
                db, tenant_id, quote_request, description
            )

            started = time.perf_counter()
            # Same trace as the original draft, linked as a child regeneration.
            requote_telemetry = AiCallContext(
                feature=FEATURE_QUOTE_REFINE,
                db=db,
                tenant_id=tenant_id,
                actor_type=ACTOR_SYSTEM,
                trace_id=get_or_create_trace_id(quote),
                parent_event_id=get_last_event_id(quote),
                attempt_no=next_attempt_no(quote),
                quote_id=quote.id,
                quote_request_id=quote_request_id,
            )
            retrieved, retrieval_status = await quotes_router.search_cost_items_with_status(  # type: ignore[attr-defined]
                description
            )
            generated = await quotes_router.generate_quote_from_prompt(  # type: ignore[attr-defined]
                job_description=description,
                cost_items=retrieved,
                tenant_settings=tenant.settings,
                telemetry=requote_telemetry,
            )
            completeness = quotes_router._intake_completeness(description, quote_request)
            validated = quotes_router.validate_generated_quote(  # type: ignore[attr-defined]
                generated=generated,
                retrieved_items=retrieved,
                tenant_settings=tenant.settings,
                completeness=completeness,
            )
            if not validated["line_items"]:
                logger.warning(
                    "requote_empty",
                    quote_id=str(quote.id),
                    quote_request_id=str(quote_request_id),
                )
                return

            # Every existing line is AI-generated (checked above), so the whole
            # draft is replaced in place, exactly like a refine with no manual
            # lines to preserve.
            for item in list(quote.line_items):
                await db.delete(item)
            quote.line_items = []
            for line in validated["line_items"]:
                quote.line_items.append(
                    QuoteLineItem(
                        tenant_id=tenant_id,
                        description=line["description"],
                        quantity=line["quantity"],
                        unit_price=line["unit_price"],
                        ai_generated=True,
                    )
                )
            calculate_quote_totals(quote)
            apply_quote_rounding(quote, tenant.settings)

            previous_rag = (quote.extra_data or {}).get("rag")
            quote.extra_data = {
                **(quote.extra_data or {}),
                "rag": {
                    "confidence": validated["confidence"],
                    "warnings": validated["warnings"],
                    "assumptions": validated.get("assumptions", []),
                    "notes": validated["notes"],
                    "retrieval_status": retrieval_status,
                    "generation_seconds": round(time.perf_counter() - started, 2),
                    "completeness": completeness,
                    "requote_after_triage": True,
                },
            }
            llm_usage = quotes_router._accumulate_llm_usage(
                previous_rag if isinstance(previous_rag, dict) else {},
                generated.get("usage"),
                generated.get("model"),
            )
            if llm_usage is not None:
                quote.extra_data["rag"]["llm_usage"] = llm_usage
            set_last_event_id(quote, requote_telemetry.event_id)
            quotes_router._snapshot_ai_draft(quote)
            await capture_draft_feedback(db, quote)

            await db.flush()
            await write_audit_log(
                db,
                tenant_id=tenant_id,
                actor=None,
                action=Actions.QUOTE_UPDATED,
                entity_type="quote",
                entity_id=quote.id,
                payload={
                    "requote_after_triage": True,
                    "quote_request_id": str(quote_request_id),
                    "confidence": validated["confidence"],
                    "total": str(quote.total),
                },
            )
            await db.commit()
            logger.info(
                "requote_completed",
                quote_id=str(quote.id),
                quote_request_id=str(quote_request_id),
                total=str(quote.total),
            )
    except Exception as exc:
        logger.error(
            "requote_failed",
            tenant_id=str(tenant_id),
            quote_request_id=str(quote_request_id),
            error=str(exc),
            error_type=type(exc).__name__,
        )
