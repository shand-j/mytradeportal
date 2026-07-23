"""Labour estimation for the requirements-driven BoQ engine.

Labour is produced from tenant settings and a configurable labour schedule.
The engine no longer contains hard-coded day ranges or rates.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ocerp.services.boq_models import BoQRequirement, LabourSchedule, PricingConfig


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().strip())


def _extract_bedrooms(description: str) -> Decimal:
    text = _norm(description)
    for word, num in {
        "one bed": 1,
        "two bed": 2,
        "three bed": 3,
        "four bed": 4,
        "five bed": 5,
        "six bed": 6,
    }.items():
        if word in text:
            return Decimal(num)
    m = re.search(r"(\d+)\s*bed", text)
    if m:
        return Decimal(m.group(1))
    return Decimal("0")


def _is_rewire(description: str) -> bool:
    return bool(re.search(r"\brewire\b|\brewiring\b", _norm(description)))


def _is_cu_upgrade(description: str) -> bool:
    text = _norm(description)
    return bool(
        re.search(
            r"\b(new|upgrade|replace|changing|change)\s+(consumer unit|fuse box|fusebox|distribution board)\b",
            text,
        )
        or "consumer unit upgrade" in text
    )


def _is_ev(description: str) -> bool:
    text = _norm(description)
    return "ev" in text or "charger" in text or "charge point" in text


def _is_extension(description: str) -> bool:
    return "extension" in _norm(description)


def _is_garage(description: str) -> bool:
    return "garage" in _norm(description)


def _is_eicr(description: str) -> bool:
    text = _norm(description)
    return "eicr" in text or "condition report" in text


def _is_fault_finding(description: str) -> bool:
    text = _norm(description)
    return "fault" in text or "diagnostic" in text


def _no_labour(description: str) -> bool:
    text = _norm(description)
    return "no labour" in text or "materials only" in text or "material list" in text


def _access_hours(description: str) -> Decimal:
    text = _norm(description)
    hours = Decimal("0")
    if any(word in text for word in ("loft", "attic", "hatch")):
        hours += Decimal("1.0")
    if any(word in text for word in ("floorboard", "under floor", "underfloor")):
        hours += Decimal("1.0")
    if any(word in text for word in ("chase", "chasing", "solid wall", "making good")):
        hours += Decimal("1.5")
    return hours


def _to_day_and_hour_lines(total_hours: Decimal) -> tuple[Decimal, Decimal]:
    if total_hours <= 0:
        return Decimal("0"), Decimal("0")
    days = (total_hours // Decimal("8")).quantize(Decimal("0"))
    hours = (total_hours - (days * Decimal("8"))).quantize(Decimal("0.5"))
    if hours == Decimal("8.0"):
        days += Decimal("1")
        hours = Decimal("0")
    return days, hours


def _derived_hours_from_requirements(
    requirements: list[BoQRequirement],
) -> tuple[Decimal, Decimal, Decimal]:
    """Return install, testing and certification hours from BoQ requirements."""
    install = Decimal("0")
    cable_metres = Decimal("0")
    circuit_count = Decimal("0")

    for req in requirements:
        concept = req.concept
        qty = req.quantity
        if req.category == "Cable" or "cable" in concept:
            cable_metres += qty
            continue
        if concept in {"double_socket", "single_socket", "usb_socket"}:
            install += qty * Decimal("0.35")
            continue
        if concept in {"ceiling_light", "downlight", "spotlight", "batten_light"}:
            install += qty * Decimal("0.45")
            continue
        if concept in {"dimmer_switch", "cooker_switch"}:
            install += qty * Decimal("0.30")
            continue
        if concept in {"consumer_unit", "consumer_unit_with_spd", "fuse_box", "distribution_board"}:
            install += qty * Decimal("4.5")
            continue
        if concept in {"mcb", "rcbo", "afdd", "type_a_rcd", "main_switch", "spd_module"}:
            install += qty * Decimal("0.20")
            circuit_count += qty
            continue
        if concept in {"smoke_alarm", "heat_detector", "carbon_monoxide_alarm"}:
            install += qty * Decimal("0.35")

    if cable_metres > 0:
        # Includes handling, clipping, routing and terminations.
        install += cable_metres * Decimal("0.03")

    testing = (
        max(Decimal("1.0"), circuit_count * Decimal("0.30"))
        if circuit_count > 0
        else Decimal("1.0")
    )
    cert = Decimal("0.75") if (circuit_count > 0 or cable_metres > 0) else Decimal("0")
    return install, testing, cert


def _schedule_key_for_property(description: str, property_type: str | None) -> str:
    """Map a description/property_type to a labour-schedule key."""
    if property_type:
        return property_type
    text = _norm(description)
    bedrooms = _extract_bedrooms(description)
    if "flat" in text or "apartment" in text:
        return f"{bedrooms}_bed_flat" if bedrooms > 0 else "1_bed_flat"
    if "bungalow" in text:
        # Bungalows are typically smaller; use the flat schedule as a proxy.
        return f"{bedrooms}_bed_flat" if bedrooms > 0 else "1_bed_flat"
    if bedrooms > 0:
        return f"{bedrooms}_bed_house"
    return "3_bed_house"


def _schedule_entry_for_scope(
    description: str,
    property_type: str | None,
    schedule: LabourSchedule,
) -> Any:
    if _is_rewire(description):
        key = _schedule_key_for_property(description, property_type)
        return schedule.rewire.get(key, schedule.rewire.get("3_bed_house"))
    if _is_cu_upgrade(description):
        return schedule.consumer_unit_upgrade
    if _is_ev(description):
        return schedule.ev_charger
    if _is_extension(description):
        return schedule.extension
    if _is_garage(description):
        return schedule.garage
    if _is_eicr(description):
        return schedule.eicr
    if _is_fault_finding(description):
        return schedule.fault_finding
    return schedule.small_job_default


def estimate_labour(
    description: str,
    property_type: str | None,
    pricing_config: PricingConfig,
    labour_schedule: LabourSchedule,
    has_material_items: bool = True,
    requirements: list[BoQRequirement] | None = None,
) -> list[dict[str, Any]]:
    """Return synthetic labour raw line items for the job scope.

    Each item has keys: code, quantity, labour_hours, labour_rate, notes.
    """
    if _no_labour(description):
        return []

    entry = _schedule_entry_for_scope(description, property_type, labour_schedule)
    lines: list[dict[str, Any]] = []

    schedule_hours = ((entry.electrician_days * Decimal("8")) + entry.electrician_hours).quantize(
        Decimal("0.01")
    )

    install_hours = Decimal("0")
    testing_hours = Decimal("0")
    certification_hours = Decimal("0")
    access_hours = _access_hours(description)

    if requirements:
        install_hours, testing_hours, certification_hours = _derived_hours_from_requirements(
            requirements
        )

    base_install_hours = install_hours if requirements else Decimal("0")
    total_electrician_hours = (
        max(schedule_hours, base_install_hours) if has_material_items else schedule_hours
    )

    electrician_days, electrician_hours = _to_day_and_hour_lines(total_electrician_hours)

    if electrician_days > 0:
        lines.append(
            {
                "code": "LABOUR-ELECTRICIAN-DAY",
                "quantity": electrician_days,
                "labour_hours": Decimal("8"),
                "labour_rate": pricing_config.daily_labour_rate,
                "notes": (
                    f"{electrician_days} electrician day(s) based on BoQ scope "
                    f"(install/testing/certification/access)"
                ),
            }
        )
    if electrician_hours > 0:
        lines.append(
            {
                "code": "LABOUR-ELECTRICIAN-HOUR",
                "quantity": electrician_hours,
                "labour_hours": Decimal("1"),
                "labour_rate": pricing_config.hourly_labour_rate,
                "notes": "Additional electrician hours for BoQ scope",
            }
        )

    if testing_hours > 0:
        lines.append(
            {
                "code": "LABOUR-TESTING-HOUR",
                "quantity": testing_hours.quantize(Decimal("0.5")),
                "labour_hours": Decimal("1"),
                "labour_rate": pricing_config.hourly_labour_rate,
                "notes": "Testing and inspection allowance",
            }
        )

    if certification_hours > 0:
        lines.append(
            {
                "code": "LABOUR-CERTIFICATION-HOUR",
                "quantity": certification_hours,
                "labour_hours": Decimal("1"),
                "labour_rate": pricing_config.hourly_labour_rate,
                "notes": "Certification and handover documentation",
            }
        )

    if access_hours > 0:
        lines.append(
            {
                "code": "LABOUR-ACCESS-HOUR",
                "quantity": access_hours,
                "labour_hours": Decimal("1"),
                "labour_rate": pricing_config.hourly_labour_rate,
                "notes": "Access and making-good allowance",
            }
        )

    # Add mate support on larger jobs; keep schedule-provided mate values when present.
    mate_days = entry.mate_days
    mate_hours = entry.mate_hours
    if mate_days == 0 and mate_hours == 0 and total_electrician_hours >= Decimal("24"):
        mate_days = Decimal("1")

    if mate_days > 0:
        lines.append(
            {
                "code": "LABOUR-MATE-DAY",
                "quantity": mate_days,
                "labour_hours": Decimal("8"),
                "labour_rate": pricing_config.mate_rate,
                "notes": f"{mate_days} mate day(s) estimated for scope",
            }
        )
    if mate_hours > 0:
        lines.append(
            {
                "code": "LABOUR-MATE-HOUR",
                "quantity": mate_hours,
                "labour_hours": Decimal("1"),
                "labour_rate": pricing_config.mate_rate,
                "notes": f"{mate_hours} mate hour(s) estimated for scope",
            }
        )

    if not lines and has_material_items:
        # Fallback for any small job that the schedule did not cover.
        lines.append(
            {
                "code": "LABOUR-ELECTRICIAN-HOUR",
                "quantity": labour_schedule.small_job_default.electrician_hours,
                "labour_hours": Decimal("1"),
                "labour_rate": pricing_config.hourly_labour_rate,
                "notes": "Half-day electrician labour for small job",
            }
        )

    return lines
