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

import time
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import Actions, write_audit_log
from app.calculations import calculate_quote_totals
from app.database import get_db_session
from app.models import Notification, PushToken, Quote, QuoteLineItem, QuoteRequest, Tenant
from app.push import send_expo_push
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
    """Record quote_ready notifications and push to staff devices (best-effort)."""
    await set_tenant_in_session(db, tenant_id)
    body = f"AI draft quote '{quote.title}' is ready for your review."
    link = f"/quotes/{quote.id}"
    # recipient_id=None addresses every staff user of the tenant.
    db.add(
        Notification(
            tenant_id=tenant_id,
            recipient_type="staff",
            recipient_id=None,
            type="quote_ready",
            title="Quote ready for review",
            body=body,
            link=link,
        )
    )

    # The homeowner gets their own notification when the lead is linked to a
    # customer account.
    if quote_request_id is not None:
        quote_request = await db.get(QuoteRequest, quote_request_id)
        if quote_request is not None and quote_request.customer_id is not None:
            db.add(
                Notification(
                    tenant_id=tenant_id,
                    recipient_type="customer",
                    recipient_id=quote_request.customer_id,
                    type="quote_ready",
                    title="Your quote is ready",
                    body=f"Your quote '{quote.title}' is ready to view.",
                    link=link,
                )
            )

    tokens = (
        (
            await db.execute(
                select(PushToken.token).where(
                    PushToken.tenant_id == tenant_id,
                    PushToken.owner_type == "staff",
                )
            )
        )
        .scalars()
        .all()
    )
    await send_expo_push(list(tokens), "Quote ready for review", body, data={"link": link})


async def _notify_quote_failed(db: AsyncSession, tenant_id: UUID) -> None:
    """Record a quote_failed notification for the tenant's staff."""
    await set_tenant_in_session(db, tenant_id)
    db.add(
        Notification(
            tenant_id=tenant_id,
            recipient_type="staff",
            recipient_id=None,
            type="quote_failed",
            title="Quote generation failed",
            body="Quote generation failed — please build it manually or retry.",
            link=None,
        )
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
    except Exception as exc:
        logger.error(
            "auto_draft_quote_failed",
            tenant_id=str(tenant_id),
            quote_request_id=str(quote_request_id),
            error=str(exc),
            error_type=type(exc).__name__,
        )


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
            retrieved, retrieval_status = await quotes_router.search_cost_items_with_status(  # type: ignore[attr-defined]
                description
            )
            generated = await quotes_router.generate_quote_from_prompt(  # type: ignore[attr-defined]
                job_description=description,
                cost_items=retrieved,
                tenant_settings=tenant.settings,
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
            )
            if llm_usage is not None:
                quote.extra_data["rag"]["llm_usage"] = llm_usage
            quotes_router._snapshot_ai_draft(quote)

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
