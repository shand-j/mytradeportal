"""Unit tests for the standards service."""

from ocerp.services.standards import list_standards


def test_list_standards_returns_all() -> None:
    response = list_standards()
    codes = {s.code for s in response.standards}
    assert "nrm1" in codes
    assert "csi" in codes


def test_list_standards_filters_by_region() -> None:
    response = list_standards(region="UK")
    assert all(s.region == "UK" for s in response.standards)
    assert len(response.standards) == 2


def test_list_standards_unknown_region_returns_empty() -> None:
    response = list_standards(region="XX")
    assert response.standards == []
