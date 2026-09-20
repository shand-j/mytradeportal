"""SQLAlchemy models for the operations core."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
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
    code: Mapped[str | None] = mapped_column(
        String(6), unique=True, nullable=True, index=True
    )  # 6-digit customer lookup code, generated on creation
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default="active", nullable=False
    )  # onboarding | provisional | active | suspended
    onboarding_progress: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    launched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    structure: Mapped[str | None] = mapped_column(String(50), nullable=True)
    year_established: Mapped[int | None] = mapped_column(nullable=True)
    companies_house_number: Mapped[str | None] = mapped_column(String(8), nullable=True)
    ch_verified: Mapped[str] = mapped_column(String(50), default="self_declared", nullable=False)
    nations_served: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    vat_registered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    vat_number: Mapped[str | None] = mapped_column(String(12), nullable=True)
    vat_scheme: Mapped[str | None] = mapped_column(String(50), nullable=True)
    quote_defaults: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    branding: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
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
    def postcode(self) -> str | None:
        return self.settings.get("postcode") if self.settings else None

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
    role: Mapped[str] = mapped_column(
        String(50), default="engineer", nullable=False
    )  # owner | admin | office_manager | engineer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supabase_uid: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    # Set when the account is created via POST /users/invite and cleared when
    # the invitee sets their password (accept-invite flips is_active on). A
    # row with invited_at set and is_active off is a pending invite and counts
    # against the plan's seat limit; a deactivated user (is_active off, no
    # invited_at) does not.
    invited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @property
    def invite_pending(self) -> bool:
        """True while an invited user has not yet accepted (set a password)."""
        return self.invited_at is not None and not self.is_active


class Contact(TenantScopedBase):
    """A customer or lead."""

    __tablename__ = "contacts"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Site logistics + property details captured on the CRM record so quote and
    # job creation can pre-fill them for repeat customers.
    preferred_contact_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    property_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bedrooms: Mapped[int | None] = mapped_column(nullable=True)
    parking_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Trust badges + blocking (N26). Auto badges (late_payer / non_payer /
    # time_waster) are computed on read from invoice/quote history; only manual
    # per-badge overrides are stored here ({badge: bool}) so the auto rules
    # keep tracking reality. A blocked contact's customer account cannot log
    # in, request quotes or message the business.
    badge_overrides: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    # Per-customer reminder (chase) overrides (F2). NULL = tenant defaults.
    # Supported keys: quote_chase_enabled / invoice_chase_enabled (bool),
    # max_reminders (int, caps the tenant cadence downward only) and
    # sms_opt_out (bool — set by POST /webhooks/telnyx when the customer
    # replies STOP; appointment reminders then skip SMS and fall back to
    # email, and START/UNSTOP clears it again).
    reminder_preferences: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

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
    # Internal staff notes (never customer-facing). Creation merges the CRM
    # contact's notes in, and quote → job conversion carries them onto the job.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.20"))
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    # Amount added on top of the VAT-inclusive total when the tenant's
    # quote-rounding setting rounds the total up to the nearest £5/£10. Zero
    # when rounding is off; ``total`` always includes this adjustment.
    rounding_adjustment: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), server_default="0"
    )
    valid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Dates the customer reconfirmed at acceptance; surfaced when the
    # electrician converts the quote to a job.
    accepted_dates: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    quote_request_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("quote_requests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ai_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    reviewed_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    extra_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    # Estimated total on-site working hours for the quoted work. AI-generated
    # quotes populate it from the LLM's estimate (falling back to the summed
    # time-billed line items); manual quotes can set it via PATCH. Drives the
    # multi-day split when converting to a job.
    estimated_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)

    contact: Mapped[Contact] = relationship("Contact", back_populates="quotes")
    line_items: Mapped[list[QuoteLineItem]] = relationship(
        "QuoteLineItem", back_populates="quote", cascade="all, delete-orphan"
    )
    bill_of_quantities: Mapped[BillOfQuantities | None] = relationship(
        "BillOfQuantities", back_populates="quote", uselist=False, cascade="all, delete-orphan"
    )
    quote_request: Mapped[QuoteRequest | None] = relationship(
        "QuoteRequest", foreign_keys="Quote.quote_request_id"
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
    # Billing unit (ea, hour, day, m, ...). Older rows show the default; the
    # client previously hardcoded "job".
    unit: Mapped[str] = mapped_column(String(50), default="ea", nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0.0000"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0.0000"))
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    edited_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

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
    compliance_warnings: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    # Customer-facing collapsed lines for quote documents (no internal T&M split).
    customer_summary_lines: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    # Back-office only profitability indicator snapshot from OCERP.
    margin_indicator: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    # Retrieval provenance and quality-gate metadata emitted by OCERP.
    retrieval_evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
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
    assigned_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    lat: Mapped[Decimal | None] = mapped_column(Numeric(10, 8), nullable=True)
    lng: Mapped[Decimal | None] = mapped_column(Numeric(11, 8), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    contact: Mapped[Contact] = relationship("Contact", back_populates="jobs")
    # Staff member the job is assigned to (display name surfaced on JobRead).
    assignee: Mapped[User | None] = relationship("User", foreign_keys=[assigned_user_id])
    # Photos/files carried over from the source quote's quote request.
    media: Mapped[list[MediaAsset]] = relationship("MediaAsset", foreign_keys="MediaAsset.job_id")


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
    assigned_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Invoice(TenantScopedBase):
    """An invoice for completed work, payable by card (Stripe Connect) or manually."""

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
    # Rounding uplift inherited from the source quote (see Quote.rounding_adjustment).
    rounding_adjustment: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), server_default="0"
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paddle_checkout_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    paddle_transaction_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    # Stripe Connect card payment (ADR-003): the open/succeeded PaymentIntent
    # backing the /pay page for this invoice.
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    # Per-invoice override for offering card payment online. NULL falls back
    # to the tenant default (settings["payments"]["accept_card_default"]).
    accept_card_payments: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # How the invoice was settled: "stripe" | "manual" | "paddle-legacy".
    paid_via: Mapped[str | None] = mapped_column(String(50), nullable=True)

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


class Subscription(Base, TimestampMixin):
    """A tenant's Paddle-billed subscription to the MTP platform.

    Mirrors just enough of the Paddle subscription state to gate access and
    render the billing screen without round-tripping the Paddle API. Webhooks
    are the source of truth — the row is UPSERT-ed on ``paddle_subscription_id``
    so at-least-once delivery is naturally idempotent.
    """

    __tablename__ = "subscriptions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    # One live subscription per tenant for beta.
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    plan_key: Mapped[str] = mapped_column(String(50), nullable=False)  # starter | pro | business
    status: Mapped[str] = mapped_column(
        String(50), default="incomplete", nullable=False
    )  # incomplete | trialing | active | past_due | paused | canceled
    paddle_subscription_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )
    paddle_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    paddle_transaction_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    paddle_price_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    paddle_product_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scheduled_change_action: Mapped[str | None] = mapped_column(String(50), nullable=True)
    scheduled_change_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    provider_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class ProcessedWebhook(Base, TimestampMixin):
    """Ledger of Paddle event IDs already applied.

    Paddle delivers webhooks at-least-once. Non-idempotent side effects (email
    receipts, one-off credit grants) MUST dedupe on ``event_id`` before firing.
    UPSERT-shaped handlers don't need this — see Subscription.
    """

    __tablename__ = "processed_webhooks"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(50), default="paddle", nullable=False)
    event_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    event_type: Mapped[str | None] = mapped_column(String(100), nullable=True)


class Communication(TenantScopedBase):
    """A logged message/email/SMS/call/chat message with a contact.

    For the mobile in-app chat, ``quote_request_id`` threads messages around a
    lead/quote request and ``sender_role`` distinguishes the customer, business
    staff and the AI assistant.
    """

    __tablename__ = "communications"

    contact_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    quote_request_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("quote_requests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), default="outbound", nullable=False)
    sender_role: Mapped[str] = mapped_column(
        String(20), default="business", nullable=False
    )  # customer | business | ai
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="sent", nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # AI follow-up metadata: confidence score, completion flag, and any extra
    # structured data produced by the LLM (e.g. extracted facts from the reply).
    ai_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    quote_request: Mapped[QuoteRequest | None] = relationship("QuoteRequest")


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


class BusinessCredentials(TenantScopedBase):
    """Licences, insurance and accreditations for a trade business."""

    __tablename__ = "business_credentials"

    credential_type: Mapped[str] = mapped_column(String(50), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reference_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    coverage_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    document_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(50), default="self_declared", nullable=False
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    extra_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class ServiceArea(TenantScopedBase):
    """A postcode prefix, nation or radius-based service area for a business."""

    __tablename__ = "service_areas"

    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    postcode_prefix: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nation: Mapped[str | None] = mapped_column(String(50), nullable=True)
    lat: Mapped[Decimal | None] = mapped_column(Numeric(10, 8), nullable=True)
    lng: Mapped[Decimal | None] = mapped_column(Numeric(11, 8), nullable=True)
    radius_miles: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class BusinessService(TenantScopedBase):
    """A service category offered by a trade business."""

    __tablename__ = "business_services"

    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    subcategory: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_launch_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class PricingProfile(TenantScopedBase):
    """A trade business pricing model (time & materials or per point)."""

    __tablename__ = "pricing_profiles"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    profile_type: Mapped[str] = mapped_column(
        String(50), default="time_materials", nullable=False
    )  # time_materials | per_point
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.20"))
    markup_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    call_out_fee: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0.0000"))
    minimum_charge: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0.0000"))
    extra_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class PricingRate(TenantScopedBase):
    """A line in a business rate card."""

    __tablename__ = "pricing_rates"

    pricing_profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("pricing_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0.0000"))
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    extra_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class Integration(TenantScopedBase):
    """A third-party integration connected to a tenant."""

    __tablename__ = "integrations"

    integration_type: Mapped[str] = mapped_column(String(50), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="disconnected", nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    external_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Customer(TenantScopedBase):
    """A customer account that can log in and track quotes."""

    __tablename__ = "customers"

    contact_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Address/postcode and property profile live on the customer account (not
    # only the CRM contact) so repeat quote requests can pre-fill them.
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    property_profile: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    magic_link_token: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    magic_link_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    marketing_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    preferred_contact_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Parking/access notes mirrored from the CRM contact so quote/job creation
    # can pre-fill site logistics whichever record it reads.
    parking_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Property(TenantScopedBase):
    """A customer property where work is carried out."""

    __tablename__ = "properties"

    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    address: Mapped[str] = mapped_column(Text, nullable=False)
    postcode: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    lat: Mapped[Decimal | None] = mapped_column(Numeric(10, 8), nullable=True)
    lng: Mapped[Decimal | None] = mapped_column(Numeric(11, 8), nullable=True)
    property_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bedrooms: Mapped[int | None] = mapped_column(nullable=True)
    tenure: Mapped[str | None] = mapped_column(String(50), nullable=True)
    epc_rating: Mapped[str | None] = mapped_column(String(10), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class QuoteRequest(TenantScopedBase):
    """A customer lead captured from QR, web form, universal link or message share."""

    __tablename__ = "quote_requests"

    contact_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    customer_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    property_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source: Mapped[str] = mapped_column(
        String(50), default="qr", nullable=False
    )  # qr | universal_link | web_form | app_store | sms_forward
    # How the customer arrived at the intake surface (attribution):
    # qr | code | widget | direct | app. NULL for staff-created leads.
    entry_channel: Mapped[str | None] = mapped_column(String(50), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    ai_extracted_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    urgency: Mapped[str] = mapped_column(
        String(50), default="normal", nullable=False
    )  # normal | emergency_today | this_week | this_month | flexible | just_researching
    status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False
    )  # pending | processed | draft_quote | converted_to_quote | closed
    quote_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    media_urls: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    triage_flags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    preferred_dates: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    safety_review_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Set when the AI triage closes without reaching confidence: the electrician
    # should call the customer to fill the remaining gaps before quoting.
    requires_callback: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    ai_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    reviewed_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    converted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # ORM-only relationship (no schema change): lets the leads list eager-load
    # the linked contact for the customer name/postcode shown on lead cards.
    contact: Mapped[Contact | None] = relationship("Contact")
    quote: Mapped[Quote | None] = relationship("Quote", foreign_keys="QuoteRequest.quote_id")


class MediaAsset(TenantScopedBase):
    """A photo, video or document attached to a quote request, job or quote."""

    __tablename__ = "media_assets"

    quote_request_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("quote_requests.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    job_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    quote_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    file_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(nullable=True)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="in_app", nullable=False)


class Consent(TenantScopedBase):
    """A consent record from a customer or contact."""

    __tablename__ = "consents"

    contact_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    customer_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    consent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)


class Notification(TenantScopedBase):
    """A persistent in-app notification for staff users or customer accounts.

    ``recipient_type`` distinguishes the audience: ``"staff"`` notifications
    are surfaced in the back-office app, ``"customer"`` ones in the homeowner
    app. A staff notification with ``recipient_id = None`` is addressed to
    every staff user of the tenant; otherwise it targets a single user (staff)
    or customer account (customer).
    """

    __tablename__ = "notifications"

    recipient_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # staff | customer
    # No FK: the recipient is a users.id for staff and a customers.id for
    # customer recipients. NULL means "all tenant staff" (staff only).
    recipient_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True, index=True
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Reminder(TenantScopedBase):
    """One dispatched reminder for a quote, invoice or appointment.

    The reminder scheduler appends a row per actually-delivered reminder
    across the email/sms/push channels; the row count per entity is the "how
    many reminders have gone out" state (quotes stop after the configured
    count) and ``created_at`` of the latest row is the anchor for the next
    cadence interval. Appointment reminders additionally dedupe on
    ``payload.window_hours`` + ``payload.role`` so each window fires once per
    recipient. Kept as a dedicated table (rather than a counter on the
    entity) so there is a full audit trail of what was chased and when.
    """

    __tablename__ = "reminders"

    entity_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # quote | invoice | appointment
    # No FK: points at quotes.id / invoices.id / appointments.id by entity_type.
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(20), default="email", nullable=False)
    # 1-based sequence number of this reminder for the entity.
    sequence: Mapped[int] = mapped_column(nullable=False, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class PushToken(TenantScopedBase):
    """An Expo push token registered by a staff or customer device."""

    __tablename__ = "push_tokens"

    owner_type: Mapped[str] = mapped_column(String(20), nullable=False)  # staff | customer
    owner_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)  # ios | android | web


class PasswordResetToken(TenantScopedBase):
    """A single-use password-reset token issued via email.

    ``owner_type`` distinguishes staff vs customer resets so the confirm
    endpoint can locate the right row. Tokens are hashed at rest so a leaked
    DB dump cannot be used to hijack accounts.
    """

    __tablename__ = "password_reset_tokens"

    owner_type: Mapped[str] = mapped_column(String(20), nullable=False)  # staff | customer
    owner_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Event(TenantScopedBase):
    """A timeline event for quotes, jobs or customer interactions."""

    __tablename__ = "events"

    actor_type: Mapped[str] = mapped_column(
        String(50), default="system", nullable=False
    )  # user | customer | system
    actor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class DemoQuoteEvent(Base):
    """Anonymous usage counter for the public, no-auth AI quote demo.

    Deliberately minimal so the marketing demo can run without a tenant:
    no ``tenant_id`` and no quote content (no job description, no line items)
    — only a salted IP hash plus browser/attribution metadata. Because it
    carries no ``tenant_id`` it is intentionally absent from
    ``app.rls.TENANT_SCOPED_TABLES``, so schema init does not attach a tenant
    isolation policy to it (same as the shared ``cost_items`` table).
    """

    __tablename__ = "demo_quote_events"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    # sha256(f"{ip}|{settings.auth_secret_key}") — the raw IP is never stored.
    ip_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    accept_language: Mapped[str | None] = mapped_column(String(300), nullable=True)
    referer: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    utm_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(100), nullable=True)
    generation_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)


# ---------------------------------------------------------------------------
# W2-A ENTITLEMENTS — ai_usage_counters (owned by the entitlements workstream;
# keep this block self-contained — ai_call_events from the telemetry
# workstream is added in its own separate block).
# ---------------------------------------------------------------------------


class AIUsageCounter(TenantScopedBase):
    """Legacy per-tenant monthly AI-action counter from the retired hybrid
    pricing model. Unreferenced since the move to flat unmetered pricing
    (ADR-001); retained only because the table may hold historical rows.
    Tenant-scoped: registered in ``app.rls.TENANT_SCOPED_TABLES``.
    """

    __tablename__ = "ai_usage_counters"

    period: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM (UTC)
    ai_actions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "period", name="uq_ai_usage_counters_tenant_period"),
    )


# ---------------------------------------------------------------------------
# W1-A AI TELEMETRY — ai_call_events + fx_rates (owned by the telemetry
# workstream). Both are plain ``Base`` tables, NOT tenant-scoped (same
# rationale as ``DemoQuoteEvent``: cross-tenant ops/BI queries over AI spend
# must work without an RLS context; ``tenant_id`` is a plain indexed column,
# not an RLS key). Do NOT add either table to ``app.rls.TENANT_SCOPED_TABLES``.
# ---------------------------------------------------------------------------


class AiCallEvent(Base):
    """One recorded AI call (or funnel outcome) for spend/quality observability.

    Column names follow the OpenTelemetry GenAI semantic conventions where one
    applies (``gen_ai_*``) so external tooling recognises the shape. Written
    exclusively by ``app.ai_telemetry.record_ai_event`` — never instantiate
    directly from routers. ``feature`` vocabulary:
    ``quote_draft | quote_refine | triage_followup | embedding | demo_quote |
    outcome``. ``status`` vocabulary: ``success | timeout | error |
    abandoned``. Outcome rows (quote_sent / quote_accepted / invoice_paid in
    ``raw_payload["outcome"]``) carry no model/token/cost fields — they exist
    so cost↔outcome joins run off this one table via ``trace_id``.
    """

    __tablename__ = "ai_call_events"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )
    # Plain column (no FK, no RLS): NULL for demo/system calls, set for tenant
    # calls so per-tenant spend rollups can group on it.
    tenant_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    # NULL for system/background/demo calls.
    user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    feature: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Who/what initiated the call: staff (default) | customer | system. Indexed
    # so per-actor fair-use and funnel queries stay cheap.
    actor_type: Mapped[str] = mapped_column(String(20), default="staff", nullable=False, index=True)
    # How the end user arrived at the AI surface (customer entry points):
    # qr_van | qr_card | code | widget | direct | app. NULL for staff/system calls.
    entry_channel: Mapped[str | None] = mapped_column(String(50), nullable=True)
    gen_ai_provider_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gen_ai_request_model: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    gen_ai_usage_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gen_ai_usage_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gen_ai_usage_cached_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    est_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    cost_gbp: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    fx_rate_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    latency_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="success", nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Links regenerations/refines back to the generation they replaced.
    parent_event_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ai_call_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Quote-level funnel root: minted on first generation, stored on
    # ``Quote.ai_metadata["trace_id"]``, propagated to refines/outcomes.
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    prompt_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    completeness: Mapped[float | None] = mapped_column(Float, nullable=True)
    retrieval_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Plain columns (no FK): the events table must stay writable even when the
    # referenced quote lives behind RLS or is later deleted.
    quote_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    quote_request_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True, index=True
    )
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    __table_args__ = (
        # The rollup query shape: per-tenant, per-feature, time-ordered.
        Index("ix_ai_call_events_tenant_feature_created", "tenant_id", "feature", "created_at"),
    )


class FxRate(Base):
    """Daily USD→GBP rate used to stamp ``AiCallEvent.cost_gbp`` at write time.

    Populated by the weekly refresh job (separate workstream); until the first
    row lands, ``app.fx.get_usd_gbp_rate`` falls back to
    ``settings.fx_usd_gbp_fallback_rate``.
    """

    __tablename__ = "fx_rates"

    rate_date: Mapped[date] = mapped_column(Date, primary_key=True)
    usd_gbp: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


# ---------------------------------------------------------------------------
# W1-C AI ROLLUPS + ALERT STATE — ai_rollup_user_day / ai_rollup_feature_day /
# ai_rollup_org_day / ai_alert_state (owned by the rollups/alerts/ops
# workstream). All four are plain ``Base`` tables, NOT tenant-scoped (same
# rationale as ``AiCallEvent``: cross-tenant ops/BI queries over AI spend must
# work without an RLS context; ``tenant_id`` is a plain indexed column, not an
# RLS key). Do NOT add any of these tables to ``app.rls.TENANT_SCOPED_TABLES``.
# ---------------------------------------------------------------------------


class AiRollupUserDay(Base):
    """Per-day, per-tenant, per-user, per-feature AI usage rollup.

    Folded nightly from ``ai_call_events`` (+ ``ai_draft_feedback`` when that
    table exists) by the rollup job in ``app.scheduler``; dashboards/BI read
    this table instead of scanning raw events. Rows are deleted and re-folded
    for the target day inside the job's advisory lock, so the fold is
    idempotent. Measure semantics (all NULL-safe sums):

    * ``generations`` — events with ``status='success'`` (outcome rows
      excluded; they carry no tokens/cost and land in their own
      ``feature='outcome'`` row).
    * ``retries`` — non-outcome events with ``status != 'success'``
      (timeout/error/abandoned).
    * ``latency_p50`` / ``latency_p95`` — nearest-rank percentiles over
      non-NULL ``latency_seconds`` of non-outcome events (NULL when none).
    * ``avg_keep_rate`` — mean ``ai_draft_feedback.keep_rate`` attributed to
      this group via ``generation_event_id`` (NULL when no feedback exists).
    * ``quotes_sent`` — count of ``feature='outcome'`` events with
      ``raw_payload["outcome"] = 'quote_sent'``.
    """

    __tablename__ = "ai_rollup_user_day"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # Plain columns (no FK, no RLS): NULL for platform/demo/embedding events.
    tenant_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    feature: Mapped[str] = mapped_column(String(50), nullable=False)
    generations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_input: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_output: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_cached: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    est_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("0"), nullable=False
    )
    cost_gbp: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"), nullable=False)
    latency_p50: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_p95: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_keep_rate: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    quotes_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("date", "tenant_id", "user_id", "feature", name="uq_ai_rollup_user_day"),
        Index("ix_ai_rollup_user_day_tenant_date", "tenant_id", "date"),
    )


class AiRollupFeatureDay(Base):
    """Per-day, per-feature platform-wide AI usage rollup.

    Same measures as :class:`AiRollupUserDay` but grouped only by
    ``(date, feature)`` — includes tenant-NULL events (embeddings, demo
    quotes), which only ever appear here and never in the per-user table's
    tenant rows. This is the table budget/anomaly alerts read.
    """

    __tablename__ = "ai_rollup_feature_day"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    feature: Mapped[str] = mapped_column(String(50), nullable=False)
    generations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_input: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_output: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_cached: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    est_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("0"), nullable=False
    )
    cost_gbp: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"), nullable=False)
    latency_p50: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_p95: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_keep_rate: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    quotes_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (UniqueConstraint("date", "feature", name="uq_ai_rollup_feature_day"),)


class AiRollupOrgDay(Base):
    """Per-day, per-tenant AI usage rollup across all features.

    Same measures as :class:`AiRollupUserDay` but grouped only by
    ``(date, tenant_id)`` — the granularity behind the staff ops cost
    leaderboard. Adds ``users_active`` (distinct non-NULL ``user_id`` s with
    spend events that day) and ``latency_p99`` (the user/feature rollups stop
    at p95; the org table carries p99 for cohort p99 stats). Events with
    ``tenant_id=None`` (demo/embedding) are platform-level and never fold
    here.
    """

    __tablename__ = "ai_rollup_org_day"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # Plain column (no FK, no RLS): every row is tenant-attributed by
    # definition — the fold skips tenant-NULL events.
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    users_active: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    generations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_input: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_output: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_cached: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    est_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("0"), nullable=False
    )
    cost_gbp: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"), nullable=False)
    latency_p50: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_p95: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_p99: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_keep_rate: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    quotes_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("date", "tenant_id", name="uq_ai_rollup_org_day"),
        Index("ix_ai_rollup_org_day_tenant_date", "tenant_id", "date"),
    )


class AiAlertState(Base):
    """One row per fired alert so each alert fires exactly once per period.

    ``period`` scopes the dedupe: ``YYYY-MM`` for monthly budget thresholds
    (``threshold`` = ``budget_50`` / ``budget_80`` / ``budget_100``) and
    per-org monthly fair-use crossings (``threshold`` = ``fair_use:<tenant_id>``),
    ``YYYY-MM-DD`` for daily anomalies (``threshold`` = ``cost_spike`` /
    ``latency_p95_spike`` / ``rollup_failed``). The nightly job inserts a row
    before dispatching, so a crashed/restarted job never double-fires the same alert.
    """

    __tablename__ = "ai_alert_state"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    period: Mapped[str] = mapped_column(String(10), nullable=False)
    threshold: Mapped[str] = mapped_column(String(50), nullable=False)
    fired_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("period", "threshold", name="uq_ai_alert_state_period_threshold"),
    )


# ---------------------------------------------------------------------------
# W1-B AI QUALITY — ai_draft_feedback (owned by the feedback/quality
# workstream). Tenant-scoped (registered in app.rls.TENANT_SCOPED_TABLES) so
# per-tenant quality reads respect RLS; the cross-tenant rollup folds these
# rows into ai_rollup_* via the scheduler's bypass context.
# ---------------------------------------------------------------------------


class AiDraftFeedback(TenantScopedBase):
    """One AI draft's lifecycle from generation to send, with quality metrics.

    Written by ``app.ai_quality.capture_draft_feedback`` at every generation
    point (generate / refine / requote — wherever the router snapshots
    ``extra_data["ai_draft"]``) and finalised by
    ``app.ai_quality.finalize_draft_feedback`` from ``send_quote``.
    ``compute_draft_quality`` (BackgroundTasks worker) then derives the
    keep-rate metrics in place — recompute overwrites, never duplicates.

    A quote has at most one OPEN row (``final_snapshot IS NULL``): a
    regeneration updates the open row's ``generation_event_id`` +
    ``draft_snapshot`` in place, so the metrics always compare the LATEST AI
    draft against the quote as sent. A quote sent, re-drafted and re-sent
    gets a second row, so each send is measured against the draft that
    preceded it.
    """

    __tablename__ = "ai_draft_feedback"

    # The ai_call_events row for the generation this draft came from. Plain
    # FK (SET NULL) so cost↔quality joins work but event-table cleanup never
    # breaks feedback rows.
    generation_event_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ai_call_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Plain column (no FK): the feedback row must survive quote deletion so
    # quality analytics keep their history.
    quote_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Snapshot shape mirrors extra_data["ai_draft"]:
    # {"line_items": [{"description", "quantity", "unit_price"}], "total"}.
    draft_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    final_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Unchanged AI lines / total AI lines (exact description, quantity AND
    # unit price). 0.000-1.000, quantised to 0.001.
    keep_rate: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    # (sum matched final line totals - sum matched draft line totals) /
    # sum matched draft line totals x 100. Only line-matched pairs count —
    # added/removed lines never distort the drift percentage.
    price_drift_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    lines_added: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lines_removed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Fuzzy-matched (difflib ratio ≥ 0.85) but not exact-description pairs.
    description_rewrites: Mapped[int | None] = mapped_column(Integer, nullable=True)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DocumentAccessToken(Base, TimestampMixin):
    """A bearer token that opens a public, read-only quote/invoice web page.

    Issued when a quote or invoice is emailed to the customer; the raw token
    only ever appears in the emailed link (``/{kind}/{token}`` on the landing
    site). Only the SHA-256 hash is stored so a leaked DB dump cannot be used
    to open documents. Unlike ``PasswordResetToken`` these are NOT single-use
    — a customer re-opens their quote/invoice link many times — but they
    expire (30 days) and can be revoked; re-sending a document revokes its
    earlier tokens so only the newest emailed link stays valid.

    Deliberately a plain ``Base`` (like ``DemoQuoteEvent``): the public,
    no-auth render endpoint looks the token up before any tenant context
    exists, so the table must stay out of ``app.rls.TENANT_SCOPED_TABLES``.
    ``tenant_id``/``document_id`` are plain columns (no FK) so token rows
    survive document deletion — the endpoint then 404s like any invalid token.
    """

    __tablename__ = "document_access_tokens"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # quote | invoice
    document_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # Email the link was sent to, snapshotted for audit/prefill only — never
    # returned by the public endpoint.
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class StripeAccount(Base, TimestampMixin):
    """A tenant's Stripe Connect Express account for card payments (ADR-003).

    One row per tenant (``tenant_id`` unique). Customers pay invoices by card
    via destination charges on this account — funds settle directly to the
    tradie with no platform application fee. The capability flags are mirrored
    from Stripe (onboarding return + ``account.updated`` webhooks) so the app
    can render the payments status without a live API round-trip.
    ``onboarding_complete`` flips true once Stripe reports both charges and
    payouts enabled.
    """

    __tablename__ = "stripe_accounts"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    stripe_account_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    details_submitted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    charges_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    payouts_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CustomerPortalToken(Base):
    """A magic-link bearer token that signs a homeowner into the customer portal.

    Minted when a portal magic link is emailed (or embedded in a transactional
    email such as quote-accepted); the raw token only ever appears in the
    emailed link (``/auth/magic?token=...`` on the tenant's portal subdomain).
    Only the SHA-256 hash is stored so a leaked DB dump cannot be replayed.
    Re-issuing for a customer revokes their earlier still-valid tokens so only
    the newest emailed link stays valid.

    Deliberately a plain ``Base`` (same pattern as ``DocumentAccessToken``):
    the magic-link exchange looks the token up before any tenant/auth context
    exists, so the table must stay out of ``app.rls.TENANT_SCOPED_TABLES``.
    ``tenant_id`` is a plain column (no FK) so rows survive tenant teardown;
    the exchange endpoint then 401s like any invalid token.
    """

    __tablename__ = "customer_portal_tokens"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserInviteToken(Base):
    """A single-use bearer token that lets an invited staff user set a password.

    Minted by ``POST /users/invite`` and re-issued by
    ``POST /users/invite/magic-link``; the raw token only ever appears in the
    emailed link (``/accept-invite?token=...`` on the landing site). Only the
    SHA-256 hash is stored so a leaked DB dump cannot be replayed. Re-issuing
    for a user revokes their earlier still-valid tokens so only the newest
    emailed link works, and ``used_at`` makes each token single-use.

    Deliberately a plain ``Base`` (same pattern as ``CustomerPortalToken``):
    the accept endpoint looks the token up before any tenant/auth context
    exists, so the table must stay out of ``app.rls.TENANT_SCOPED_TABLES``.
    ``tenant_id`` is a plain column (no FK) so rows survive tenant teardown;
    the accept endpoint then 401s like any invalid token.
    """

    __tablename__ = "user_invite_tokens"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmailFailureAlert(Base):
    """Dedupe ledger for staff "customer message wasn't delivered" alerts.

    One row per (tenant, contact, calendar day): the first send-time failure
    or Resend bounce webhook for a contact inserts a row and pages staff;
    every further failure that day — any purpose, either source — sees the
    row and stays silent, so a broken mailbox cannot spam the electrician's
    bell on every reminder sweep or webhook retry. Telnyx SMS delivery
    receipts (``source="telnyx_dlr"``) share the same ledger, so a customer
    whose details are wrong on both channels pages staff at most once a day.

    Deliberately a plain ``Base`` (same pattern as ``ProcessedWebhook``): rows
    are written from contexts with no tenant GUC (bounce webhooks) and are
    only ever read with an explicit tenant_id predicate. ``contact_id`` is a
    plain column (no FK) so ledger rows survive contact/tenant teardown.
    """

    __tablename__ = "email_failure_alerts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "contact_id", "alert_date", name="uq_email_failure_alerts_day"
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    contact_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    alert_date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # send | bounce | telnyx_dlr
    purpose: Mapped[str] = mapped_column(String(100), nullable=False)
    error_class: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
