"""Tests for the quoting knowledge loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from data_pipeline.knowledge_loader import (
    KnowledgeChunk,
    chunk_job_capture_data_model,
    chunk_json_tables,
    chunk_markdown,
)


@pytest.fixture
def sample_kb(tmp_path: Path) -> Path:
    """Create a small Markdown knowledge base."""
    path = tmp_path / "kb.md"
    path.write_text(
        "# Knowledge Base\n\n"
        "## 1. Sockets\n\n"
        "Socket circuits need RCD protection.\n\n"
        "| Size | Breaker |\n|------|---------|\n| 32A | Type A |\n\n"
        "### 1.1 Bathrooms\n\n"
        "Bathroom sockets are special locations.\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def sample_tables(tmp_path: Path) -> Path:
    """Create a small extracted-tables JSON file."""
    path = tmp_path / "tables.json"
    data = {
        "metadata": {"source": "test"},
        "tables": [
            {
                "section_path": ["Protection", "RCDs"],
                "table": {
                    "headers": ["Circuit", "RCD"],
                    "rows": [
                        {"Circuit": "Socket", "RCD": "Type A"},
                        {"Circuit": "Bathroom", "RCD": "Type A"},
                    ],
                },
            }
        ],
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture
def sample_job_capture(tmp_path: Path) -> Path:
    """Create a minimal job-capture data model JSON."""
    path = tmp_path / "job_capture.json"
    data = {
        "metadata": {"title": "Test Model"},
        "universal_questions": [
            {
                "id": "UQ-01",
                "question": "Property type?",
                "type": "single_choice",
                "options": ["House", "Flat"],
                "required": True,
                "rationale": "Drives access.",
            }
        ],
        "job_categories": [
            {
                "id": "CAT-01",
                "name": "Power",
                "job_types": [
                    {
                        "id": "JOB-0101",
                        "name": "Socket Addition",
                        "part_p_notifiable": "No",
                        "typical_price_range": {"low": 40, "high": 150, "unit": "GBP"},
                        "typical_duration": "1 hour",
                        "triggers": ["extra socket"],
                        "specific_questions": [],
                    }
                ],
            }
        ],
        "decision_logic": {
            "cable_sizing_rules": [
                {
                    "id": "CSR-01",
                    "circuit_type": "Lighting",
                    "typical_cable": "1.5mm² T&E",
                    "breaker": "6A MCB",
                }
            ]
        },
        "compliance_flags": [
            {
                "id": "FLAG-01",
                "trigger": "Old CU",
                "severity": "recommendation",
                "response": "Upgrade",
            }
        ],
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_chunk_markdown(sample_kb: Path) -> None:
    chunks = chunk_markdown(sample_kb, "test_kb")
    assert len(chunks) == 2
    paths = [" > ".join(c.section_path) for c in chunks]
    assert "1. Sockets" in paths
    assert "1. Sockets > 1.1 Bathrooms" in paths
    socket_chunk = next(c for c in chunks if c.section_path == ["1. Sockets"])
    assert "Socket circuits need RCD protection" in socket_chunk.text
    assert "| 32A | Type A |" in socket_chunk.text


def test_chunk_json_tables(sample_tables: Path) -> None:
    chunks = chunk_json_tables(sample_tables, "test_tables")
    assert len(chunks) == 1
    assert chunks[0].section_path == ["Protection", "RCDs"]
    assert "| Socket | Type A |" in chunks[0].text
    assert chunks[0].doc_type == "table"


def test_chunk_job_capture_data_model(sample_job_capture: Path) -> None:
    chunks = chunk_job_capture_data_model(sample_job_capture, "test_capture")
    sections = {" > ".join(c.section_path) for c in chunks}
    assert any("Universal Questions" in s for s in sections)
    assert any("Socket Addition" in s for s in sections)
    assert any("Compliance Flags" in s for s in sections)
    flag_chunk = next(c for c in chunks if c.doc_type == "compliance_flag")
    assert flag_chunk.rule_tier == "recommendation"


def test_chunk_heuristics_tag_mandatory() -> None:
    path = Path("/tmp/test_mandatory.md")
    path.write_text("## Mandatory RCDs\n\nA socket circuit must have RCD protection.\n")
    chunks = chunk_markdown(path, "test")
    assert chunks[0].rule_tier == "mandatory"
    assert "socket" in chunks[0].job_types
    path.unlink()


def test_knowledge_chunk_defaults() -> None:
    chunk = KnowledgeChunk(text="hello", source="test")
    assert chunk.rule_tier == "reference"
    assert chunk.doc_type == "prose"
