"""Customer payment-received notifications, shared by both settlement paths.

The ``payment_received`` confirmation (+ review prompt) fires when an invoice
is settled — no matter the rail:

* **Stripe webhook** (``app.routers.stripe_webhooks``) — card payment settled
  online; the copy mentions Stripe's own card receipt.
* **Manual mark-paid** (``app.routers.invoices``) — bank transfer, cash, or
  any offline settlement the tradie records by hand; the copy must not claim
  a card payment, so the Stripe receipt note is omitted.

Everything is best-effort and never raises: dispatch gaps surface via
:func:`app.email.send_customer_email`'s logging (and its staff failure
alert), never to the caller.
"""

from datetime import datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.email import send_customer_email
from app.email_templates import payment_received as payment_received_template
from app.models import Contact, Invoice, Tenant

logger = structlog.get_logger("api.payment_notifications")


async def send_payment_received_email(
    session: AsyncSession,
    invoice: Invoice,
    *,
    card_payment: bool,
) -> None:
    """Best-effort payment confirmation (+ review prompt) to the customer.

    Reads everything it needs while the session's RLS context is still live,
    then renders and dispatches through ``send_customer_email``. The review
    CTA is included only when the tenant has configured ``review_url``.
    ``card_payment`` selects the copy variant: the Stripe path mentions
    Stripe's card receipt; the manual path does not.
    """
    try:
        contact = await session.get(Contact, invoice.contact_id)
        if contact is None or not contact.email:
            logger.warning(
                "payment_received_email_skipped",
                invoice_id=str(invoice.id),
                reason="no_contact_email",
            )
            return
        tenant = await session.get(Tenant, invoice.tenant_id)
        business_name = tenant.name if tenant is not None else "Your tradesperson"
        review_url_raw = (tenant.settings or {}).get("review_url") if tenant is not None else None
        review_url = str(review_url_raw) if review_url_raw else None
        paid_at = invoice.paid_at or datetime.utcnow()
        subject, html, text = payment_received_template(
            customer_name=contact.name.split()[0] if contact.name else "there",
            business_name=business_name,
            invoice_number=invoice.invoice_number,
            amount_paid=f"£{invoice.total}",
            paid_date=paid_at.strftime("%d %b %Y"),
            review_url=review_url,
            card_payment=card_payment,
        )
        await send_customer_email(
            session,
            tenant_id=invoice.tenant_id,
            contact_id=contact.id,
            purpose="payment receipt",
            to_email=contact.email,
            subject=subject,
            html_body=html,
            text_body=text,
            event="payment_received",
            template="payment_received",
            from_name=business_name,
            reply_to=(tenant.email if tenant is not None and tenant.email else None),
            context={
                "invoice_id": str(invoice.id),
                "tenant_id": str(invoice.tenant_id),
            },
        )
    except Exception as exc:
        logger.error(
            "payment_received_email_failed",
            invoice_id=str(invoice.id),
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
