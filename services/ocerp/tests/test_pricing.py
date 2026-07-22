"""Unit tests for the price lookup service."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from ocerp.models import CostItem
from ocerp.services.pricing import lookup_price
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_lookup_price_found() -> None:
    item = CostItem(
        code="ELEC-SOCKET-ADD",
        description="Install one additional double socket",
        unit="each",
        unit_price=Decimal("85.00"),
        currency="GBP",
        region="UK",
        trade="electrical",
        category="Sockets",
        is_active=True,
        source="seed",
        extra_data={},
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = item
    db = AsyncMock(spec=AsyncSession)
    db.execute.return_value = mock_result

    response = await lookup_price(db, "ELEC-SOCKET-ADD", "UK")

    assert response.found is True
    assert response.code == "ELEC-SOCKET-ADD"
    assert response.unit_price == Decimal("85.00")
    assert response.region == "UK"


@pytest.mark.asyncio
async def test_lookup_price_not_found() -> None:
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db = AsyncMock(spec=AsyncSession)
    db.execute.return_value = mock_result

    response = await lookup_price(db, "UNKNOWN", "UK")

    assert response.found is False
    assert response.code == "UNKNOWN"
    assert response.region == "UK"
