"""Tenant context propagation and RLS helpers."""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from collections.abc import Iterator

from fastapi import Header, HTTPException, status

TenantContext: ContextVar[UUID | None] = ContextVar("tenant_id", default=None)


def set_tenant(tenant_id: UUID) -> None:
    """Set the current tenant in context."""
    TenantContext.set(tenant_id)


def get_tenant() -> UUID | None:
    """Return the current tenant id, if any."""
    return TenantContext.get()


def require_tenant() -> UUID:
    """Return the current tenant id or raise a 401."""
    tenant_id = get_tenant()
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant context is required",
        )
    return tenant_id


@contextmanager
def tenant_scope(tenant_id: UUID) -> "Iterator[UUID]":
    """Run a block of code within a tenant context."""
    token = TenantContext.set(tenant_id)
    try:
        yield tenant_id
    finally:
        TenantContext.reset(token)


def tenant_dependency(x_tenant_id: UUID = Header(..., alias="X-Tenant-ID")) -> UUID:
    """FastAPI dependency that reads the tenant id from a header.

    In production this will be replaced/supplemented by JWT validation.
    """
    set_tenant(x_tenant_id)
    return x_tenant_id
