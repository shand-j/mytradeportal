"""Pydantic schemas for API requests and responses."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field, model_validator

# ---------------------------------------------------------------------------
# Tenant
# ---------------------------------------------------------------------------


class TenantCreate(BaseModel):
    slug: str = Field(..., min_length=2, max_length=63)
    name: str = Field(..., min_length=1, max_length=255)

    # Optional atomic bootstrap of the tenant's first admin user. All three
    # fields must be provided together; when omitted only the tenant is
    # created (used by tests and seed scripts).
    admin_email: EmailStr | None = None
    admin_password: str | None = Field(default=None, min_length=12, max_length=128)
    admin_name: str | None = Field(default=None, min_length=1, max_length=255)

    @model_validator(mode="after")
    def _admin_fields_all_or_none(self) -> "TenantCreate":
        provided = (self.admin_email, self.admin_password, self.admin_name)
        if any(v is not None for v in provided) and not all(v is not None for v in provided):
            raise ValueError("admin_email, admin_password and admin_name must be provided together")
        return self


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    settings: dict[str, Any] | None = None

    # Business details
    email: str | None = Field(default=None, alias="email")
    phone: str | None = Field(default=None, alias="phone")
    website: str | None = Field(default=None, alias="website")
    address: str | None = Field(default=None, alias="address")

    # Branding
    logo_url: str | None = Field(default=None, alias="logoUrl")
    primary_color: str | None = Field(default=None, alias="primaryColor")
    secondary_color: str | None = Field(default=None, alias="secondaryColor")

    # Pricing
    hourly_labour_rate: float | None = Field(default=None, alias="hourlyLaborRate")
    daily_labour_rate: float | None = Field(default=None, alias="dailyLaborRate")
    mate_daily_rate: float | None = Field(default=None, alias="mateDailyRate")
    mate_percent: float | None = Field(default=None, alias="matePercent")
    markup_percentage: float | None = Field(default=None, alias="markupPercentage")
    min_margin_percent: float | None = Field(default=None, alias="minMarginPercent")
    price_tolerance_percent: float | None = Field(default=None, alias="priceTolerancePercent")
    minimum_charge: float | None = Field(default=None, alias="minimumCharge")
    vat_rate: float | None = Field(default=None, alias="vatRate")

    # Plan / integrations
    plan_tier: str | None = Field(default=None, alias="planTier")
    google_place_id: str | None = Field(default=None, alias="googlePlaceId")


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    is_active: bool
    settings: dict[str, Any]
    paddle_sandbox: bool
    created_at: datetime
    updated_at: datetime

    # Business details
    email: str = Field(default="", serialization_alias="email")
    phone: str = Field(default="", serialization_alias="phone")
    website: str | None = Field(default=None, serialization_alias="website")
    address: str = Field(default="", serialization_alias="address")

    # Branding
    logo_url: str | None = Field(default=None, serialization_alias="logoUrl")
    primary_color: str = Field(default="#D4650A", serialization_alias="primaryColor")
    secondary_color: str = Field(default="#7C3AED", serialization_alias="secondaryColor")

    # Pricing
    hourly_labour_rate: float = Field(default=0.0, serialization_alias="hourlyLaborRate")
    daily_labour_rate: float = Field(default=0.0, serialization_alias="dailyLaborRate")
    mate_daily_rate: float = Field(default=0.0, serialization_alias="mateDailyRate")
    mate_percent: float = Field(default=55.0, serialization_alias="matePercent")
    markup_percentage: float = Field(default=0.0, serialization_alias="markupPercentage")
    min_margin_percent: float = Field(default=0.0, serialization_alias="minMarginPercent")
    price_tolerance_percent: float = Field(
        default=15.0, serialization_alias="priceTolerancePercent"
    )
    minimum_charge: float = Field(default=0.0, serialization_alias="minimumCharge")
    vat_rate: float = Field(default=20.0, serialization_alias="vatRate")

    # Plan / integrations
    plan_tier: str = Field(default="starter", serialization_alias="planTier")
    google_place_id: str | None = Field(default=None, serialization_alias="googlePlaceId")


# ---------------------------------------------------------------------------
# Contact
# ---------------------------------------------------------------------------


class ContactCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    postcode: str | None = None
    notes: str | None = None


class ContactUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    postcode: str | None = None
    notes: str | None = None


class ContactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    email: str | None
    phone: str | None
    address: str | None
    postcode: str | None
    notes: str | None
    avatar_url: str | None = None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def first_name(self) -> str:
        return self.name.split(" ", 1)[0]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def last_name(self) -> str:
        parts = self.name.split(" ", 1)
        return parts[1] if len(parts) > 1 else ""


# ---------------------------------------------------------------------------
# Quote
# ---------------------------------------------------------------------------


class QuoteLineItemCreate(BaseModel):
    description: str
    quantity: Decimal = Decimal("1.00")
    unit_price: Decimal = Decimal("0.00")


class QuoteLineItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    description: str
    quantity: Decimal
    unit_price: Decimal
    total: Decimal


class BoQLineItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    description: str
    category: str | None
    unit: str
    quantity: Decimal
    labour_hours: Decimal
    labour_rate: Decimal
    labour_total: Decimal
    material_cost: Decimal
    material_total: Decimal
    plant_cost: Decimal
    plant_total: Decimal
    unit_price: Decimal
    total: Decimal
    supplier: str | None
    brand: str | None
    sku: str | None
    product_url: str | None
    retail_price_incl_vat: Decimal | None
    notes: str | None


class BoQLineItemUpdate(BaseModel):
    id: UUID | None = None
    code: str = Field(..., min_length=1, max_length=63)
    description: str = Field(..., min_length=1)
    category: str | None = None
    unit: str = Field(default="item", min_length=1, max_length=50)
    quantity: Decimal = Decimal("1.00")
    labour_hours: Decimal = Decimal("0.00")
    labour_rate: Decimal = Decimal("0.0000")
    labour_total: Decimal = Decimal("0.0000")
    material_cost: Decimal = Decimal("0.0000")
    material_total: Decimal = Decimal("0.0000")
    plant_cost: Decimal = Decimal("0.0000")
    plant_total: Decimal = Decimal("0.0000")
    supplier: str | None = None
    brand: str | None = None
    sku: str | None = None
    product_url: str | None = None
    retail_price_incl_vat: Decimal | None = None
    notes: str | None = None


class CustomerSummaryLineRead(BaseModel):
    description: str
    total: Decimal


class MarginIndicatorRead(BaseModel):
    material_subtotal: Decimal = Decimal("0.00")
    labour_subtotal: Decimal = Decimal("0.00")
    subtotal: Decimal = Decimal("0.00")
    target_markup_percent: Decimal = Decimal("0.00")
    estimated_margin_percent: Decimal = Decimal("0.00")
    estimated_margin_amount: Decimal = Decimal("0.00")


class RetrievalEvidenceRead(BaseModel):
    knowledge_available: bool = True
    job_types: list[str] = Field(default_factory=list)
    citations_used: int = 0
    source_documents: list[str] = Field(default_factory=list)
    retrieval_warnings: list[str] = Field(default_factory=list)
    top_relevance_score: float = 0.0
    resolved_catalogue_items: int = 0
    resolved_catalogue_sources: list[str] = Field(default_factory=list)
    quality_score: float = 1.0
    quality_gate_passed: bool = True
    quality_gate_reasons: list[str] = Field(default_factory=list)
    fallback_policy_applied: str = "none"
    confidence_capped: bool = False


class BillOfQuantitiesRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    quote_id: UUID
    status: str
    notes: str | None
    subtotal: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    total: Decimal
    confidence: float
    warnings: list[str]
    regulatory_citations: list[dict[str, Any]] = Field(default_factory=list)
    compliance_warnings: list[str] = Field(default_factory=list)
    customer_summary_lines: list[CustomerSummaryLineRead] = Field(default_factory=list)
    margin_indicator: MarginIndicatorRead | None = None
    retrieval_evidence: RetrievalEvidenceRead | None = None
    standard: str | None
    line_items: list[BoQLineItemRead]
    created_at: datetime
    updated_at: datetime


class BillOfQuantitiesUpdate(BaseModel):
    notes: str | None = None
    line_items: list[BoQLineItemUpdate] = Field(default_factory=list)


class QuoteCreate(BaseModel):
    contact_id: UUID
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    line_items: list[QuoteLineItemCreate] = Field(default_factory=list)
    vat_rate: Decimal = Decimal("0.20")
    valid_until: datetime | None = None


class QuoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    contact_id: UUID
    title: str
    description: str | None
    status: str
    subtotal: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    total: Decimal
    valid_until: datetime | None
    approved_at: datetime | None
    sent_at: datetime | None
    line_items: list[QuoteLineItemRead]
    bill_of_quantities: BillOfQuantitiesRead | None
    created_at: datetime
    updated_at: datetime
    customer: ContactRead = Field(validation_alias="contact", serialization_alias="customer")


class QuoteApprove(BaseModel):
    approved: bool = True


class QuoteUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    valid_until: datetime | None = None
    status: str | None = None
    line_items: list[QuoteLineItemCreate] | None = None


class QuoteGenerateRequest(BaseModel):
    contact_id: UUID | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    description: str = Field(..., min_length=5)
    property_type: str | None = None
    site_survey: dict[str, Any] | None = None
    use_ocerp: bool = False


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------


class JobCreate(BaseModel):
    contact_id: UUID
    quote_id: UUID | None = None
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None


class JobUpdate(BaseModel):
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    notes: str | None = None


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    contact_id: UUID
    quote_id: UUID | None
    title: str
    description: str | None
    status: str
    scheduled_start: datetime | None
    scheduled_end: datetime | None
    completed_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    customer: ContactRead = Field(validation_alias="contact", serialization_alias="customer")


# ---------------------------------------------------------------------------
# Appointment
# ---------------------------------------------------------------------------


class AppointmentCreate(BaseModel):
    contact_id: UUID
    job_id: UUID | None = None
    title: str = Field(..., min_length=1, max_length=255)
    start_at: datetime
    end_at: datetime
    address: str | None = None
    notes: str | None = None


class AppointmentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    start_at: datetime | None = None
    end_at: datetime | None = None
    status: str | None = None
    address: str | None = None
    notes: str | None = None


class AppointmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    contact_id: UUID
    job_id: UUID | None
    title: str
    start_at: datetime
    end_at: datetime
    status: str
    address: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------


class InvoiceLineItemCreate(BaseModel):
    description: str
    quantity: Decimal = Decimal("1.00")
    unit_price: Decimal = Decimal("0.00")


class InvoiceLineItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    description: str
    quantity: Decimal
    unit_price: Decimal
    total: Decimal


class InvoiceCreate(BaseModel):
    contact_id: UUID
    job_id: UUID | None = None
    quote_id: UUID | None = None
    invoice_number: str | None = Field(default=None, min_length=1, max_length=50)
    due_date: datetime | None = None
    vat_rate: Decimal = Decimal("0.20")
    line_items: list[InvoiceLineItemCreate] = Field(default_factory=list)


class InvoiceUpdate(BaseModel):
    due_date: datetime | None = None
    notes: str | None = None
    status: str | None = None


class QuoteConvertToInvoice(BaseModel):
    invoice_number: str | None = Field(default=None, min_length=1, max_length=50)
    due_date: datetime | None = None


class InvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    contact_id: UUID
    job_id: UUID | None
    quote_id: UUID | None
    invoice_number: str
    status: str
    issue_date: datetime
    due_date: datetime | None
    subtotal: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    total: Decimal
    paid_at: datetime | None
    notes: str | None
    paddle_checkout_id: str | None
    paddle_transaction_id: str | None
    line_items: list[InvoiceLineItemRead]
    created_at: datetime
    updated_at: datetime
    customer: ContactRead = Field(validation_alias="contact", serialization_alias="customer")


# ---------------------------------------------------------------------------
# Payment / Paddle
# ---------------------------------------------------------------------------


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    invoice_id: UUID
    amount: Decimal
    currency_code: str
    status: str
    provider: str
    provider_transaction_id: str | None
    provider_checkout_id: str | None
    paid_at: datetime | None
    created_at: datetime


class PaddleCheckoutCreate(BaseModel):
    invoice_id: UUID
    success_url: str | None = None
    customer_email: str | None = None


class PaddleCheckoutRead(BaseModel):
    checkout_id: str
    checkout_url: str


# ---------------------------------------------------------------------------
# Communication
# ---------------------------------------------------------------------------


class CommunicationCreate(BaseModel):
    contact_id: UUID | None = None
    channel: str
    direction: str = "outbound"
    subject: str | None = None
    body: str | None = None
    status: str | None = "sent"


class CommunicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    contact_id: UUID | None
    channel: str
    direction: str
    subject: str | None
    body: str | None
    status: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------


class ReviewCreate(BaseModel):
    contact_id: UUID
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = None
    source: str | None = None


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    contact_id: UUID
    rating: int
    comment: str | None
    source: str | None
    status: str
    response: str | None
    responded_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ReviewStats(BaseModel):
    average_rating: float
    total_count: int
    pending_count: int
    approved_count: int
    rejected_count: int


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


class DashboardKPIs(BaseModel):
    revenue_this_month: float
    revenue_change: float
    active_jobs: int
    jobs_capacity: int
    pending_quotes: int
    pending_quotes_value: float
    quotes_expiring_soon: int
    average_rating: float
    review_count: int


class RevenueChartData(BaseModel):
    labels: list[str]
    revenue: list[float]
    target: list[float]


class ServiceBreakdownItem(BaseModel):
    service: str
    percentage: float
    revenue: float
    color: str


class Activity(BaseModel):
    id: UUID
    type: str
    title: str
    description: str | None
    entity_type: str
    entity_id: UUID
    created_at: datetime


class VoiceStats(BaseModel):
    calls_today: int
    resolution_rate: int
    quotes_from_voice: int
    avg_call_duration: str


class DashboardData(BaseModel):
    kpi: DashboardKPIs
    revenue_chart: RevenueChartData
    service_breakdown: list[ServiceBreakdownItem]
    recent_activity: list[Activity]
    voice_stats: VoiceStats | None = None


class AiQuotePerformanceMonthlyData(BaseModel):
    month: str
    ai_quotes: int
    manual_quotes: int
    ai_acceptance: int
    manual_acceptance: int


class AiQuotePerformance(BaseModel):
    total_generated: int
    acceptance_rate: float
    average_value: float
    average_generation_time: float
    monthly_data: list[AiQuotePerformanceMonthlyData]


class VoiceCall(BaseModel):
    caller: str
    duration: str
    outcome: str
    quote_adjusted: bool
    date: str


class VoiceAnalytics(BaseModel):
    total_calls: int
    average_duration: str
    resolution_rate: float
    total_revenue: float
    recent_calls: list[VoiceCall]


class DemandForecastPrediction(BaseModel):
    week: str
    predicted_jobs: int
    confidence: float


class DemandForecast(BaseModel):
    predictions: list[DemandForecastPrediction]
    insight: str


class AIInsights(BaseModel):
    ai_quote_performance: AiQuotePerformance
    demand_forecast: DemandForecast | None = None
    voice_analytics: VoiceAnalytics | None = None


# ---------------------------------------------------------------------------
# File upload
# ---------------------------------------------------------------------------


class PresignedUploadRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str | None = None


class PresignedUploadResponse(BaseModel):
    url: str
    fields: dict[str, str]
    key: str


# ---------------------------------------------------------------------------
# User / Auth
# ---------------------------------------------------------------------------


class UserCreate(BaseModel):
    email: str = Field(..., min_length=1, max_length=255)
    full_name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(default="technician")
    phone: str | None = Field(default=None, max_length=50)


class UserUpdate(BaseModel):
    email: str | None = Field(default=None, min_length=1, max_length=255)
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    role: str | None = None
    phone: str | None = Field(default=None, max_length=50)
    is_active: bool | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    phone: str | None
    created_at: datetime
    updated_at: datetime


class UserLogin(BaseModel):
    email: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)
    # Optional explicit tenant slug. When provided it takes precedence over
    # Host-subdomain resolution so login works on bare domains (e.g.
    # Railway's *.up.railway.app) where every tenant shares one hostname.
    tenant_slug: str | None = Field(default=None, min_length=2, max_length=63)


class TenantBootstrapRead(TenantRead):
    """Tenant plus the first admin user created alongside it (if requested)."""

    admin_user: UserRead | None = None
