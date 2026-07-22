"""Tests for the knowledge retrieval router."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from ocerp.main import app
from ocerp.services.knowledge_store import KnowledgeSearchResult

client = TestClient(app)


def _make_hit(overrides: dict[str, Any] | None = None) -> KnowledgeSearchResult:
    defaults: dict[str, Any] = {
        "id": "test-id",
        "score": 0.95,
        "text": "RCDs are required for socket circuits.",
        "source": "test",
        "section_path": ["Protection", "RCDs"],
        "rule_tier": "mandatory",
        "job_types": ["socket"],
        "doc_type": "prose",
    }
    if overrides:
        defaults.update(overrides)
    return KnowledgeSearchResult(**defaults)


def test_search_knowledge_endpoint() -> None:
    mock_result = _make_hit()
    with patch(
        "ocerp.services.knowledge_store.KnowledgeStore.search",
        new_callable=AsyncMock,
        return_value=[mock_result],
    ):
        response = client.post("/knowledge/search", json={"query": "RCD for socket"})

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["text"] == mock_result.text
    assert data[0]["rule_tier"] == "mandatory"


def test_search_knowledge_with_filters() -> None:
    mock_result = _make_hit({"job_types": ["ev_charger"], "rule_tier": "mandatory"})
    with patch(
        "ocerp.services.knowledge_store.KnowledgeStore.search",
        new_callable=AsyncMock,
        return_value=[mock_result],
    ) as mock_search:
        response = client.post(
            "/knowledge/search",
            json={
                "query": "EV charger earthing",
                "job_type": "ev_charger",
                "rule_tier": "mandatory",
                "limit": 3,
            },
        )

    assert response.status_code == 200
    call_args = mock_search.call_args[0][0]
    assert call_args.job_type == "ev_charger"
    assert call_args.rule_tier == "mandatory"
    assert call_args.limit == 3
