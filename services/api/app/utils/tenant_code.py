"""Helpers for generating unique 6-digit tenant customer-lookup codes."""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models import Tenant

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

CODE_LENGTH = 6
MAX_RETRIES = 10


def _generate_code() -> str:
    """Return a zero-padded 6-digit numeric string."""
    return secrets.randbelow(10**CODE_LENGTH).__str__().zfill(CODE_LENGTH)


async def generate_unique_tenant_code(db: AsyncSession, max_retries: int = MAX_RETRIES) -> str:
    """Generate a 6-digit numeric code that is unique across all tenants.

    Retries on collision up to ``max_retries`` times, then raises RuntimeError.
    """
    for _ in range(max_retries):
        code = _generate_code()
        existing = await db.scalar(select(Tenant).where(Tenant.code == code))
        if existing is None:
            return code
    raise RuntimeError(f"Could not generate a unique tenant code after {max_retries} attempts")
