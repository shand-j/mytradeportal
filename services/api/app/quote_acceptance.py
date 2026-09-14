"""Shared quote accept/decline transitions for customer-facing flows.

Both customer-facing action paths — the authenticated portal endpoints
(``POST /customer/quotes/{id}/accept|reject``) and the token-authorized
emailed web page (``POST /public/quote/{token}/accept|decline``) — run the
same state transition, staff notification, outcome event and confirmation
email. The logic lives here so the two routers can never drift apart.

Callers own the preconditions (status check, RLS scoping) and re-fetch
whatever they need for their response afterwards.
"""

from __future__ import annotations

import inspect
from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.ai_telemetry import record_quote_outcome
from app.email import send_customer_email
from app.email_templates import quote_accepted as quote_accepted_template
from app.portal_links import magic_link_url, portal_url
from app.push import notify_staff

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
    if quote.accepted_dates:
        dates_note = f" Customer confirmed preferred dates: {', '.join(quote.accepted_dates)}."
    await notify_staff(
        db,
        quote.tenant_id,
        kind="quote_accepted",
        title="Quote accepted",
        body=f"{customer_name} accepted quote '{quote.title}'.{dates_note}",
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
