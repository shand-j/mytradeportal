"""Optional Supabase Auth integration.

When SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set, email/password
authentication is delegated to Supabase Auth (GoTrue). The API still issues
its own short-lived session cookie after verifying the Supabase credentials.
"""

from typing import Any, cast

import httpx

from app.config import settings


def _base_url() -> str:
    return str(settings.supabase_url).rstrip("/")


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


def _admin_headers() -> dict[str, str]:
    key = settings.supabase_service_role_key
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _find_user_by_email(client: httpx.Client, email: str) -> dict[str, Any] | None:
    """Return the first Supabase Auth user with a matching email, or None."""
    page = 1
    while True:
        response = client.get(
            f"{_auth_url()}/admin/users",
            headers=_admin_headers(),
            params={"page": page, "per_page": 1000},
        )
        if response.status_code != 200:
            return None
        users = response.json().get("users", [])
        if not users:
            return None
        for user in users:
            if str(user.get("email", "")).casefold() == email.casefold():
                return cast("dict[str, Any]", user)
        if len(users) < 1000:
            return None
        page += 1


def admin_create_user(
    email: str,
    password: str,
    *,
    full_name: str | None = None,
    role: str | None = None,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Create a Supabase Auth user with the service role key.

    Idempotent: if the email already exists in Supabase (orphaned record from
    an earlier partial bootstrap), the existing user is adopted — password
    reset and metadata refreshed — instead of raising.

    Raises RuntimeError if creation fails. Identity metadata (name, role,
    tenant) rides along so the hosted user record isn't just an email.
    """
    if not is_supabase_configured():
        raise RuntimeError("Supabase is not configured")
    user_metadata = {
        k: v for k, v in {"full_name": full_name, "role": role, "tenant_id": tenant_id}.items() if v
    }
    with httpx.Client() as client:
        response = client.post(
            f"{_auth_url()}/admin/users",
            headers=_admin_headers(),
            json={
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": user_metadata,
            },
        )
        if response.status_code in (200, 201):
            return cast("dict[str, Any]", response.json())
        body = (
            response.json()
            if response.headers.get("content-type", "").startswith("application/json")
            else {}
        )
        if response.status_code == 422 and body.get("error_code") == "email_exists":
            existing = _find_user_by_email(client, email)
            if existing is None:
                raise RuntimeError(
                    f"Failed to create Supabase user: {response.status_code} {response.text}"
                )
            existing_metadata = existing.get("user_metadata") or {}
            update = client.put(
                f"{_auth_url()}/admin/users/{existing['id']}",
                headers=_admin_headers(),
                json={
                    "password": password,
                    "email_confirm": True,
                    "user_metadata": {**existing_metadata, **user_metadata},
                },
            )
            if update.status_code not in (200, 201):
                raise RuntimeError(
                    f"Failed to adopt existing Supabase user: {update.status_code} {update.text}"
                )
            return cast("dict[str, Any]", update.json())
        raise RuntimeError(
            f"Failed to create Supabase user: {response.status_code} {response.text}"
        )


def admin_update_password(supabase_uid: str, password: str) -> None:
    """Update a Supabase Auth user's password with the service role key.

    Raises RuntimeError if the update fails.
    """
    if not is_supabase_configured():
        raise RuntimeError("Supabase is not configured")
    with httpx.Client() as client:
        response = client.put(
            f"{_auth_url()}/admin/users/{supabase_uid}",
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": "application/json",
            },
            json={"password": password},
        )
        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"Failed to update Supabase user password: {response.status_code} {response.text}"
            )
