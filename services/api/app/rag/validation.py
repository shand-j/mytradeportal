"""Validation and confidence scoring for AI-generated quote drafts."""

import re
from decimal import Decimal
from typing import Any

from app.calculations import calculate_quote_totals
from app.models import Quote, QuoteLineItem

QUOTE_LINE_STYLE_ITEMISED = "itemised"
QUOTE_LINE_STYLE_JOB_SUMMARY = "job_summary"


def resolve_quote_line_style(tenant_settings: dict[str, Any] | None) -> str:
    """Read the tenant's preferred AI quote line style from tenant settings.

    ``job_summary`` asks the LLM for one plain-English line per task (e.g.
    "Install a double socket in the bedroom") instead of the default
    ``itemised`` labour/materials breakdown. Unknown or missing values fall
    back to ``itemised`` so existing tenants are unaffected.
    """
    raw = str((tenant_settings or {}).get("quote_line_style", "") or "").strip().lower()
    if raw == QUOTE_LINE_STYLE_JOB_SUMMARY:
        return QUOTE_LINE_STYLE_JOB_SUMMARY
    return QUOTE_LINE_STYLE_ITEMISED


# Plausible per-unit price ranges (ex-VAT GBP) used to clamp obvious LLM
# pricing mistakes before the electrician sees the draft. Labour is split by
# unit: hourly rates sit in a much tighter band than fixed per-job pricing.
_DEFAULT_PRICE_RANGE = (Decimal("0.5"), Decimal("10000"))
_PRICE_RANGES: dict[str, tuple[Decimal, Decimal]] = {
    "labour_hour": (Decimal("25"), Decimal("200")),
    "labour_job": (Decimal("50"), Decimal("10000")),
    "material": (Decimal("0.5"), Decimal("5000")),
    "callout": (Decimal("0"), Decimal("300")),
}

# Tokens that carry no matching signal on their own. Kept aligned with
# ``app.rag.retrieval._LEXICAL_STOPWORDS`` — the two need not be identical but
# should broadly agree on what "meaningful" means.
_AUTO_GROUND_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "for",
        "on",
        "with",
        "install",
        "installation",
        "supply",
        "fit",
        "fitting",
        "new",
        "add",
        "replace",
        "replacement",
        "upgrade",
        "labour",
        "material",
        "each",
        "point",
        "per",
        "unit",
        "no",
        "one",
        "two",
        "three",
        "kw",
        "w",
        "v",
    }
)

# A retrieved item must cover at least this fraction of the LLM line's
# meaningful tokens to be considered a match. Calibrated by hand: 0.5 lets
# short lines like "Mains smoke alarm" match "[Security & Fire] Aico Ei146e
# Mains Interlinked Optical Smoke Alarm ..." (3 of 3 tokens present) but
# rejects "cable" alone matching every cable-adjacent item.
_AUTO_GROUND_MIN_SCORE = 0.5

# Lines shorter than this many meaningful tokens skip auto-grounding —
# single-word matches ("cable") are too permissive to be useful.
_AUTO_GROUND_MIN_LINE_TOKENS = 2


def _significant_tokens(text: str | None) -> set[str]:
    """Lowercase, strip punctuation, drop stopwords + short tokens."""
    if not text:
        return set()
    normalised = re.sub(r"[^a-z0-9²\s]+", " ", text.lower())
    return {tok for tok in normalised.split() if len(tok) > 1 and tok not in _AUTO_GROUND_STOPWORDS}


def _description_match_score(line_desc: str, item_desc: str | None) -> float:
    """Fraction of the line's meaningful tokens present in the item description."""
    line_tokens = _significant_tokens(line_desc)
    item_tokens = _significant_tokens(item_desc)
    if len(line_tokens) < _AUTO_GROUND_MIN_LINE_TOKENS or not item_tokens:
        return 0.0
    return len(line_tokens & item_tokens) / len(line_tokens)


def _auto_ground_line(
    line_desc: str,
    retrieved_items: list[dict[str, Any]],
) -> tuple[dict[str, Any], float] | None:
    """Return the best-matching catalogue item + score for a line description.

    Deterministic fallback for the LLM's "1-code-per-job" ceiling: when Kimi
    returns a material line without a ``code`` but the retrieval layer *did*
    return a close match, we attach the code server-side. Ties broken by the
    retrieval score so the top-K ranking is preserved.
    """
    best: tuple[dict[str, Any], float] | None = None
    for item in retrieved_items:
        score = _description_match_score(line_desc, item.get("description"))
        if score < _AUTO_GROUND_MIN_SCORE:
            continue
        if (
            best is None
            or score > best[1]
            or (score == best[1] and (item.get("score") or 0.0) > (best[0].get("score") or 0.0))
        ):
            best = (item, score)
    return best


