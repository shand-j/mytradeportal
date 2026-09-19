"""Shared quote accept/decline transitions for customer-facing flows.

Both customer-facing action paths — the authenticated portal endpoints
(``POST /customer/quotes/{id}/accept|reject``) and the token-authorized
emailed web page (``POST /public/quote/{token}/accept|decline``) — run the
same state transition, staff notification, outcome event and confirmation
email. The logic lives here so the two routers can never drift apart.

Callers own the preconditions (status check, RLS scoping) and re-fetch
whatever they need for their response afterwards.

Draft jobs: when the customer submits ranked date/time preferences, the
acceptance also creates a tentative DRAFT job pre-filled with their 1st
choice (:func:`ensure_draft_job`). A draft job never blocks the calendar
(see ``app.availability``) and never emails the customer a booking
confirmation — it exists so the electrician has one tap to confirm
(convert-to-job adopts it) or reschedule onto the 2nd/3rd choice.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.ai_telemetry import record_quote_outcome
from app.email import send_customer_email
from app.email_templates import quote_accepted as quote_accepted_template
from app.models import Contact, Job, QuoteLineItem
from app.portal_links import magic_link_url, portal_url
from app.preferred_dates import first_preferred_date
from app.push import notify_staff
from app.work_blocks import estimate_hours_from_lines

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models import Customer, Quote, Tenant


async def apply_quote_acceptance(
    db: AsyncSession,
    *,
    quote: Quote,
    tenant: Tenant | None,
    customer_name: str,
    preferred_dates: list[str] | None,
    outcome_payload: dict[str, Any],
    email_contact_id: UUID | None,
    email_to: str | None,
    customer: Customer | None = None,
) -> None:
    """Transition a sent quote to accepted and run the customer side effects.

    ``customer`` is the portal account when one exists (authenticated path,
    or an emailed-link accept whose recipient matches an account): the
    confirmation email then carries a magic sign-in link so the customer can
    track the booking without a password. Commits the transition before the
    (best-effort) confirmation email, then commits again so any email-failure
    staff alert persists.
    """
    quote.status = "approved"
    quote.approved_at = datetime.utcnow()
    # The customer's reconfirmed dates ride on the quote so they surface when
    # the electrician converts it to a job.
    if preferred_dates is not None:
        quote.accepted_dates = preferred_dates
    dates_note = ""
    draft_note = ""
    if quote.accepted_dates:
        dates_note = f" Customer confirmed preferred dates: {', '.join(quote.accepted_dates)}."
        # Tentative hold on the customer's 1st choice; the electrician confirms
        # or moves it to the 2nd/3rd choice when scheduling.
        draft_job = await ensure_draft_job(db, quote=quote)
        if draft_job is not None:
            draft_note = " A draft job was created from their first choice."
    await notify_staff(
        db,
        quote.tenant_id,
        kind="quote_accepted",
        title="Quote accepted",
        body=f"{customer_name} accepted quote '{quote.title}'.{dates_note}{draft_note}",
        link=f"/quotes/{quote.id}",
    )
    await record_quote_outcome(
        db,
        outcome="quote_accepted",
        tenant_id=quote.tenant_id,
        quote=quote,
        extra_payload=outcome_payload,
    )
    business_name = tenant.name if tenant is not None else "Your electrician"
    magic_link: str | None = None
    portal_home: str | None = None
    if tenant is not None:
        portal_home = portal_url(tenant, "/quotes")
        if customer is not None:
            magic_link = await magic_link_url(db, tenant, customer, f"/quotes/{quote.id}")
    await db.commit()
    # Confirm the acceptance to the customer by email. No response is expected,
    # so it goes out platform-branded from the no-reply sender. Best-effort:
    # the wrapper logs and never raises.
    template_kwargs: dict[str, Any] = {
        "customer_name": customer_name.split()[0] if customer_name else "there",
        "business_name": business_name,
        "quote_title": quote.title,
        "quote_total": f"£{quote.total}",
    }
    # The email-template rewrite (magic-link + booking-pending copy) ships
    # separately; pass the new kwargs only when the template accepts them so
    # this call site works against both versions. The template's ``portal_url``
    # is the magic sign-in link (falling back to the plain portal home page).
    accepted_params = inspect.signature(quote_accepted_template).parameters
    accepts_var_kwargs = any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in accepted_params.values()
    )
    for key, value in (
        ("magic_link", magic_link),
        ("portal_url", magic_link or portal_home),
    ):
        if value is not None and (accepts_var_kwargs or key in accepted_params):
            template_kwargs[key] = value
    subject, html, text = quote_accepted_template(**template_kwargs)
    await send_customer_email(
        db,
        tenant_id=quote.tenant_id,
        contact_id=email_contact_id,
        purpose="quote confirmation",
        to_email=email_to,
        subject=subject,
        html_body=html,
        text_body=text,
        event="quote_accepted",
        template="quote_accepted",
        context={
            "quote_id": str(quote.id),
            "tenant_id": str(quote.tenant_id),
            **({"customer_id": str(customer.id)} if customer is not None else {}),
        },
    )
    # The acceptance commit already happened above; persist any email-failure
    # alert the send just raised (no-op when the send succeeded).
    await db.commit()


async def apply_quote_decline(db: AsyncSession, *, quote: Quote) -> None:
    """Transition a sent quote to declined and commit."""
    quote.status = "rejected"
    quote.approved_at = None
    await db.commit()


# Start time for a draft job from a preference's coarse time window, under
# the naive-UTC convention of the schedule columns (same 09:00 default as the
# convert-to-job prefill).
_WINDOW_START_HOURS = {"morning": 9, "afternoon": 13}
_DEFAULT_START_HOUR = 9
# Fallback visit length when the quote carries no duration signal.
_DEFAULT_DRAFT_DURATION = timedelta(hours=2)


async def ensure_draft_job(db: AsyncSession, *, quote: Quote) -> Job | None:
    """Create (or re-seat) the tentative draft job from the customer's 1st choice.

    Returns the draft job, or None when there is no parseable preference or
    the quote already has a confirmed (non-draft) job. An existing draft is
    re-seated onto the new 1st choice so post-acceptance preference updates
    stay reflected. The draft never emails the customer and never blocks the
    calendar (``app.availability`` excludes draft jobs); converting the quote
    to a job adopts it. Does not commit — the caller owns the transaction.
    """
    first = first_preferred_date(quote.accepted_dates, datetime.utcnow().date())
    if first is None:
        return None
    first_day, window = first

    existing = await db.scalar(select(Job).where(Job.quote_id == quote.id))
    if existing is not None and existing.status != "draft":
        return None

    start_hour = _WINDOW_START_HOURS.get(window or "", _DEFAULT_START_HOUR)
    scheduled_start = datetime(first_day.year, first_day.month, first_day.day, start_hour, 0)
    estimated = float(quote.estimated_hours) if quote.estimated_hours is not None else 0.0
    if estimated <= 0:
        result = await db.execute(select(QuoteLineItem).where(QuoteLineItem.quote_id == quote.id))
        estimated = estimate_hours_from_lines(
            ((float(item.quantity), item.unit) for item in result.scalars().all()), None
        )
    duration = timedelta(hours=estimated) if estimated > 0 else _DEFAULT_DRAFT_DURATION
    notes = (
        "Customer confirmed preferred dates: "
        + ", ".join(quote.accepted_dates)
        + "\n\nDrafted automatically from the customer's first choice — confirm or reschedule."
    )

    if existing is not None:
        existing.scheduled_start = scheduled_start
        existing.scheduled_end = scheduled_start + duration
        existing.notes = notes
        await db.flush()
        return existing

    contact = await db.get(Contact, quote.contact_id)
    job = Job(
        tenant_id=quote.tenant_id,
        contact_id=quote.contact_id,
        quote_id=quote.id,
        title=quote.title,
        description=quote.description,
        status="draft",
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_start + duration,
        # Denormalise the contact's current address, same as job create.
        address=contact.address if contact is not None else None,
        postcode=contact.postcode if contact is not None else None,
        notes=notes,
    )
    db.add(job)
    await db.flush()
    return job
