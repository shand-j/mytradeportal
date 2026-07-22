"""SQLAlchemy models for the operations core."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    """Mixin that adds created_at and updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class CostItem(Base, TimestampMixin):
    """A priced cost item from the shared cost database."""

    __tablename__ = "cost_items"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(63), unique=True, nullable=False, index=True)
    trade: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    region: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="GBP", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="seed", nullable=False)
    extra_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class Tenant(Base, TimestampMixin):
    """A trade business tenant (electrical contractor)."""

    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(63), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    # Paddle-specific merchant configuration (sandbox vs production per tenant optional)
    paddle_sandbox: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Convenience properties that expose commonly-used tenant settings so the
    # Pydantic read schema can surface them as top-level fields.
    @property
    def email(self) -> str:
        return self.settings.get("email", "") if self.settings else ""

    @property
    def phone(self) -> str:
        return self.settings.get("phone", "") if self.settings else ""

    @property
    def website(self) -> str | None:
        return self.settings.get("website") if self.settings else None

    @property
    def address(self) -> str:
        return self.settings.get("address", "") if self.settings else ""

    @property
    def logo_url(self) -> str | None:
        return self.settings.get("logo_url") if self.settings else None

    @property
    def primary_color(self) -> str:
        return (
            self.settings.get("primary_color", "")
            or (self.settings.get("branding") or {}).get("primary_color", "")
            or "#D4650A"
        )

    @property
    def secondary_color(self) -> str:
        return (
            self.settings.get("secondary_color", "")
            or (self.settings.get("branding") or {}).get("secondary_color", "")
            or "#7C3AED"
        )

    @property
    def hourly_labour_rate(self) -> float:
        return float(self.settings.get("hourly_labour_rate", 0) or 0)

    @property
    def daily_labour_rate(self) -> float:
        return float(self.settings.get("daily_labour_rate", 0) or 0)

    @property
    def mate_daily_rate(self) -> float:
        return float(self.settings.get("mate_daily_rate", 0) or 0)

    @property
    def mate_percent(self) -> float:
        return float(self.settings.get("mate_percent", 55) or 55)

    @property
    def markup_percentage(self) -> float:
        return float(self.settings.get("markup_percentage", 0) or 0)

    @property
    def min_margin_percent(self) -> float:
        return float(self.settings.get("min_margin_percent", 0) or 0)

    @property
    def price_tolerance_percent(self) -> float:
        return float(self.settings.get("price_tolerance_percent", 15) or 15)

    @property
    def minimum_charge(self) -> float:
        return float(self.settings.get("minimum_charge", 0) or 0)

    @property
    def vat_rate(self) -> float:
        return float(self.settings.get("vat_rate", 20) or 20)

    @property
    def plan_tier(self) -> str:
        return self.settings.get("plan_tier", "starter") if self.settings else "starter"

    @property
    def google_place_id(self) -> str | None:
        return self.settings.get("google_place_id") if self.settings else None


