"""Dashboard analytics endpoints."""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import TenantDep
from app.models import Invoice, Job, Quote, QuoteLineItem, Review
from app.rls import set_tenant_in_session
from app.schemas import (
    Activity,
    AIInsights,
    AiQuotePerformance,
    AiQuotePerformanceMonthlyData,
    DashboardData,
    DashboardKPIs,
    RevenueChartData,
    ServiceBreakdownItem,
)

router = APIRouter(prefix="/analytics", tags=["Analytics"])
DbDep = Annotated[AsyncSession, Depends(get_db)]

# Time-saved assumption: drafting a comparable quote manually (turning site
# notes into priced line items) takes an electrician ~25 minutes; the AI draft
# needs only a quick review, treated as negligible against that baseline.
AI_DRAFT_MANUAL_MINUTES = 25


_SERVICE_COLORS = [
    "#2563EB",
    "#16A34A",
    "#D4650A",
    "#A8A29E",
    "#7C3AED",
    "#DC2626",
]


def _month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _previous_month_start(dt: datetime) -> datetime:
    start = _month_start(dt)
    if start.month == 1:
        return start.replace(year=start.year - 1, month=12)
    return start.replace(month=start.month - 1)


def _last_6_months() -> list[tuple[datetime, str, str]]:
    """Return (start_dt, label, key) for the last 6 months."""
    now = datetime.utcnow()
    starts: list[datetime] = []
    m = _month_start(now)
    for _ in range(6):
        starts.insert(0, m)
        m = m.replace(year=m.year - 1, month=12) if m.month == 1 else m.replace(month=m.month - 1)
    return [(s, s.strftime("%b"), s.strftime("%Y-%m")) for s in starts]


def _to_float(value: Any) -> float:
    return float(value) if value is not None else 0.0


