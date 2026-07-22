"""Base Pydantic and tenancy-aware models."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class BaseEntity(BaseModel):
    """Common fields for all domain entities."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TenantBase(BaseModel):
    """Base fields for a tenant entity."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    slug: str = Field(..., min_length=2, max_length=63)
    name: str = Field(..., min_length=1, max_length=255)
    is_active: bool = True
    settings: dict[str, Any] = Field(default_factory=dict)


class TenantScopedModel(BaseEntity):
    """Mixin-like base for any entity that belongs to a tenant.

    SQLAlchemy models should inherit from this Pydantic schema and add their own
    `tenant_id: UUID` foreign key. This class enforces the contract in API payloads.
    """

    tenant_id: UUID