def _price_range_for(kind: str | None, unit: str | None) -> tuple[Decimal, Decimal]:
    """Return the plausible (min, max) unit-price range for a line item."""
    if kind == "labour":
        return _PRICE_RANGES["labour_hour" if unit == "hour" else "labour_job"]
    return _PRICE_RANGES.get(kind or "", _DEFAULT_PRICE_RANGE)


def _clamp_price(
    description: str,
    kind: str | None,
    unit: str | None,
    unit_price: Decimal,
    warnings: list[str],
) -> Decimal:
    """Clamp a unit price into the plausible range, warning when adjusted."""
    low, high = _price_range_for(kind, unit)
    clamped = min(max(unit_price, low), high)
    if clamped != unit_price:
        warnings.append(
            f"Unit price for '{description}' adjusted from £{unit_price} to "
            f"£{clamped} (outside typical range)"
        )
    return clamped


# Billing units the prompts instruct (plus the mobile app's manual "item"),
# used by the line-validity confidence check.
_RECOGNISED_UNITS = frozenset({"hour", "day", "ea", "each", "m", "job", "point", "item"})

# Mechanical confidence rubric weights (must sum to 1.0). Every check is a
# deterministic, verifiable property of the validated draft — no model
# self-assessment, no priors that dominate the score.
_CONFIDENCE_WEIGHTS = {
    "line_validity": 0.30,
    "request_coverage": 0.25,
    "price_plausibility": 0.15,
    "catalogue_grounding": 0.15,
    "estimated_hours": 0.10,
    "intake_completeness": 0.05,
}

# Request-coverage fraction that earns full marks. Verbose briefs mention
# context (parking, wall construction, access) that legitimately never lands
# on a quote line, so 60% token coverage counts as fully covered.
_COVERAGE_FULL_MARKS = 0.6

# Penalty applied when the draft needed a minimum-charge adjustment line —
# pricing below the business's own minimum is a real quality signal.
_MIN_CHARGE_PENALTY = 0.05

# Assumed hours per "day"-billed line for the duration cross-check.
_DAY_UNIT_HOURS = 8.0


