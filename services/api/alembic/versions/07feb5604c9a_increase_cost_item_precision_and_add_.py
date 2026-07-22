"""increase cost item precision and add retail price incl vat

Revision ID: 07feb5604c9a
Revises: f527dd39ecee
Create Date: 2026-06-22 22:58:46.531453

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "07feb5604c9a"
down_revision: str | Sequence[str] | None = "f527dd39ecee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Increase cost-item price precision and store supplier VAT-inclusive price on BoQ lines."""
    op.alter_column(
        "cost_items",
        "unit_price",
        existing_type=sa.NUMERIC(precision=12, scale=2),
        type_=sa.Numeric(precision=12, scale=4),
        existing_nullable=False,
    )
    op.add_column(
        "boq_line_items",
        sa.Column("retail_price_incl_vat", sa.Numeric(precision=12, scale=2), nullable=True),
    )


def downgrade() -> None:
    """Revert cost-item price precision and remove supplier VAT-inclusive price."""
    op.drop_column("boq_line_items", "retail_price_incl_vat")
    op.alter_column(
        "cost_items",
        "unit_price",
        existing_type=sa.Numeric(precision=12, scale=4),
        type_=sa.NUMERIC(precision=12, scale=2),
        existing_nullable=False,
    )
