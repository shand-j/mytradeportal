"""Public business lookup and quote-request submission for the iOS app.

These endpoints are called by the white-label app before the customer or
tradesperson has authenticated, so they identify the target business by slug
and do not require an auth token.
"""

from typing import Annotated
from uuid import UUID, uuid4

import structlog
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import _extract_token
from app.guest_auth import issue_guest_token
from app.intake_triage import run_intake_check
from app.limiter import limiter
from app.models import BusinessService, Communication, Contact, Customer, QuoteRequest, Tenant
from app.quote_automation import auto_draft_quote_for_request
from app.rls import bypass_rls_for_transaction, set_tenant_in_session
from app.routers.contacts import BLOCKED_CUSTOMER_DETAIL, contact_is_blocked
from app.schemas import (
    BusinessPublicConfig,
    PublicIntakeCheck,
    PublicQuoteRequestAck,
    PublicQuoteRequestCreate,
)
from app.security import decode_access_token
from app.utils.contact_preference import normalise_preferred_contact

router = APIRouter(prefix="/businesses", tags=["Businesses"])
DbDep = Annotated[AsyncSession, Depends(get_db)]
logger = structlog.get_logger("api.businesses")


async def _resolve_active_tenant(db: AsyncSession, slug: str) -> Tenant:
    """Resolve an active tenant by slug. ``tenants`` is a global (non-RLS) table."""
    tenant = await db.scalar(select(Tenant).where(Tenant.slug == slug, Tenant.is_active.is_(True)))
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found",
        )
    return tenant


async def _resolve_active_tenant_by_code(db: AsyncSession, code: str) -> Tenant:
    """Resolve an active tenant by its 6-digit customer lookup code."""
    tenant = await db.scalar(select(Tenant).where(Tenant.code == code, Tenant.is_active.is_(True)))
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found",
        )
    return tenant


@router.get("/by-code/{code}/public-config", response_model=BusinessPublicConfig)
async def get_public_config_by_code(code: str, db: DbDep) -> BusinessPublicConfig:
    """Return the public white-label config for a business by 6-digit code.

    Called from the generic marketplace entry screen when a homeowner types in
    the electrician's code instead of using a white-label build.
    """
    await bypass_rls_for_transaction(db)
    tenant = await _resolve_active_tenant_by_code(db, code)
    return await _build_public_config(db, tenant)


async def _build_public_config(db: AsyncSession, tenant: Tenant) -> BusinessPublicConfig:
    """Build the white-label public config for a resolved tenant."""
    service_rows = await db.scalars(
        select(BusinessService.category).where(
            BusinessService.tenant_id == tenant.id,
            BusinessService.is_active.is_(True),
            BusinessService.is_launch_enabled.is_(True),
        )
    )
    categories = list(service_rows.all())

    return BusinessPublicConfig(
        slug=tenant.slug,
        code=tenant.code,
        name=tenant.name,
        logo_url=tenant.logo_url,
        primary_color=tenant.primary_color,
        secondary_color=tenant.secondary_color,
        business_services=categories,
        contact_phone=tenant.phone or None,
        address=tenant.address or None,
        reply_email=tenant.email or None,
        review_url=(tenant.settings or {}).get("review_url") or None,
    )


@router.get("/{slug}/public-config", response_model=BusinessPublicConfig)
async def get_public_config(slug: str, db: DbDep) -> BusinessPublicConfig:
    """Return the public white-label config for a business (no auth required).

    This is called by the iOS app before the customer or tradesperson has
    logged in, so it intentionally bypasses RLS.
    """
    await bypass_rls_for_transaction(db)
    tenant = await _resolve_active_tenant(db, slug)
    return await _build_public_config(db, tenant)


async def _get_or_provision_customer(
    db: AsyncSession,
    tenant: Tenant,
    contact: Contact,
    data: PublicQuoteRequestCreate,
) -> Customer | None:
    """Auto-provision a passwordless customer account for the contact email.

    A homeowner who submits with an email gets a real (passwordless, active)
    customer record so the inline AI thread, notifications and later
    registration attach to it. Best-effort: runs in a savepoint and any
    failure rolls back only itself, returning ``None`` — the submission is
    never affected.
    """
    if not contact.email:
        return None
    try:
        async with db.begin_nested():
            customer = await db.scalar(
                select(Customer).where(
                    Customer.tenant_id == tenant.id,
                    func.lower(Customer.email) == contact.email.lower(),
                )
            )
            if customer is None:
                prop = (data.structured_data or {}).get("property")
                customer = Customer(
                    tenant_id=tenant.id,
                    contact_id=contact.id,
                    email=contact.email,
                    full_name=contact.name or data.contact.name,
                    phone=data.contact.phone,
                    address=data.contact.address,
                    postcode=data.contact.postcode,
                    password_hash=None,
                    is_active=True,
                    marketing_consent=data.marketing_consent,
                    property_profile=prop if isinstance(prop, dict) else {},
                )
                db.add(customer)
                await db.flush()
            elif customer.contact_id is None:
                customer.contact_id = contact.id
        return customer
    except Exception as exc:
        logger.warning(
            "intake_customer_provision_failed",
            tenant_id=str(tenant.id),
            error_type=type(exc).__name__,
            error=str(exc)[:200],
        )
        return None


