"""Shared fixtures for the golden-dataset evaluation harness."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pytest
import yaml

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

EVAL_DIR = Path(__file__).parent
YAML_PATH = EVAL_DIR / "golden_dataset.yaml"


@pytest.fixture(scope="session")
def golden_dataset() -> dict[str, Any]:
    """Load the full golden dataset YAML."""
    with YAML_PATH.open() as fh:
        data: dict[str, Any] = yaml.safe_load(fh)
    return data


@pytest.fixture(scope="session")
def golden_cases(golden_dataset: dict[str, Any]) -> list[dict[str, Any]]:
    """Return just the list of test cases."""
    cases: list[dict[str, Any]] = golden_dataset["test_cases"]
    return cases


@pytest.fixture(scope="session")
def ocerp_base_url() -> str:
    """URL of the running OCERP service."""
    return os.environ.get("OCERP_URL", "http://localhost:8002")


@pytest.fixture
async def ocerp_client(ocerp_base_url: str) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client pointed at the OCERP service (one per test)."""
    async with httpx.AsyncClient(base_url=ocerp_base_url, timeout=120) as client:
        yield client


@pytest.fixture(scope="session")
def tenant_settings() -> dict[str, str]:
    """Default tradesperson pricing for a consistent labour baseline."""
    return {
        "hourly_labour_rate": "45.00",
        "daily_labour_rate": "360.00",
        "minimum_charge": "0",
        "markup_percent": "25",
    }
