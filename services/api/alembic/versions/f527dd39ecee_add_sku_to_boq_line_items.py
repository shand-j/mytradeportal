"""add sku to boq line items

Revision ID: f527dd39ecee
Revises: add_boq_supplier_attribution
Create Date: 2026-06-22 22:44:12.472708

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f527dd39ecee"
down_revision: str | Sequence[str] | None = "add_boq_supplier_attribution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add SKU attribution to BoQ line items."""
    op.add_column("boq_line_items", sa.Column("sku", sa.String(length=100), nullable=True))


def downgrade() -> None:
    """Remove SKU attribution from BoQ line items."""
    op.drop_column("boq_line_items", "sku")