@router.post(
    "/{slug}/quote-requests",
    status_code=status.HTTP_201_CREATED,
    response_model=PublicQuoteRequestAck,
)
@limiter.limit("10/minute")
async def submit_public_quote_request(
    slug: str,
    data: PublicQuoteRequestCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: DbDep,
) -> PublicQuoteRequestAck:
    """Create a quote request from a homeowner via the white-label app.

    Unauthenticated: the target business is identified by ``slug``. A CRM
    contact is created (or reused by email) and linked to the new request so it
    shows up as a lead in the tradesperson's dashboard. An AI draft quote is
    generated in the background — the 201 ack never waits on the LLM.
    """
    tenant = await _resolve_active_tenant(db, slug)
    # Insert tenant-scoped rows under this tenant's RLS context.
    await set_tenant_in_session(db, tenant.id)

    # If the homeowner is logged in (customer token for this tenant), link the
    # request to their account so it appears in their history, and reuse their
    # contact record.
    customer: Customer | None = None
    token = _extract_token(request)
    if token:
        claims = decode_access_token(token)
        if claims is not None and claims.get("subject_type") == "customer":
            try:
                token_customer_id = UUID(str(claims.get("sub")))
                token_tenant_id = UUID(str(claims.get("tenant_id")))
            except (ValueError, TypeError):
                token_customer_id = token_tenant_id = None  # type: ignore[assignment]
            if token_customer_id is not None and token_tenant_id == tenant.id:
                candidate = await db.get(Customer, token_customer_id)
                if candidate is not None and candidate.tenant_id == tenant.id:
                    customer = candidate

    contact: Contact | None = None
    if customer is not None and customer.contact_id:
        contact = await db.get(Contact, customer.contact_id)
    if contact is None and data.contact.email:
        contact = await db.scalar(
            select(Contact).where(
                Contact.tenant_id == tenant.id,
                Contact.email == str(data.contact.email),
            )
        )
    # Blocked customers (N26) cannot submit via the public form either. Only a
    # reused contact can be blocked — a brand-new one is created below.
    if contact is not None and await contact_is_blocked(db, tenant.id, contact.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=BLOCKED_CUSTOMER_DETAIL)
    if contact is None:
        contact = Contact(
            tenant_id=tenant.id,
            name=data.contact.name,
            email=str(data.contact.email) if data.contact.email else None,
            phone=data.contact.phone,
            address=data.contact.address,
            postcode=data.contact.postcode,
        )
        db.add(contact)
        await db.flush()
    else:
        # Reused contact: refresh details the homeowner just re-entered.
        if data.contact.phone:
            contact.phone = data.contact.phone
        if data.contact.address:
            contact.address = data.contact.address
        if data.contact.postcode:
            contact.postcode = data.contact.postcode
        if data.contact.name:
            contact.name = data.contact.name

    # Persist the captured preferred contact method (staff follow-up channel).
    # Mobile sends it as structured_data.preferredContact (string); the portal
    # sends {"method": ...}; an explicit contact field wins either way.
    preferred_method = normalise_preferred_contact(data.contact.preferred_contact_method)
    if preferred_method is None:
        preferred_method = normalise_preferred_contact(
            (data.structured_data or {}).get("preferredContact")
        )
    if preferred_method is not None:
        contact.preferred_contact_method = preferred_method

    # Logged-in customer: keep their account details current so repeat quote
    # requests pre-fill (postcode/phone + property profile).
    if customer is not None:
        if data.contact.postcode:
            customer.postcode = data.contact.postcode
        if data.contact.phone:
            customer.phone = data.contact.phone
        if data.contact.address:
            customer.address = data.contact.address
        prop = (data.structured_data or {}).get("property")
        if isinstance(prop, dict) and prop:
            customer.property_profile = prop

    # Guest submission with an email: auto-provision a passwordless customer
    # account so the inline AI thread, notifications and a later registration
    # have a customer record to attach to. Best-effort (see helper).
    if customer is None and contact.email:
        customer = await _get_or_provision_customer(db, tenant, contact, data)

    structured_data = {
        **data.structured_data,
        "category": data.category,
        "title": data.title,
        "marketing_consent": data.marketing_consent,
    }

    quote_request = QuoteRequest(
        tenant_id=tenant.id,
        contact_id=contact.id,
        customer_id=customer.id if customer is not None else None,
        source="app",
        raw_text=data.raw_text,
        structured_data=structured_data,
        urgency=data.urgency,
        media_urls=data.media_urls,
        preferred_dates=data.preferred_dates,
        safety_review_required=data.safety_review_required,
    )
    db.add(quote_request)
    await db.flush()
    # Commit before scheduling the background auto-draft: background tasks run
    # before the get_db dependency cleanup commits, and the worker opens its
    # own session, so the new rows must already be durable.
    await db.commit()
    await db.refresh(quote_request)

    # Kick off AI quote generation in the background. Failures are logged by
    # the worker and never affect this ack.
    background_tasks.add_task(auto_draft_quote_for_request, tenant.id, quote_request.id)

    ack_id = quote_request.id
    ack_status = quote_request.status

    # Optional quick AI check: ONE bounded cheap-model call (hard timeout,
    # fail-open) the "submitting…" view waits on. When it has a follow-up
    # question, persist it on the chat thread and hand back a guest-scoped
    # thread token so the homeowner can answer inline without an account.
    ai_check: PublicIntakeCheck | None = None
    if data.sync_check:
        check = await run_intake_check(db, quote_request, tenant, entry_channel=data.entry_channel)
        if check.status == "questions" and check.question:
            db.add(
                Communication(
                    tenant_id=tenant.id,
                    contact_id=contact.id,
                    quote_request_id=quote_request.id,
                    channel="in_app_chat",
                    direction="outbound",
                    sender_role="ai",
                    body=check.question,
                    status="sent",
                    ai_metadata={"complete": False, "intake_check": True},
                )
            )
            thread_token, thread_expires_at = issue_guest_token(quote_request.id, tenant.id)
            ai_check = PublicIntakeCheck(
                status="questions",
                question=check.question,
                thread_token=thread_token,
                thread_expires_at=thread_expires_at,
            )
        elif check.status == "ok":
            ai_check = PublicIntakeCheck(status="ok")
        else:
            ai_check = PublicIntakeCheck(status="unavailable")
        # Persist the AI question and the check's telemetry row.
        await db.commit()

    return PublicQuoteRequestAck(
        id=ack_id,
        status=ack_status,
        reference=str(ack_id)[:8].upper(),
        ai_check=ai_check,
    )


