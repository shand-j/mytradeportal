"""Add customer summary and margin indicator to bills_of_quantities.

Revision ID: d13f7a21
Revises: c0a1d1e5
Create Date: 2026-06-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d13f7a21"
down_revision: str | Sequence[str] | None = "c0a1d1e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bills_of_quantities",
        sa.Column(
            "customer_summary_lines",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "bills_of_quantities",
        sa.Column(
            "margin_indicator",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("bills_of_quantities", "margin_indicator")
    op.drop_column("bills_of_quantities", "customer_summary_lines")
