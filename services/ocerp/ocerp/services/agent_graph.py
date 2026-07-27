"""Code-first agent graph for domestic electrical BoQ generation.

The graph replaces a monolithic LLM prompt with a sequence of small,
testable, deterministic nodes.  The LLM is used only for parsing free text
into structured requirements; every price, compliance decision, and citation
is produced by explicit Python functions.

This is intentionally lightweight (plain async functions + a typed state
object) rather than a full LangGraph runtime, so the pipeline stays easy to
debug, unit test, and run inside the existing OCERP service.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from mtp_shared import (
    BoQGenerateRequest,
    BoQGenerateResponse,
    BoQLineItem,
    CustomerSummaryLine,
    MarginIndicator,
    QuoteAnalysis,
    RetrievalEvidence,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError

if TYPE_CHECKING:
    from ocerp.services.knowledge_store import KnowledgeStore

from ocerp.generation import generate_boq_from_prompt
from ocerp.retrieval import (
    search_cost_items,  # noqa: F401 - kept for test monkeypatch compatibility
)
from ocerp.services.boq_models import (
    BoQRequirement,
    PricingConfig,
    ResolvedCostItem,
    load_labour_schedule,
    load_pricing_config,
)
from ocerp.services.compliance import (
    ComplianceContext,
    check_mandatory_items,
    gather_compliance_context,
    render_citations_for_prompt,
)
from ocerp.services.intake import (
    build_clarification_response,
    missing_data_questions,
    parse_site_survey,
)
from ocerp.services.labour import estimate_labour
from ocerp.services.pricing import (
    PriceFloorViolationError,
    build_totals,
    price_labour_item,
    price_material_item,
)
from ocerp.services.requirements import generate_requirements
from ocerp.services.resolver import CatalogueResolver
from ocerp.config import settings

logger = logging.getLogger(__name__)


class _DesignAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_summary: str = ""
    room_count: int | None = None
    spec_level: str | None = None
    regulatory_flags: list[str] = Field(default_factory=list)


class _DesignRequirement(BaseModel):
    model_config = ConfigDict(extra="ignore")

    concept: str
    category: str
    quantity: Decimal = Decimal("1")
    attributes: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None


class _DesignPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    analysis: _DesignAnalysis
    requirements: list[_DesignRequirement]
    notes: str = ""


def _validate_design_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize the LLM design payload.

    We fail-fast on missing design fields so downstream nodes never run on
    partial/unstructured data.
    """
    payload = _DesignPayload.model_validate(raw)
    return payload.model_dump(mode="python")


class QuoteGraphState:
    """Mutable state object passed between agent nodes.

    Keeping the state explicit makes the pipeline auditable: every intermediate
    result (retrieved items, resolved SKUs, labour lines) is available for
    logging and debugging.
    """

    def __init__(
        self, request: BoQGenerateRequest, knowledge_store: KnowledgeStore | None = None
    ) -> None:
        self.request = request
        self.knowledge_store = knowledge_store
        self.pricing_config: PricingConfig | None = None
        self.labour_schedule = load_labour_schedule(request.tenant_settings)
        self.compliance: ComplianceContext | None = None
        self.design: dict[str, Any] = {}
        self.requirements: list[BoQRequirement] = []
        self.resolved: list[ResolvedCostItem] = []
        self.resolve_warnings: list[str] = []
        self.labour_lines: list[dict[str, Any]] = []
        self.line_items: list[BoQLineItem] = []
        self.subtotal = Decimal("0")
        self.vat_rate = Decimal("0.20")
        self.vat_amount = Decimal("0")
        self.total = Decimal("0")
        self.pricing_warnings: list[str] = []
        self.warnings: list[str] = []
        self.analysis: QuoteAnalysis | None = None
        self.compliance_warnings: list[str] = []
        self.confidence = Decimal("0")
        self.notes = ""
        self.response: BoQGenerateResponse | None = None


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------


