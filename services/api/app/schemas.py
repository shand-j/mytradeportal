"""Pydantic schemas for API requests and responses."""

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

# ---------------------------------------------------------------------------
# Tenant
# ---------------------------------------------------------------------------


class TenantCreate(BaseModel):
    slug: str = Field(..., min_length=2, max_length=63)
    name: str = Field(..., min_length=1, max_length=255)
    # Business contact details captured in onboarding; persisted on the tenant
    # so Settings shows them (previously dropped at registration).
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=2000)
    postcode: str | None = Field(default=None, max_length=20)

    # Optional atomic bootstrap of the tenant's first admin user. All three
    # fields must be provided together; when omitted only the tenant is
    # created (used by tests and seed scripts).
    admin_email: EmailStr | None = None
    admin_password: str | None = Field(default=None, min_length=8, max_length=128)
    admin_name: str | None = Field(default=None, min_length=1, max_length=255)

    @model_validator(mode="after")
    def _admin_fields_all_or_none(self) -> "TenantCreate":
        provided = (self.admin_email, self.admin_password, self.admin_name)
        if any(v is not None for v in provided) and not all(v is not None for v in provided):
            raise ValueError("admin_email, admin_password and admin_name must be provided together")
        return self


class TenantUpdate(BaseModel):
    # Accept both snake_case (what the mobile app sends) and camelCase
    # aliases (legacy web client) for every field.
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = Field(default=None, min_length=1, max_length=255)
    settings: dict[str, Any] | None = None

    # Business details
    email: str | None = Field(default=None, alias="email")
    phone: str | None = Field(default=None, alias="phone")
    website: str | None = Field(default=None, alias="website")
    address: str | None = Field(default=None, alias="address")
    postcode: str | None = Field(default=None, alias="postcode")

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

    # Workload metrics captured during onboarding (feed the client-side
    # time-saved metric; persisted verbatim into tenant.settings).
    quotes_per_week: int | None = Field(default=None, alias="quotesPerWeek")
    avg_minutes_per_quote: int | None = Field(default=None, alias="avgMinutesPerQuote")


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    code: str | None = None
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
    postcode: str | None = Field(default=None, serialization_alias="postcode")

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
    preferred_contact_method: str | None = Field(default=None, max_length=50)
    property_type: str | None = Field(default=None, max_length=50)
    bedrooms: int | None = None
    parking_notes: str | None = None
    access_notes: str | None = None


class ContactUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    postcode: str | None = None
    notes: str | None = None
    preferred_contact_method: str | None = Field(default=None, max_length=50)
    property_type: str | None = Field(default=None, max_length=50)
    bedrooms: int | None = None
    parking_notes: str | None = None
    access_notes: str | None = None
    # Manual trust-badge overrides (N26): {badge: true} forces a badge on,
    # {badge: false} forces it off, {badge: null} clears the override so the
    # auto rule decides again. Keys must be known badge slugs.
    badge_overrides: dict[str, bool | None] | None = None


class ContactBlockRequest(BaseModel):
    """Optional reason recorded when blocking a customer (N26)."""

    reason: str | None = Field(default=None, max_length=500)


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
    preferred_contact_method: str | None = None
    property_type: str | None = None
    bedrooms: int | None = None
    parking_notes: str | None = None
    access_notes: str | None = None
    avatar_url: str | None = None
    created_at: datetime
    updated_at: datetime
    # True when a customer account is linked to this contact. Unregistered
    # contacts are email-only for comms — the UI flags them so staff know.
    has_account: bool = False
    # Trust badges (N26): ``badges`` is the effective list (manual override
    # wins), ``auto_badges`` is what the rules computed from invoice/quote
    # history, ``badge_overrides`` holds only the manual per-badge overrides.
    badges: list[str] = Field(default_factory=list)
    auto_badges: list[str] = Field(default_factory=list)
    badge_overrides: dict[str, bool] = Field(default_factory=dict)
    is_blocked: bool = False
    blocked_at: datetime | None = None
    blocked_reason: str | None = None

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
    unit: str = "ea"
    # Clients must round-trip this flag when editing line items, otherwise an
    # edit silently strips the AI lineage and refine/analytics misbehave.
    ai_generated: bool = False


class QuoteLineItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    description: str
    quantity: Decimal
    unit_price: Decimal
    unit: str = "ea"
    total: Decimal
    ai_generated: bool = False


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

    @field_validator(
        "quantity",
        "labour_hours",
        "labour_rate",
        "labour_total",
        "material_cost",
        "material_total",
        "plant_cost",
        "plant_total",
        "unit_price",
        "total",
        mode="before",
    )
    @classmethod
    def _coerce_decimal(cls, value: Any) -> Decimal:
        if value is None:
            return Decimal("0.00")
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return Decimal("0.00")


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

    @staticmethod
    def _clean_summary_lines(customer_summary_lines: Any) -> list[Any]:
        """Drop malformed customer summary lines persisted by older code."""
        if not isinstance(customer_summary_lines, list):
            return []
        return [
            item
            for item in customer_summary_lines
            if isinstance(item, dict)
            and item.get("description") not in (None, "")
            and item.get("total") is not None
        ]

    @staticmethod
    def _clean_nested_object(data: Any) -> dict[str, Any] | None:
        """Normalise a JSONB object field into a dict the nested model accepts.

        Persisted ``margin_indicator`` / ``retrieval_evidence`` payloads written
        by earlier code versions may be ``None``, an empty ``{}``, or a partial
        object where some keys hold ``null``. The nested Read models expose
        non-nullable fields with defaults, so an explicit ``null`` value fails
        validation even though a *missing* key would fall back to the default.
        Strip ``null`` values so the defaults apply, and collapse an empty
        result to ``None`` so the field is reported as absent.
        """
        if not isinstance(data, dict):
            return None
        cleaned = {key: val for key, val in data.items() if val is not None}
        return cleaned or None

    @model_validator(mode="before")
    @classmethod
    def _sanitize_jsonb_fields(cls, value: Any) -> Any:
        if isinstance(value, dict):
            value["customer_summary_lines"] = cls._clean_summary_lines(
                value.get("customer_summary_lines")
            )
            for key in ("margin_indicator", "retrieval_evidence"):
                value[key] = cls._clean_nested_object(value.get(key))
            return value

        value.customer_summary_lines = cls._clean_summary_lines(
            getattr(value, "customer_summary_lines", None)
        )
        for key in ("margin_indicator", "retrieval_evidence"):
            setattr(value, key, cls._clean_nested_object(getattr(value, key, None)))

        return value


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
    accepted_dates: list[str] = Field(default_factory=list)
    line_items: list[QuoteLineItemRead]
    bill_of_quantities: BillOfQuantitiesRead | None
    quote_request_id: UUID | None
    created_at: datetime
    updated_at: datetime
    customer: ContactRead = Field(validation_alias="contact", serialization_alias="customer")

    # AI generation metadata, derived from extra_data["rag"] and the line
    # items rather than stored as dedicated columns.
    ai_generated: bool = False
    ai_confidence: float | None = None
    ai_warnings: list[str] = Field(default_factory=list)
    ai_assumptions: list[str] = Field(default_factory=list)
    ai_notes: str | None = None
    retrieval_status: str | None = None
    # Uplift from the tenant's quote-rounding setting (0 when off). ``total``
    # already includes it; the UI shows a "rounded up" indicator when > 0.
    rounding_adjustment: Decimal = Decimal("0.00")

    @model_validator(mode="before")
    @classmethod
    def _extract_ai_metadata(cls, value: Any) -> Any:
        """Populate the AI fields from the ORM object's extra_data/line_items."""
        if isinstance(value, dict):
            extra_data = value.get("extra_data") or {}
            line_items = value.get("line_items") or []
        else:
            extra_data = getattr(value, "extra_data", None) or {}
            line_items = getattr(value, "line_items", None) or []

        rag = extra_data.get("rag") if isinstance(extra_data, dict) else None
        if not isinstance(rag, dict):
            rag = {}

        def _is_ai(item: Any) -> bool:
            if isinstance(item, dict):
                return bool(item.get("ai_generated"))
            return bool(getattr(item, "ai_generated", False))

        ai_fields = {
            "ai_generated": any(_is_ai(item) for item in line_items),
            "ai_confidence": rag.get("confidence"),
            "ai_warnings": rag.get("warnings") or [],
            "ai_assumptions": rag.get("assumptions") or [],
            "ai_notes": rag.get("notes"),
            "retrieval_status": rag.get("retrieval_status"),
        }
        if isinstance(value, dict):
            merged = {**ai_fields, **value}
            return merged
        for key, val in ai_fields.items():
            setattr(value, key, val)
        return value


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
    # When set, generate from an existing lead: the description, contact and
    # captured questionnaire are taken from the quote request.
    quote_request_id: UUID | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    description: str = Field(default="", max_length=5000)
    property_type: str | None = None
    site_survey: dict[str, Any] | None = None
    use_ocerp: bool = False

    @model_validator(mode="after")
    def _require_description_or_lead(self) -> "QuoteGenerateRequest":
        if self.quote_request_id is None and len(self.description.strip()) < 5:
            raise ValueError("description (min 5 chars) or quote_request_id is required")
        return self


