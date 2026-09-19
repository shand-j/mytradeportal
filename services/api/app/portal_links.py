"""Customer portal magic-link URLs and token issuance.

Backs the invisible (passwordless) customer auth flow: transactional emails
embed a magic link on the tenant's portal subdomain; the portal exchanges the
token for a customer JWT via ``POST /customer/auth/magic``. Raw tokens are
256-bit random and only the SHA-256 hash is persisted, so a leaked DB dump
cannot be replayed. Re-issuing for a customer revokes their earlier
still-valid tokens so only the newest emailed link works.

This module is imported by the email call sites (quote accepted, magic-link
request) and the customer portal router; keep the public signatures stable.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import PORTAL_BASE_DOMAIN, PORTAL_MAGIC_TTL_DAYS
from app.models import Contact, Customer, CustomerPortalToken, Tenant

_TOKEN_BYTES = 32

# Contact-preference value meaning "the customer has the app — app first,
# email too". Set when an account is claimed or a customer push token is
# registered (the strongest 'has the app' signals).
APP_CONTACT_PREFERENCE = "app"


async def flip_preferred_contact_to_app(db: AsyncSession, customer: Customer) -> None:
    """Flip a customer's contact preference to "app" (idempotent).

    Writes both the CRM contact (staff-facing follow-up channel) and the
    customer account mirror so either read path sees the app-first signal.
    Only writes when the value is not already "app". The caller commits with
    the rest of the surrounding transaction.
    """
    if customer.contact_id is not None:
        contact = await db.get(Contact, customer.contact_id)
        if contact is not None and contact.preferred_contact_method != APP_CONTACT_PREFERENCE:
            contact.preferred_contact_method = APP_CONTACT_PREFERENCE
    if customer.preferred_contact_method != APP_CONTACT_PREFERENCE:
        customer.preferred_contact_method = APP_CONTACT_PREFERENCE


def portal_base_url(tenant: Tenant) -> str:
    """Absolute origin of the tenant's portal subdomain (no path)."""
    return f"https://{tenant.slug}.{PORTAL_BASE_DOMAIN}"


def portal_url(tenant: Tenant, path: str) -> str:
    """Absolute URL on the tenant's portal subdomain (``path`` starts with /)."""
    return f"{portal_base_url(tenant)}{path}"


def hash_portal_token(raw: str) -> str:
    """SHA-256 of the raw bearer token — only this digest is persisted."""
    return hashlib.sha256(raw.encode()).hexdigest()


async def issue_portal_token(db: AsyncSession, customer: Customer) -> str:
    """Mint a portal magic-link token and return the raw value for the email link.

    Revokes any still-valid earlier tokens for the same customer so only the
    newest emailed link signs them in. The caller commits with the rest of the
    surrounding transaction.
    """
    await db.execute(
        update(CustomerPortalToken)
        .where(
            CustomerPortalToken.customer_id == customer.id,
            CustomerPortalToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
    raw = secrets.token_urlsafe(_TOKEN_BYTES)
    db.add(
        CustomerPortalToken(
            customer_id=customer.id,
            tenant_id=customer.tenant_id,
            token_hash=hash_portal_token(raw),
            expires_at=datetime.now(UTC) + timedelta(days=PORTAL_MAGIC_TTL_DAYS),
        )
    )
    await db.flush()
    return raw


async def magic_link_url(
    db: AsyncSession, tenant: Tenant, customer: Customer, next_path: str
) -> str:
    """Issue a fresh portal token and return the full magic-link URL for it."""
    raw = await issue_portal_token(db, customer)
    return portal_url(tenant, f"/auth/magic?token={raw}&next={quote(next_path)}")
