"""increase line item precision to 4 dp

Revision ID: 450d95702829
Revises: 07feb5604c9a
Create Date: 2026-06-22 23:04:25.672421

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "450d95702829"
down_revision: str | Sequence[str] | None = "07feb5604c9a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LINE_ITEM_COLUMNS = {
    "boq_line_items": [
        "labour_rate",
        "labour_total",
        "material_cost",
        "material_total",
        "plant_cost",
        "plant_total",
        "unit_price",
        "total",
    ],
    "quote_line_items": ["unit_price", "total"],
    "invoice_line_items": ["unit_price", "total"],
}


def upgrade() -> None:
    """Increase per-line pricing precision to avoid per-unit rounding drift."""
    for table, columns in LINE_ITEM_COLUMNS.items():
        for column in columns:
            op.alter_column(
                table,
                column,
                existing_type=sa.NUMERIC(precision=12, scale=2),
                type_=sa.Numeric(precision=12, scale=4),
                existing_nullable=False,
            )


def downgrade() -> None:
    """Revert per-line pricing precision to 2 dp."""
    for table, columns in LINE_ITEM_COLUMNS.items():
        for column in columns:
            op.alter_column(
                table,
                column,
                existing_type=sa.Numeric(precision=12, scale=4),
                type_=sa.NUMERIC(precision=12, scale=2),
                existing_nullable=False,
            )
