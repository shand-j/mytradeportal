"""Quote request capture, triage and AI interpretation endpoints."""

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import Actions, write_audit_log
from app.database import get_db
from app.dependencies import CurrentUserDep, TenantDep
from app.limiter import limiter, tenant_key
from app.models import BillOfQuantities, Customer, MediaAsset, Property, Quote, QuoteRequest
from app.rls import set_tenant_in_session
from app.schemas import (
    AiInterpretLineItem,
    AiInterpretQuoteResponse,
    QuoteRequestCreate,
    QuoteRequestMediaCreate,
    QuoteRequestRead,
    QuoteRequestUpdate,
)

router = APIRouter(prefix="/quote-requests", tags=["Quote Requests"])
DbDep = Annotated[AsyncSession, Depends(get_db)]


async def _set_tenant(db: AsyncSession, tenant_id: UUID) -> None:
    await set_tenant_in_session(db, tenant_id)


async def _reads_with_account_flags(
    db: AsyncSession, tenant_id: UUID, quote_requests: list[QuoteRequest]
) -> list[QuoteRequestRead]:
    """Serialise quote requests and flag contacts with no customer account.

    Quotes sent to account-less contacts persist (contact + quote rows stand
    on their own), but the electrician must see that comms with that customer
    are email-only: ``customer.has_account`` is False until the homeowner
    registers, True once an active customer account points at the contact.
    """
    reads = [QuoteRequestRead.model_validate(qr) for qr in quote_requests]
    contact_ids = {read.customer.id for read in reads if read.customer is not None}
    if not contact_ids:
        return reads
    result = await db.execute(
        select(Customer.contact_id).where(
            Customer.tenant_id == tenant_id,
            Customer.contact_id.in_(contact_ids),
            Customer.is_active.is_(True),
        )
    )
    with_account = set(result.scalars().all())
    return [
        read.model_copy(update={"customer": read.customer.model_copy(update={"has_account": True})})
        if read.customer is not None and read.customer.id in with_account
        else read
        for read in reads
    ]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=QuoteRequestRead)