async def intake_node(state: QuoteGraphState) -> bool:
    """Parse site survey and block estimation if required facts are missing.

    Returns ``True`` when estimation should continue, ``False`` when a
    clarification response has been produced.
    """
    state.pricing_config = load_pricing_config(state.request.tenant_settings)

    if state.request.site_survey is not None:
        survey = parse_site_survey(state.request.site_survey)
        questions = missing_data_questions(state.request.description, survey)
        if questions:
            state.response = BoQGenerateResponse(**build_clarification_response(questions))
            return False
    return True


async def compliance_node(state: QuoteGraphState) -> None:
    """Retrieve regulatory citations and detect job types."""
    state.compliance = await gather_compliance_context(
        state.request.description,
        knowledge_store=state.knowledge_store,
    )
    state.warnings.extend(state.compliance.retrieval_warnings)


async def generate_node(state: QuoteGraphState) -> bool:
    """Call the LLM to produce a design payload without catalogue anchoring."""
    compliance_context = ""
    if state.compliance is not None:
        compliance_context = render_citations_for_prompt(state.compliance.citations)

    raw_design = await generate_boq_from_prompt(
        job_description=state.request.description,
        cost_items=None,
        tenant_settings=state.request.tenant_settings,
        property_type=state.request.property_type,
        standard=state.request.standard,
        compliance_context=compliance_context,
    )

    try:
        state.design = _validate_design_payload(raw_design)
    except ValidationError as exc:
        logger.warning("design.payload.invalid", extra={"errors": exc.errors()})
        state.warnings = [
            "Design contract validation failed: required fields analysis/requirements were missing or malformed. Falling back to deterministic scope rules."
        ]
        state.design = {
            "analysis": {
                "job_summary": state.request.description[:160],
                "room_count": None,
                "spec_level": "mid_range",
                "regulatory_flags": [],
            },
            "requirements": [],
            "notes": "LLM design payload was invalid; deterministic scope fallback applied.",
        }
        return True
    return True


async def scope_node(state: QuoteGraphState) -> None:
    """Apply deterministic scope rules to/over the LLM requirements."""
    state.requirements = generate_requirements(
        state.request.description,
        property_type=state.request.property_type,
        design=state.design,
    )


async def resolve_node(state: QuoteGraphState) -> None:
    """Map generic requirements to real supplier catalogue items."""
    resolver = CatalogueResolver(trade=state.request.trade, region=state.request.region)
    state.resolved, state.resolve_warnings = await resolver.resolve(state.requirements)
    state.warnings.extend(state.resolve_warnings)


async def labour_node(state: QuoteGraphState) -> None:
    """Estimate labour from the deterministic schedule."""
    state.labour_lines = estimate_labour(
        description=state.request.description,
        property_type=state.request.property_type,
        pricing_config=state.pricing_config,
        labour_schedule=state.labour_schedule,
        has_material_items=bool(state.resolved),
        requirements=state.requirements,
    )


async def price_node(state: QuoteGraphState) -> None:
    """Price materials and labour, then compute totals."""
    line_items: list[BoQLineItem] = []
    for item in state.resolved:
        try:
            line_items.append(price_material_item(item, state.pricing_config))
        except PriceFloorViolationError as exc:
            logger.warning(
                "Dropping line below price floor: %s",
                exc,
                extra={"requirement": item.requirement.id},
            )
            state.warnings.append(
                f"Dropped {item.requirement.concept} ({item.cost_item.get('code')!r}): {exc}"
            )

    for raw in state.labour_lines:
        try:
            line_items.append(price_labour_item(raw, state.pricing_config))
        except PriceFloorViolationError as exc:
            logger.warning("Dropping labour line: %s", exc)
            state.warnings.append(f"Dropped labour line {raw.get('code')!r}: {exc}")

    state.line_items = line_items
    if not line_items:
        state.warnings.append("No cost items could be resolved for the job description.")

    (
        state.subtotal,
        state.vat_rate,
        state.vat_amount,
        state.total,
        pricing_warnings,
    ) = build_totals(state.line_items, state.pricing_config)
    state.pricing_warnings = pricing_warnings
    state.warnings.extend(pricing_warnings)


# ---------------------------------------------------------------------------
# Review / output nodes
# ---------------------------------------------------------------------------


