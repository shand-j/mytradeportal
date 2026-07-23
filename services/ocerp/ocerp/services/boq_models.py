"""Internal data models for the requirements-driven BoQ engine.

These models are not exposed in the OCERP API; they are used inside
`boq_engine.py` and its helpers to separate requirement generation, catalogue
resolution, labour estimation, and pricing.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BoQRequirement(BaseModel):
    """A brandless, generic requirement for one or more cost items.

    Requirements are produced from the job description and then resolved to
    real catalogue items by the `CatalogueResolver`.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    concept: str
    category: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    quantity: Decimal = Decimal("1")
    scope_tag: str = "general"
    source: str = "mandatory"  # mandatory | llm | fallback
    notes: str | None = None

    @field_validator("quantity", mode="before")
    @classmethod
    def _validate_quantity(cls, value: Any) -> Decimal:
        if value is None:
            return Decimal("1")
        return Decimal(str(value))


class ResolvedCostItem(BaseModel):
    """A requirement that has been mapped to a real cost item."""

    model_config = ConfigDict(from_attributes=True)

    requirement: BoQRequirement
    cost_item: dict[str, Any]
    resolution_source: str  # domestic_pipeline | curated_seed
    score: float = 0.0


class PricingConfig(BaseModel):
    """Tenant-overridable pricing rules."""

    model_config = ConfigDict(from_attributes=True)

    hourly_labour_rate: Decimal = Decimal("45.00")
    daily_labour_rate: Decimal = Decimal("360.00")
    mate_daily_rate: Decimal = Decimal("0.00")
    mate_percent: Decimal = Decimal("55.00")
    vat_rate: Decimal = Decimal("0.20")
    markup_percent: Decimal = Decimal("0.00")
    minimum_charge: Decimal = Decimal("0.00")
    price_tolerance_percent: Decimal = Decimal("0.15")
    # Minimum required margin (as a percentage of catalogue cost) applied to
    # every material line. When greater than zero, items that would price
    # below this floor are dropped with a warning rather than shipped to the
    # customer. Default 0 (no enforcement) — operators MUST set this in
    # tenant settings for any production deployment that handles real money.
    min_margin_percent: Decimal = Decimal("0.00")

    @field_validator(
        "hourly_labour_rate",
        "daily_labour_rate",
        "mate_daily_rate",
        "mate_percent",
        "vat_rate",
        "markup_percent",
        "minimum_charge",
        "price_tolerance_percent",
        "min_margin_percent",
        mode="before",
    )
    @classmethod
    def _to_decimal(cls, value: Any) -> Decimal:
        if value is None:
            return Decimal("0")
        return Decimal(str(value))

    @property
    def mate_rate(self) -> Decimal:
        """Return the effective mate daily rate.

        If `mate_daily_rate` is explicit and positive, use it; otherwise derive
        it from `mate_percent` of the electrician daily rate.
        """
        if self.mate_daily_rate > 0:
            return self.mate_daily_rate
        return (self.daily_labour_rate * (self.mate_percent / Decimal("100"))).quantize(
            Decimal("0.01")
        )


class LabourEntry(BaseModel):
    """A single entry in the labour schedule."""

    model_config = ConfigDict(from_attributes=True)

    electrician_days: Decimal = Decimal("0")
    electrician_hours: Decimal = Decimal("0")
    mate_days: Decimal = Decimal("0")
    mate_hours: Decimal = Decimal("0")

    @field_validator(
        "electrician_days",
        "electrician_hours",
        "mate_days",
        "mate_hours",
        mode="before",
    )
    @classmethod
    def _to_decimal(cls, value: Any) -> Decimal:
        if value is None:
            return Decimal("0")
        return Decimal(str(value))


