"""Contact endpoints."""

from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import Actions, write_audit_log
from app.database import get_db
from app.dependencies import CurrentUserDep, TenantDep
from app.models import Contact, Customer, Invoice, Quote
from app.rls import set_tenant_in_session
from app.schemas import ContactBlockRequest, ContactCreate, ContactRead, ContactUpdate

router = APIRouter(prefix="/contacts", tags=["Contacts"])
DbDep = Annotated[AsyncSession, Depends(get_db)]

# --- Trust badges (N26) ------------------------------------------------------
# Auto badges are computed on read from invoice/quote history (never stored),
# so they always reflect current data. Manual overrides live on
# ``Contact.badge_overrides`` and win over the auto result per badge.
LATE_PAYER_BADGE = "late_payer"
NON_PAYER_BADGE = "non_payer"
TIME_WASTER_BADGE = "time_waster"
KNOWN_BADGES = (LATE_PAYER_BADGE, NON_PAYER_BADGE, TIME_WASTER_BADGE)

# --- Reminder (chase) preferences (F2) ---------------------------------------
# Per-customer overrides for the reminder scheduler, stored on
# ``Contact.reminder_preferences`` (NULL = tenant defaults). Merged key-by-key
# on PATCH, mirroring ``badge_overrides``.
REMINDER_PREF_QUOTE_CHASE = "quote_chase_enabled"
REMINDER_PREF_INVOICE_CHASE = "invoice_chase_enabled"
REMINDER_PREF_MAX_REMINDERS = "max_reminders"
KNOWN_REMINDER_PREFS = (
    REMINDER_PREF_QUOTE_CHASE,
    REMINDER_PREF_INVOICE_CHASE,
    REMINDER_PREF_MAX_REMINDERS,
)

# Rule thresholds (documented defaults):
# - Late Payer: paid after the due date more than once (>= 2 late payments).
# - Non-payer: any issued invoice still unpaid > 30 days past its due date.
# - Time Waster: more than two quotes issued (>= 3) with zero engagement
#   (none ever approved, rejected or invoiced).
LATE_PAYER_MIN_LATE_PAYMENTS = 2
NON_PAYER_OVERDUE_DAYS = 30
TIME_WASTER_MIN_ISSUED_QUOTES = 3
# Quote statuses that prove the customer replied/engaged. Draft quotes were
# never sent, so they count neither as issued nor as engagement.
QUOTE_ENGAGED_STATUSES = ("approved", "rejected", "invoiced")

# 403 detail shared by every block-enforcement point so clients can key on the
# stable prefix and show a helpful message.
BLOCKED_CUSTOMER_DETAIL = (
    "customer_blocked: This customer has been blocked by the business and cannot "
    "log in, request quotes or send messages. Contact the business directly."
)


async def contact_is_blocked(db: AsyncSession, tenant_id: UUID, contact_id: UUID | None) -> bool:
    """True when the contact exists (same tenant) and is blocked."""
    if contact_id is None:
        return False
    contact = await db.get(Contact, contact_id)
    return bool(contact is not None and contact.tenant_id == tenant_id and contact.is_blocked)