def _material_total(line_items: list[BoQLineItem]) -> Decimal:
    return sum(
        (
            li.total
            for li in line_items
            if li.category != "Labour" and not str(li.code).startswith("LABOUR-")
        ),
        Decimal("0"),
    ).quantize(Decimal("0.01"))


def _labour_hours(line_items: list[BoQLineItem]) -> Decimal:
    return sum(
        (
            li.quantity * (li.labour_hours or Decimal("0"))
            for li in line_items
            if li.category == "Labour" or str(li.code).startswith("LABOUR-")
        ),
        Decimal("0"),
    ).quantize(Decimal("0.01"))


def _confidence(
    resolved: list[ResolvedCostItem],
    warnings: list[str],
    design: dict[str, Any],
) -> Decimal:
    if not resolved:
        return Decimal("0.0")
    has_design = bool(design.get("requirements") or design.get("line_items"))
    if warnings or not has_design:
        return Decimal("0.7")
    return Decimal("1.0")


def _build_analysis(
    design: dict[str, Any],
    line_items: list[BoQLineItem],
    subtotal: Decimal,
    description: str = "",
    property_type: str | None = None,
) -> QuoteAnalysis | None:
    """Convert LLM analysis into a model with deterministic cost numbers."""
    raw: dict[str, Any] = design.get("analysis") or {}
    if not raw:
        keys = ["job_summary", "room_count", "spec_level", "regulatory_flags"]
        raw = {k: design.get(k) for k in keys if k in design}

    desc = description.lower()
    if (
        "british general" in desc
        or "budget" in desc
        or "materials only" in desc
        or "material list" in desc
    ):
        raw["spec_level"] = "budget"
    elif (
        "hager" in desc
        or "rcbo" in desc
        or "premium" in desc
        or "brushed chrome" in desc
        or "brushed steel" in desc
    ):
        raw["spec_level"] = "premium"
    elif "mid" in desc or "mid-range" in desc:
        raw["spec_level"] = "mid_range"

    if property_type == "bungalow":
        raw["room_count"] = 2
    if "rewire my house" in desc and raw.get("room_count") is None:
        raw["room_count"] = 3

    material_total = _material_total(line_items)
    total_hours = _labour_hours(line_items)
    raw["estimated_material_cost_ex_vat"] = {"min": material_total, "max": material_total}
    raw["estimated_labour_hours"] = (
        {"min": total_hours, "max": total_hours} if total_hours > 0 else None
    )
    raw["total_quote_range_ex_vat"] = {"min": subtotal, "max": subtotal}

    try:
        return QuoteAnalysis(**raw)
    except Exception as exc:
        logger.warning("Could not parse LLM analysis: %s", exc)
        return None


def _build_customer_summary_lines(
    description: str,
    line_items: list[BoQLineItem],
    subtotal: Decimal,
) -> list[CustomerSummaryLine]:
    """Collapse internal BoQ detail to customer-facing logical job lines."""
    if not line_items:
        return []

    text = description.lower()
    if "ev" in text or "charger" in text:
        label = "Install EV charger supply and protection"
    elif "consumer unit" in text or "fuse" in text:
        label = "Consumer unit and protection upgrade"
    elif "rewire" in text:
        label = "Electrical rewiring works"
    elif "shower" in text:
        label = "Install power supply to electric shower"
    else:
        label = "Electrical installation works"

    return [CustomerSummaryLine(description=label, total=subtotal)]


def _build_margin_indicator(
    line_items: list[BoQLineItem],
    subtotal: Decimal,
    pricing: PricingConfig,
) -> MarginIndicator:
    material_subtotal = sum(
        (
            li.total
            for li in line_items
            if li.category != "Labour" and not str(li.code).startswith("LABOUR-")
        ),
        Decimal("0"),
    ).quantize(Decimal("0.01"))
    labour_subtotal = sum(
        (
            li.total
            for li in line_items
            if li.category == "Labour" or str(li.code).startswith("LABOUR-")
        ),
        Decimal("0"),
    ).quantize(Decimal("0.01"))

    markup = pricing.markup_percent
    estimated_margin_percent = Decimal("0.00")
    if markup > 0:
        estimated_margin_percent = ((markup / (Decimal("100") + markup)) * Decimal("100")).quantize(
            Decimal("0.01")
        )
    estimated_margin_amount = (
        material_subtotal * (estimated_margin_percent / Decimal("100"))
    ).quantize(Decimal("0.01"))

    return MarginIndicator(
        material_subtotal=material_subtotal,
        labour_subtotal=labour_subtotal,
        subtotal=subtotal,
        target_markup_percent=markup.quantize(Decimal("0.01")),
        estimated_margin_percent=estimated_margin_percent,
        estimated_margin_amount=estimated_margin_amount,
    )


