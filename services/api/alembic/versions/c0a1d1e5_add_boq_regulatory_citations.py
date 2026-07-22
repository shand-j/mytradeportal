"""Add regulatory grounding columns to bills_of_quantities.

Revision ID: c0a1d1e5
Revises: b7e1c0f4
Create Date: 2026-06-23

Adds two JSONB columns so the BoQ can persist the regulatory grounding
emitted by the OCERP compliance pipeline:

* ``regulatory_citations`` — chunk-level provenance for every BS 7671 /
  Part P / BS 5839 excerpt the LLM saw during generation. These are surfaced
  on the customer quote so the trader can defend it during dispute.
* ``compliance_warnings`` — operator-facing nags for mandatory items per
  detected job type that the resolved BoQ does not visibly contain.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c0a1d1e5"
down_revision: str | Sequence[str] | None = "b7e1c0f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bills_of_quantities",
        sa.Column(
            "regulatory_citations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "bills_of_quantities",
        sa.Column(
            "compliance_warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("bills_of_quantities", "compliance_warnings")
    op.drop_column("bills_of_quantities", "regulatory_citations")
