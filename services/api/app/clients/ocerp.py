"""HTTP client for the OpenConstructionERP microservice."""

import logging
from typing import Any

import httpx
from mtp_shared import (
    BoQGenerateRequest,
    BoQGenerateResponse,
    PriceLookupRequest,
    PriceLookupResponse,
    StandardsListResponse,
)

from app.calculations import calculate_quote_totals
from app.config import settings
from app.models import BillOfQuantities, BoQLineItem, Quote, QuoteLineItem

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = httpx.Timeout(350.0, connect=10.0)


class OCERPClient:
    """Async client for the OpenConstructionERP internal API."""

    def __init__(self, base_url: str | None = None, timeout: httpx.Timeout | None = None) -> None:
        self.base_url = (base_url or settings.ocerp_url).rstrip("/")
        self.timeout = timeout or DEFAULT_TIMEOUT
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "OCERPClient":
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _client_or_raise(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("OCERPClient must be used as an async context manager")
        return self._client

    async def generate_boq(self, request: BoQGenerateRequest) -> BoQGenerateResponse:
        """Generate a Bill of Quantities from a job description."""
        response = await self._client_or_raise().post(
            f"{self.base_url}/ocerp/v1/boq/generate",
            json=request.model_dump(mode="json"),
        )
        response.raise_for_status()
        return BoQGenerateResponse.model_validate(response.json())

    async def lookup_price(self, request: PriceLookupRequest) -> PriceLookupResponse:
        """Look up a cost item price by code and region."""
        response = await self._client_or_raise().post(
            f"{self.base_url}/ocerp/v1/price/lookup",
            json=request.model_dump(mode="json"),
        )
        response.raise_for_status()
        return PriceLookupResponse.model_validate(response.json())

    async def list_standards(self, region: str | None = None) -> StandardsListResponse:
        """Return the list of supported estimating standards."""
        params = {"region": region} if region else {}
        response = await self._client_or_raise().get(
            f"{self.base_url}/ocerp/v1/standards/list",
            params=params,
        )
        response.raise_for_status()
        return StandardsListResponse.model_validate(response.json())


async def get_ocerp_client() -> "OCERPClient":
    """Return an async context-managed OCERP client.

    Usage:
        async with get_ocerp_client() as client:
            result = await client.generate_boq(request)
    """
    return OCERPClient()


def build_quote_from_ocerp_response(
    quote: Quote,
    response: BoQGenerateResponse,
) -> BillOfQuantities:
    """Create a Bill of Quantities from the OCERP response and link it to the quote.

    The BoQ is an internal Time & Materials document. The customer-facing quote
    line items are derived from the BoQ totals so the quote still presents a
    clean summary to the customer.
    """
    boq = BillOfQuantities(
        tenant_id=quote.tenant_id,
        quote_id=quote.id,
        status="draft",
        notes=response.notes,
        subtotal=response.subtotal,
        vat_rate=response.vat_rate,
        vat_amount=response.vat_amount,
        total=response.total,
        confidence=response.confidence,
        warnings=response.warnings,
        regulatory_citations=[c.model_dump(mode="json") for c in response.regulatory_citations],
        compliance_warnings=list(response.compliance_warnings),
        customer_summary_lines=[
            line.model_dump(mode="json") for line in response.customer_summary_lines
        ],
        margin_indicator=response.margin_indicator.model_dump(mode="json")
        if response.margin_indicator is not None
        else {},
        standard=response.standard,
    )

    for item in response.line_items:
        boq.line_items.append(
            BoQLineItem(
                tenant_id=quote.tenant_id,
                code=item.code,
                description=item.description,
                category=item.category,
                unit=item.unit,
                quantity=item.quantity,
                labour_hours=item.labour_hours,
                labour_rate=item.labour_rate,
                labour_total=item.labour_total,
                material_cost=item.material_cost,
                material_total=item.material_total,
                plant_cost=item.plant_cost,
                plant_total=item.plant_total,
                unit_price=item.unit_price,
                total=item.total,
                supplier=item.supplier,
                brand=item.brand,
                sku=item.sku,
                product_url=item.product_url,
                retail_price_incl_vat=item.retail_price_incl_vat,
                notes=item.notes,
            )
        )

    quote.bill_of_quantities = boq

    # Derive customer-facing quote line items from the BoQ. Each BoQ line becomes
    # a quote line so the customer quote reflects the itemised breakdown, but the
    # detailed T&M split lives only in the BoQ.
    quote.line_items = []
    if response.customer_summary_lines:
        for summary in response.customer_summary_lines:
            quote.line_items.append(
                QuoteLineItem(
                    tenant_id=quote.tenant_id,
                    description=summary.description,
                    quantity=1,
                    unit_price=summary.total,
                    total=summary.total,
                )
            )
    else:
        for boq_item in response.line_items:
            quote.line_items.append(
                QuoteLineItem(
                    tenant_id=quote.tenant_id,
                    description=boq_item.description,
                    quantity=boq_item.quantity,
                    unit_price=boq_item.unit_price,
                    total=boq_item.total,
                )
            )

    calculate_quote_totals(quote)
    return boq
