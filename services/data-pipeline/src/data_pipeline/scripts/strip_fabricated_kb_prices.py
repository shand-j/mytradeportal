"""Strip AI-fabricated pricing content from the UK electrical KB.

The KB document at ``docs/UK_Domestic_Electrical_Quoting_Knowledge_Base.md``
carries 162 footnote-style citations (``[^N^]``) but has ZERO matching
footnote definitions, which is the classic LLM-hallucination signature: the
model produced confident-looking source markers with no real provenance.

The £ pricing tables (Section 13 trade prices, Section 8.3 job benchmarks,
and embedded price columns in Sections 4.4 / 6.5 / 7.x) drive the BoQ
engine's regulatory grounding context — leaving fabricated prices in the
LLM's view risks the model anchoring its analysis on imaginary numbers.

This script:

1. Deletes Sections 8.3, 8.4, and 13 from the markdown, replacing each
   with a short stub that explains the redaction and points to the live
   ``cost_items`` catalogue as the source of truth.
2. Replaces the embedded price tables in Sections 4.4 / 6.5 / 7.1 / 7.2 /
   7.3 with the same stub.
3. Drops the corresponding entries from the JSON extract (the entries are
   already broken — every row was a header-repeat — but they still get
   embedded into Qdrant by the knowledge loader so we strip them too).

Run once. The knowledge_loader will re-index Qdrant from the cleaned
sources on its next run.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
KB_MD = REPO_ROOT / "docs" / "UK_Domestic_Electrical_Quoting_Knowledge_Base.md"
KB_JSON = (
    REPO_ROOT
    / "docs"
    / "ai_electrician_quoting_platform_research"
    / "uk_domestic_electrical_knowledge_base.json"
)
JOB_CAPTURE_JSON = (
    REPO_ROOT
    / "docs"
    / "ai_electrician_quoting_platform_research"
    / "job_capture_data_model.json"
)

STUB = (
    "_Pricing data redacted: the figures originally in this section were "
    "AI-fabricated (the document carries citation markers with no resolvable "
    "footnote definitions). The BoQ engine resolves prices from the live "
    "supplier catalogue (`cost_items` table) rather than from this document._\n"
)

# Whole-section deletes: replace everything between ``start`` (inclusive) and
# the line that matches ``end_pattern`` (exclusive). The section heading is
# preserved so cross-references and the table of contents remain intact.
SECTION_DELETES: list[tuple[str, re.Pattern[str]]] = [
    ("### 8.3 Common Domestic Job Pricing Benchmarks", re.compile(r"^## 9\. ")),
    ("## 13. MATERIAL COST BENCHMARKS FOR QUOTING", re.compile(r"^## 14\. ")),
]

# In-place table redactions inside otherwise-useful sections. Each entry is
# (section-heading-prefix, prose-end-marker). Everything between the heading
# and the marker that matches the markdown table pattern is replaced with the
# stub.
TABLE_REDACTIONS: list[tuple[str, str]] = [
    # Section 4.4 — certification cost table
    ("### 4.4 Certification Costs", "For CPS-registered electricians"),
    # Section 6.5 — EICR bonding fault remedial cost
    ("### 6.5 Common EICR Bonding Failures", "## 7. PROTECTION DEVICES"),
    # Section 7.1 — RCD type pricing
    ("#### RCD Type Selection", "**Critical quoting note**"),
    # Section 7.2 — SPD types / device cost
    ("#### SPD Types and Applications", "For typical domestic installations"),
    # Section 7.3 — AFDD pricing
    ("#### AFDD Pricing and Quoting Implications", "## 9."),
]


def _is_table_line(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("|") or stripped.startswith("- ")


def _is_price_line(line: str) -> bool:
    return "£" in line


def _delete_section(lines: list[str], heading_prefix: str, end_pat: re.Pattern[str]) -> list[str]:
    """Delete the body of a section, keeping the heading and adding a stub."""
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.startswith(heading_prefix):
            out.append(line)
            out.append("\n")
            out.append(STUB)
            out.append("\n")
            # Skip until next matching heading
            i += 1
            while i < n and not end_pat.match(lines[i]):
                i += 1
            continue
        out.append(line)
        i += 1
    return out


def _redact_tables_in_section(
    lines: list[str], heading_prefix: str, prose_marker: str
) -> list[str]:
    """Replace markdown tables containing £ inside a sub-section with a stub.

    Walks lines starting at ``heading_prefix``, collects table runs until the
    ``prose_marker`` appears, and substitutes any £-bearing table with a stub.
    """
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if not line.startswith(heading_prefix):
            out.append(line)
            i += 1
            continue
        out.append(line)
        i += 1
        while i < n and prose_marker not in lines[i]:
            current = lines[i]
            if _is_table_line(current):
                # Collect the whole table block
                block_start = i
                while i < n and (_is_table_line(lines[i]) or lines[i].strip() == ""):
                    if lines[i].strip() == "":
                        # Tables end at the next blank line
                        if any(_is_table_line(lines[j]) for j in range(block_start, i)):
                            break
                    i += 1
                table_block = lines[block_start:i]
                if any(_is_price_line(b) for b in table_block):
                    out.append(STUB)
                    out.append("\n")
                else:
                    out.extend(table_block)
            else:
                out.append(current)
                i += 1
        # Continue main loop from prose_marker line (or EOF)
    return out


def clean_markdown(text: str) -> str:
    lines = text.splitlines(keepends=True)
    for prefix, end_pat in SECTION_DELETES:
        lines = _delete_section(lines, prefix, end_pat)
    for prefix, prose in TABLE_REDACTIONS:
        lines = _redact_tables_in_section(lines, prefix, prose)
    return "".join(lines)


def clean_json(data: dict) -> dict:
    """Drop pricing tables from the structured JSON extract.

    Match by section_path tokens — any path that hits the deleted sections or
    that has 'Price', 'Cost', 'Trade Price', 'Day Rate', 'Pricing Benchmark',
    'Material Cost' in its breadcrumb is removed.
    """
    drop_tokens = (
        "Material Cost",
        "Trade Price",
        "Common Domestic Job Pricing",
        "Emergency Call-Out Pricing",
        "Material Markup Strategy",
        "Common Material Trade Prices",
        "Consumer Units and Protection Devices",  # sub-heading inside 13.1
        "Cable (PVC Twin & Earth",
        "Accessories",
        "Conduit, Trunking, and Containment",
        "Earthing and Bonding",
        "EV Charger Materials",
        "Certification Costs and Time Implications",
        "Common EICR Bonding Failures",
        "RCD Type Selection",
        "SPD Types and Applications",
        "AFDD Pricing and Quoting Implications",
    )

    kept = []
    dropped = 0
    for entry in data.get("tables", []):
        path = " > ".join(entry.get("section_path", []))
        if any(tok in path for tok in drop_tokens):
            dropped += 1
            continue
        kept.append(entry)
    data["tables"] = kept
    data.setdefault("metadata", {})["dropped_pricing_tables"] = dropped
    return data


def clean_job_capture(data: dict) -> tuple[dict, int]:
    """Remove ``typical_price_range`` fields from the conversational data model.

    The job categories, question taxonomy, compliance flags and conversational
    guidelines are kept — those are structurally useful. Only the AI-fabricated
    price ranges are stripped.
    """
    stripped = [0]

    def _walk(node: object) -> None:
        if isinstance(node, dict):
            if "typical_price_range" in node:
                node.pop("typical_price_range")
                stripped[0] += 1
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(data)
    return data, stripped[0]


def main() -> None:
    md_text = KB_MD.read_text()
    new_md = clean_markdown(md_text)
    KB_MD.write_text(new_md)

    json_data = json.loads(KB_JSON.read_text())
    before = len(json_data.get("tables", []))
    new_json = clean_json(json_data)
    KB_JSON.write_text(json.dumps(new_json, indent=2) + "\n")

    capture_data = json.loads(JOB_CAPTURE_JSON.read_text())
    capture_data, stripped_prices = clean_job_capture(capture_data)
    JOB_CAPTURE_JSON.write_text(json.dumps(capture_data, indent=2) + "\n")

    print(
        f"Markdown: {len(md_text):,} -> {len(new_md):,} chars "
        f"({100 * (1 - len(new_md) / len(md_text)):.1f}% reduction)"
    )
    print(
        f"JSON tables: {before} -> {len(new_json['tables'])} "
        f"(dropped {before - len(new_json['tables'])})"
    )
    print(
        f"Job capture: stripped {stripped_prices} fabricated "
        "typical_price_range fields"
    )


if __name__ == "__main__":
    main()
