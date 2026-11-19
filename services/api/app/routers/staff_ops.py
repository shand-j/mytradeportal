"""Staff ops endpoints — platform-level, cross-tenant.

These endpoints serve the internal operations/back-office surface, not any
tenant's dashboard. There is no tenant-scoped role that can authorise them
(a tenant ``admin`` must never see other orgs' costs), so every route here
gates on :data:`PlatformStaffDep` — an authenticated active user whose email
is in the ``PLATFORM_STAFF_EMAILS`` env allowlist (see
:func:`app.dependencies.get_current_platform_staff` for the rationale).

``GET /staff/ops/ai-costs`` is the per-organisation AI cost leaderboard from
PRD §4.3: current-calendar-month rollup rows per org (cost, generations,
keep-rate, latency p50/p95/p99) plus cohort p50/p95/p99 stats across orgs.
"""

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import DbDep, PlatformStaffDep
from app.limiter import limiter
from app.models import AiRollupOrgDay, Tenant
from app.scheduler import _percentile

router = APIRouter(prefix="/staff/ops", tags=["staff-ops"])

# Monthly latency rollups approximate each org's month-level percentile as the
# generation-weighted mean of its daily percentiles: the day rollups store
# percentiles but not the underlying sample counts, so an exact re-aggregation
# would require scanning ai_call_events (which the PRD reserves for the fold,
# not dashboards). Across many days with similar latency this converges to the
# true value; the daily drill-down in the admin stays exact.


def _weighted_daily_latency(days: list[AiRollupOrgDay], attr: str) -> float | None:
    """Generation-weighted mean of a daily latency percentile (None if no data)."""
    total_weight = 0
    acc = 0.0
    for row in days:
        value = getattr(row, attr)
        if value is None:
            continue
        weight = max(row.generations, 1)
        total_weight += weight
        acc += value * weight
    if total_weight == 0:
        return None
    return acc / total_weight


async def _month_org_days(db: AsyncSession, month_start: date) -> dict[UUID, list[AiRollupOrgDay]]:
    """All org-day rollup rows for the current month, grouped by tenant."""
    rows = (
        (
            await db.execute(
                select(AiRollupOrgDay)
                .where(AiRollupOrgDay.date >= month_start)
                .order_by(AiRollupOrgDay.date)
            )
        )
        .scalars()
        .all()
    )
    grouped: dict[UUID, list[AiRollupOrgDay]] = defaultdict(list)
    for row in rows:
        grouped[row.tenant_id].append(row)
    return grouped


def _org_entry(
    tenant_id: UUID,
    tenant_names: dict[UUID, tuple[str | None, str | None]],
    days: list[AiRollupOrgDay],
) -> dict[str, Any]:
    """Aggregate one org's month of daily rollup rows into a leaderboard entry."""
    slug, name = tenant_names.get(tenant_id, (None, None))
    keep_rates = [row.avg_keep_rate for row in days if row.avg_keep_rate is not None]
    return {
        "tenant_id": str(tenant_id),
        "slug": slug,
        "name": name,
        # Sum of daily distinct users (a user active N days counts N times).
        "users_active": sum(row.users_active for row in days),
        "generations": sum(row.generations for row in days),
        "retries": sum(row.retries for row in days),
        "tokens_input": sum(row.tokens_input for row in days),
        "tokens_output": sum(row.tokens_output for row in days),
        "tokens_cached": sum(row.tokens_cached for row in days),
        "est_cost_usd": float(sum((row.est_cost_usd for row in days), Decimal("0"))),
        "cost_gbp": float(sum((row.cost_gbp for row in days), Decimal("0"))),
        "keep_rate": float(sum(keep_rates, Decimal("0")) / len(keep_rates)) if keep_rates else None,
        "quotes_sent": sum(row.quotes_sent for row in days),
        "latency_p50": _weighted_daily_latency(days, "latency_p50"),
        "latency_p95": _weighted_daily_latency(days, "latency_p95"),
        "latency_p99": _weighted_daily_latency(days, "latency_p99"),
    }


def _cohort_stats(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """p50/p95/p99 across orgs of monthly cost and of per-org latency p99."""
    costs = sorted(entry["cost_gbp"] for entry in entries)
    latencies = sorted(
        entry["latency_p99"] for entry in entries if entry["latency_p99"] is not None
    )
    return {
        "orgs": len(entries),
        "cost_gbp": {
            "p50": _percentile(costs, 50),
            "p95": _percentile(costs, 95),
            "p99": _percentile(costs, 99),
        },
        "latency_p99": {
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
            "p99": _percentile(latencies, 99),
        },
    }


@router.get("/ai-costs")
@limiter.limit("30/minute")
async def ai_cost_leaderboard(
    request: Request,
    staff: PlatformStaffDep,
    db: DbDep,
) -> dict[str, Any]:
    """Per-org AI cost leaderboard for the current UTC month + cohort stats.

    Staff-only (platform-staff allowlist). Reads ``ai_rollup_org_day`` — the
    nightly fold — never the raw event table.
    """
    now = datetime.utcnow()
    month_start = date(now.year, now.month, 1)
    grouped = await _month_org_days(db, month_start)

    tenant_ids = list(grouped)
    tenant_names: dict[UUID, tuple[str | None, str | None]] = {}
    if tenant_ids:
        tenants = (
            (await db.execute(select(Tenant).where(Tenant.id.in_(tenant_ids)))).scalars().all()
        )
        tenant_names = {t.id: (t.slug, t.name) for t in tenants}

    leaderboard = [_org_entry(tenant_id, tenant_names, days) for tenant_id, days in grouped.items()]
    leaderboard.sort(key=lambda entry: entry["cost_gbp"], reverse=True)

    return {
        "period": f"{now.year:04d}-{now.month:02d}",
        "month_start": month_start.isoformat(),
        "leaderboard": leaderboard,
        "cohort": _cohort_stats(leaderboard),
    }