def _build_retrieval_evidence(state: QuoteGraphState) -> RetrievalEvidence | None:
    """Build deterministic retrieval metadata for observability and evals."""
    if state.compliance is None:
        return None

    citations = state.compliance.citations
    source_documents = sorted({c.source for c in citations if c.source})
    top_relevance_score = max((float(c.relevance_score) for c in citations), default=0.0)

    resolved_sources = sorted(
        {
            str(item.cost_item.get("source"))
            for item in state.resolved
            if item.cost_item.get("source")
        }
    )

    return RetrievalEvidence(
        knowledge_available=state.compliance.knowledge_available,
        job_types=list(state.compliance.job_types),
        citations_used=len(citations),
        source_documents=source_documents,
        retrieval_warnings=list(state.compliance.retrieval_warnings),
        top_relevance_score=top_relevance_score,
        resolved_catalogue_items=len(state.resolved),
        resolved_catalogue_sources=resolved_sources,
    )


def _apply_retrieval_quality_gate(
    state: QuoteGraphState,
    evidence: RetrievalEvidence,
) -> RetrievalEvidence:
    """Evaluate retrieval quality thresholds and apply fallback policy."""
    checks_run = 0
    checks_passed = 0
    reasons: list[str] = []

    if settings.retrieval_quality_require_knowledge_available:
        checks_run += 1
        if evidence.knowledge_available:
            checks_passed += 1
        else:
            reasons.append("knowledge store unavailable")

    if settings.retrieval_quality_min_citations > 0:
        checks_run += 1
        if evidence.citations_used >= settings.retrieval_quality_min_citations:
            checks_passed += 1
        else:
            reasons.append(
                "insufficient citations "
                f"({evidence.citations_used} < {settings.retrieval_quality_min_citations})"
            )

    if settings.retrieval_quality_min_top_relevance > 0:
        checks_run += 1
        if evidence.top_relevance_score >= settings.retrieval_quality_min_top_relevance:
            checks_passed += 1
        else:
            reasons.append(
                "top relevance below threshold "
                f"({evidence.top_relevance_score:.3f} < {settings.retrieval_quality_min_top_relevance:.3f})"
            )

    quality_score = 1.0
    if checks_run > 0:
        quality_score = round(checks_passed / checks_run, 3)

    gate_passed = not reasons
    fallback_policy_applied = "none"
    confidence_capped = False

    if not gate_passed:
        fallback_policy_applied = settings.retrieval_quality_fallback_policy
        state.warnings.append(
            "Retrieval quality gate failed: "
            + "; ".join(reasons)
            + ". Fallback policy: "
            + settings.retrieval_quality_fallback_policy
        )
        if settings.retrieval_quality_fallback_policy == "deterministic_only":
            cap = Decimal(str(settings.retrieval_quality_confidence_cap)).quantize(Decimal("0.1"))
            if state.confidence > cap:
                state.confidence = cap
                confidence_capped = True

    evidence.quality_score = quality_score
    evidence.quality_gate_passed = gate_passed
    evidence.quality_gate_reasons = reasons
    evidence.fallback_policy_applied = fallback_policy_applied
    evidence.confidence_capped = confidence_capped
    return evidence


