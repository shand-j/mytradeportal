"""Load quoting knowledge documents into Qdrant for RAG retrieval.

This module chunks the generic UK domestic electrical knowledge base, the
extracted JSON tables and the conversational job-capture data model, embeds
them, and stores them in a dedicated Qdrant collection.
"""

from __future__ import annotations

import argparse
import json
import re
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from qdrant_client.models import Distance, PointStruct, VectorParams

from data_pipeline.config import settings
from data_pipeline.embeddings import embed_texts, get_embedding_dimension
from data_pipeline.qdrant import get_qdrant_client


class KnowledgeChunk(BaseModel):
    """A single retrievable unit of quoting knowledge."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str
    source: str
    section_path: list[str] = Field(default_factory=list)
    rule_tier: str = "reference"
    job_types: list[str] = Field(default_factory=list)
    doc_type: str = "prose"


DEFAULT_KB_MARKDOWN = Path("docs/UK_Domestic_Electrical_Quoting_Knowledge_Base.md")
DEFAULT_KB_JSON = Path(
    "docs/ai_electrician_quoting_platform_research/uk_domestic_electrical_knowledge_base.json"
)
DEFAULT_JOB_CAPTURE_JSON = Path(
    "docs/ai_electrician_quoting_platform_research/job_capture_data_model.json"
)

# Simple heuristics to tag chunks for agent retrieval filters.
_RULE_TIER_HINTS = {
    "mandatory": ["mandatory", "must", "shall", "required", "danger present", "urgent remedial"],
    "default": ["risk assessment", "typically required", "standard specification"],
    "suggestion": ["recommended", "recommend", "suggest", "optional", "upgrade"],
}

_JOB_TYPE_HINTS = {
    "consumer_unit": ["consumer unit", "fuse board", "distribution board"],
    "ev_charger": ["ev charger", "ev charging", "chargepoint", "vehicle"],
    "bathroom": ["bathroom", "shower room", "zone 0", "zone 1", "zone 2"],
    "outdoor": ["outdoor", "garden", "shed", "garage supply", "outbuilding"],
    "eicr": ["eicr", "condition report", "periodic inspection"],
    "rewire": ["rewire", "rewiring"],
    "lighting": ["downlight", "light fitting", "lighting circuit"],
    "socket": ["socket", "spur", "ring final"],
    "shower": ["electric shower", "shower circuit"],
    "alarm": ["smoke alarm", "fire alarm", "heat detector", "interlinked"],
    "smart_home": ["smart home", "knx", "dali", "zigbee", "z-wave"],
    "solar_pv": ["solar", "pv", "battery storage"],
}


def _infer_rule_tier(text: str, section_path: list[str]) -> str:
    """Guess the rule tier from the content and heading."""
    haystack = " ".join(section_path).lower() + " " + text.lower()
    for tier, hints in _RULE_TIER_HINTS.items():
        if any(hint in haystack for hint in hints):
            return tier
    return "reference"


def _infer_job_types(text: str, section_path: list[str]) -> list[str]:
    """Guess relevant job-type tags from the content and heading."""
    haystack = " ".join(section_path).lower() + " " + text.lower()
    return [job for job, hints in _JOB_TYPE_HINTS.items() if any(h in haystack for h in hints)]


def _chunk_id(source: str, section_path: list[str], index: int) -> str:
    """Generate a deterministic UUID5 for a chunk so reruns overwrite cleanly."""
    namespace = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # DNS namespace
    path = " > ".join(section_path) if section_path else "root"
    return str(uuid.uuid5(namespace, f"mtp:knowledge:{source}:{path}:{index}"))


def _render_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a list of rows as a Markdown table."""
    if not headers or not rows:
        return ""
    header_line = "| " + " | ".join(headers) + " |"
    sep_line = "|" + "|".join(" --- " for _ in headers) + "|"
    row_lines = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header_line, sep_line, *row_lines])


def _parse_markdown_table(lines: list[str], start: int) -> tuple[str, int]:
    """Parse a Markdown table starting at `start`. Returns the rendered table and next index."""
    rows: list[list[str]] = []
    i = start
    while i < len(lines) and lines[i].strip().startswith("|"):
        line = lines[i].strip()
        if re.match(r"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?$", line):
            i += 1
            continue
        cells = [cell.strip() for cell in line.split("|")]
        # Drop empty leading/trailing cells caused by outer pipes
        if cells and cells[0] == "":
            cells = cells[1:]
        if cells and cells[-1] == "":
            cells = cells[:-1]
        rows.append(cells)
        i += 1
    if len(rows) < 2:
        return "", i
    table = _render_markdown_table(rows[0], rows[1:])
    return table, i


