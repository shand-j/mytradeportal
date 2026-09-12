"""AI draft quality: feedback capture + keep-rate computation (W1-B).

Lifecycle of one ``ai_draft_feedback`` row:

1. **Capture** — :func:`capture_draft_feedback` runs wherever the router
   snapshots the AI draft (generate / refine / requote, i.e. every
   ``_snapshot_ai_draft`` call site). It links the row to the generation via
   ``ai_metadata.last_event_id`` + ``trace_id`` and stores the draft snapshot.
   A quote has at most one OPEN row (``final_snapshot IS NULL``): a
   regeneration updates the open row in place so the final comparison always
   uses the LATEST AI draft.
2. **Finalise** — :func:`finalize_draft_feedback` runs from ``send_quote`` and
   writes the at-send line items as ``final_snapshot``.
3. **Compute** — :func:`compute_draft_quality` (a ``BackgroundTasks`` worker
   fired by ``send_quote``) derives the metrics in place. Idempotent:
   recompute overwrites, never duplicates.

Matching algorithm (:func:`compute_quality_metrics`, pure + stdlib-only):

* Descriptions are normalised (casefold + whitespace collapse).
* Phase 1 — exact match on the normalised description (greedy, first-come so
  duplicated lines pair up one-to-one). An exact pair whose quantity AND unit
  price are both unchanged counts toward ``keep_rate``; one whose price or
  quantity moved counts as a matched-but-edited line (drift only).
* Phase 2 — for the remaining lines, all pairwise ``difflib.SequenceMatcher``
  ratios are computed and pairs with ratio ≥ 0.85 are assigned greedily,
  best-ratio first. These count as ``description_rewrites``.
* Unmatched draft lines → ``lines_removed``; unmatched final lines →
  ``lines_added``.

Metric semantics:

* ``keep_rate`` = unchanged AI lines / total AI draft lines (0.000-1.000).
* ``price_drift_pct`` = (sum matched final line totals - sum matched draft
  line totals) / sum matched draft line totals x 100. Only matched pairs
  count, so added/removed lines never distort it; ``None`` when nothing
  matched or the matched draft total is zero.

Both capture helpers are fail-open (SAVEPOINT + swallow-and-log, mirroring
``app.ai_telemetry.record_ai_event``): quality telemetry must never break the
customer-facing quote flow. The coarse ``extra_data["ai_feedback"]`` blob is
still maintained by the router for one release — this table is the source of
truth going forward.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select

from app.ai_telemetry import get_last_event_id
from app.database import get_db_session
from app.models import AiDraftFeedback
from app.rls import set_tenant_in_session

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models import Quote

logger = structlog.get_logger("api.ai_quality")

FUZZY_MATCH_THRESHOLD = 0.85
_KEEP_RATE_QUANTUM = Decimal("0.001")
_PCT_QUANTUM = Decimal("0.01")


def snapshot_line_items(quote: Quote) -> dict[str, Any]:
    """Serialise a quote's current line items (same shape as ``extra_data["ai_draft"]``)."""
    return {
        "line_items": [
            {
                "description": item.description,
                "quantity": str(item.quantity),
                "unit_price": str(item.unit_price),
            }
            for item in quote.line_items
        ],
        "total": str(quote.total),
    }