@router.get("/dashboard")
async def dashboard(tenant: TenantDep, db: DbDep) -> DashboardData:
    """Return aggregated KPIs and charts for the admin dashboard."""
    await set_tenant_in_session(db, tenant.id)

    now = datetime.utcnow()
    previous_month_start = _previous_month_start(now)

    # Revenue this month and last month (paid invoices)
    revenue_result = await db.execute(
        select(Invoice.status, func.sum(Invoice.total).label("total"))
        .where(
            Invoice.tenant_id == tenant.id,
            Invoice.status == "paid",
            Invoice.issue_date >= previous_month_start,
        )
        .group_by(Invoice.status)
    )
    revenue_by_period = {row.status: _to_float(row.total) for row in revenue_result.all()}

    # Month-level revenue for the chart
    month_rows = await db.execute(
        select(
            func.to_char(Invoice.issue_date, "YYYY-MM").label("month"),
            func.sum(Invoice.total).label("revenue"),
        )
        .where(
            Invoice.tenant_id == tenant.id,
            Invoice.status == "paid",
            Invoice.issue_date >= _last_6_months()[0][0],
        )
        .group_by("month")
        .order_by("month")
    )
    revenue_by_month = {row.month: _to_float(row.revenue) for row in month_rows.all()}

    months = _last_6_months()
    revenue_chart_values = [revenue_by_month.get(key, 0.0) for _, _, key in months]
    target_values = [0.0, *revenue_chart_values[:-1]]
    if not any(target_values):
        target_values = [max(v, 1000.0) for v in revenue_chart_values]

    # Active jobs
    active_jobs_result = await db.execute(
        select(func.count(Job.id)).where(
            Job.tenant_id == tenant.id,
            Job.status.in_({"scheduled", "in_progress"}),
        )
    )
    active_jobs = active_jobs_result.scalar() or 0

    # Pending quotes
    pending_quotes_result = await db.execute(
        select(
            Quote.status, func.count(Quote.id).label("cnt"), func.sum(Quote.total).label("value")
        )
        .where(Quote.tenant_id == tenant.id, Quote.status.in_({"draft", "sent"}))
        .group_by(Quote.status)
    )
    pending_quotes = 0
    pending_quotes_value = 0.0
    for pq_row in pending_quotes_result.all():
        pending_quotes += int(pq_row.cnt) if pq_row.cnt else 0
        pending_quotes_value += _to_float(pq_row.value)

    week_ahead = now + timedelta(days=7)
    expiring_soon_result = await db.execute(
        select(func.count(Quote.id)).where(
            Quote.tenant_id == tenant.id,
            Quote.status.in_({"draft", "sent"}),
            Quote.valid_until.isnot(None),
            Quote.valid_until >= now,
            Quote.valid_until <= week_ahead,
        )
    )
    quotes_expiring_soon = expiring_soon_result.scalar() or 0

    # AI-drafted quotes: quotes carrying the ai_draft snapshot, plus any quote
    # with an AI-flagged line item (older drafts predate the snapshot).
    ai_quotes_result = await db.execute(
        select(func.count(func.distinct(Quote.id)))
        .outerjoin(QuoteLineItem, QuoteLineItem.quote_id == Quote.id)
        .where(
            Quote.tenant_id == tenant.id,
            or_(
                Quote.extra_data.has_key("ai_draft"),
                QuoteLineItem.ai_generated.is_(True),
            ),
        )
    )
    ai_generated_quotes = ai_quotes_result.scalar() or 0
    ai_time_saved_hours = round(ai_generated_quotes * AI_DRAFT_MANUAL_MINUTES / 60, 1)

    # Reviews
    review_stats = await db.execute(
        select(func.avg(Review.rating).label("avg"), func.count(Review.id).label("cnt")).where(
            Review.tenant_id == tenant.id
        )
    )
    review_row = review_stats.one_or_none()
    average_rating = round(_to_float(review_row.avg) if review_row else 0.0, 1)
    review_count = int(review_row.cnt) if review_row else 0

    # Service mix from quote line items
    line_items = await db.execute(
        select(QuoteLineItem.description, QuoteLineItem.total)
        .join(Quote)
        .where(Quote.tenant_id == tenant.id)
    )
    service_revenue: dict[str, float] = defaultdict(float)
    service_counts: dict[str, int] = defaultdict(int)
    for description, total in line_items.all():
        service = (description or "").split()[0] if description else "Unknown"
        service = service.capitalize()
        service_revenue[service] += _to_float(total)
        service_counts[service] += 1

    total_service_revenue = sum(service_revenue.values()) or 1.0
    sorted_services = sorted(service_counts.items(), key=lambda x: -x[1])
    service_breakdown = [
        ServiceBreakdownItem(
            service=service,
            percentage=round(service_revenue[service] / total_service_revenue * 100, 1),
            revenue=round(service_revenue[service], 2),
            color=_SERVICE_COLORS[i % len(_SERVICE_COLORS)],
        )
        for i, (service, _) in enumerate(sorted_services)
    ]

    # Recent activity
    quotes_recent = await db.execute(
        select(Quote.id, Quote.title, Quote.status, Quote.created_at)
        .where(Quote.tenant_id == tenant.id)
        .order_by(Quote.created_at.desc())
        .limit(10)
    )
    jobs_recent = await db.execute(
        select(Job.id, Job.title, Job.status, Job.created_at)
        .where(Job.tenant_id == tenant.id)
        .order_by(Job.created_at.desc())
        .limit(10)
    )
    invoices_recent = await db.execute(
        select(Invoice.id, Invoice.invoice_number, Invoice.status, Invoice.created_at)
        .where(Invoice.tenant_id == tenant.id)
        .order_by(Invoice.created_at.desc())
        .limit(10)
    )

    recent: list[Activity] = []
    for q_row in quotes_recent.all():
        q_type = "quote_sent" if q_row.status == "sent" else "quote_created"
        recent.append(
            Activity(
                id=q_row.id,
                type=q_type,
                title=f"Quote: {q_row.title}",
                description=f"Status: {q_row.status}",
                entity_type="quote",
                entity_id=q_row.id,
                created_at=q_row.created_at,
            )
        )
    for j_row in jobs_recent.all():
        j_type = {
            "scheduled": "job_scheduled",
            "in_progress": "job_started",
            "completed": "job_completed",
            "cancelled": "job_cancelled",
        }.get(j_row.status, "job_created")
        recent.append(
            Activity(
                id=j_row.id,
                type=j_type,
                title=f"Job: {j_row.title}",
                description=f"Status: {j_row.status}",
                entity_type="job",
                entity_id=j_row.id,
                created_at=j_row.created_at,
            )
        )
    for i_row in invoices_recent.all():
        i_type = {
            "draft": "invoice_created",
            "sent": "invoice_sent",
            "paid": "invoice_paid",
            "cancelled": "invoice_cancelled",
        }.get(i_row.status, "invoice_created")
        recent.append(
            Activity(
                id=i_row.id,
                type=i_type,
                title=f"Invoice {i_row.invoice_number}",
                description=f"Status: {i_row.status}",
                entity_type="invoice",
                entity_id=i_row.id,
                created_at=i_row.created_at,
            )
        )

    recent.sort(key=lambda x: x.created_at, reverse=True)
    recent = recent[:10]

    revenue_this_month = revenue_by_period.get("paid", 0.0)
    # Last month revenue requires filtering by date range; approximate using the
    # same paid-invoice total for the two-month window and subtracting this month.
    revenue_last_two_months = revenue_by_period.get("paid", 0.0)
    revenue_last_month = max(0.0, revenue_last_two_months - revenue_this_month)
    revenue_change = (
        round((revenue_this_month - revenue_last_month) / revenue_last_month * 100, 1)
        if revenue_last_month
        else 0.0
    )

    return DashboardData(
        kpi=DashboardKPIs(
            revenue_this_month=round(revenue_this_month, 2),
            revenue_change=revenue_change,
            active_jobs=active_jobs,
            jobs_capacity=20,
            pending_quotes=pending_quotes,
            pending_quotes_value=round(pending_quotes_value, 2),
            quotes_expiring_soon=quotes_expiring_soon,
            average_rating=average_rating,
            review_count=review_count,
            ai_generated_quotes=ai_generated_quotes,
            ai_time_saved_hours=ai_time_saved_hours,
        ),
        revenue_chart=RevenueChartData(
            labels=[label for _, label, _ in months],
            revenue=revenue_chart_values,
            target=target_values,
        ),
        service_breakdown=service_breakdown,
        recent_activity=recent,
        voice_stats=None,
    )


