"""Shared request/response schemas for the OpenConstructionERP microservice."""

from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BoQLineItem(BaseModel):
    """A single line item in a generated Bill of Quantities.

    Each line captures a Time & Materials breakdown so the BoQ can be used as
    an internal pricing document that supports the customer-facing quote.
    """

    model_config = ConfigDict(from_attributes=True)

    code: str
    description: str
    unit: str
    quantity: Decimal

    # Time & Materials breakdown (per unit)
    labour_hours: Decimal = Decimal("0.00")
    labour_rate: Decimal = Decimal("0.00")
    labour_total: Decimal = Decimal("0.00")
    material_cost: Decimal = Decimal("0.00")
    material_total: Decimal = Decimal("0.00")
    plant_cost: Decimal = Decimal("0.00")
    plant_total: Decimal = Decimal("0.00")

    unit_price: Decimal
    total: Decimal

    cost_item_id: UUID | None = None
    category: str | None = None
    supplier: str | None = None
    brand: str | None = None
    sku: str | None = None
    product_url: str | None = None
    retail_price_incl_vat: Decimal | None = None
    notes: str | None = None


class BoQGenerateRequest(BaseModel):
    """Request body for BoQ generation."""

    description: str = Field(..., min_length=5)
    trade: str = Field(default="electrical")
    region: str = Field(default="UK")
    property_type: str | None = None
    standard: str | None = None
    tenant_settings: dict[str, Any] = Field(default_factory=dict)
    site_survey: dict[str, Any] | None = Field(
        default=None,
        description="Optional structured site-survey data used to drive the missing-data gate.",
    )


class QuoteAnalysis(BaseModel):
    """Structured analysis of a job description for evaluation purposes."""

    model_config = ConfigDict(from_attributes=True)

    job_summary: str = ""
    room_count: int | None = None
    spec_level: str | None = None
    regulatory_flags: list[str] = Field(default_factory=list)
    estimated_material_cost_ex_vat: dict[str, Decimal | None] | None = None
    estimated_labour_hours: dict[str, Decimal | None] | None = None
    total_quote_range_ex_vat: dict[str, Decimal | None] | None = None


class RegulatoryCitation(BaseModel):
    """A citation to an authoritative regulatory/knowledge-base chunk.

    Citations are emitted DETERMINISTICALLY from the retrieved knowledge
    chunks, not from the LLM, so the BoQ always grounds itself in a real
    document we control rather than something the model may have invented.
    """

    model_config = ConfigDict(from_attributes=True)

    chunk_id: str
    source: str
    section_path: list[str] = Field(default_factory=list)
    rule_tier: str = "reference"
    job_type: str | None = None
    snippet: str = ""
    relevance_score: float = 0.0


class CustomerSummaryLine(BaseModel):
    """Customer-facing summary line without internal cost breakdown."""

    model_config = ConfigDict(from_attributes=True)

    description: str
    total: Decimal


class MarginIndicator(BaseModel):
    """Internal margin summary for back-office review."""

    model_config = ConfigDict(from_attributes=True)

    material_subtotal: Decimal = Decimal("0.00")
    labour_subtotal: Decimal = Decimal("0.00")
    subtotal: Decimal = Decimal("0.00")
    target_markup_percent: Decimal = Decimal("0.00")
    estimated_margin_percent: Decimal = Decimal("0.00")
    estimated_margin_amount: Decimal = Decimal("0.00")


class BoQGenerateResponse(BaseModel):
    """Response from the BoQ generation endpoint."""

    model_config = ConfigDict(from_attributes=True)

    line_items: list[BoQLineItem] = Field(default_factory=list)
    subtotal: Decimal = Decimal("0.00")
    vat_rate: Decimal = Decimal("0.20")
    vat_amount: Decimal = Decimal("0.00")
    total: Decimal = Decimal("0.00")
    confidence: Decimal = Decimal("0.0")
    warnings: list[str] = Field(default_factory=list)
    notes: str = ""
    standard: str | None = None
    analysis: QuoteAnalysis | None = None
    # Citations to the regulatory knowledge base chunks used to ground the
    # quote. Always populated when the knowledge store is reachable.
    regulatory_citations: list[RegulatoryCitation] = Field(default_factory=list)
    # Human-readable warnings for mandatory items that the rule-based
    # compliance checker expected but did not find in the BoQ.
    compliance_warnings: list[str] = Field(default_factory=list)
    # Customer-facing collapsed presentation. These are safe to show in quote
    # PDFs where internal material/labour breakdown should remain hidden.
    customer_summary_lines: list[CustomerSummaryLine] = Field(default_factory=list)
    # Internal-only financial hint for the back-office bill-of-quantities view.
    margin_indicator: MarginIndicator | None = None
    # When the missing-data gate blocks estimation, this lists the questions
    # the user must answer before a BoQ can be produced.
    clarification_questions: list[str] = Field(default_factory=list)


class PriceLookupRequest(BaseModel):
    """Request body for regional price lookup by item code."""

    code: str
    region: str = Field(default="UK")


class PriceLookupResponse(BaseModel):
    """Response from the price lookup endpoint."""

    model_config = ConfigDict(from_attributes=True)

    code: str
    description: str | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    currency: str = "GBP"
    region: str
    found: bool


class StandardInfo(BaseModel):
    """A supported regional estimating standard."""

    code: str
    name: str
    region: str


class StandardsListResponse(BaseModel):
    """Response from the standards list endpoint."""

    standards: list[StandardInfo] = Field(default_factory=list)