# Public intake photo upload constraints.
_INTAKE_UPLOAD_MAX_BYTES = 10 * 1024 * 1024  # 10 MB per image
_INTAKE_UPLOAD_MAX_FILES = 5
_INTAKE_UPLOAD_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


def _store_intake_upload(tenant_id: UUID, file: UploadFile, content: bytes) -> dict[str, str]:
    """Store one intake photo under the tenant's ``intake/`` prefix.

    Reuses the files router's MinIO client/bucket helpers; the key still
    starts with ``tenants/{tenant_id}/`` so the tenant-prefixed download
    check applies unchanged.
    """
    from app.config import settings
    from app.routers.files import _ensure_bucket, s3_client

    safe_name = (file.filename or "photo").split("/")[-1][:120]
    key = f"tenants/{tenant_id}/intake/{uuid4()}/{safe_name}"
    client = s3_client()
    _ensure_bucket(client)
    client.put_object(
        Bucket=settings.minio_bucket,
        Key=key,
        Body=content,
        ContentType=file.content_type or "application/octet-stream",
    )
    return {"key": key, "url": f"/files/download?key={key}"}


@router.post("/{slug}/quote-requests/uploads", status_code=status.HTTP_201_CREATED)
@limiter.limit("20/hour")
async def upload_intake_photos(
    slug: str,
    request: Request,
    db: DbDep,
    files: list[UploadFile] = File(...),
) -> dict[str, list[str]]:
    """Public photo upload for the quote-request intake form (no auth).

    Accepts up to 5 images (jpeg/png/webp, ≤10 MB each), stores them under
    the tenant's ``intake/`` prefix and returns the proxy URLs the form then
    submits back as ``media_urls`` on the quote request.
    """
    tenant = await _resolve_active_tenant(db, slug)

    if len(files) > _INTAKE_UPLOAD_MAX_FILES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"At most {_INTAKE_UPLOAD_MAX_FILES} photos per upload",
        )

    urls: list[str] = []
    for file in files:
        if (file.content_type or "").lower() not in _INTAKE_UPLOAD_CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Only jpeg, png or webp images are accepted",
            )
        content = await file.read()
        if len(content) > _INTAKE_UPLOAD_MAX_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Each photo must be 10 MB or smaller",
            )
        try:
            stored = _store_intake_upload(tenant.id, file, content)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not store file: {exc}",
            ) from exc
        urls.append(stored["url"])

    return {"urls": urls}
