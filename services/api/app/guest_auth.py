"""Guest-scoped tokens for unauthenticated quote-request chat threads.

When the public intake's quick AI check returns a follow-up question, the
homeowner answers it inline — before (and without) registering an account.
The intake ack therefore carries a short-lived JWT scoped to exactly one
quote request: ``subject_type="guest"`` with ``qr_id`` + ``tenant_id``
claims. It is only accepted by the ``/public/threads`` endpoints, which
re-check the scope against the path id, so a guest token can never read or
write another lead's thread or act as a customer/staff token anywhere else
(every other surface rejects unknown ``subject_type`` values).
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from jose import jwt

from app import config
from app.config import settings
from app.security import ALGORITHM, decode_access_token


def issue_guest_token(quote_request_id: UUID, tenant_id: UUID) -> tuple[str, datetime]:
    """Mint a guest token for one quote request; returns (token, expires_at)."""
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=config.GUEST_THREAD_TTL_MINUTES)
    payload: dict[str, Any] = {
        "sub": f"guest:{quote_request_id}",
        "subject_type": "guest",
        "qr_id": str(quote_request_id),
        "tenant_id": str(tenant_id),
        "iat": now,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.auth_secret_key, algorithm=ALGORITHM), expires_at


def verify_guest_token(token: str, quote_request_id: UUID) -> dict[str, Any] | None:
    """Decode a guest token and enforce its scope; None when invalid.

    Expiry, signature and ``subject_type`` are checked by the shared decode;
    the strict scope check here pins the token to the quote request in the
    path so a token leaked from one thread cannot open another.
    """
    claims = decode_access_token(token)
    if claims is None:
        return None
    if claims.get("subject_type") != "guest":
        return None
    if str(claims.get("qr_id")) != str(quote_request_id):
        return None
    if not claims.get("tenant_id"):
        return None
    return claims