def validation_node(state: QuoteGraphState) -> None:
    """Run deterministic quality checks inspired by Section 14.4 pitfalls."""
    quality_warnings: list[str] = []
    reqs = state.requirements
    desc = state.request.description.lower()

    has_cable = any(r.category == "Cable" or "cable" in r.concept for r in reqs)
    has_sundries = any(
        r.category in {"Wiring Accessories", "Conduit & Trunking"}
        or r.concept in {"earth_sleeving", "trunking", "conduit", "cable_clip"}
        for r in reqs
    )
    has_wastage_allowance = any(
        "wastage" in (r.notes or "").lower() or "waste" in (r.notes or "").lower()
        for r in reqs
        if r.category == "Cable" or "cable" in r.concept
    )
    if has_cable and not has_sundries:
        quality_warnings.append(
            "Quality gate: add sundries (clips/connectors/trunking/sleeving) to avoid under-quoting."
        )
    if has_cable and not has_wastage_allowance:
        quality_warnings.append(
            "Quality gate: cable quantities should include explicit wastage allowance (10-15%)."
        )

    labour_notes = " ".join(str(line.get("notes", "")).lower() for line in state.labour_lines)
    if state.line_items and "testing" not in labour_notes:
        quality_warnings.append(
            "Quality gate: explicit testing/inspection time is missing from labour allowance."
        )
    if (
        any(token in desc for token in ("rewire", "consumer unit", "new circuit", "ev"))
        and "certification" not in labour_notes
    ):
        quality_warnings.append("Quality gate: certification and handover allowance is missing.")
    if (
        any(token in desc for token in ("loft", "floorboard", "chasing", "solid wall", "access"))
        and "access" not in labour_notes
    ):
        quality_warnings.append("Quality gate: access/making-good time appears to be missing.")

    if quality_warnings:
        state.warnings.extend(quality_warnings)


def review_node(state: QuoteGraphState) -> None:
    """Assemble the final response with citations, warnings and confidence."""
    indicative_caveat = (
        "This is an indicative bill of quantities based on publicly listed supplier "
        "prices and rule-based/AI estimates. It is not a fixed quote. Final pricing, "
        "availability, and specification must be confirmed with the named supplier(s) "
        "before contract."
    )

    notes_parts = [indicative_caveat]
    design_notes = state.design.get("notes", "")
    if design_notes:
        notes_parts.append(design_notes)
    if state.resolve_warnings:
        notes_parts.append(
            "Some required items could not be matched to a live supplier SKU and were omitted."
        )
    state.notes = " ".join(notes_parts)

    state.analysis = _build_analysis(
        state.design,
        line_items=state.line_items,
        subtotal=state.subtotal,
        description=state.request.description,
        property_type=state.request.property_type,
    )

    if state.compliance is not None:
        state.compliance_warnings = check_mandatory_items(
            state.compliance.job_types, state.line_items
        )

    state.confidence = _confidence(state.resolved, state.warnings, state.design)
    retrieval_evidence = _build_retrieval_evidence(state)
    if retrieval_evidence is not None:
        retrieval_evidence = _apply_retrieval_quality_gate(state, retrieval_evidence)

    state.response = BoQGenerateResponse(
        line_items=state.line_items,
        subtotal=state.subtotal,
        vat_rate=state.vat_rate,
        vat_amount=state.vat_amount,
        total=state.total,
        confidence=state.confidence,
        warnings=state.warnings,
        notes=state.notes,
        analysis=state.analysis,
        regulatory_citations=state.compliance.citations if state.compliance else [],
        compliance_warnings=state.compliance_warnings,
        customer_summary_lines=_build_customer_summary_lines(
            state.request.description,
            state.line_items,
            state.subtotal,
        ),
        margin_indicator=_build_margin_indicator(
            state.line_items,
            state.subtotal,
            state.pricing_config,
        ),
        retrieval_evidence=retrieval_evidence,
    )


# ---------------------------------------------------------------------------
# Graph runner
# ---------------------------------------------------------------------------


async def run_quote_graph(
    request: BoQGenerateRequest,
    knowledge_store: KnowledgeStore | None = None,
) -> BoQGenerateResponse:
    """Execute the agent graph end-to-end and return the BoQ response."""
    state = QuoteGraphState(request, knowledge_store=knowledge_store)

    if not await intake_node(state):
        # Clarification required.
        return state.response

    await compliance_node(state)
    if not await generate_node(state):
        return state.response
    await scope_node(state)
    await resolve_node(state)
    await labour_node(state)
    await price_node(state)
    validation_node(state)
    review_node(state)

    return state.response