async def _compute_auto_badges(
    db: AsyncSession, tenant_id: UUID, contact_ids: list[UUID]
) -> dict[UUID, list[str]]:
    """Compute rule-based badges for the given contacts (three aggregate queries)."""
    badges: dict[UUID, list[str]] = {contact_id: [] for contact_id in contact_ids}
    if not contact_ids:
        return badges

    # Late Payer — invoices paid after their due date (date-level comparison so
    # a same-day payment never counts as late).
    late_rows = await db.execute(
        select(Invoice.contact_id, func.count())
        .where(
            Invoice.tenant_id == tenant_id,
            Invoice.contact_id.in_(contact_ids),
            Invoice.paid_at.is_not(None),
            Invoice.due_date.is_not(None),
            func.date(Invoice.paid_at) > func.date(Invoice.due_date),
        )
        .group_by(Invoice.contact_id)
    )
    for contact_id, late_count in late_rows.all():
        if late_count >= LATE_PAYER_MIN_LATE_PAYMENTS:
            badges[contact_id].append(LATE_PAYER_BADGE)

    # Non-payer — issued ("sent") invoices unpaid well past due.
    overdue_cutoff = datetime.utcnow() - timedelta(days=NON_PAYER_OVERDUE_DAYS)
    overdue_rows = await db.execute(
        select(Invoice.contact_id)
        .where(
            Invoice.tenant_id == tenant_id,
            Invoice.contact_id.in_(contact_ids),
            Invoice.status == "sent",
            Invoice.due_date.is_not(None),
            Invoice.due_date < overdue_cutoff,
        )
        .group_by(Invoice.contact_id)
    )
    for (contact_id,) in overdue_rows.all():
        badges[contact_id].append(NON_PAYER_BADGE)

    # Time Waster — several quotes issued, none ever engaged with.
    quote_rows = await db.execute(
        select(
            Quote.contact_id,
            func.count().filter(Quote.status != "draft"),
            func.count().filter(Quote.status.in_(QUOTE_ENGAGED_STATUSES)),
        )
        .where(Quote.tenant_id == tenant_id, Quote.contact_id.in_(contact_ids))
        .group_by(Quote.contact_id)
    )
    for contact_id, issued_count, engaged_count in quote_rows.all():
        if issued_count >= TIME_WASTER_MIN_ISSUED_QUOTES and engaged_count == 0:
            badges[contact_id].append(TIME_WASTER_BADGE)

    return badges


def _effective_badges(auto_badges: list[str], overrides: dict[str, object]) -> list[str]:
    """Apply manual overrides on top of the auto-computed badges."""
    return [
        badge
        for badge in KNOWN_BADGES
        if (overrides[badge] is True if badge in overrides else badge in auto_badges)
    ]


async def _attach_badge_state(
    db: AsyncSession, tenant_id: UUID, contacts: list[Contact], reads: list[ContactRead]
) -> None:
    """Populate auto/effective badge lists on the reads (in place)."""
    auto = await _compute_auto_badges(db, tenant_id, [contact.id for contact in contacts])
    for contact, read in zip(contacts, reads, strict=True):
        overrides = dict(contact.badge_overrides or {})
        read.auto_badges = auto.get(contact.id, [])
        read.badges = _effective_badges(read.auto_badges, overrides)


async def _get_contact(db: AsyncSession, tenant_id: UUID, contact_id: UUID) -> Contact:
    await set_tenant_in_session(db, tenant_id)
    contact = await db.get(Contact, contact_id)
    if contact is None or contact.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return contact


async def _contacts_with_accounts(db: AsyncSession, tenant_id: UUID) -> set[UUID]:
    """Contact ids that have a linked customer account (one query for the list)."""
    result = await db.execute(
        select(Customer.contact_id).where(
            Customer.tenant_id == tenant_id, Customer.contact_id.is_not(None)
        )
    )
    return {row for row in result.scalars().all() if row is not None}


def _normalise_name(value: str | None) -> str:
    return " ".join((value or "").split()).lower()


