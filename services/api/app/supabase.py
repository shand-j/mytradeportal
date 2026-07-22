"""Optional Supabase Auth integration.

When SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set, email/password
authentication is delegated to Supabase Auth (GoTrue). The API still issues
its own short-lived session cookie after verifying the Supabase credentials.
"""

from typing import Any, cast

import httpx

from app.config import settings


def _base_url() -> str:
    return settings.supabase_url.rstrip("/")


def _auth_url() -> str:
    return f"{_base_url()}/auth/v1"


def is_supabase_configured() -> bool:
    """Return True when Supabase Auth credentials are available."""
    return bool(settings.supabase_url and settings.supabase_service_role_key)


async def sign_in_with_password(email: str, password: str) -> dict[str, Any] | None:
    """Sign in via Supabase Auth and return the user payload, or None on failure."""
    if not is_supabase_configured():
        return None
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{_auth_url()}/token?grant_type=password",
            headers={
                "apikey": settings.supabase_anon_key,
                "Content-Type": "application/json",
            },
            json={"email": email, "password": password},
        )
        if response.status_code != 200:
            return None
        return cast("dict[str, Any]", response.json())


def admin_create_user(email: str, password: str) -> dict[str, Any]:
    """Create a Supabase Auth user with the service role key.

    Raises RuntimeError if creation fails.
    """
    if not is_supabase_configured():
        raise RuntimeError("Supabase is not configured")
    with httpx.Client() as client:
        response = client.post(
            f"{_auth_url()}/admin/users",
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": "application/json",
            },
            json={"email": email, "password": password, "email_confirm": True},
        )
        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"Failed to create Supabase user: {response.status_code} {response.text}"
            )
        return cast("dict[str, Any]", response.json())
