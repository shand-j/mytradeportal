"""Guest-scoped public chat threads for the inline AI intake check.

A homeowner who submits a quote request with ``sync_check=true`` may get an
immediate AI follow-up question plus a guest thread token. These endpoints
let them read the thread and answer inline — no account, no app install —
authenticated only by the guest JWT (``subject_type="guest"``, scoped to one
quote request, TTL ``GUEST_THREAD_TTL_MINUTES``).

The AI turn reuses the same ``generate_followup`` machinery and closure
rules as the authenticated ``/communications/{id}/ai-followup`` endpoint
(confidence ≥ 80 or the turn cap closes the thread; a turn-cap closure flags
the lead for a callback). The portal awaits the reply synchronously, so the
turn is bounded by its own (larger) timeout —
``settings.guest_followup_timeout_seconds`` — rather than the intake check's
12s budget. AI failures fail open: the customer's message is always
persisted and returned, ``ai_reply`` is simply absent — never a 5xx. On
closure the existing background requote is scheduled.
"""

import asyncio
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_telemetry import ACTOR_CUSTOMER, FEATURE_TRIAGE_FOLLOWUP, AiCallContext
from app.config import settings
from app.database import get_db
from app.dependencies import _extract_token
from app.guest_auth import verify_guest_token
from app.limiter import limiter
from app.models import Communication, QuoteRequest, Tenant
from app.quote_automation import build_triage_description, requote_after_triage_close
from app.rag import generate_followup
from app.rls import set_tenant_in_session
from app.routers.communications import _notify_staff_triage_closed

router = APIRouter(prefix="/public/threads", tags=["Public Threads"])
DbDep = Annotated[AsyncSession, Depends(get_db)]
logger = structlog.get_logger("api.public_threads")


class GuestThreadMessage(BaseModel):
    """One chat message as exposed to the guest (no tenant/contact internals)."""

    id: UUID
    sender_role: str
    body: str | None
    created_at: datetime


class GuestThreadMessages(BaseModel):
    messages: list[GuestThreadMessage]


class GuestThreadPostCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=2000)


class GuestAiReply(BaseModel):
    body: str


class GuestThreadPostResponse(BaseModel):
    message: GuestThreadMessage
    ai_reply: GuestAiReply | None = None
    closed: bool = False


async def _get_guest_thread(
    qr_id: UUID,
    request: Request,
    db: DbDep,
) -> tuple[Tenant, QuoteRequest]:
    """Authenticate the guest token and load the scoped quote request."""
    token = _extract_token(request)
    claims = verify_guest_token(token, qr_id) if token else None
    if claims is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid guest token")
    try:
        tenant_id = UUID(str(claims.get("tenant_id")))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid guest token"
        ) from exc

    await set_tenant_in_session(db, tenant_id)
    tenant = await db.get(Tenant, tenant_id)
    quote_request = await db.scalar(
        select(QuoteRequest).where(
            QuoteRequest.id == qr_id,
            QuoteRequest.tenant_id == tenant_id,
        )
    )
    if tenant is None or quote_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote request not found")
    return tenant, quote_request


def _message_read(comm: Communication) -> GuestThreadMessage:
    return GuestThreadMessage(
        id=comm.id,
        sender_role=comm.sender_role,
        body=comm.body,
        created_at=comm.created_at,
    )


@router.get("/{qr_id}/messages", response_model=GuestThreadMessages)
@limiter.limit("30/minute")
async def list_guest_messages(
    qr_id: UUID,
    request: Request,
    db: DbDep,
) -> GuestThreadMessages:
    """List the guest thread's messages in chronological order."""
    tenant, _quote_request = await _get_guest_thread(qr_id, request, db)
    result = await db.scalars(
        select(Communication)
        .where(
            Communication.tenant_id == tenant.id,
            Communication.quote_request_id == qr_id,
        )
        .order_by(Communication.created_at.asc())
    )
    return GuestThreadMessages(messages=[_message_read(comm) for comm in result.all()])