async def _find_open_feedback(db: AsyncSession, quote_id: UUID) -> AiDraftFeedback | None:
    """Return the quote's open (not yet finalised) feedback row, if any."""
    result = await db.execute(
        select(AiDraftFeedback)
        .where(
            AiDraftFeedback.quote_id == quote_id,
            AiDraftFeedback.final_snapshot.is_(None),
        )
        .order_by(AiDraftFeedback.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def capture_draft_feedback(db: AsyncSession, quote: Quote) -> UUID | None:
    """Record the AI draft snapshot on a feedback row. Fail-open.

    Call right after ``_snapshot_ai_draft`` at every generation point. Reuses
    the quote's open row when one exists (a regeneration replaces the pending
    draft) so a quote carries at most one open row; otherwise inserts a new
    one. Returns the feedback row id, or ``None`` when there is no draft
    snapshot or the write failed.
    """
    draft = (quote.extra_data or {}).get("ai_draft")
    if not isinstance(draft, dict):
        return None
    trace_id = (quote.ai_metadata or {}).get("trace_id")
    try:
        # SAVEPOINT: a failed feedback write rolls back only itself, so the
        # caller's business transaction can still commit.
        async with db.begin_nested():
            row = await _find_open_feedback(db, quote.id)
            if row is None:
                row = AiDraftFeedback(tenant_id=quote.tenant_id, quote_id=quote.id)
                db.add(row)
            row.generation_event_id = get_last_event_id(quote)
            row.trace_id = str(trace_id) if trace_id else None
            row.draft_snapshot = draft
            await db.flush()
        return row.id
    except Exception as exc:  # fail-open, mirrors record_ai_event discipline
        logger.warning(
            "ai_quality.capture_failed",
            quote_id=str(quote.id),
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
        return None


async def finalize_draft_feedback(db: AsyncSession, quote: Quote) -> UUID | None:
    """Write the at-send line items as ``final_snapshot`` on the open row.

    Returns the feedback row id so the caller can schedule
    :func:`compute_draft_quality`, or ``None`` when the quote has no open
    feedback row (manual quotes have no AI draft to compare). Fail-open.
    """
    try:
        async with db.begin_nested():
            row = await _find_open_feedback(db, quote.id)
            if row is None:
                return None
            row.final_snapshot = snapshot_line_items(quote)
            await db.flush()
        return row.id
    except Exception as exc:  # fail-open: never break the send
        logger.warning(
            "ai_quality.finalize_failed",
            quote_id=str(quote.id),
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
        return None


@dataclass
class _Line:
    """One snapshot line item, parsed for matching."""

    qty: Decimal
    price: Decimal
    norm: str


def _normalise(description: Any) -> str:
    """Casefold + whitespace-collapse a line description for matching."""
    return " ".join(str(description).strip().lower().split())


def _parse_lines(snapshot: dict[str, Any]) -> list[_Line]:
    lines: list[_Line] = []
    for raw in snapshot.get("line_items") or []:
        if not isinstance(raw, dict):
            continue
        try:
            qty = Decimal(str(raw.get("quantity", "0") or "0"))
            price = Decimal(str(raw.get("unit_price", "0") or "0"))
        except InvalidOperation:
            continue
        lines.append(_Line(qty=qty, price=price, norm=_normalise(raw.get("description", ""))))
    return lines


def compute_quality_metrics(
    draft_snapshot: dict[str, Any], final_snapshot: dict[str, Any]
) -> dict[str, Any]:
    """Derive keep-rate metrics from a draft/final snapshot pair. Pure."""
    drafts = _parse_lines(draft_snapshot)
    finals = _parse_lines(final_snapshot)

    matched_draft: set[int] = set()
    matched_final: set[int] = set()
    pairs: list[tuple[int, int]] = []
    unchanged = 0

    # Phase 1: exact normalised-description matches (greedy, first-come).
    draft_by_norm: dict[str, list[int]] = {}
    for i, line in enumerate(drafts):
        draft_by_norm.setdefault(line.norm, []).append(i)
    for j, final in enumerate(finals):
        bucket = draft_by_norm.get(final.norm)
        if not bucket:
            continue
        i = bucket.pop(0)
        matched_draft.add(i)
        matched_final.add(j)
        pairs.append((i, j))
        if drafts[i].qty == final.qty and drafts[i].price == final.price:
            unchanged += 1

    # Phase 2: fuzzy matches on the leftovers, best ratio first.
    candidates: list[tuple[float, int, int]] = []
    for i, draft in enumerate(drafts):
        if i in matched_draft:
            continue
        for j, final in enumerate(finals):
            if j in matched_final:
                continue
            ratio = SequenceMatcher(None, draft.norm, final.norm).ratio()
            if ratio >= FUZZY_MATCH_THRESHOLD:
                candidates.append((ratio, i, j))
    candidates.sort(key=lambda candidate: candidate[0], reverse=True)
    rewrites = 0
    for _ratio, i, j in candidates:
        if i in matched_draft or j in matched_final:
            continue
        matched_draft.add(i)
        matched_final.add(j)
        pairs.append((i, j))
        rewrites += 1

    total_draft = len(drafts)
    keep_rate: Decimal | None = None
    if total_draft:
        keep_rate = (Decimal(unchanged) / Decimal(total_draft)).quantize(_KEEP_RATE_QUANTUM)

    price_drift_pct: Decimal | None = None
    if pairs:
        draft_sum = sum((drafts[i].qty * drafts[i].price for i, _j in pairs), Decimal("0"))
        final_sum = sum((finals[j].qty * finals[j].price for _i, j in pairs), Decimal("0"))
        if draft_sum != 0:
            price_drift_pct = ((final_sum - draft_sum) / draft_sum * 100).quantize(_PCT_QUANTUM)

    return {
        "keep_rate": keep_rate,
        "price_drift_pct": price_drift_pct,
        "lines_added": len(finals) - len(matched_final),
        "lines_removed": len(drafts) - len(matched_draft),
        "description_rewrites": rewrites,
    }


async def compute_draft_quality(feedback_id: UUID, tenant_id: UUID) -> None:
    """BackgroundTasks worker: compute keep-rate metrics for one feedback row.

    Opens its own session (``get_db_session`` pattern) with the tenant's RLS
    context, reads the finalised snapshots and overwrites the metric columns
    in place — recompute is idempotent and never duplicates rows. Fail-open:
    every failure is logged and swallowed so a quality-telemetry problem never
    surfaces to the send flow that scheduled it.
    """
    try:
        async with get_db_session() as db:
            await set_tenant_in_session(db, tenant_id)
            row = await db.get(AiDraftFeedback, feedback_id)
            if row is None:
                logger.info("ai_quality.feedback_missing", feedback_id=str(feedback_id))
                return
            if not isinstance(row.draft_snapshot, dict) or not isinstance(row.final_snapshot, dict):
                logger.info("ai_quality.snapshots_incomplete", feedback_id=str(feedback_id))
                return
            metrics = compute_quality_metrics(row.draft_snapshot, row.final_snapshot)
            row.keep_rate = metrics["keep_rate"]
            row.price_drift_pct = metrics["price_drift_pct"]
            row.lines_added = metrics["lines_added"]
            row.lines_removed = metrics["lines_removed"]
            row.description_rewrites = metrics["description_rewrites"]
            row.computed_at = datetime.utcnow()
            await db.flush()
        logger.info(
            "ai_quality.computed",
            feedback_id=str(feedback_id),
            keep_rate=str(metrics["keep_rate"]),
            price_drift_pct=str(metrics["price_drift_pct"]),
        )
    except Exception as exc:  # fail-open
        logger.warning(
            "ai_quality.compute_failed",
            feedback_id=str(feedback_id),
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
