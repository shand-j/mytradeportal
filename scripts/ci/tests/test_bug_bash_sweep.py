from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "bug_bash_sweep.py"
SPEC = importlib.util.spec_from_file_location("bug_bash_sweep", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules["bug_bash_sweep"] = MODULE
SPEC.loader.exec_module(MODULE)


def test_inventory_feature_records_tags(tmp_path: Path) -> None:
    feature = tmp_path / "example.feature"
    feature.write_text(
        "@example\nFeature: Example\n\n  @automated-unit @p0\n"
        "  Scenario: A passing journey\n"
        "    Given setup\n",
        encoding="utf-8",
    )

    scenarios = MODULE.inventory_feature(feature)

    assert len(scenarios) == 1
    assert scenarios[0].name == "A passing journey"
    assert scenarios[0].tags == ("@automated-unit", "@p0")


def test_render_log_records_every_scenario_and_uat_item(tmp_path: Path) -> None:
    feature = tmp_path / "journey.feature"
    feature.write_text(
        "Feature: Journey\n  Scenario: First step\n  Scenario Outline: Second step\n",
        encoding="utf-8",
    )

    log = MODULE.render_log(
        features_dir=tmp_path,
        commit="abc123",
        environment="staging",
        tester="tester",
        statuses={
            "journey:First step": "pass",
            "journey:Second step": "fail",
        },
        uat_statuses={MODULE.UAT_ITEMS[0]: "pass"},
    )

    assert "[PASS] First step" in log
    assert "[FAIL] Second step" in log
    assert "- PASS: 1" in log
    assert "- FAIL: 1" in log
    assert "[PASS] Onboarding:" in log
    assert len(MODULE.UAT_ITEMS) == 9
