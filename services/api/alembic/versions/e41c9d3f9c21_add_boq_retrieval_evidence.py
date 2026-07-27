"""Add retrieval evidence metadata to bills_of_quantities.

Revision ID: e41c9d3f9c21
Revises: d13f7a21
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e41c9d3f9c21"
down_revision: str | Sequence[str] | None = "d13f7a21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bills_of_quantities",
        sa.Column(
            "retrieval_evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("bills_of_quantities", "retrieval_evidence")
