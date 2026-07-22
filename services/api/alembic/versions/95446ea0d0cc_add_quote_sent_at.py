"""add quote sent_at

Revision ID: 95446ea0d0cc
Revises: 20260621_add_cost_items
Create Date: 2026-06-21 23:35:13.038124

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '95446ea0d0cc'
down_revision: str | Sequence[str] | None = '20260621_add_cost_items'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('quotes', sa.Column('sent_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('quotes', 'sent_at')
