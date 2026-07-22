"""add_boq_supplier_attribution

Revision ID: add_boq_supplier_attribution
Revises: 75e833e344cf
Create Date: 2026-06-22 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_boq_supplier_attribution"
down_revision: str | Sequence[str] | None = "75e833e344cf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("boq_line_items", sa.Column("supplier", sa.String(100), nullable=True))
    op.add_column("boq_line_items", sa.Column("brand", sa.String(100), nullable=True))
    op.add_column("boq_line_items", sa.Column("product_url", sa.Text, nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("boq_line_items", "product_url")
    op.drop_column("boq_line_items", "brand")
    op.drop_column("boq_line_items", "supplier")
