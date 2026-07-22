"""Event schemas used across services."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class EventType(StrEnum):
    QUOTE_CREATED = "quote.created"
    QUOTE_UPDATED = "quote.updated"
    QUOTE_APPROVED = "quote.approved"
    APPOINTMENT_BOOKED = "appointment.booked"
    INVOICE_PAID = "invoice.paid"


class DomainEvent(BaseModel):
    event_type: EventType
    tenant_id: UUID
    aggregate_id: UUID
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=datetime.utcnow)