def chunk_markdown(path: Path, source: str) -> list[KnowledgeChunk]:
    """Chunk a Markdown knowledge base by H2/H3 sections."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    chunks: list[KnowledgeChunk] = []

    # Stack of (level, title) to build section paths
    stack: list[tuple[int, str]] = []
    current_body: list[str] = []
    current_title = ""

    def flush_section() -> None:
        if not current_title or not current_body:
            return
        section_path = [title for _, title in stack]
        body_text = "\n".join(line.strip() for line in current_body if line.strip())
        if not body_text:
            return
        full_text = f"# {' > '.join(section_path)}\n\n{body_text}"
        chunk = KnowledgeChunk(
            id=_chunk_id(source, section_path, 0),
            text=full_text,
            source=source,
            section_path=section_path,
            rule_tier=_infer_rule_tier(full_text, section_path),
            job_types=_infer_job_types(full_text, section_path),
            doc_type="prose",
        )
        chunks.append(chunk)

    i = 0
    while i < len(lines):
        line = lines[i]
        heading = re.match(r"^(#{2,6})\s+(.*)", line)
        if heading:
            flush_section()
            level = len(heading.group(1))
            title = heading.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            current_title = title
            current_body = []
            i += 1
            continue

        if line.strip().startswith("|"):
            table, i = _parse_markdown_table(lines, i)
            if table:
                current_body.append(table)
            continue

        current_body.append(line)
        i += 1

    flush_section()
    return chunks


def chunk_json_tables(path: Path, source: str) -> list[KnowledgeChunk]:
    """Chunk extracted JSON tables into retrievable units."""
    data = json.loads(path.read_text(encoding="utf-8"))
    chunks: list[KnowledgeChunk] = []
    for idx, item in enumerate(data.get("tables", [])):
        section_path = item.get("section_path", [])
        table = item.get("table", {})
        headers = table.get("headers", [])
        rows = [list(row.values()) for row in table.get("rows", [])]
        rendered = _render_markdown_table(headers, rows)
        if not rendered:
            continue
        text = f"# {' > '.join(section_path)}\n\n{rendered}"
        chunks.append(
            KnowledgeChunk(
                id=_chunk_id(source, section_path, idx),
                text=text,
                source=source,
                section_path=section_path,
                rule_tier=_infer_rule_tier(text, section_path),
                job_types=_infer_job_types(text, section_path),
                doc_type="table",
            )
        )
    return chunks


def chunk_job_capture_data_model(path: Path, source: str) -> list[KnowledgeChunk]:
    """Chunk the conversational job-capture data model."""
    data = json.loads(path.read_text(encoding="utf-8"))
    chunks: list[KnowledgeChunk] = []

    metadata = data.get("metadata", {})
    base_path = [metadata.get("title", "Job Capture Data Model")]

    # Universal questions
    uq_path = [*base_path, "Universal Questions"]
    for idx, q in enumerate(data.get("universal_questions", [])):
        text = (
            f"Question {q.get('id')}: {q.get('question')}\n"
            f"Type: {q.get('type')}\n"
            f"Options: {', '.join(str(o) for o in q.get('options', []))}\n"
            f"Rationale: {q.get('rationale', '')}"
        )
        chunks.append(
            KnowledgeChunk(
                id=_chunk_id(source, [*uq_path, q.get("id", str(idx))], 0),
                text=text,
                source=source,
                section_path=[*uq_path, q.get("id", "")],
                rule_tier="reference",
                doc_type="question",
            )
        )

    # Job types
    for category in data.get("job_categories", []):
        cat_name = category.get("name", "")
        for job in category.get("job_types", []):
            job_name = job.get("name", "")
            job_path = [*base_path, cat_name, job_name]
            text = (
                f"Job type: {job_name} ({job.get('id')})\n"
                f"Category: {cat_name}\n"
                f"Part P notifiable: {job.get('part_p_notifiable', '')}\n"
                f"Typical price range: {job.get('typical_price_range', {})}\n"
                f"Typical duration: {job.get('typical_duration', '')}\n"
                f"Triggers: {', '.join(job.get('triggers', []))}"
            )
            chunks.append(
                KnowledgeChunk(
                    id=_chunk_id(source, job_path, 0),
                    text=text,
                    source=source,
                    section_path=job_path,
                    rule_tier=_infer_rule_tier(text, job_path),
                    job_types=_infer_job_types(text, job_path),
                    doc_type="job_type",
                )
            )
            for qidx, q in enumerate(job.get("specific_questions", [])):
                q_text = (
                    f"Question {q.get('id')}: {q.get('question')}\n"
                    f"Type: {q.get('type')}\n"
                    f"Options: {', '.join(str(o) for o in q.get('options', []))}\n"
                    f"Required: {q.get('required', False)}\n"
                    f"Rationale: {q.get('rationale', '')}"
                )
                chunks.append(
                    KnowledgeChunk(
                        id=_chunk_id(source, [*job_path, q.get("id", str(qidx))], 0),
                        text=q_text,
                        source=source,
                        section_path=[*job_path, q.get("id", "")],
                        rule_tier="reference",
                        job_types=_infer_job_types(text, job_path),
                        doc_type="question",
                    )
                )

    # Compliance flags
    flags_path = [*base_path, "Compliance Flags"]
    for idx, flag in enumerate(data.get("compliance_flags", [])):
        text = (
            f"Flag {flag.get('id')}: {flag.get('trigger')}\n"
            f"Severity: {flag.get('severity')}\n"
            f"Response: {flag.get('response')}"
        )
        chunks.append(
            KnowledgeChunk(
                id=_chunk_id(source, [*flags_path, flag.get("id", str(idx))], 0),
                text=text,
                source=source,
                section_path=[*flags_path, flag.get("id", "")],
                rule_tier=flag.get("severity", "reference"),
                job_types=_infer_job_types(text, flags_path),
                doc_type="compliance_flag",
            )
        )

    # Decision logic
    decision = data.get("decision_logic", {})
    for rule_set_name, rules in decision.items():
        rs_path = [*base_path, "Decision Logic", rule_set_name]
        for idx, rule in enumerate(rules):
            text = "\n".join(f"{k}: {v}" for k, v in rule.items())
            chunks.append(
                KnowledgeChunk(
                    id=_chunk_id(source, [*rs_path, rule.get("id", str(idx))], 0),
                    text=text,
                    source=source,
                    section_path=[*rs_path, rule.get("id", "")],
                    rule_tier=_infer_rule_tier(text, rs_path),
                    job_types=_infer_job_types(text, rs_path),
                    doc_type="decision_rule",
                )
            )

    return chunks


def _chunk_payload(chunk: KnowledgeChunk) -> dict[str, Any]:
    """Build a Qdrant payload from a chunk."""
    return {
        "text": chunk.text,
        "source": chunk.source,
        "section_path": chunk.section_path,
        "rule_tier": chunk.rule_tier,
        "job_types": chunk.job_types,
        "doc_type": chunk.doc_type,
    }


async def load_knowledge(
    *,
    reset: bool = True,
    dry_run: bool = False,
    batch_size: int = 8,
) -> list[KnowledgeChunk]:
    """Load all quoting knowledge into Qdrant.

    Args:
        reset: If True, delete and recreate the knowledge collection before loading.
        dry_run: If True, chunk and return without embedding or upserting.
        batch_size: Number of chunks to embed per batch.
    """
    chunks: list[KnowledgeChunk] = []
    chunks.extend(chunk_markdown(DEFAULT_KB_MARKDOWN, "uk_domestic_electrical_kb"))
    chunks.extend(chunk_json_tables(DEFAULT_KB_JSON, "uk_domestic_electrical_kb_tables"))
    chunks.extend(chunk_job_capture_data_model(DEFAULT_JOB_CAPTURE_JSON, "job_capture_data_model"))

    if dry_run:
        return chunks

    client = get_qdrant_client()
    collection_name = settings.qdrant_knowledge_collection_name
    vector_size = get_embedding_dimension()

    exists = await client.collection_exists(collection_name)
    if reset and exists:
        await client.delete_collection(collection_name)
        exists = False

    if not exists:
        await client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )

    total_batches = (len(chunks) + batch_size - 1) // batch_size
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        batch_num = i // batch_size + 1
        print(f"Embedding batch {batch_num}/{total_batches} ({len(batch)} chunks)...")
        vectors = await embed_texts([chunk.text for chunk in batch])
        points = [
            PointStruct(
                id=chunk.id,
                vector=vector,
                payload=_chunk_payload(chunk),
            )
            for chunk, vector in zip(batch, vectors, strict=True)
        ]
        await client.upsert(collection_name=collection_name, points=points)
        print(f"  -> upserted batch {batch_num}/{total_batches}")

    print(f"Knowledge collection '{collection_name}' now contains {len(chunks)} chunks.")
    return chunks


def main() -> None:
    """CLI entry point for the knowledge loader."""
    parser = argparse.ArgumentParser(description="Load quoting knowledge into Qdrant.")
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Keep the existing collection and overwrite chunks by deterministic ID.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chunk documents and print counts without embedding or upserting.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="Number of chunks to embed per batch. Lower is better for local Ollama.",
    )
    args = parser.parse_args()

    import asyncio

    chunks = asyncio.run(
        load_knowledge(
            reset=not args.no_reset,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
        )
    )
    print(f"Processed {len(chunks)} knowledge chunks.")
    if args.dry_run:
        for chunk in chunks[:5]:
            print("\n---")
            print(f"source={chunk.source} type={chunk.doc_type} tier={chunk.rule_tier}")
            print(f"path={' > '.join(chunk.section_path)}")
            print(chunk.text[:300])


if __name__ == "__main__":
    main()