@router.get("/ai-insights")
async def ai_insights(tenant: TenantDep, db: DbDep) -> AIInsights:
    """Return AI-driven insights for quotes, demand forecast and voice activity."""
    await set_tenant_in_session(db, tenant.id)

    performance_result = await db.execute(
        select(Quote.status, func.count(Quote.id))
        .where(Quote.tenant_id == tenant.id)
        .group_by(Quote.status)
    )
    counts: dict[str, int] = dict.fromkeys(
        {"draft", "sent", "approved", "rejected", "invoiced", "cancelled"}, 0
    )
    for status, cnt in performance_result.all():
        counts[status] = cnt

    total_generated = sum(counts.values())
    total_sent = counts["sent"] + counts["approved"] + counts["rejected"] + counts["invoiced"]
    accepted = counts["approved"] + counts["invoiced"]
    acceptance_rate = (accepted / total_sent * 100) if total_sent else 0.0

    value_result = await db.execute(
        select(func.avg(Quote.total)).where(Quote.tenant_id == tenant.id)
    )
    average_value = _to_float(value_result.scalar())

    months = _last_6_months()

    # AI quote usage: quotes with at least one AI-generated line item, grouped
    # by month, plus acceptance (approved/invoiced) for those quotes.
    ai_monthly_result = await db.execute(
        select(
            func.to_char(Quote.created_at, "YYYY-MM").label("month"),
            func.count(func.distinct(Quote.id)).label("ai_quotes"),
            func.count(func.distinct(Quote.id))
            .filter(Quote.status.in_(["approved", "invoiced"]))
            .label("ai_accepted"),
        )
        .join(QuoteLineItem, QuoteLineItem.quote_id == Quote.id)
        .where(Quote.tenant_id == tenant.id, QuoteLineItem.ai_generated.is_(True))
        .group_by("month")
    )
    ai_by_month = {row.month: row for row in ai_monthly_result.all()}

    # extra_data payloads for AI-drafted quotes: generation timing and edit
    # feedback. The cohort is keyed on the ai_draft snapshot rather than the
    # per-line flag so a quote the electrician fully rewrote still counts
    # towards edit-rate metrics.
    ai_extra_result = await db.execute(
        select(Quote.extra_data)
        .where(Quote.tenant_id == tenant.id)
        .where(Quote.extra_data.has_key("ai_draft"))
    )
    ai_extras = [row for row in ai_extra_result.scalars().all() if isinstance(row, dict)]

    generation_times = [
        float(rag["generation_seconds"])
        for extra in ai_extras
        if isinstance(rag := extra.get("rag"), dict) and rag.get("generation_seconds") is not None
    ]
    average_generation_time = (
        round(sum(generation_times) / len(generation_times), 2) if generation_times else None
    )

    feedbacks = [
        feedback for extra in ai_extras if isinstance(feedback := extra.get("ai_feedback"), dict)
    ]
    edit_rate = (
        round(sum(1 for feedback in feedbacks if feedback.get("edited")) / len(feedbacks), 2)
        if feedbacks
        else None
    )
    price_drifts = [
        float(feedback["price_drift_pct"])
        for feedback in feedbacks
        if feedback.get("price_drift_pct") is not None
    ]
    avg_price_drift_pct = round(sum(price_drifts) / len(price_drifts), 2) if price_drifts else None

    # AI spend: token usage + estimated cost recorded per quote under
    # extra_data["rag"]["llm_usage"].
    llm_usages = [
        rag["llm_usage"]
        for extra in ai_extras
        if isinstance(rag := extra.get("rag"), dict) and isinstance(rag.get("llm_usage"), dict)
    ]
    ai_quotes_with_usage = len(llm_usages)
    ai_costs = [
        float(usage["est_cost_usd"])
        for usage in llm_usages
        if usage.get("est_cost_usd") is not None
    ]
    total_ai_cost_usd = round(sum(ai_costs), 6) if ai_costs else None

    monthly_data: list[AiQuotePerformanceMonthlyData] = []
    for _, label, key in months:
        month_result = await db.execute(
            select(func.count(Quote.id)).where(
                Quote.tenant_id == tenant.id,
                func.to_char(Quote.created_at, "YYYY-MM") == key,
            )
        )
        month_total = month_result.scalar() or 0
        ai_row = ai_by_month.get(key)
        month_ai = int(ai_row.ai_quotes) if ai_row else 0
        month_ai_accepted = int(ai_row.ai_accepted) if ai_row else 0
        monthly_data.append(
            AiQuotePerformanceMonthlyData(
                month=label,
                ai_quotes=month_ai,
                manual_quotes=month_total - month_ai,
                ai_acceptance=month_ai_accepted,
                manual_acceptance=month_total - month_ai,
            )
        )

    return AIInsights(
        ai_quote_performance=AiQuotePerformance(
            total_generated=total_generated,
            acceptance_rate=round(acceptance_rate, 1),
            average_value=round(average_value, 2),
            average_generation_time=average_generation_time,
            edit_rate=edit_rate,
            avg_price_drift_pct=avg_price_drift_pct,
            total_ai_cost_usd=total_ai_cost_usd,
            ai_quotes_with_usage=ai_quotes_with_usage,
            monthly_data=monthly_data,
        ),
        demand_forecast=None,
        voice_analytics=None,
    )
