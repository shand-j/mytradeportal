#!/usr/bin/env python3
"""Seed a full demo estate (3 tenant businesses) for LOCAL manual testing.

Wipes and re-seeds the demo tenants identified by slug, so the script is
idempotent: re-running it deletes each demo tenant (database-level
``ON DELETE CASCADE`` removes all tenant-scoped rows) and recreates the whole
estate from scratch. Non-demo tenants are never touched.

Usage (from the repo root, with the repo venv active):

    docker compose up -d postgres
    source .venv/bin/activate
    python scripts/init_db.py            # first run only, if the schema is missing
    python scripts/seed_demo_estate.py

Connection: ``DATABASE_URL`` env var, defaulting to the docker-compose local
Postgres (``postgresql+asyncpg://mtp:mtp@localhost:5432/mtp``). The script
refuses to run when ``ENVIRONMENT=production``.

All seeded logins use the password ``GoLive2026!`` — local testing only.
See ``docs/testing-accounts.md`` for the full account list and test flows.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
API_DIR = ROOT / "services" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from app.calculations import build_invoice_from_quote, calculate_quote_totals  # noqa: E402
from app.config import settings  # noqa: E402
from app.models import (  # noqa: E402
    Appointment,
    Communication,
    Contact,
    Customer,
    Invoice,
    Job,
    Notification,
    Payment,
    Quote,
    QuoteLineItem,
    QuoteRequest,
    Review,
    Tenant,
    User,
)
from app.rls import bypass_rls_in_session  # noqa: E402
from app.security import get_password_hash  # noqa: E402
from app.utils.tenant_code import generate_unique_tenant_code  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

SEED_PASSWORD = "GoLive2026!"
DEFAULT_DATABASE_URL = "postgresql+asyncpg://mtp:mtp@localhost:5432/mtp"

NOW = datetime.utcnow()

# ---------------------------------------------------------------------------
# Demo tenant specifications
# ---------------------------------------------------------------------------

TENANT_SPECS: list[dict[str, Any]] = [
    {
        "slug": "sparks",
        "name": "Sparks & Sons Electrical",
        "structure": "family_business",
        "year_established": 1998,
        "settings": {
            "email": "office@sparksandsons.co.uk",
            "phone": "020 7946 0101",
            "address": "14 Mill Lane, Croydon CR0 2AB",
            "website": "https://sparksandsons.co.uk",
            "primary_color": "#D4650A",
            "secondary_color": "#1E3A8A",
            "hourly_labour_rate": 65,
            "daily_labour_rate": 450,
            "markup_percentage": 20,
            "minimum_charge": 95,
            "vat_rate": 20,
            "plan_tier": "pro",
        },
        "users": [
            ("Sam Spark", "sam@sparksandsons.co.uk", "owner", "07700 900101"),
            ("Danny Reeves", "danny@sparksandsons.co.uk", "engineer", "07700 900102"),
        ],
        "contacts": [
            (
                "Margaret Holloway",
                "margaret.holloway@example.co.uk",
                "07911 123456",
                "22 Chestnut Avenue, Croydon",
                "CR0 4HD",
            ),
            (
                "Peter Okafor",
                "peter.okafor@example.co.uk",
                "07911 234567",
                "8 Bramley Close, South Croydon",
                "CR2 7DA",
            ),
            (
                "Susan Doyle",
                "susan.doyle@example.co.uk",
                "07911 345678",
                "156 Brighton Road, Purley",
                "CR8 4AG",
            ),
            (
                "Rajesh Patel",
                "rajesh.patel@example.co.uk",
                "07911 456789",
                "3 The Glade, Shirley",
                "CR0 7UD",
            ),
            (
                "Emma Whitfield",
                "emma.whitfield@example.co.uk",
                "07911 567890",
                "41 Selsdon Park Road, Sanderstead",
                "CR2 9JJ",
            ),
            (
                "Colin Briggs",
                "colin.briggs@example.co.uk",
                "07911 678901",
                "9 Addiscombe Grove, Croydon",
                "CR0 5LR",
            ),
        ],
    },
    {
        "slug": "voltworks",
        "name": "VoltWorks Ltd",
        "structure": "ltd_company",
        "year_established": 2014,
        "companies_house_number": "09213487",
        "settings": {
            "email": "hello@voltworks.co.uk",
            "phone": "0161 496 0202",
            "address": "Unit 7, Trafford Park, Manchester M17 1AE",
            "website": "https://voltworks.co.uk",
            "primary_color": "#0F766E",
            "secondary_color": "#7C3AED",
            "hourly_labour_rate": 70,
            "daily_labour_rate": 500,
            "markup_percentage": 25,
            "minimum_charge": 110,
            "vat_rate": 20,
            "plan_tier": "pro",
        },
        "users": [
            ("Olivia Chen", "olivia@voltworks.co.uk", "owner", "07700 900201"),
            ("Marcus Webb", "marcus@voltworks.co.uk", "engineer", "07700 900202"),
        ],
        "contacts": [
            (
                "Hannah Sutcliffe",
                "hannah.sutcliffe@example.co.uk",
                "07800 111222",
                "12 Palatine Road, Didsbury",
                "M20 2JQ",
            ),
            (
                "Tom Gallagher",
                "tom.gallagher@example.co.uk",
                "07800 222333",
                "88 Wilmslow Road, Withington",
                "M20 4BW",
            ),
            (
                "Aisha Rahman",
                "aisha.rahman@example.co.uk",
                "07800 333444",
                "5 Barlow Moor Road, Chorlton",
                "M21 8AX",
            ),
            (
                "Gordon McAllister",
                "gordon.mcallister@example.co.uk",
                "07800 444555",
                "27 Burton Road, West Didsbury",
                "M20 1LN",
            ),
            (
                "Lucy Thornton",
                "lucy.thornton@example.co.uk",
                "07800 555666",
                "102 School Lane, Didsbury",
                "M20 6RY",
            ),
        ],
    },
    {
        "slug": "brightsparks",
        "name": "Bright Sparks London",
        "structure": "sole_trader",
        "year_established": 2019,
        "settings": {
            "email": "bookings@brightsparkslondon.co.uk",
            "phone": "020 7946 0303",
            "address": "3 Roman Road, Bethnal Green, London E2 0HU",
            "website": "https://brightsparkslondon.co.uk",
            "primary_color": "#B91C1C",
            "secondary_color": "#F59E0B",
            "hourly_labour_rate": 75,
            "daily_labour_rate": 550,
            "markup_percentage": 15,
            "minimum_charge": 120,
            "vat_rate": 20,
            "plan_tier": "starter",
        },
        "users": [
            ("Kieran Doyle", "kieran@brightsparkslondon.co.uk", "owner", "07700 900301"),
            ("Priya Nair", "priya@brightsparkslondon.co.uk", "office_manager", "07700 900302"),
        ],
        "contacts": [
            (
                "Freddie Aldous",
                "freddie.aldous@example.co.uk",
                "07712 111222",
                "45 Columbia Road, Bethnal Green",
                "E2 7RG",
            ),
            (
                "Nadia Hussain",
                "nadia.hussain@example.co.uk",
                "07712 222333",
                "19 Vallance Road, Whitechapel",
                "E1 5HR",
            ),
            (
                "George Papadopoulos",
                "george.papa@example.co.uk",
                "07712 333444",
                "72 Roman Road, Bow",
                "E3 5ES",
            ),
            (
                "Claire Beaumont",
                "claire.beaumont@example.co.uk",
                "07712 444555",
                "30 Victoria Park Square, Hackney",
                "E9 7PB",
            ),
            (
                "Ivan Petrov",
                "ivan.petrov@example.co.uk",
                "07712 555666",
                "8 Approach Road, Bethnal Green",
                "E2 9JT",
            ),
            (
                "Sandra Okonkwo",
                "sandra.okonkwo@example.co.uk",
                "07712 666777",
                "210 Hackney Road, Shoreditch",
                "E2 7QL",
            ),
        ],
    },
]


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _line(description: str, quantity: str, unit_price: str, ai: bool = False) -> dict[str, Any]:
    return {
        "description": description,
        "quantity": Decimal(quantity),
        "unit_price": Decimal(unit_price),
        "ai_generated": ai,
    }


def _ai_rag_block(confidence: float) -> dict[str, Any]:
    """Mirror the ``extra_data["rag"]`` shape written by the generate/refine endpoints."""
    return {
        "confidence": confidence,
        "warnings": [
            "Guide prices only — confirm consumer unit compatibility on site",
            "Access to the loft space was assumed; confirm before quoting final price",
        ],
        "assumptions": [
            "Property is a standard 3-bed semi with existing PVC consumer unit",
            "No asbestos or listed-building constraints",
            "Work carried out during normal working hours",
        ],
        "notes": (
            "Draft priced from the UK electrical cost catalogue; labour estimated "
            "from typical job durations. Excludes VAT."
        ),
        "retrieval_status": "grounded",
        "generation_seconds": 8.31,
    }


def _snapshot_ai_draft(quote: Quote) -> None:
    """Replicate ``routers/quotes.py::_snapshot_ai_draft`` for seeded AI quotes."""
    quote.extra_data = {
        **(quote.extra_data or {}),
        "ai_draft": {
            "line_items": [
                {
                    "description": item.description,
                    "quantity": str(item.quantity),
                    "unit_price": str(item.unit_price),
                }
                for item in quote.line_items
            ],
            "total": str(quote.total),
        },
    }


def _refresh_ai_feedback(quote: Quote) -> None:
    """Replicate ``routers/quotes.py::_refresh_ai_feedback`` for seeded AI quotes."""
    draft = (quote.extra_data or {}).get("ai_draft")
    if not isinstance(draft, dict):
        return
    draft_lines = draft.get("line_items") or []
    draft_total = Decimal(str(draft.get("total", "0") or "0"))

    line_count_delta = len(quote.line_items) - len(draft_lines)
    price_drift_pct: float | None = None
    if draft_total != 0:
        drift = (quote.total - draft_total) / draft_total * 100
        price_drift_pct = float(round(drift, 2))

    quote.extra_data = {
        **(quote.extra_data or {}),
        "ai_feedback": {
            "edited": line_count_delta != 0 or price_drift_pct not in (None, 0.0),
            "line_count_delta": line_count_delta,
            "price_drift_pct": price_drift_pct,
        },
    }


def _make_quote(
    tenant: Tenant,
    contact: Contact,
    title: str,
    description: str,
    status: str,
    lines: list[dict[str, Any]],
    ai_confidence: float | None = None,
    edited_after_snapshot: bool = False,
    quote_request: QuoteRequest | None = None,
) -> Quote:
    """Build a quote with computed totals and (optionally) AI metadata shapes."""
    quote = Quote(
        tenant_id=tenant.id,
        contact_id=contact.id,
        title=title,
        description=description,
        status=status,
        valid_until=NOW + timedelta(days=30),
        quote_request_id=quote_request.id if quote_request else None,
    )
    quote.line_items = [QuoteLineItem(tenant_id=tenant.id, **line) for line in lines]
    calculate_quote_totals(quote)

    if ai_confidence is not None:
        quote.extra_data = {"rag": _ai_rag_block(ai_confidence)}
        _snapshot_ai_draft(quote)
        if edited_after_snapshot:
            # Simulate the electrician refining the draft: one extra manual line.
            manual = QuoteLineItem(
                tenant_id=tenant.id,
                description="Attendance and certification — EIC issued on completion",
                quantity=Decimal("1"),
                unit_price=Decimal("85.00"),
                ai_generated=False,
            )
            quote.line_items.append(manual)
            calculate_quote_totals(quote)
        _refresh_ai_feedback(quote)

    if status in {"sent", "approved", "rejected", "invoiced"}:
        quote.sent_at = NOW - timedelta(days=5)
    if status in {"approved", "invoiced"}:
        quote.approved_at = NOW - timedelta(days=3)
    return quote


async def _wipe_demo_tenant(session: AsyncSession, slug: str) -> bool:
    """Delete an existing demo tenant; CASCADE removes all tenant-scoped rows."""
    tenant = await session.scalar(select(Tenant).where(Tenant.slug == slug))
    if tenant is None:
        return False
    await session.delete(tenant)
    await session.flush()
    return True


async def seed_tenant(session: AsyncSession, spec: dict[str, Any]) -> dict[str, Any]:
    """Wipe and re-seed one demo tenant; return summary info for the report."""
    wiped = await _wipe_demo_tenant(session, spec["slug"])

    tenant = Tenant(
        slug=spec["slug"],
        code=await generate_unique_tenant_code(session),
        name=spec["name"],
        is_active=True,
        status="active",
        launched_at=NOW - timedelta(days=90),
        structure=spec["structure"],
        year_established=spec["year_established"],
        companies_house_number=spec.get("companies_house_number"),
        nations_served=["England"],
        vat_registered=True,
        vat_number="GB123456789",
        vat_scheme="standard",
        quote_defaults={
            "validity_days": 30,
            "terms": "Payment due within 14 days of invoice. All prices exclude VAT.",
        },
        branding={"primary_color": spec["settings"]["primary_color"]},
        settings=spec["settings"],
    )
    session.add(tenant)
    await session.flush()

    password_hash = get_password_hash(SEED_PASSWORD)

    users = [
        User(
            tenant_id=tenant.id,
            email=email,
            full_name=full_name,
            role=role,
            phone=phone,
            password_hash=password_hash,
            is_active=True,
        )
        for full_name, email, role, phone in spec["users"]
    ]
    session.add_all(users)

    contacts = [
        Contact(
            tenant_id=tenant.id,
            name=name,
            email=email,
            phone=phone,
            address=address,
            postcode=postcode,
        )
        for name, email, phone, address, postcode in spec["contacts"]
    ]
    session.add_all(contacts)
    await session.flush()

    # The first three contacts get customer portal login accounts, plus
    # contacts[3] (Rajesh Patel — the showcase AI-triage lead) so testers can
    # log into the customer app and see his completed triage thread.
    portal_contacts = [*contacts[:3], contacts[3]]
    customers = [
        Customer(
            tenant_id=tenant.id,
            contact_id=contact.id,
            email=contact.email,
            full_name=contact.name,
            phone=contact.phone,
            password_hash=password_hash,
            is_active=True,
            marketing_consent=True,
            preferred_contact_method="email",
        )
        for contact in portal_contacts
    ]
    session.add_all(customers)
    await session.flush()

    engineer = next((u for u in users if u.role == "engineer"), users[0])

    # --- Quote requests: new / in-triage / converted -----------------------
    # Rajesh Patel (contacts[3]) is the showcase lead for the AI demo: it
    # carries a COMPLETED AI triage thread (see below) and the structured
    # answers the triage collected, in the same shapes the real backend and
    # customer wizard write (property/questionnaire/ai_extracted).
    qr_new = QuoteRequest(
        tenant_id=tenant.id,
        contact_id=contacts[3].id,
        # Linked to Rajesh's portal account so testers can demo the customer
        # side of the triage chat (customer tokens may only read their own
        # quote requests).
        customer_id=customers[3].id,
        source="web_form",
        raw_text="Fuse box keeps tripping when the kettle and shower run together.",
        structured_data={
            "category": "consumer_unit",
            "title": "Consumer unit replacement (tripping fuse box)",
            "property": {
                "type": "semi",
                "age": "1930-1960",
                "bedrooms": 3,
                "parking": True,
                "tenure": "owner",
            },
            "questionnaire": {
                "consumer_unit": {
                    "circuits": "8",
                    "reason": "repeated_tripping",
                    "known_faults": "none",
                    "occupied": "yes",
                },
                "notes": "Fuse box trips when the kettle and electric shower run together.",
            },
            # Flat str→str facts, exactly as the ai-followup endpoint persists
            # them (structured_data["ai_extracted"], snake_case keys).
            "ai_extracted": {
                "property_type": "semi-detached house",
                "bedrooms": "3",
                "consumer_unit_location": "under the stairs",
                "parking": "driveway",
                "shower_type": "electric shower",
            },
        },
        ai_extracted_summary="Consumer unit upgrade — tripping under combined kettle/shower load.",
        urgency="this_week",
        status="pending",
    )
    qr_triage = QuoteRequest(
        tenant_id=tenant.id,
        contact_id=contacts[4].id,
        customer_id=customers[2].id,
        source="qr",
        raw_text="Need 6 LED downlights in the kitchen and two extra double sockets.",
        ai_extracted_summary="Kitchen: 6 LED downlights + 2 double sockets.",
        urgency="this_month",
        status="processed",
        ai_confidence=Decimal("0.6000"),
    )
    qr_converted = QuoteRequest(
        tenant_id=tenant.id,
        contact_id=contacts[0].id,
        customer_id=customers[0].id,
        source="universal_link",
        raw_text="Old fuse box with rewirable fuses — want a modern consumer unit fitted.",
        ai_extracted_summary="Consumer unit replacement, 3-bed semi.",
        urgency="flexible",
        status="converted_to_quote",
        converted_at=NOW - timedelta(days=6),
        ai_confidence=Decimal("0.8700"),
    )
    session.add_all([qr_new, qr_triage, qr_converted])
    await session.flush()

    # In-app chat triage thread on the in-triage quote request.
    session.add_all(
        [
            Communication(
                tenant_id=tenant.id,
                contact_id=contacts[4].id,
                quote_request_id=qr_triage.id,
                channel="in_app_chat",
                direction="inbound",
                sender_role="customer",
                body="Need 6 LED downlights in the kitchen and two extra double sockets.",
                status="sent",
                created_at=NOW - timedelta(days=1, minutes=40),
            ),
            Communication(
                tenant_id=tenant.id,
                contact_id=contacts[4].id,
                quote_request_id=qr_triage.id,
                channel="in_app_chat",
                direction="outbound",
                sender_role="ai",
                body=(
                    "Thanks! To price this accurately, could you tell me the "
                    "approximate size of the kitchen and whether there's loft "
                    "access above it?"
                ),
                status="sent",
                ai_metadata={"complete": False, "confidence": 60},
                created_at=NOW - timedelta(days=1, minutes=39),
            ),
            Communication(
                tenant_id=tenant.id,
                contact_id=contacts[4].id,
                quote_request_id=qr_triage.id,
                channel="in_app_chat",
                direction="inbound",
                sender_role="customer",
                body="Kitchen is about 4m by 3m, and yes there's a loft hatch above.",
                status="sent",
                created_at=NOW - timedelta(days=1, minutes=35),
            ),
            Communication(
                tenant_id=tenant.id,
                contact_id=contacts[4].id,
                quote_request_id=qr_triage.id,
                channel="in_app_chat",
                direction="outbound",
                sender_role="ai",
                body="Great — and are the existing sockets on the ring main or spurs?",
                status="sent",
                ai_metadata={"complete": False, "confidence": 60},
                created_at=NOW - timedelta(days=1, minutes=34),
            ),
        ]
    )

    # Completed AI triage thread on the showcase lead (Rajesh Patel): the
    # assistant asked two clarifying questions, the customer answered both, and
    # the final AI message closes the loop with complete:true / confidence 85,
    # matching what the ai-followup endpoint persists.
    session.add_all(
        [
            Communication(
                tenant_id=tenant.id,
                contact_id=contacts[3].id,
                quote_request_id=qr_new.id,
                channel="in_app_chat",
                direction="inbound",
                sender_role="customer",
                body="Fuse box keeps tripping when the kettle and shower run together.",
                status="sent",
                created_at=NOW - timedelta(hours=20),
            ),
            Communication(
                tenant_id=tenant.id,
                contact_id=contacts[3].id,
                quote_request_id=qr_new.id,
                channel="in_app_chat",
                direction="outbound",
                sender_role="ai",
                body=(
                    "Thanks for the detail! Could you tell me what type of property "
                    "it is, how many bedrooms it has, and whether the shower is an "
                    "electric shower? That helps us gauge the load on the fuse box."
                ),
                status="sent",
                ai_metadata={"complete": False, "confidence": 45},
                created_at=NOW - timedelta(hours=20) + timedelta(minutes=1),
            ),
            Communication(
                tenant_id=tenant.id,
                contact_id=contacts[3].id,
                quote_request_id=qr_new.id,
                channel="in_app_chat",
                direction="inbound",
                sender_role="customer",
                body=(
                    "It's a 3-bed semi-detached house and yes, the shower is electric."
                ),
                status="sent",
                created_at=NOW - timedelta(hours=19, minutes=42),
            ),
            Communication(
                tenant_id=tenant.id,
                contact_id=contacts[3].id,
                quote_request_id=qr_new.id,
                channel="in_app_chat",
                direction="outbound",
                sender_role="ai",
                body=(
                    "That's helpful — an electric shower plus a kettle would strain an "
                    "old fuse box. Where is the fuse box located, and is there parking "
                    "available for the electrician's van?"
                ),
                status="sent",
                ai_metadata={"complete": False, "confidence": 65},
                created_at=NOW - timedelta(hours=19, minutes=41),
            ),
            Communication(
                tenant_id=tenant.id,
                contact_id=contacts[3].id,
                quote_request_id=qr_new.id,
                channel="in_app_chat",
                direction="inbound",
                sender_role="customer",
                body="It's under the stairs, and there's a driveway you can park on.",
                status="sent",
                created_at=NOW - timedelta(hours=19, minutes=18),
            ),
            Communication(
                tenant_id=tenant.id,
                contact_id=contacts[3].id,
                quote_request_id=qr_new.id,
                channel="in_app_chat",
                direction="outbound",
                sender_role="ai",
                body=(
                    "Thank you for the details. The electrician will review your "
                    "request and you'll be notified once the quote is ready."
                ),
                status="sent",
                ai_metadata={"complete": True, "confidence": 85},
                created_at=NOW - timedelta(hours=19, minutes=17),
            ),
        ]
    )

    # --- Quotes -------------------------------------------------------------
    labour_desc = "Labour — qualified electrician (hourly)"
    q_ai_draft = _make_quote(
        tenant,
        contacts[0],
        "Consumer unit replacement",
        "Supply and fit a modern 10-way RCBO consumer unit; test and certify.",
        "draft",
        [
            _line("Consumer unit — 10-way RCBO board (supply)", "1", "215.00", ai=True),
            _line(labour_desc, "4", "65.00", ai=True),
            _line("Circuit testing and EIC certification", "1", "95.00", ai=True),
        ],
        ai_confidence=0.87,
        quote_request=qr_converted,
    )
    q_ai_sent = _make_quote(
        tenant,
        contacts[1],
        "Kitchen downlights and additional sockets",
        "Install 6 LED downlights and 2 additional double sockets in the kitchen.",
        "sent",
        [
            _line("LED downlight — fire-rated, dimmable (supply & fit)", "6", "38.50", ai=True),
            _line("Double socket outlet — 13A (supply & fit)", "2", "72.00", ai=True),
            _line(labour_desc, "5", "65.00", ai=True),
        ],
        ai_confidence=0.74,
        edited_after_snapshot=True,
    )
    q_approved = _make_quote(
        tenant,
        contacts[2],
        "EV charger installation",
        "Supply and install 7kW tethered home EV charger with dedicated circuit.",
        "approved",
        [
            _line("EV charger — 7kW tethered unit (supply)", "1", "489.00"),
            _line("Dedicated 32A circuit from consumer unit", "1", "185.00"),
            _line(labour_desc, "4", "65.00"),
        ],
    )
    q_rejected = _make_quote(
        tenant,
        contacts[3],
        "Garden lighting installation",
        "Supply and install 8 LED spike lights and a weatherproof socket.",
        "rejected",
        [
            _line("LED garden spike light (supply & fit)", "8", "42.00"),
            _line("Weatherproof 13A socket (supply & fit)", "1", "88.00"),
            _line(labour_desc, "6", "65.00"),
        ],
    )
    q_invoiced = _make_quote(
        tenant,
        contacts[4],
        "EICR with minor remedial works",
        "Electrical Installation Condition Report plus replacement of two faulty accessories.",
        "invoiced",
        [
            _line("EICR — 3-bed domestic property", "1", "180.00"),
            _line("Remedial works — replace damaged socket and switch", "1", "65.00"),
            _line(labour_desc, "2", "65.00"),
        ],
    )
    quotes = [q_ai_draft, q_ai_sent, q_approved, q_rejected, q_invoiced]
    session.add_all(quotes)
    await session.flush()

    # Link the converted quote request to the AI draft quote (both directions,
    # matching the generate endpoint).
    qr_converted.quote_id = q_ai_draft.id

    # --- Jobs ---------------------------------------------------------------
    job_scheduled = Job(
        tenant_id=tenant.id,
        contact_id=contacts[2].id,
        quote_id=q_approved.id,
        title="EV charger installation",
        description=q_approved.description,
        status="scheduled",
        scheduled_start=NOW + timedelta(days=4, hours=9),
        scheduled_end=NOW + timedelta(days=4, hours=13),
        assigned_user_id=engineer.id,
        address=contacts[2].address,
        postcode=contacts[2].postcode,
    )
    job_in_progress = Job(
        tenant_id=tenant.id,
        contact_id=contacts[2].id,
        quote_id=q_approved.id,
        title="EV charger — site survey and cable run",
        status="in_progress",
        scheduled_start=NOW - timedelta(hours=2),
        scheduled_end=NOW + timedelta(hours=3),
        assigned_user_id=engineer.id,
        address=contacts[2].address,
        postcode=contacts[2].postcode,
    )
    job_completed = Job(
        tenant_id=tenant.id,
        contact_id=contacts[4].id,
        quote_id=q_invoiced.id,
        title="EICR with minor remedial works",
        status="completed",
        scheduled_start=NOW - timedelta(days=7, hours=4),
        scheduled_end=NOW - timedelta(days=7),
        completed_at=NOW - timedelta(days=7),
        assigned_user_id=engineer.id,
        address=contacts[4].address,
        postcode=contacts[4].postcode,
    )
    session.add_all([job_scheduled, job_in_progress, job_completed])
    await session.flush()

    # --- Appointments (this week and next) -----------------------------------
    appointments = [
        Appointment(
            tenant_id=tenant.id,
            contact_id=contacts[2].id,
            job_id=job_in_progress.id,
            title="EV charger — cable run visit",
            start_at=NOW + timedelta(hours=3),
            end_at=NOW + timedelta(hours=6),
            status="confirmed",
            address=contacts[2].address,
            assigned_user_id=engineer.id,
        ),
        Appointment(
            tenant_id=tenant.id,
            contact_id=contacts[1].id,
            title="Kitchen downlights — site visit",
            start_at=NOW + timedelta(days=1, hours=10),
            end_at=NOW + timedelta(days=1, hours=12),
            status="confirmed",
            address=contacts[1].address,
            assigned_user_id=engineer.id,
        ),
        Appointment(
            tenant_id=tenant.id,
            contact_id=contacts[3].id,
            title="Tripping fuse box — diagnostic visit",
            start_at=NOW + timedelta(days=3, hours=14),
            end_at=NOW + timedelta(days=3, hours=15),
            status="confirmed",
            address=contacts[3].address,
            assigned_user_id=engineer.id,
        ),
        Appointment(
            tenant_id=tenant.id,
            contact_id=contacts[0].id,
            title="Consumer unit replacement",
            start_at=NOW + timedelta(days=8, hours=9),
            end_at=NOW + timedelta(days=8, hours=13),
            status="confirmed",
            address=contacts[0].address,
            assigned_user_id=engineer.id,
        ),
        Appointment(
            tenant_id=tenant.id,
            contact_id=contacts[3].id,
            title="Quoting visit — garden lighting",
            start_at=NOW - timedelta(days=1, hours=10),
            end_at=NOW - timedelta(days=1, hours=9),
            status="completed",
            address=contacts[3].address,
            assigned_user_id=engineer.id,
        ),
        Appointment(
            tenant_id=tenant.id,
            contact_id=contacts[3].id,
            title="Follow-up visit (customer cancelled)",
            start_at=NOW + timedelta(days=2, hours=15),
            end_at=NOW + timedelta(days=2, hours=16),
            status="cancelled",
            address=contacts[3].address,
            assigned_user_id=engineer.id,
        ),
    ]
    session.add_all(appointments)

    # --- Invoices: draft / sent / paid ---------------------------------------
    invoice_draft = build_invoice_from_quote(
        q_ai_sent, "INV-001", due_date=NOW + timedelta(days=14)
    )
    invoice_draft.job_id = job_in_progress.id

    invoice_sent = build_invoice_from_quote(
        q_approved, "INV-002", due_date=NOW + timedelta(days=11)
    )
    invoice_sent.status = "sent"
    invoice_sent.issue_date = NOW - timedelta(days=3)
    invoice_sent.job_id = job_scheduled.id

    invoice_paid = build_invoice_from_quote(q_invoiced, "INV-003", due_date=NOW - timedelta(days=1))
    invoice_paid.status = "paid"
    invoice_paid.issue_date = NOW - timedelta(days=7)
    invoice_paid.paid_at = NOW - timedelta(days=6)
    invoice_paid.job_id = job_completed.id
    session.add_all([invoice_draft, invoice_sent, invoice_paid])
    await session.flush()

    payment = Payment(
        tenant_id=tenant.id,
        invoice_id=invoice_paid.id,
        amount=invoice_paid.total,
        currency_code="GBP",
        status="completed",
        provider="paddle",
        provider_transaction_id=f"txn_seed_{spec['slug']}_001",
        provider_checkout_id=f"chk_seed_{spec['slug']}_001",
        paid_at=invoice_paid.paid_at,
    )
    session.add(payment)

    # --- Reviews --------------------------------------------------------------
    reviews = [
        Review(
            tenant_id=tenant.id,
            contact_id=contacts[4].id,
            rating=5,
            comment="Punctual, tidy and the certificate came through the same day.",
            source="in_app",
            status="approved",
            response="Thanks for the kind words — glad we could help!",
            responded_at=NOW - timedelta(days=6),
        ),
        Review(
            tenant_id=tenant.id,
            contact_id=contacts[2].id,
            rating=4,
            comment="Good work on the charger. Scheduling was a bit slow but the job is solid.",
            source="google",
            status="approved",
        ),
        Review(
            tenant_id=tenant.id,
            contact_id=contacts[0].id,
            rating=5,
            comment="Quoted quickly and explained everything clearly.",
            source="in_app",
            status="pending",
        ),
    ]
    session.add_all(reviews)

    # Realistic notification backlog so the bell isn't empty on first login.
    # These mirror the events the live producers fire in production.
    notifications = [
        Notification(
            tenant_id=tenant.id,
            recipient_type="staff",
            recipient_id=None,
            type="quote_ready",
            title="Quote ready for review",
            body="AI draft quote 'Consumer unit replacement' is ready for your review.",
            link=f"/quotes/{quotes[0].id}",
            read_at=None,
        ),
        Notification(
            tenant_id=tenant.id,
            recipient_type="staff",
            recipient_id=None,
            type="chat_reply",
            title="Customer replied",
            body="Kitchen downlights lead — customer replied to the AI chat.",
            link=f"/lead/{qr_triage.id}",
            read_at=None,
        ),
        Notification(
            tenant_id=tenant.id,
            recipient_type="staff",
            recipient_id=None,
            type="quote_accepted",
            title="Quote accepted",
            body="Customer accepted the EV charger installation quote.",
            link=f"/quote/{quotes[2].id}",
            read_at=NOW - timedelta(days=1),
        ),
        Notification(
            tenant_id=tenant.id,
            recipient_type="staff",
            recipient_id=None,
            type="invoice_paid",
            title="Invoice paid",
            body="Invoice INV-003 has been marked paid.",
            link=None,
            read_at=NOW - timedelta(days=2),
        ),
    ]
    session.add_all(notifications)

    return {
        "tenant": tenant,
        "wiped": wiped,
        "users": users,
        "customers": customers,
    }


# ---------------------------------------------------------------------------
# Verification + report
# ---------------------------------------------------------------------------

SCOPED_COUNT_TABLES = (
    ("users", User),
    ("contacts", Contact),
    ("customers", Customer),
    ("quote_requests", QuoteRequest),
    ("communications", Communication),
    ("quotes", Quote),
    ("jobs", Job),
    ("appointments", Appointment),
    ("invoices", Invoice),
    ("payments", Payment),
    ("reviews", Review),
)


async def verify_counts(session: AsyncSession, tenant_id: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name, model in SCOPED_COUNT_TABLES:
        counts[name] = await session.scalar(
            select(func.count()).select_from(model).where(model.tenant_id == tenant_id)
        )
    return counts


async def main() -> None:
    if settings.environment == "production":
        raise RuntimeError("This seed script must not be run in production")

    database_url = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    print(f"Seeding demo estate into: {database_url}")
    engine = create_async_engine(database_url, future=True)

    summaries: list[dict[str, Any]] = []
    async with AsyncSession(engine, expire_on_commit=False) as session:
        # Seed scripts legitimately cross tenant boundaries (see
        # seed_admin_user.py): opt out of RLS for this connection. The local
        # `mtp` role is also a superuser, so RLS would not block us anyway.
        await bypass_rls_in_session(session)
        for spec in TENANT_SPECS:
            summary = await seed_tenant(session, spec)
            summaries.append(summary)
        await session.commit()

        print()
        # commit() released the connection; re-apply the RLS bypass on the new
        # checkout before the verification queries (belt and braces — the local
        # `mtp` role is a superuser and bypasses RLS anyway).
        await bypass_rls_in_session(session)
        for summary in summaries:
            tenant = summary["tenant"]
            verified = await verify_counts(session, tenant.id)
            action = "re-seeded (wiped existing)" if summary["wiped"] else "created"
            print(f"Tenant: {tenant.name} (slug={tenant.slug}, code={tenant.code}) — {action}")
            for user in summary["users"]:
                print(f"  staff:   {user.email}  role={user.role}  password={SEED_PASSWORD}")
            for customer in summary["customers"]:
                print(f"  portal:  {customer.email}  password={SEED_PASSWORD}")
            print("  counts:  " + "  ".join(f"{key}={value}" for key, value in verified.items()))
            print()

    await engine.dispose()
    print(
        "Feature flags: served at runtime from Railway Signals (no DB seeding). "
        "Locally RAILWAY_TOKEN is unset, so voice_ai_insights, demand_forecasting "
        "and external_integrations all default to OFF."
    )
    print("Done. See docs/testing-accounts.md for logins and test flows.")


if __name__ == "__main__":
    asyncio.run(main())