def _phone_digits(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


async def find_duplicate_contact(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    name: str | None,
    email: str | None,
    phone: str | None,
) -> tuple[Contact, str] | None:
    """Return ``(existing_contact, match_kind)`` when a create would duplicate.

    Match kinds: ``email`` (same email, case-insensitive) or ``name_phone``
    (same normalised name AND same phone digits). Guards against the repeat
    sign-up / re-entry duplicates seen in beta tenants.
    """
    if email and email.strip():
        result = await db.execute(
            select(Contact).where(
                Contact.tenant_id == tenant_id,
                Contact.email.is_not(None),
                Contact.email.ilike(email.strip()),
            )
        )
        existing = result.scalars().first()
        if existing is not None:
            return existing, "email"

    name_key = _normalise_name(name)
    phone_key = _phone_digits(phone)
    if name_key and phone_key:
        result = await db.execute(select(Contact).where(Contact.tenant_id == tenant_id))
        for candidate in result.scalars().all():
            if (
                _normalise_name(candidate.name) == name_key
                and _phone_digits(candidate.phone) == phone_key
            ):
                return candidate, "name_phone"
    return None


@router.get("")
async def list_contacts(
    tenant: TenantDep,
    db: DbDep,
    has_account: bool | None = None,
) -> list[ContactRead]:
    """List contacts for the current tenant.

    ``?has_account=true`` narrows the list to contacts with a linked customer
    account (e.g. the new-message recipient picker — in-app chat only reaches
    customers with the app installed).
    """
    await set_tenant_in_session(db, tenant.id)
    result = await db.execute(select(Contact).where(Contact.tenant_id == tenant.id))
    contacts = list(result.scalars().all())
    with_account = await _contacts_with_accounts(db, tenant.id)
    reads = [ContactRead.model_validate(c) for c in contacts]
    for read in reads:
        read.has_account = read.id in with_account
    await _attach_badge_state(db, tenant.id, contacts, reads)
    if has_account is not None:
        reads = [read for read in reads if read.has_account is has_account]
    return reads


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_contact(
    data: ContactCreate,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ContactRead:
    """Create a contact for the current tenant."""
    await set_tenant_in_session(db, tenant.id)
    duplicate = await find_duplicate_contact(
        db, tenant.id, name=data.name, email=data.email, phone=data.phone
    )
    if duplicate is not None:
        existing, match_kind = duplicate
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"duplicate_contact:{match_kind}:{existing.id}: "
                f"A contact named '{existing.name}' already exists with this "
                f"{'email address' if match_kind == 'email' else 'name and phone number'}. "
                "Edit the existing customer instead of creating a new one."
            ),
        )
    contact = Contact(tenant_id=tenant.id, **data.model_dump())
    db.add(contact)
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.CONTACT_CREATED,
        entity_type="contact",
        entity_id=contact.id,
        payload={"name": contact.name, "email": contact.email},
    )
    await db.commit()
    await db.refresh(contact)
    return ContactRead.model_validate(contact)


@router.get("/{contact_id}")
async def get_contact(contact_id: UUID, tenant: TenantDep, db: DbDep) -> ContactRead:
    """Get a single contact."""
    contact = await _get_contact(db, tenant.id, contact_id)
    with_account = await _contacts_with_accounts(db, tenant.id)
    read = ContactRead.model_validate(contact)
    read.has_account = contact.id in with_account
    await _attach_badge_state(db, tenant.id, [contact], [read])
    return read