def _mechanical_confidence(
    lines: list[dict[str, Any]],
    *,
    job_summary: bool,
    estimated_hours_raw: Any,
    job_description: str | None,
    completeness: float | None,
    clamped_count: int,
    min_charge_applied: bool,
) -> tuple[float, list[dict[str, Any]]]:
    """Score a validated draft with a rubric of deterministic checks.

    Each check is mechanically verifiable from the draft itself — lines fully
    specified, prices inside plausible ranges without clamping, the request's
    own words covered by the line descriptions, materials grounded to real
    catalogue prices, a duration estimate that agrees with the time-billed
    lines, and how complete the customer's intake was. Returns the 0-1
    confidence plus a per-check breakdown (stored on the quote so the score
    is explainable, not a black box).
    """
    total = len(lines)
    checks: list[dict[str, Any]] = []

    def _record(name: str, score: float, detail: str) -> None:
        checks.append(
            {
                "check": name,
                "score": round(score, 2),
                "weight": _CONFIDENCE_WEIGHTS[name],
                "detail": detail,
            }
        )

    valid = sum(
        1
        for line in lines
        if len(str(line.get("description") or "").strip()) >= 4
        and str(line.get("description")).strip().lower() != "line item"
        and line.get("quantity") is not None
        and Decimal(str(line["quantity"])) > 0
        and Decimal(str(line.get("unit_price") or "0")) > 0
        and str(line.get("unit") or "").lower() in _RECOGNISED_UNITS
    )
    _record("line_validity", valid / total, f"{valid}/{total} lines fully specified")

    if job_description:
        tokens = _significant_tokens(job_description)
        haystack = " ".join(str(line.get("description") or "") for line in lines).lower()
        if len(tokens) < 2:
            _record("request_coverage", 1.0, "short request — nothing specific left to cover")
        else:
            hits = sum(1 for token in tokens if token in haystack)
            _record(
                "request_coverage",
                min(1.0, (hits / len(tokens)) / _COVERAGE_FULL_MARKS),
                f"{hits}/{len(tokens)} request terms appear in the line items",
            )
    else:
        _record("request_coverage", 0.5, "request text unavailable for coverage check")

    unclamped = total - clamped_count
    _record(
        "price_plausibility",
        unclamped / total,
        f"{unclamped}/{total} prices within typical range without adjustment",
    )

    if job_summary:
        # Job-summary lines deliberately carry no catalogue codes — their
        # whole-task prices cannot be verified against the catalogue, so the
        # check sits at neutral rather than pretending verification happened.
        _record("catalogue_grounding", 0.5, "not verifiable for plain-English job-summary lines")
    else:
        material_lines = [
            line for line in lines if line.get("kind") == "material" or line.get("code")
        ]
        if not material_lines:
            _record("catalogue_grounding", 1.0, "no material lines to ground")
        else:
            grounded = sum(1 for line in material_lines if line.get("code"))
            _record(
                "catalogue_grounding",
                grounded / len(material_lines),
                f"{grounded}/{len(material_lines)} material lines priced from the catalogue",
            )

    try:
        estimated_hours = float(estimated_hours_raw)
    except (TypeError, ValueError):
        estimated_hours = 0.0
    if estimated_hours <= 0:
        _record("estimated_hours", 0.0, "no duration estimate returned")
    else:
        billed = sum(
            float(line["quantity"]) for line in lines if str(line.get("unit")) == "hour"
        ) + _DAY_UNIT_HOURS * sum(
            float(line["quantity"]) for line in lines if str(line.get("unit")) == "day"
        )
        if billed > 0:
            drift = abs(estimated_hours - billed) / max(billed, 1.0)
            score = 1.0 if drift <= 0.4 else (0.6 if drift <= 0.75 else 0.3)
            _record(
                "estimated_hours",
                score,
                f"estimate {estimated_hours:g}h vs {billed:g}h across time-billed lines",
            )
        else:
            _record(
                "estimated_hours",
                0.8,
                f"{estimated_hours:g}h estimated; no time-billed lines to cross-check",
            )

    if completeness is not None:
        _record("intake_completeness", completeness, f"intake completeness {completeness:.0%}")
    else:
        _record("intake_completeness", 0.5, "intake completeness unknown")

    score = sum(check["score"] * check["weight"] for check in checks)
    if min_charge_applied:
        score -= _MIN_CHARGE_PENALTY
    return round(max(0.0, min(1.0, score)), 2), checks