class QuoteRefineRequest(BaseModel):
    """Electrician's free-text instructions for refining an AI-generated quote."""

    instructions: str = Field(..., min_length=1, max_length=2000)


class QuoteGenerateAsyncResponse(BaseModel):
    """202 ack for ``POST /quotes/generate-async``.

    The quote is generated by a background worker; the client polls
    ``GET /notifications`` (or the quote list) to learn the outcome.
    """

    status: str = "generating"
    quote_request_id: UUID | None = None


class QuoteTrainingEventRead(BaseModel):
    """One captured quote-edit event for the AI fine-tuning dataset.

    ``payload`` carries ``before``/``after`` line-item snapshots (and
    ``instructions`` for refine events) — the raw material for later export
    into an AI training set.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    event_type: str  # quote_lines_edited | quote_refined
    entity_id: UUID  # the quote id
    actor_id: UUID | None
    payload: dict[str, Any]
    created_at: datetime


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    recipient_type: str  # staff | customer
    recipient_id: UUID | None
    type: str
    title: str
    body: str
    link: str | None
    read_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UnreadCountRead(BaseModel):
    unread_count: int


class PushTokenCreate(BaseModel):
    token: str = Field(..., min_length=1, max_length=255)
    platform: str = Field(..., min_length=1, max_length=50)


class PushTokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    owner_type: str
    owner_id: UUID
    token: str
    platform: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------


def _strip_tz(value: datetime | None) -> datetime | None:
    """Store naive UTC — job schedule columns are `DateTime` (no timezone)."""
    if value is not None and value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


class JobCreate(BaseModel):
    contact_id: UUID
    quote_id: UUID | None = None
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    notes: str | None = None
    assigned_user_id: UUID | None = None

    _normalize_schedule = field_validator("scheduled_start", "scheduled_end", mode="after")(
        _strip_tz
    )


class JobConvertRequest(BaseModel):
    """Optional scheduling for quote → job conversion."""

    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    notes: str | None = None
    assigned_user_id: UUID | None = None

    _normalize_schedule = field_validator("scheduled_start", "scheduled_end", mode="after")(
        _strip_tz
    )


class JobUpdate(BaseModel):
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    notes: str | None = None
    assigned_user_id: UUID | None = None

    _normalize_schedule = field_validator("scheduled_start", "scheduled_end", mode="after")(
        _strip_tz
    )


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
    assigned_user_id: UUID | None
    # Display name of the assignee, derived from the ORM `assignee` relationship.
    assigned_to: str | None = None
    # Photo/file URLs carried over from the source quote's quote request.
    photos: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    customer: ContactRead = Field(validation_alias="contact", serialization_alias="customer")

    @model_validator(mode="before")
    @classmethod
    def _derive_assignee_and_photos(cls, value: Any) -> Any:
        """Populate assigned_to/photos from the ORM relationships when present."""
        if isinstance(value, dict):
            return value
        try:
            assignee = getattr(value, "assignee", None)
            value.assigned_to = assignee.full_name if assignee is not None else None
        except Exception:  # unloaded relationship outside a session
            value.assigned_to = None
        try:
            media = getattr(value, "media", None) or []
            value.photos = [asset.file_url for asset in media]
        except Exception:  # unloaded relationship outside a session
            value.photos = []
        return value


# ---------------------------------------------------------------------------
# Appointment
# ---------------------------------------------------------------------------


class AppointmentCreate(BaseModel):
    contact_id: UUID | None = None
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
    # Full replacement when provided (same semantics as QuoteUpdate).
    line_items: list[InvoiceLineItemCreate] | None = None


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
    # Rounding uplift inherited from the source quote (0 for scratch invoices).
    rounding_adjustment: Decimal = Decimal("0.00")
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
# Subscription / Billing
# ---------------------------------------------------------------------------


class BillingCheckoutCreate(BaseModel):
    plan_key: str  # sole_trader | pro | team (legacy: starter | pro | business)
    success_url: str | None = None
    interval: Literal["month", "year"] = "month"
    # Seat count for per-seat plans (team, min 3). Ignored for fixed-seat
    # plans; defaults to the plan's minimum seats.
    seats: int | None = Field(default=None, ge=1, le=100)


class BillingCheckoutRead(BaseModel):
    transaction_id: str
    checkout_url: str


class SubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_key: str
    status: str
    paddle_subscription_id: str | None
    paddle_customer_id: str | None
    trial_ends_at: datetime | None
    current_period_start: datetime | None
    current_period_end: datetime | None
    scheduled_change_action: str | None
    scheduled_change_at: datetime | None
    canceled_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Communication
# ---------------------------------------------------------------------------


class CommunicationCreate(BaseModel):
    contact_id: UUID | None = None
    quote_request_id: UUID | None = None
    channel: str
    direction: str = "outbound"
    sender_role: str = "business"  # customer | business | ai
    subject: str | None = None
    body: str | None = None
    status: str | None = "sent"
    ai_metadata: dict[str, Any] | None = None


class CommunicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    contact_id: UUID | None
    quote_request_id: UUID | None
    channel: str
    direction: str
    sender_role: str
    subject: str | None
    body: str | None
    status: str
    ai_metadata: dict[str, Any] | None = None
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
    # Quotes drafted by the AI pipeline (ai_draft snapshot or AI line items).
    ai_generated_quotes: int = 0
    # Estimated hours saved by AI drafting (ai_generated_quotes x per-quote
    # manual drafting time; see AI_DRAFT_MANUAL_MINUTES in routers/analytics.py).
    ai_time_saved_hours: float = 0.0


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
    # Mean of extra_data["rag"]["generation_seconds"] across AI quotes; None
    # when no AI quote has recorded a generation time yet.
    average_generation_time: float | None = None
    # Fraction of AI quotes the electrician edited after generation; None when
    # no AI quote has feedback recorded yet.
    edit_rate: float | None = None
    # Mean of extra_data["ai_feedback"]["price_drift_pct"]; None when no
    # feedback with a price drift exists yet.
    avg_price_drift_pct: float | None = None
    # Sum of extra_data["rag"]["llm_usage"]["est_cost_usd"] across the tenant's
    # AI quotes; None when no quote has a priced usage record yet.
    total_ai_cost_usd: float | None = None
    # Number of AI quotes that recorded LLM token usage.
    ai_quotes_with_usage: int = 0
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


class PasswordResetRequest(BaseModel):
    """Kick off a password-reset flow. Email must match an active user."""

    email: str = Field(..., min_length=3, max_length=255)


class PasswordResetConfirm(BaseModel):
    """Complete a password-reset flow with the token issued by /request."""

    token: str = Field(..., min_length=32, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


class TokenResponse(BaseModel):
    """Bearer token response for native (iOS) clients.

    Web clients use the cookie-based ``/auth/login`` endpoint; native clients
    that cannot rely on cookies use ``/auth/token`` and send the token as an
    ``Authorization: Bearer`` header on subsequent requests.
    """

    access_token: str
    token_type: str = "bearer"
    tenant_slug: str
    user: UserRead


class TenantBootstrapRead(TenantRead):
    """Tenant plus the first admin user created alongside it (if requested)."""

    admin_user: UserRead | None = None


# ---------------------------------------------------------------------------
# Mobile pivot schemas
# ---------------------------------------------------------------------------


class BusinessPublicConfig(BaseModel):
    """White-label config returned to the iOS app before authentication."""

    slug: str
    code: str | None = None
    name: str
    logo_url: str | None = Field(default=None, serialization_alias="logoUrl")
    primary_color: str = Field(default="#2563EB", serialization_alias="primaryColor")
    secondary_color: str = Field(default="#1D4ED8", serialization_alias="secondaryColor")
    business_services: list[str] = Field(
        default_factory=list, serialization_alias="businessServices"
    )
    contact_phone: str | None = Field(default=None, serialization_alias="contactPhone")
    address: str | None = None


class PublicContactInput(BaseModel):
    """Homeowner contact details captured by the public quote-request form."""

    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=2000)
    postcode: str | None = Field(default=None, max_length=20)


class PublicQuoteRequestCreate(BaseModel):
    """A quote request submitted by a homeowner via the white-label app.

    No authentication is required: the target business is identified by slug in
    the URL. Everything else is the captured questionnaire data.
    """

    contact: PublicContactInput
    category: str | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, max_length=255)
    raw_text: str | None = None
    structured_data: dict[str, Any] = Field(default_factory=dict)
    urgency: str = Field(default="normal", max_length=50)
    media_urls: list[str] = Field(default_factory=list)
    preferred_dates: list[dict[str, Any]] = Field(default_factory=list)
    safety_review_required: bool = False
    marketing_consent: bool = False


class PublicQuoteRequestAck(BaseModel):
    """Minimal acknowledgement returned to the (unauthenticated) homeowner."""

    id: UUID
    status: str
    reference: str


class CustomerCreate(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    marketing_consent: bool = False
    preferred_contact_method: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=2000)
    postcode: str | None = Field(default=None, max_length=20)
    parking_notes: str | None = None
    access_notes: str | None = None


class CustomerUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=2000)
    postcode: str | None = Field(default=None, max_length=20)
    preferred_contact_method: str | None = Field(default=None, max_length=50)
    parking_notes: str | None = None
    access_notes: str | None = None
    marketing_consent: bool | None = None


class CustomerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    contact_id: UUID | None
    email: str
    full_name: str
    phone: str | None
    address: str | None
    postcode: str | None
    property_profile: dict[str, Any] = Field(default_factory=dict)
    is_active: bool
    marketing_consent: bool
    preferred_contact_method: str | None
    parking_notes: str | None = None
    access_notes: str | None = None
    created_at: datetime
    updated_at: datetime


class CustomerRegister(BaseModel):
    """Homeowner self-registration against a specific business (by slug)."""

    slug: str = Field(..., min_length=2, max_length=63)
    full_name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)
    marketing_consent: bool = False
    address: str | None = Field(default=None, max_length=2000)
    postcode: str | None = Field(default=None, max_length=20)
    preferred_contact_method: str | None = Field(default=None, max_length=50)
    quote_request_id: UUID | None = Field(
        default=None,
        validation_alias=AliasChoices("quote_request_id", "quoteRequestId"),
        serialization_alias="quoteRequestId",
    )


class CustomerQuoteAccept(BaseModel):
    """Acceptance payload: the customer reconfirms preferred visit dates."""

    preferred_dates: list[str] | None = None


class CustomerLogin(BaseModel):
    # Optional: when omitted, the account is located by email across tenants
    # (mobile is tenant-agnostic at login; tenants were a web-subdomain hangover).
    slug: str | None = Field(default=None, min_length=2, max_length=63)
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class CustomerTenantAssociation(BaseModel):
    """One business (tenant) a customer account email is associated with.

    Login resolves a single current tenant today, but the response always
    carries the full association list so multi-tenant customers (a homeowner
    using several electricians on the platform) can be supported without an
    API shape change.
    """

    tenant_id: UUID
    slug: str
    name: str
    # True for the tenant the issued bearer token is scoped to.
    is_current: bool


class CustomerTokenResponse(BaseModel):
    access_token: str = Field(serialization_alias="accessToken")
    token_type: str = Field(default="bearer", serialization_alias="tokenType")
    customer: CustomerRead
    # Every active tenant association for this email; empty only in hand-built
    # responses. Post-auth tenant resolution, so this is never disclosed
    # before credentials check out.
    tenants: list[CustomerTenantAssociation] = Field(default_factory=list)


class PropertyCreate(BaseModel):
    customer_id: UUID
    address: str = Field(..., min_length=1, max_length=2000)
    postcode: str = Field(..., min_length=1, max_length=20)
    lat: Decimal | None = None
    lng: Decimal | None = None
    property_type: str | None = Field(default=None, max_length=50)
    bedrooms: int | None = None
    tenure: str | None = Field(default=None, max_length=50)
    epc_rating: str | None = Field(default=None, max_length=10)
    notes: str | None = None


class PropertyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    customer_id: UUID
    address: str
    postcode: str
    lat: Decimal | None
    lng: Decimal | None
    property_type: str | None
    bedrooms: int | None
    tenure: str | None
    epc_rating: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PricingProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    profile_type: str = Field(default="time_materials")
    is_default: bool = False
    vat_rate: Decimal = Decimal("0.20")
    markup_percentage: Decimal = Decimal("0.00")
    call_out_fee: Decimal = Decimal("0.0000")
    minimum_charge: Decimal = Decimal("0.0000")


class PricingProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    profile_type: str
    is_default: bool
    vat_rate: Decimal
    markup_percentage: Decimal
    call_out_fee: Decimal
    minimum_charge: Decimal
    created_at: datetime
    updated_at: datetime


class PricingRateCreate(BaseModel):
    pricing_profile_id: UUID
    category: str = Field(..., max_length=50)
    label: str = Field(..., min_length=1, max_length=255)
    unit: str | None = Field(default=None, max_length=50)
    rate: Decimal = Decimal("0.0000")
    cost: Decimal | None = None
    is_active: bool = True


class PricingRateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    pricing_profile_id: UUID
    category: str
    label: str
    unit: str | None
    rate: Decimal
    cost: Decimal | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class QuoteRequestCreate(BaseModel):
    contact_id: UUID | None = None
    customer_id: UUID | None = None
    property_id: UUID | None = None
    source: str = Field(default="qr")
    raw_text: str | None = None
    structured_data: dict[str, Any] = Field(default_factory=dict)
    urgency: str = Field(default="normal")
    media_urls: list[str] = Field(default_factory=list)
    preferred_dates: list[dict[str, Any]] = Field(default_factory=list)
    safety_review_required: bool = False


class QuoteRequestUpdate(BaseModel):
    """Fields a tradesperson may edit while reviewing a lead."""

    raw_text: str | None = Field(default=None, max_length=5000)
    structured_data: dict[str, Any] | None = None
    urgency: str | None = Field(default=None, max_length=50)
    status: str | None = Field(default=None, max_length=50)
    quote_id: UUID | None = None
    safety_review_required: bool | None = None
    ai_confidence: Decimal | None = None

    @field_validator("ai_confidence")
    @classmethod
    def _clamp_ai_confidence(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return value
        if value < Decimal("0") or value > Decimal("1"):
            raise ValueError("ai_confidence must be between 0 and 1")
        return value.quantize(Decimal("0.0001"))


class QuoteRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    contact_id: UUID | None
    customer_id: UUID | None
    property_id: UUID | None
    source: str
    raw_text: str | None
    structured_data: dict[str, Any]
    ai_extracted_summary: str | None
    urgency: str
    status: str
    quote_id: UUID | None
    media_urls: list[str]
    triage_flags: list[str]
    preferred_dates: list[dict[str, Any]]
    safety_review_required: bool
    requires_callback: bool
    ai_confidence: Decimal | None
    reviewed_by: UUID | None
    converted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    customer: ContactRead | None = Field(
        default=None, validation_alias="contact", serialization_alias="customer"
    )
    quote: QuoteRead | None = None


class QuoteRequestMediaCreate(BaseModel):
    file_url: str
    file_key: str | None = None
    mime_type: str | None = Field(default=None, max_length=100)
    size_bytes: int | None = None
    source: str = Field(default="in_app")


class AiInterpretLineItem(BaseModel):
    kind: str = Field(..., max_length=50)
    description: str
    qty: Decimal = Decimal("1")
    unit: str
    unit_price: Decimal


class AiInterpretQuoteRequest(BaseModel):
    quote_request_id: UUID


class AiInterpretQuoteResponse(BaseModel):
    confidence: float = Field(..., ge=0.0, le=1.0)
    route: str
    assumptions: list[str] = Field(default_factory=list)
    line_items: list[AiInterpretLineItem] = Field(default_factory=list)
    callout_fee: Decimal = Decimal("0.00")
    minimum_charge: Decimal = Decimal("0.00")
    emergency_multiplier: Decimal = Decimal("1.00")
    compliance_notes: list[str] = Field(default_factory=list)


class OnboardingStepUpdate(BaseModel):
    step: str
    value: dict[str, Any] = Field(default_factory=dict)


class OnboardingStatusRead(BaseModel):
    status: str
    onboarding_progress: dict[str, Any]
    launch_enabled: bool = False
    pending_steps: list[str] = Field(default_factory=list)