async def create_quote_request(
    data: QuoteRequestCreate,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> QuoteRequestRead:
    """Create a quote request from any source (QR, web form, share extension)."""
    await _set_tenant(db, tenant.id)

    if data.customer_id is not None:
        customer = await db.get(Customer, data.customer_id)
        if customer is None or customer.tenant_id != tenant.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid customer")

    if data.property_id is not None:
        property_ = await db.get(Property, data.property_id)
        if property_ is None or property_.tenant_id != tenant.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid property")

    quote_request = QuoteRequest(
        tenant_id=tenant.id,
        contact_id=data.contact_id,
        customer_id=data.customer_id,
        property_id=data.property_id,
        source=data.source,
        raw_text=data.raw_text,
        structured_data=data.structured_data,
        urgency=data.urgency,
        media_urls=data.media_urls,
        preferred_dates=data.preferred_dates,
        safety_review_required=data.safety_review_required,
    )
    db.add(quote_request)
    await db.flush()
    await db.refresh(quote_request, ["contact"])
    return (await _reads_with_account_flags(db, tenant.id, [quote_request]))[0]


@router.get("", response_model=list[QuoteRequestRead])
async def list_quote_requests(
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> list[QuoteRequestRead]:
    """List quote requests for the current tenant (Leads tab)."""
    await _set_tenant(db, tenant.id)
    result = await db.execute(
        select(QuoteRequest)
        .options(
            selectinload(QuoteRequest.contact),
            selectinload(QuoteRequest.quote).selectinload(Quote.line_items),
            selectinload(QuoteRequest.quote).selectinload(Quote.contact),
            selectinload(QuoteRequest.quote)
            .selectinload(Quote.bill_of_quantities)
            .selectinload(BillOfQuantities.line_items),
        )
        .where(QuoteRequest.tenant_id == tenant.id)
        .order_by(QuoteRequest.created_at.desc())
    )
    return await _reads_with_account_flags(db, tenant.id, list(result.scalars().all()))


@router.get("/{quote_request_id}", response_model=QuoteRequestRead)
async def get_quote_request(
    quote_request_id: UUID,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> QuoteRequestRead:
    """Get a single quote request."""
    await _set_tenant(db, tenant.id)
    quote_request = await db.scalar(
        select(QuoteRequest)
        .options(
            selectinload(QuoteRequest.contact),
            selectinload(QuoteRequest.quote).selectinload(Quote.line_items),
            selectinload(QuoteRequest.quote).selectinload(Quote.contact),
            selectinload(QuoteRequest.quote)
            .selectinload(Quote.bill_of_quantities)
            .selectinload(BillOfQuantities.line_items),
        )
        .where(QuoteRequest.id == quote_request_id)
    )
    if quote_request is None or quote_request.tenant_id != tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote request not found")
    return (await _reads_with_account_flags(db, tenant.id, [quote_request]))[0]


@router.patch("/{quote_request_id}", response_model=QuoteRequestRead)
async def update_quote_request(
    quote_request_id: UUID,
    data: QuoteRequestUpdate,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> QuoteRequestRead:
    """Update a quote request (lead) with tradesperson review notes/edits.

    The caller can merge into ``structured_data`` by supplying the keys they
    want to overwrite; existing keys not present in the request are preserved.
    """
    await _set_tenant(db, tenant.id)
    quote_request = await db.scalar(
        select(QuoteRequest)
        .options(selectinload(QuoteRequest.contact))
        .where(QuoteRequest.id == quote_request_id, QuoteRequest.tenant_id == tenant.id)
    )
    if quote_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote request not found")

    update_data = data.model_dump(exclude_unset=True)
    changed_fields: list[str] = []

    if "structured_data" in update_data:
        # Merge rather than replace so electrician notes supplement customer data.
        merged = dict(quote_request.structured_data or {})
        merged.update(update_data.pop("structured_data"))
        quote_request.structured_data = merged
        changed_fields.append("structured_data")

    for key, value in update_data.items():
        setattr(quote_request, key, value)
        changed_fields.append(key)

    if "reviewed_by" not in changed_fields and current_user is not None:
        quote_request.reviewed_by = current_user.id

    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.QUOTE_REQUEST_UPDATED,
        entity_type="quote_request",
        entity_id=quote_request.id,
        payload={"changed_fields": sorted(changed_fields)},
    )
    await db.commit()
    # Re-fetch with eager loads so the response model can serialise the linked
    # quote (and its line items / bill of quantities) without triggering a lazy load.
    quote_request = await db.scalar(
        select(QuoteRequest)
        .options(
            selectinload(QuoteRequest.contact),
            selectinload(QuoteRequest.quote).selectinload(Quote.line_items),
            selectinload(QuoteRequest.quote).selectinload(Quote.contact),
            selectinload(QuoteRequest.quote)
            .selectinload(Quote.bill_of_quantities)
            .selectinload(BillOfQuantities.line_items),
        )
        .where(QuoteRequest.id == quote_request_id, QuoteRequest.tenant_id == tenant.id)
    )
    if quote_request is None:  # pragma: no cover - deleted between update and re-fetch
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote request not found")
    return (await _reads_with_account_flags(db, tenant.id, [quote_request]))[0]


@router.post("/{quote_request_id}/media", status_code=status.HTTP_201_CREATED)
async def attach_media(
    quote_request_id: UUID,
    data: QuoteRequestMediaCreate,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> dict[str, str]:
    """Attach a media asset to a quote request."""
    await _set_tenant(db, tenant.id)
    quote_request = await db.get(QuoteRequest, quote_request_id)
    if quote_request is None or quote_request.tenant_id != tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote request not found")

    asset = MediaAsset(
        tenant_id=tenant.id,
        quote_request_id=quote_request_id,
        file_url=data.file_url,
        file_key=data.file_key,
        mime_type=data.mime_type,
        size_bytes=data.size_bytes,
        source=data.source,
    )
    db.add(asset)
    await db.flush()
    return {"id": str(asset.id), "file_url": data.file_url}


@router.post("/from-share", status_code=status.HTTP_201_CREATED, response_model=QuoteRequestRead)
async def create_quote_request_from_share(
    request: Request,
    data: QuoteRequestCreate,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> QuoteRequestRead:
    """Create a draft quote request from a forwarded message (iOS Share Extension)."""
    data.source = "sms_forward"
    return await create_quote_request(data, tenant, current_user, db)


@router.post(
    "/{quote_request_id}/interpret",
    status_code=status.HTTP_200_OK,
    response_model=AiInterpretQuoteResponse,
)
@limiter.limit("20/minute", key_func=tenant_key)
async def interpret_quote_request(
    request: Request,
    quote_request_id: UUID,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> AiInterpretQuoteResponse:
    """Run the AI interpreter on a quote request and return draft line items.

    This MVP stub returns a deterministic example. A production implementation
    calls OpenAI with a structured-output schema using the business's
    pricing profile and the quote request data.
    """
    await _set_tenant(db, tenant.id)
    quote_request = await db.get(QuoteRequest, quote_request_id)
    if quote_request is None or quote_request.tenant_id != tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote request not found")

    # MVP stub: deterministic response for demo and testing.
    if quote_request.safety_review_required or quote_request.urgency == "emergency_today":
        return AiInterpretQuoteResponse(
            confidence=0.0,
            route="site_visit_needed",
            assumptions=["Emergency / safety flag detected"],
            compliance_notes=["Part P self-certification included"],
        )

    return AiInterpretQuoteResponse(
        confidence=0.78,
        route="draft_with_assumptions",
        assumptions=[
            "Assumed stud/plasterboard walls",
            "Assumed consumer unit is accessible",
        ],
        line_items=[
            AiInterpretLineItem(
                kind="labour",
                description="Consumer unit replacement - 6-8 circuits",
                qty=Decimal("1"),
                unit="job",
                unit_price=Decimal("520.00"),
            ),
            AiInterpretLineItem(
                kind="materials",
                description="Metal 12-way RCBO board + extras",
                qty=Decimal("1"),
                unit="job",
                unit_price=Decimal("180.00"),
            ),
            AiInterpretLineItem(
                kind="callout",
                description="Call-out fee",
                qty=Decimal("1"),
                unit="item",
                unit_price=Decimal("45.00"),
            ),
        ],
        callout_fee=Decimal("45.00"),
        minimum_charge=Decimal("95.00"),
        emergency_multiplier=Decimal("1.0"),
        compliance_notes=["Part P self-certification included"],
    )