def validate_generated_quote(
    generated: dict[str, Any],
    retrieved_items: list[dict[str, Any]],
    tenant_settings: dict[str, Any],
    completeness: float | None = None,
    retrieval_quality: dict[str, Any] | None = None,
    job_description: str | None = None,
) -> dict[str, Any]:
    """Assemble editable guide-priced line items from the LLM output.

    Every line item the model returns is kept — the electrician reviews and
    edits the draft. When a line references a catalogue ``code`` we ground its
    unit price against the retrieved supplier price; otherwise the model's own
    guide price is used. Prices are clamped to plausible per-kind ranges and
    the tenant's minimum charge is enforced with an adjustment line. Nothing
    is silently dropped.

    Confidence is mechanical: a weighted rubric of deterministic checks over
    the validated draft (see :func:`_mechanical_confidence`) — line validity,
    request coverage, price plausibility, catalogue grounding, duration
    estimate consistency, and intake completeness. The per-check breakdown is
    returned as ``confidence_checks`` so the score is explainable. No line
    items: 0.0.

    When ``retrieval_quality`` is supplied (from
    :func:`app.rag.retrieval.compute_retrieval_quality`) and its ``passes_gates``
    is False, confidence is capped at ``confidence_cap`` and a warning is
    added so the electrician knows the retrieval side was thin.

    Kimi habitually cites at most one catalogue code per job even when
    retrieval returns a good match for every material line. Uncited material
    lines are auto-grounded here: for each such line we fuzzy-match its
    description against the retrieved items (token overlap >= 0.5 on the
    line's meaningful tokens) and, when a match is found, attach the catalogue
    code and swap in the catalogue's ``unit_price``. The ``auto_grounded``
    counter in the return dict reports how many lines this deterministic
    fallback covered.

    Returns a dict with:
        - line_items: list of dicts ready for QuoteLineItem creation
        - line_style: the resolved quote line style (``itemised`` or ``job_summary``)
        - confidence: float 0-1
        - confidence_checks: per-check breakdown behind ``confidence``
        - warnings: list of human-readable warnings
        - assumptions: list of assumptions the model recorded
        - notes: LLM notes
        - confidence_capped: bool (True when the retrieval-quality gate applied a cap)
        - auto_grounded: int (material lines force-grounded via the fuzzy fallback)
        - labour_snapped: int (labour lines snapped to the tenant's configured hourly rate)
    """
    retrieved_by_code = {item["code"]: item for item in retrieved_items if item.get("code")}
    validated: list[dict[str, Any]] = []
    warnings: list[str] = []
    auto_grounded = 0
    labour_snapped = 0
    clamped_count = 0
    line_style = resolve_quote_line_style(tenant_settings)
    job_summary = line_style == QUOTE_LINE_STYLE_JOB_SUMMARY

    minimum_charge = Decimal(str(tenant_settings.get("minimum_charge", "0") or "0"))
    tenant_hourly_rate_raw = tenant_settings.get("hourly_labour_rate", "0") or "0"
    try:
        tenant_hourly_rate = Decimal(str(tenant_hourly_rate_raw))
    except (ArithmeticError, ValueError):
        tenant_hourly_rate = Decimal("0")

    for raw in generated.get("line_items", []):
        # ``or`` would swallow a genuine 0, so test explicitly for None.
        raw_quantity = raw.get("quantity")
        quantity = Decimal(str(raw_quantity)) if raw_quantity is not None else Decimal("1")
        code = raw.get("code")
        kind = raw.get("kind") if isinstance(raw.get("kind"), str) else None
        unit = raw.get("unit") if isinstance(raw.get("unit"), str) else None
        line_desc_raw = str(raw.get("description") or "Line item")

        if job_summary:
            # Job-summary style: every line is a plain-English task priced as a
            # whole. Catalogue grounding must not fire here — it would replace
            # the customer-friendly description with a supplier product name.
            description = line_desc_raw
            unit_price = Decimal(str(raw.get("unit_price", "0") or "0"))
            code = None
        elif code and code in retrieved_by_code:
            item = retrieved_by_code[code]
            description = item["description"]
            # The catalogue unit is authoritative for grounded lines (C6):
            # a line priced from the catalogue's per-unit price must bill in
            # the catalogue's unit (e.g. cable priced per metre bills in "m"),
            # never in whatever unit the LLM guessed.
            catalogue_unit = item.get("unit") if isinstance(item.get("unit"), str) else None
            unit = catalogue_unit or unit
            unit_price = Decimal(str(item.get("unit_price", "0") or "0"))
        elif kind == "material" and retrieved_items:
            # Kimi habitually cites at most one code per job. When a material
            # line is left ungrounded but a retrieved item covers >= 50% of the
            # line's meaningful tokens, force-attach the code and swap in the
            # catalogue's unit price — deterministic fallback for the LLM's
            # citation ceiling.
            match = _auto_ground_line(line_desc_raw, retrieved_items)
            if match is not None:
                item, _score = match
                code = item.get("code")
                description = line_desc_raw
                catalogue_unit = item.get("unit") if isinstance(item.get("unit"), str) else None
                unit = catalogue_unit or unit
                unit_price = Decimal(str(item.get("unit_price", "0") or "0"))
                auto_grounded += 1
            else:
                description = line_desc_raw
                unit_price = Decimal(str(raw.get("unit_price", "0") or "0"))
                if raw.get("code"):
                    warnings.append(
                        f"Guide price used for '{description}' "
                        f"(code {raw['code']} not in catalogue)"
                    )
        else:
            # Guide-priced line from the model's own knowledge.
            description = line_desc_raw
            unit_price = Decimal(str(raw.get("unit_price", "0") or "0"))
            if code:
                warnings.append(
                    f"Guide price used for '{description}' (code {code} not in catalogue)"
                )

        if quantity == 0:
            warnings.append(f"Zero quantity on '{description}'; kept for review")
        if unit_price == 0:
            warnings.append(f"Zero unit price on '{description}'; kept for review")
        # Anchor labour to the tenant's configured hourly rate — deterministic
        # override for the LLM's guessed labour price, which is the biggest
        # source of total-price run-to-run variance.
        if (
            kind == "labour"
            and unit == "hour"
            and tenant_hourly_rate > 0
            and unit_price != tenant_hourly_rate
        ):
            drift = abs(unit_price - tenant_hourly_rate) / tenant_hourly_rate
            if unit_price > 0 and drift > Decimal("0.20"):
                warnings.append(
                    f"Labour rate on '{description}' snapped from £{unit_price} to "
                    f"tenant rate £{tenant_hourly_rate}/hr (drift {drift:.0%})"
                )
            unit_price = tenant_hourly_rate
            labour_snapped += 1
        pre_clamp = unit_price
        unit_price = _clamp_price(description, kind, unit, unit_price, warnings)
        if unit_price != pre_clamp:
            clamped_count += 1

        validated.append(
            {
                "description": description,
                "quantity": quantity,
                "unit_price": unit_price,
                # Kept on the line so QuoteLineItem.unit is real, not the
                # client's old "job" default.
                "unit": unit or ("hour" if kind == "labour" else "ea"),
                "kind": kind,
                "code": code if code in retrieved_by_code else None,
                "reason": raw.get("reason", ""),
            }
        )

    subtotal = sum((line["quantity"] * line["unit_price"] for line in validated), Decimal("0"))
    min_charge_applied = False
    if minimum_charge and subtotal < minimum_charge and validated:
        min_charge_applied = True
        difference = minimum_charge - subtotal
        validated.append(
            {
                "description": "Minimum charge adjustment",
                "quantity": Decimal("1"),
                "unit_price": difference,
                "unit": "ea",
                "kind": None,
                "code": None,
                "reason": f"Raised to the tenant minimum charge of {minimum_charge}",
            }
        )
        warnings.append(
            f"Subtotal {subtotal} below minimum charge {minimum_charge}; "
            "a minimum-charge adjustment line item was added."
        )

    total = len(validated)
    if not total:
        confidence = 0.0
        confidence_checks: list[dict[str, Any]] = []
    else:
        confidence, confidence_checks = _mechanical_confidence(
            validated,
            job_summary=job_summary,
            estimated_hours_raw=generated.get("estimated_hours"),
            job_description=job_description,
            completeness=completeness,
            clamped_count=clamped_count,
            min_charge_applied=min_charge_applied,
        )

    confidence_capped = False
    if retrieval_quality is not None and not retrieval_quality.get("passes_gates", True) and total:
        cap = float(retrieval_quality.get("confidence_cap", confidence))
        if confidence > cap:
            confidence = round(cap, 2)
            confidence_capped = True
            reasons = []
            if not retrieval_quality.get("passes_min_citations", True):
                reasons.append(
                    f"only {retrieval_quality.get('citations', 0)} catalogue items retrieved"
                )
            if not retrieval_quality.get("passes_min_relevance", True):
                reasons.append(
                    f"top-relevance {retrieval_quality.get('top_relevance', 0)} below threshold"
                )
            if not retrieval_quality.get("passes_knowledge_requirement", True):
                reasons.append("knowledge base unavailable")
            reason = "; ".join(reasons) or "retrieval quality gate not met"
            warnings.append(f"Confidence capped at {cap} ({reason}).")

    return {
        "line_items": validated,
        "line_style": line_style,
        "confidence": confidence,
        "confidence_checks": confidence_checks,
        "confidence_capped": confidence_capped,
        "auto_grounded": auto_grounded,
        "labour_snapped": labour_snapped,
        "warnings": warnings,
        "assumptions": generated.get("assumptions", []) or [],
        "notes": generated.get("notes", ""),
    }


def build_quote_from_validation(
    quote: Quote,
    validation_result: dict[str, Any],
    retrieval_status: str | None = None,
) -> None:
    """Populate an existing Quote object with validated line items and totals."""
    for line in validation_result["line_items"]:
        quote.line_items.append(
            QuoteLineItem(
                tenant_id=quote.tenant_id,
                description=line["description"],
                quantity=line["quantity"],
                unit_price=line["unit_price"],
                unit=line.get("unit") or "ea",
                ai_generated=True,
            )
        )
    calculate_quote_totals(quote)
    if quote.extra_data is None:
        quote.extra_data = {}
    quote.extra_data["rag"] = {
        "line_style": validation_result.get("line_style"),
        "confidence": validation_result["confidence"],
        "confidence_checks": validation_result.get("confidence_checks") or [],
        "warnings": validation_result["warnings"],
        "assumptions": validation_result.get("assumptions", []),
        "notes": validation_result["notes"],
        "retrieval_status": retrieval_status,
    }