@router.patch("/{contact_id}")
async def update_contact(
    contact_id: UUID,
    data: ContactUpdate,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ContactRead:
    """Update a contact.

    ``badge_overrides`` is merged key-by-key: ``true`` forces a badge on,
    ``false`` forces it off and ``null`` clears the override so the auto rule
    decides again. Unknown badge slugs are rejected so typos cannot silently
    create dead overrides.

    ``reminder_preferences`` is merged the same way: booleans toggle chasing
    for quotes/invoices, ``max_reminders`` (int >= 1) caps the tenant reminder
    cadence downward, ``null`` clears a key back to the tenant default and an
    empty result stores NULL (tenant defaults). Unknown keys are rejected.
    """
    contact = await _get_contact(db, tenant.id, contact_id)
    changed = data.model_dump(exclude_unset=True)
    badge_changes = changed.pop("badge_overrides", None)
    if badge_changes:
        unknown = sorted(set(badge_changes) - set(KNOWN_BADGES))
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"unknown_badge: unknown badge slug(s): {', '.join(unknown)}",
            )
        overrides = dict(contact.badge_overrides or {})
        for badge, value in badge_changes.items():
            if value is None:
                overrides.pop(badge, None)
            else:
                overrides[badge] = bool(value)
        contact.badge_overrides = overrides
        changed["badge_overrides"] = overrides
    pref_changes = changed.pop("reminder_preferences", None)
    if pref_changes:
        unknown = sorted(set(pref_changes) - set(KNOWN_REMINDER_PREFS))
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"unknown_reminder_preference: unknown key(s): {', '.join(unknown)}",
            )
        prefs = dict(contact.reminder_preferences or {})
        for key, value in pref_changes.items():
            if value is None:
                prefs.pop(key, None)
            elif key == REMINDER_PREF_MAX_REMINDERS:
                try:
                    prefs[key] = max(1, int(str(value)))
                except (TypeError, ValueError):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"invalid_reminder_preference: {key} must be an integer",
                    ) from None
            else:
                prefs[key] = bool(value)
        # Empty dict collapses back to NULL so "no overrides" reads cleanly
        # and the scheduler treats the contact as on tenant defaults.
        contact.reminder_preferences = prefs or None
        changed["reminder_preferences"] = contact.reminder_preferences
    for key, value in changed.items():
        if key == "badge_overrides":
            continue
        setattr(contact, key, value)
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.CONTACT_UPDATED,
        entity_type="contact",
        entity_id=contact.id,
        payload={"changed_fields": sorted(changed.keys())},
    )
    await db.commit()
    await db.refresh(contact)
    read = ContactRead.model_validate(contact)
    await _attach_badge_state(db, tenant.id, [contact], [read])
    return read


@router.post("/{contact_id}/block")
async def block_contact(
    contact_id: UUID,
    data: ContactBlockRequest,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ContactRead:
    """Block a customer (N26).

    A blocked customer's account cannot log in, create quote requests or
    message the business (enforced server-side at login and quote-request
    creation). Staff-side CRM records, invoices and history are unaffected.
    """
    contact = await _get_contact(db, tenant.id, contact_id)
    if not contact.is_blocked:
        contact.is_blocked = True
        contact.blocked_at = datetime.utcnow()
    contact.blocked_reason = data.reason
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.CONTACT_UPDATED,
        entity_type="contact",
        entity_id=contact.id,
        payload={"changed_fields": ["is_blocked"], "is_blocked": True, "reason": data.reason},
    )
    await db.commit()
    await db.refresh(contact)
    read = ContactRead.model_validate(contact)
    await _attach_badge_state(db, tenant.id, [contact], [read])
    return read


@router.post("/{contact_id}/unblock")
async def unblock_contact(
    contact_id: UUID,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ContactRead:
    """Lift a customer block (N26); the account can log in again immediately."""
    contact = await _get_contact(db, tenant.id, contact_id)
    if contact.is_blocked:
        contact.is_blocked = False
        contact.blocked_at = None
        contact.blocked_reason = None
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.CONTACT_UPDATED,
        entity_type="contact",
        entity_id=contact.id,
        payload={"changed_fields": ["is_blocked"], "is_blocked": False},
    )
    await db.commit()
    await db.refresh(contact)
    read = ContactRead.model_validate(contact)
    await _attach_badge_state(db, tenant.id, [contact], [read])
    return read


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: UUID,
    tenant: TenantDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> None:
    """Delete a contact."""
    contact = await _get_contact(db, tenant.id, contact_id)
    # Capture identifying fields BEFORE deletion so the audit row still has
    # human-readable context after the contact row is gone.
    snapshot = {"name": contact.name, "email": contact.email}
    await db.delete(contact)
    await db.flush()
    await write_audit_log(
        db,
        tenant_id=tenant.id,
        actor=current_user,
        action=Actions.CONTACT_DELETED,
        entity_type="contact",
        entity_id=contact_id,
        payload=snapshot,
    )
    await db.commit()
