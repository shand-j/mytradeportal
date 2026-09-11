"""Communication log and in-app chat endpoints."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings as settings
from app.database import get_db
from app.dependencies import TenantDep, _extract_token
from app.models import Communication, Contact, Customer, QuoteRequest, User
from app.push import notify_customer, notify_staff
from app.quote_automation import (
    build_triage_description,
    email_triage_question,
    requote_after_triage_close,
)
from app.rag import generate_followup
from app.rls import set_tenant_in_session
from app.schemas import CommunicationCreate, CommunicationRead
from app.security import decode_access_token

router = APIRouter(prefix="/communications", tags=["Communications"])
DbDep = Annotated[AsyncSession, Depends(get_db)]


async def _get_current_actor(
    request: Request,
    db: DbDep,
) -> User | Customer:
    """Accept either a staff user token or a customer token."""
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    claims = decode_access_token(token)
    if claims is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    subject_type = claims.get("subject_type")
    if subject_type == "customer":
        try:
            customer_id = UUID(str(claims.get("sub")))
            tenant_id = UUID(str(claims.get("tenant_id")))
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
            ) from exc
        await set_tenant_in_session(db, tenant_id)
        customer = await db.get(Customer, customer_id)
        if customer is None or not customer.is_active or customer.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )
        return customer

    # Staff user token.
    try:
        user_id = UUID(str(claims.get("sub")))
        tenant_id = UUID(str(claims.get("tenant_id")))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc
    await set_tenant_in_session(db, tenant_id)
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


ActorDep = Annotated[User | Customer, Depends(_get_current_actor)]


async def _get_quote_request(
    db: AsyncSession, tenant_id: UUID, quote_request_id: UUID
) -> QuoteRequest:
    """Fetch a quote request and enforce tenant isolation."""
    await set_tenant_in_session(db, tenant_id)
    quote_request = await db.scalar(
        select(QuoteRequest)
        .options(selectinload(QuoteRequest.contact))
        .where(QuoteRequest.id == quote_request_id, QuoteRequest.tenant_id == tenant_id)
    )
    if quote_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote request not found")
    return quote_request


def _ensure_actor_can_access_quote_request(
    actor: User | Customer, quote_request: QuoteRequest
) -> None:
    """Customers may only access their own quote requests; staff can access any."""
    if isinstance(actor, Customer) and quote_request.customer_id != actor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorised to access this quote request",
        )


async def _notify_staff_customer_reply(
    db: AsyncSession,
    tenant_id: UUID,
    quote_request: QuoteRequest,
    body: str,
) -> None:
    """Notify tenant staff that a customer replied in a chat thread."""
    snippet = body[:80] + ("…" if len(body) > 80 else "")
    await notify_staff(
        db,
        tenant_id,
        kind="chat_reply",
        title="Customer replied",
        body=snippet or "Customer sent a new chat message.",
        link=f"/chat/{quote_request.id}",
    )


async def _notify_staff_triage_closed(
    db: AsyncSession,
    tenant_id: UUID,
    quote_request: QuoteRequest,
    requires_callback: bool,
) -> None:
    """Notify staff when the AI intake chat closes for a lead."""
    if requires_callback:
        title = "Triage needs your callback"
        body = "The AI chat closed without full confidence — please call the customer to finalise."
    else:
        title = "Triage complete — quote refreshing"
        body = "The AI chat gathered enough info; the draft quote is being refreshed."
    # Land on the linked quote when one exists; otherwise the chat thread.
    link = (
        f"/quotes/{quote_request.quote_id}"
        if quote_request.quote_id is not None
        else f"/chat/{quote_request.id}"
    )
    await notify_staff(
        db,
        tenant_id,
        kind="triage_closed",
        title=title,
        body=body,
        link=link,
    )


@router.get("", response_model=list[CommunicationRead])
async def list_communications(
    tenant: TenantDep,
    actor: ActorDep,
    db: DbDep,
    quote_request_id: UUID | None = Query(None),
) -> list[Communication]:
    """List communications for the current tenant, optionally filtered by thread."""
    await set_tenant_in_session(db, tenant.id)

    if quote_request_id is not None:
        quote_request = await _get_quote_request(db, tenant.id, quote_request_id)
        _ensure_actor_can_access_quote_request(actor, quote_request)

    stmt = (
        select(Communication)
        .where(Communication.tenant_id == tenant.id)
        .order_by(Communication.created_at.asc())
    )
    if quote_request_id is not None:
        stmt = stmt.where(Communication.quote_request_id == quote_request_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CommunicationRead)
async def create_communication(
    data: CommunicationCreate,
    tenant: TenantDep,
    actor: ActorDep,
    db: DbDep,
) -> Communication:
    """Log a communication for the current tenant."""
    await set_tenant_in_session(db, tenant.id)

    if data.contact_id:
        contact = await db.get(Contact, data.contact_id)
        if contact is None or contact.tenant_id != tenant.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid contact")

    if data.quote_request_id:
        quote_request = await _get_quote_request(db, tenant.id, data.quote_request_id)
        _ensure_actor_can_access_quote_request(actor, quote_request)
        # Thread messages inherit the lead's contact so CRM views and exports
        # can attribute them (customer chat previously stored NULL).
        if data.contact_id is None and quote_request.contact_id is not None:
            data.contact_id = quote_request.contact_id

    # Derive the sender role from the authenticated actor so a customer token
    # cannot impersonate business staff (and vice versa). Direction is
    # overridden the same way: it is always from the tenant's perspective, so
    # customer-authored messages are inbound regardless of client payload.
    resolved_role = "customer" if isinstance(actor, Customer) else "business"
    direction = "inbound" if isinstance(actor, Customer) else "outbound"
    communication = Communication(
        tenant_id=tenant.id,
        **data.model_dump(exclude={"sender_role", "direction"}),
        sender_role=resolved_role,
        direction=direction,
    )
    db.add(communication)
    # Notify staff on a customer reply only once AI triage has closed — while
    # the triage assistant is mid-conversation the electrician doesn't need a
    # bell for every interim answer.
    if resolved_role == "customer" and data.quote_request_id:
        triage_closed = await db.scalar(
            select(func.count())
            .select_from(Communication)
            .where(
                Communication.tenant_id == tenant.id,
                Communication.quote_request_id == data.quote_request_id,
                Communication.sender_role == "ai",
                Communication.ai_metadata["complete"].astext == "true",
            )
        )
        if triage_closed:
            await _notify_staff_customer_reply(db, tenant.id, quote_request, data.body or "")
    await db.commit()
    await db.refresh(communication)
    return communication


@router.post("/{quote_request_id}/ai-followup", response_model=CommunicationRead)
async def ai_followup(
    quote_request_id: UUID,
    background_tasks: BackgroundTasks,
    tenant: TenantDep,
    actor: ActorDep,
    db: DbDep,
) -> Communication:
    """Generate a clarifying question for the customer and persist it as a chat message.

    The endpoint is idempotent: if the latest thread message is an unanswered
    AI question it is returned unchanged (no near-identical re-asks), and once
    the conversation has closed the closure message is returned. The mobile app
    should normally call it once when the chat thread is first opened and again
    after each customer reply.
    """
    await set_tenant_in_session(db, tenant.id)

    quote_request = await _get_quote_request(db, tenant.id, quote_request_id)
    _ensure_actor_can_access_quote_request(actor, quote_request)

    prior = await db.execute(
        select(Communication)
        .where(
            Communication.tenant_id == tenant.id,
            Communication.quote_request_id == quote_request_id,
        )
        .order_by(Communication.created_at.asc())
    )
    prior_records = list(prior.scalars().all())
    # generate_followup applies its own tail cap + warning; here we just build
    # the full chronological transcript.
    prior_messages = [
        {"role": comm.sender_role, "text": comm.body or ""} for comm in prior_records if comm.body
    ]

    # If the conversation already has a closure message, return it instead of
    # asking another question. This keeps the chat from looping forever once the
    # AI has decided it has enough detail.
    existing_closure = next(
        (
            comm
            for comm in reversed(prior_records)
            if comm.sender_role == "ai" and comm.ai_metadata.get("complete")
        ),
        None,
    )
    if existing_closure:
        return existing_closure

    # Dedupe guard: if the customer has not answered the latest AI question
    # yet, return it unchanged instead of stacking another near-identical one.
    if prior_records and prior_records[-1].sender_role == "ai":
        return prior_records[-1]

    max_followup_turns = settings.max_followup_turns
    ai_turn_count = sum(1 for comm in prior_records if comm.sender_role == "ai")

    description = build_triage_description(quote_request)

    try:
        result = await generate_followup(
            description,
            prior_messages,
            final_turn=ai_turn_count + 1 >= max_followup_turns,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    confidence = int(result.get("confidence", 0))
    complete = bool(result.get("complete", False)) or confidence >= 80
    options = result.get("options") or []
    suggested_questions = result.get("suggested_questions") or []

    # Persist facts the customer explicitly stated so they inform quote
    # generation without the electrician re-asking for them.
    extracted = result.get("extracted")
    if isinstance(extracted, dict) and extracted:
        structured = dict(quote_request.structured_data or {})
        ai_extracted = structured.get("ai_extracted")
        if not isinstance(ai_extracted, dict):
            ai_extracted = {}
        structured["ai_extracted"] = {**ai_extracted, **extracted}
        quote_request.structured_data = structured

    # Force a graceful closure once we reach the final allowed turn or the
    # confidence threshold, so the customer always gets a clear next step. A
    # turn-cap closure without confidence flags the lead for a callback. The
    # final turn is `ai_turn_count + 1` (this call), so the flow is: initial
    # question + up to (max_followup_turns - 1) answers, then always a closure
    # — never an open-ended "the electrician will call" with complete=false.
    if complete or ai_turn_count + 1 >= max_followup_turns:
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

    assistant_message = Communication(
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
    db.add(assistant_message)
    # Surface the AI's reply to the customer: persistent in-app notification
    # plus a push, so they don't have to stumble onto the chat banner.
    if quote_request.customer_id is not None:
        snippet = body[:80] + ("…" if len(body) > 80 else "")
        await notify_customer(
            db,
            tenant.id,
            quote_request.customer_id,
            kind="chat_message",
            title=f"New message from {tenant.name}",
            body=snippet,
            link=f"/customer/chat/{quote_request_id}",
        )
    # A still-open AI question also goes out by email: in-app + push only reach
    # customers with an account and the app installed. Best-effort; the wrapper
    # logs (and never raises) on failure or a missing contact email.
    if not closed:
        await email_triage_question(db, tenant, quote_request, body)
    await db.commit()
    await db.refresh(assistant_message)

    if closed:
        # Notify staff up-front — the requote is a background LLM call that
        # takes 60-120s, so surfacing "triage complete" now avoids the bell
        # staying silent until the requote finishes.
        await _notify_staff_triage_closed(
            db, tenant.id, quote_request, bool(quote_request.requires_callback)
        )
        await db.commit()
        # Triage finished with richer data (ai_extracted facts + full chat):
        # refresh the linked AI draft quote in the background if the
        # electrician has not touched it yet.
        background_tasks.add_task(requote_after_triage_close, tenant.id, quote_request_id)

    return assistant_message
