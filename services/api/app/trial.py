"""No-card trial logic for new tenants.

Model: every tenant created via ``POST /tenants`` gets an internal
``Subscription(status="trialing", trial_ends_at=now + TRIAL_DAYS)`` row with
no Paddle interaction. When the tenant later completes Paddle checkout, the
``_upsert_subscription`` webhook handler (keyed on ``custom_data.tenant_id``)
hydrates THAT SAME row in place — there is never a second row or a unique-key
conflict.

Extension: a trialing tenant that has sent at least
``TRIAL_EXTENSION_SENT_AI_QUOTES`` quotes with AI-generated line items gets
their trial extended to ``trial_ends_at = now + TRIAL_EXTENSION_DAYS``.

Extension semantics (chosen): extend FROM NOW, not from the original trial
start. It is simpler (no need to remember the start date), strictly more
generous, and never shortens an in-flight trial. The extension fires exactly
once per tenant, marked by ``TRIAL_EXTENDED_SETTINGS_KEY`` in the tenant
``settings`` JSONB. The marker lives on the tenant rather than
``Subscription.provider_payload`` because the webhook handler replaces that
payload wholesale with the Paddle event body.

``beta_comped`` tenants are untouched by all of this: the paywall/tenant-status
beta override reads tenant settings, which this module never clears, and the
extension itself is a no-op unless the subscription is still ``trialing``.
"""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func, select

from app.models import Quote, QuoteLineItem, Subscription, Tenant
from app.plans import TRIAL_EXTENSION_DAYS, TRIAL_EXTENSION_SENT_AI_QUOTES

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Tenant settings key recording when the trial extension fired (ISO timestamp).
TRIAL_EXTENDED_SETTINGS_KEY = "trial_extended_at"

# Quote statuses that count as "sent" for the extension trigger — the same
# funnel stages the analytics module treats as delivered to the customer.
TRIAL_EXTENSION_QUOTE_STATUSES: tuple[str, ...] = ("sent", "approved", "invoiced")


async def count_sent_ai_quotes(db: "AsyncSession", tenant_id: UUID) -> int:
    """Count the tenant's sent quotes containing at least one AI-generated line.

    Uses the same ``ai_generated`` derivation as ``QuoteRead`` (the per-line
    ``ai_generated`` flag on ``quote_line_items``), so the trigger agrees with
    what the UI labels as an AI quote.
    """
    result = await db.scalar(
        select(func.count(func.distinct(Quote.id)))
        .join(QuoteLineItem, QuoteLineItem.quote_id == Quote.id)
        .where(
            Quote.tenant_id == tenant_id,
            Quote.status.in_(TRIAL_EXTENSION_QUOTE_STATUSES),
            QuoteLineItem.ai_generated.is_(True),
        )
    )
    return int(result or 0)


async def maybe_extend_trial(db: "AsyncSession", tenant_id: UUID) -> bool:
    """Extend the tenant's trial to TRIAL_EXTENSION_DAYS from now, at most once.

    Called from the quote-send path after the quote has been flushed, so the
    just-sent quote is included in the count. No-op (returns False) when the
    tenant has no trialing subscription or the extension already fired. The
    caller's transaction commits the change together with the send.
    """
    sub = await db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))
    if sub is None or sub.status != "trialing":
        return False
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None or tenant.settings.get(TRIAL_EXTENDED_SETTINGS_KEY):
        return False
    sent_ai_quotes = await count_sent_ai_quotes(db, tenant_id)
    if sent_ai_quotes < TRIAL_EXTENSION_SENT_AI_QUOTES:
        return False

    now = datetime.utcnow()
    sub.trial_ends_at = now + timedelta(days=TRIAL_EXTENSION_DAYS)
    tenant.settings = {**tenant.settings, TRIAL_EXTENDED_SETTINGS_KEY: now.isoformat()}
    return True