class LabourSchedule(BaseModel):
    """Configurable, scope-keyed labour schedule.

    The schedule is intentionally data-driven.  The engine reads a default JSON
    file and allows tenant settings to override individual keys.
    """

    model_config = ConfigDict(from_attributes=True, extra="allow")

    rewire: dict[str, LabourEntry] = Field(default_factory=dict)
    consumer_unit_upgrade: LabourEntry = Field(default_factory=LabourEntry)
    ev_charger: LabourEntry = Field(default_factory=LabourEntry)
    extension: LabourEntry = Field(default_factory=LabourEntry)
    garage: LabourEntry = Field(default_factory=LabourEntry)
    small_job_default: LabourEntry = Field(
        default_factory=lambda: LabourEntry(electrician_hours=Decimal("4"))
    )
    eicr: LabourEntry = Field(default_factory=lambda: LabourEntry(electrician_days=Decimal("1")))
    fault_finding: LabourEntry = Field(
        default_factory=lambda: LabourEntry(electrician_hours=Decimal("1"))
    )

    @field_validator("rewire", mode="before")
    @classmethod
    def _validate_rewire(cls, value: Any) -> dict[str, LabourEntry]:
        if not isinstance(value, dict):
            return {}
        return {k: LabourEntry.model_validate(v) for k, v in value.items()}

    @field_validator(
        "consumer_unit_upgrade",
        "ev_charger",
        "extension",
        "garage",
        "small_job_default",
        "eicr",
        "fault_finding",
        mode="before",
    )
    @classmethod
    def _validate_entry(cls, value: Any) -> LabourEntry:
        if isinstance(value, LabourEntry):
            return value
        return LabourEntry.model_validate(value or {})


def _data_file(name: str) -> Path:
    return Path(__file__).parent.parent / "data" / name


def _load_json_data(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open() as fh:
        return json.load(fh)


def _default_pricing_config() -> dict[str, Any]:
    return {
        "hourly_labour_rate": "45.00",
        "daily_labour_rate": "360.00",
        "mate_daily_rate": "0.00",
        "mate_percent": "55.00",
        "vat_rate": "0.20",
        "markup_percent": "0.00",
        "minimum_charge": "0.00",
        "price_tolerance_percent": "0.15",
        "min_margin_percent": "0.00",
    }


def _default_labour_schedule() -> dict[str, Any]:
    return {
        "rewire": {
            "1_bed_flat": {"electrician_days": "4", "mate_days": "2"},
            "2_bed_house": {"electrician_days": "5", "mate_days": "2"},
            "3_bed_house": {"electrician_days": "7", "mate_days": "3"},
            "4_bed_house": {"electrician_days": "9", "mate_days": "4"},
            "5_bed_house": {"electrician_days": "11", "mate_days": "4"},
        },
        "consumer_unit_upgrade": {"electrician_days": "1", "mate_days": "0"},
        "ev_charger": {"electrician_hours": "8"},
        "extension": {"electrician_days": "2", "mate_days": "1"},
        "garage": {"electrician_days": "1", "mate_days": "0"},
        "small_job_default": {"electrician_hours": "4"},
        "eicr": {"electrician_days": "1"},
        "fault_finding": {"electrician_hours": "1"},
    }


def load_pricing_config(tenant_settings: dict[str, Any] | None = None) -> PricingConfig:
    """Build pricing config from default data file, overridden by tenant settings."""
    defaults = _load_json_data(_data_file("default_pricing.json")) or _default_pricing_config()
    overrides = tenant_settings or {}
    # The API stores tenant markup under ``markup_percentage``; OCERP uses
    # ``markup_percent``.  Accept both for interoperability.
    if "markup_percentage" in overrides and "markup_percent" not in overrides:
        overrides["markup_percent"] = overrides["markup_percentage"]
    # Only accept known keys so random tenant data cannot break the model.
    data = {**defaults, **{k: v for k, v in overrides.items() if k in PricingConfig.model_fields}}
    return PricingConfig.model_validate(data)


def load_labour_schedule(tenant_settings: dict[str, Any] | None = None) -> LabourSchedule:
    """Build labour schedule from default data file, overridden by tenant settings."""
    defaults = (
        _load_json_data(_data_file("default_labour_schedule.json")) or _default_labour_schedule()
    )
    overrides = tenant_settings or {}
    data = {**defaults, **{k: v for k, v in overrides.items() if k in LabourSchedule.model_fields}}
    return LabourSchedule.model_validate(data)