@router.post("/{qr_id}/messages", response_model=GuestThreadPostResponse)
@limiter.limit("10/minute")
async def post_guest_message(
    qr_id: UUID,
    data: GuestThreadPostCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: DbDep,
) -> GuestThreadPostResponse:
    """Post a guest (customer) reply and run the bounded AI follow-up turn.

    Mirrors the closure rules of ``/communications/{id}/ai-followup``: an
    already-closed thread returns the closure message; confidence ≥ 80 or the
    final allowed turn closes with a thank-you (or callback-flagged) message;
    closure schedules the background requote. The awaited AI call is wrapped
    in ``settings.guest_followup_timeout_seconds`` and every failure returns
    the customer message without an ``ai_reply``.
    """
    tenant, quote_request = await _get_guest_thread(qr_id, request, db)

    customer_message = Communication(
        tenant_id=tenant.id,
        contact_id=quote_request.contact_id,
        quote_request_id=qr_id,
        channel="in_app_chat",
        direction="inbound",
        sender_role="customer",
        body=data.body,
        status="sent",
    )
    db.add(customer_message)
    await db.flush()

    prior = await db.execute(
        select(Communication)
        .where(
            Communication.tenant_id == tenant.id,
            Communication.quote_request_id == qr_id,
        )
        .order_by(Communication.created_at.asc())
    )
    prior_records = list(prior.scalars().all())
    prior_messages = [
        {"role": comm.sender_role, "text": comm.body or ""} for comm in prior_records if comm.body
    ]

    # Thread already closed (e.g. the background auto-triage finished first):
    # return the closure message, same as the ai-followup endpoint.
    existing_closure = next(
        (
            comm
            for comm in reversed(prior_records)
            if comm.sender_role == "ai" and comm.ai_metadata.get("complete")
        ),
        None,
    )
    if existing_closure is not None:
        await db.commit()
        await db.refresh(customer_message)
        return GuestThreadPostResponse(
            message=_message_read(customer_message),
            ai_reply=GuestAiReply(body=existing_closure.body or ""),
            closed=True,
        )

    ai_turn_count = sum(1 for comm in prior_records if comm.sender_role == "ai")
    description = build_triage_description(quote_request)

    result: dict[str, Any] | None = None
    try:
        result = await asyncio.wait_for(
            generate_followup(
                description,
                prior_messages,
                final_turn=ai_turn_count + 1 >= settings.max_followup_turns,
                telemetry=AiCallContext(
                    feature=FEATURE_TRIAGE_FOLLOWUP,
                    db=db,
                    tenant_id=tenant.id,
                    actor_type=ACTOR_CUSTOMER,
                    # Mirrors the ai-followup endpoint, which receives no
                    # entry channel and leaves it None.
                    quote_request_id=qr_id,
                ),
            ),
            timeout=settings.guest_followup_timeout_seconds,
        )
    except Exception as exc:
        # Timeout, RuntimeError from the LLM layer, anything: fail open. The
        # customer's message is already persisted; the staff dashboard still
        # shows it and the background draft is unaffected.
        logger.warning(
            "guest_followup_failed",
            tenant_id=str(tenant.id),
            quote_request_id=str(qr_id),
            error_type=type(exc).__name__,
            error=str(exc)[:200],
        )
    if result is None:
        await db.commit()
        await db.refresh(customer_message)
        return GuestThreadPostResponse(message=_message_read(customer_message))

    confidence = int(result.get("confidence", 0))
    complete = bool(result.get("complete", False)) or confidence >= 80
    options = result.get("options") or []
    suggested_questions = result.get("suggested_questions") or []

    # Persist facts the customer explicitly stated so quote generation (and
    # the requote on close) uses them without re-asking.
    extracted = result.get("extracted")
    if isinstance(extracted, dict) and extracted:
        structured = dict(quote_request.structured_data or {})
        ai_extracted = structured.get("ai_extracted")
        if not isinstance(ai_extracted, dict):
            ai_extracted = {}
        structured["ai_extracted"] = {**ai_extracted, **extracted}
        quote_request.structured_data = structured

    # Closure rules identical to the ai-followup endpoint: close on
    # confidence or force a graceful closure on the final allowed turn.
    if complete or ai_turn_count + 1 >= settings.max_followup_turns:
        if complete:
            quote_request.requires_callback = False
            body = (
                "Thank you for the details. The electrician will review your request "
                "and you'll be notified once the quote is ready."
            )
            ai_metadata: dict[str, Any] = {
                "complete": True,
                "confidence": max(confidence, 80),
                "requires_callback": False,
            }
        else:
            quote_request.requires_callback = True
            body = (
                "Thanks — the electrician has everything you sent and will give you "
                "a call to go over a few last details before quoting."
            )
            ai_metadata = {
                "complete": True,
                "confidence": confidence,
                "requires_callback": True,
            }
            if suggested_questions:
                ai_metadata["suggested_questions"] = suggested_questions
        closed = True
    else:
        body = result.get("message") or (
            "Could you share any other details that might help with the quote?"
        )
        ai_metadata = {"complete": False, "confidence": confidence}
        if options:
            ai_metadata["options"] = options
        closed = False

    db.add(
        Communication(
            tenant_id=tenant.id,
            contact_id=quote_request.contact_id,
            quote_request_id=qr_id,
            channel="in_app_chat",
            direction="outbound",
            sender_role="ai",
            body=body,
            status="sent",
            ai_metadata=ai_metadata,
        )
    )
    await db.commit()

    if closed:
        # Staff hear about the closure up-front; the requote runs in the
        # background (60-120s) exactly like the authenticated endpoint.
        await _notify_staff_triage_closed(
            db, tenant.id, quote_request, bool(quote_request.requires_callback)
        )
        await db.commit()
        background_tasks.add_task(requote_after_triage_close, tenant.id, qr_id)

    await db.refresh(customer_message)
    return GuestThreadPostResponse(
        message=_message_read(customer_message),
        ai_reply=GuestAiReply(body=body),
        closed=closed,
    )