class TenantScopedBase(Base, TimestampMixin):
    """Abstract base for any entity that belongs to a tenant."""

    __abstract__ = True

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class User(TenantScopedBase):
    """A person who works for the tenant (owner, admin, electrician, office staff)."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="technician", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supabase_uid: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)


class Contact(TenantScopedBase):
    """A customer or lead."""

    __tablename__ = "contacts"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    quotes: Mapped[list[Quote]] = relationship(
        "Quote", back_populates="contact", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[Job]] = relationship(
        "Job", back_populates="contact", cascade="all, delete-orphan"
    )
    invoices: Mapped[list[Invoice]] = relationship(
        "Invoice", back_populates="contact", cascade="all, delete-orphan"
    )


class Quote(TenantScopedBase):
    """A quote sent to a customer for electrical work."""

    __tablename__ = "quotes"

    contact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.20"))
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    extra_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    contact: Mapped[Contact] = relationship("Contact", back_populates="quotes")
    line_items: Mapped[list[QuoteLineItem]] = relationship(
        "QuoteLineItem", back_populates="quote", cascade="all, delete-orphan"
    )
    bill_of_quantities: Mapped[BillOfQuantities | None] = relationship(
        "BillOfQuantities", back_populates="quote", uselist=False, cascade="all, delete-orphan"
    )


class QuoteLineItem(Base, TimestampMixin):
    """A line item on a quote."""

    __tablename__ = "quote_line_items"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quote_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cost_item_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cost_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    boq_line_item_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("boq_line_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("1.00"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0.0000"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0.0000"))

    quote: Mapped[Quote] = relationship("Quote", back_populates="line_items")


class BillOfQuantities(Base, TimestampMixin):
    """Internal Bill of Quantities supporting a customer quote."""

    __tablename__ = "bills_of_quantities"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quote_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.20"))
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), default=0.0)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    # Citations to the regulatory KB chunks used to ground the BoQ. Each entry
    # is a serialised :class:`mtp_shared.RegulatoryCitation`.
    regulatory_citations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    # Operator-facing warnings for mandatory items the rule-based compliance
    # checker did not find in the BoQ.
    compliance_warnings: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    # Customer-facing collapsed lines for quote documents (no internal T&M split).
    customer_summary_lines: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    # Back-office only profitability indicator snapshot from OCERP.
    margin_indicator: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    standard: Mapped[str | None] = mapped_column(String(50), nullable=True)

    quote: Mapped[Quote] = relationship("Quote", back_populates="bill_of_quantities")
    line_items: Mapped[list[BoQLineItem]] = relationship(
        "BoQLineItem", back_populates="boq", cascade="all, delete-orphan"
    )


class BoQLineItem(Base, TimestampMixin):
    """A single Time & Materials line inside a Bill of Quantities."""

    __tablename__ = "boq_line_items"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    boq_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("bills_of_quantities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cost_item_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cost_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(63), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("1.00"))
    labour_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    labour_rate: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0.0000"))
    labour_total: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0.0000"))
    material_cost: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0.0000"))
    material_total: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0.0000"))
    plant_cost: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0.0000"))
    plant_total: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0.0000"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0.0000"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0.0000"))
    supplier: Mapped[str | None] = mapped_column(String(100), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    product_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    retail_price_incl_vat: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    boq: Mapped[BillOfQuantities] = relationship("BillOfQuantities", back_populates="line_items")


class Job(TenantScopedBase):
    """A job created from an approved quote."""

    __tablename__ = "jobs"

    contact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quote_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="scheduled", nullable=False)
    scheduled_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scheduled_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    contact: Mapped[Contact] = relationship("Contact", back_populates="jobs")


class Appointment(TenantScopedBase):
    """An appointment booking on a tradesperson's calendar."""

    __tablename__ = "appointments"

    contact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="confirmed", nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Invoice(TenantScopedBase):
    """An invoice for completed work, payable via Paddle."""

    __tablename__ = "invoices"

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    contact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    quote_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    issue_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.20"))
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paddle_checkout_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    paddle_transaction_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )

    contact: Mapped[Contact] = relationship("Contact", back_populates="invoices")
    line_items: Mapped[list[InvoiceLineItem]] = relationship(
        "InvoiceLineItem", back_populates="invoice", cascade="all, delete-orphan"
    )
    payments: Mapped[list[Payment]] = relationship(
        "Payment", back_populates="invoice", cascade="all, delete-orphan"
    )


class InvoiceLineItem(Base, TimestampMixin):
    """A line item on an invoice."""

    __tablename__ = "invoice_line_items"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invoice_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("1.00"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0.0000"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0.0000"))

    invoice: Mapped[Invoice] = relationship("Invoice", back_populates="line_items")


class Payment(Base, TimestampMixin):
    """A payment record linked to Paddle."""

    __tablename__ = "payments"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invoice_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), default="GBP", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    provider: Mapped[str] = mapped_column(String(50), default="paddle", nullable=False)
    provider_transaction_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    provider_checkout_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    provider_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    invoice: Mapped[Invoice] = relationship("Invoice", back_populates="payments")


class Communication(TenantScopedBase):
    """A logged message/email/SMS/call with a contact."""

    __tablename__ = "communications"

    contact_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), default="outbound", nullable=False)
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="sent", nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Review(TenantScopedBase):
    """A customer review collected from a job or external source."""

    __tablename__ = "reviews"

    contact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rating: Mapped[int] = mapped_column(nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditLog(TenantScopedBase):
    """Immutable audit log for quote changes and other sensitive actions."""

    __tablename__ = "audit_logs"

    actor_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
