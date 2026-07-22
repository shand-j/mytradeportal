"""Password hashing and session cookie helpers."""

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

import bcrypt
from fastapi import Response
from jose import JWTError, jwt

from app.config import settings

AUTH_COOKIE_NAME = "session"
ALGORITHM = "HS256"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if the plain password matches the stored hash."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def get_password_hash(password: str) -> str:
    """Hash a plain-text password."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_access_token(
    user_id: UUID,
    tenant_id: UUID,
    role: str,
    email: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token for a user."""
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.auth_access_token_expire_minutes)
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "email": email,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.auth_secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode and return JWT claims, or None if invalid/expired."""
    try:
        return jwt.decode(token, settings.auth_secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None


def _cookie_samesite() -> Literal["lax", "none"]:
    """Return the SameSite policy for the auth cookie.

    In production the back-office UI and the API are served from different
    sites (e.g. separate Railway domains), so the cookie must be
    ``SameSite=None; Secure`` to survive cross-site ``fetch`` calls with
    ``credentials: 'include'``. In development everything is same-site
    localhost, where ``Lax`` is safer.
    """
    return "none" if settings.environment == "production" else "lax"


def set_auth_cookie(response: Response, token: str) -> None:
    """Attach the auth token to the response as an HTTP-only cookie."""
    max_age = int(timedelta(minutes=settings.auth_access_token_expire_minutes).total_seconds())
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.environment == "production",
        samesite=_cookie_samesite(),
        max_age=max_age,
    )


def clear_auth_cookie(response: Response) -> None:
    """Remove the auth cookie from the response."""
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        httponly=True,
        secure=settings.environment == "production",
        samesite=_cookie_samesite(),
    )
