"""add cost_items table

Revision ID: 20260621_add_cost_items
Revises: 5ef71f957293
Create Date: 2026-06-21 22:00:00.000000

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260621_add_cost_items"
down_revision: str | Sequence[str] | None = "5ef71f957293"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cost_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            default=uuid4,
        ),
        sa.Column("code", sa.String(63), nullable=False, unique=True, index=True),
        sa.Column("trade", sa.String(50), nullable=False, index=True),
        sa.Column("region", sa.String(50), nullable=False, index=True),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("unit", sa.String(50), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, default="GBP"),
        sa.Column("is_active", sa.Boolean, nullable=False, default=True),
        sa.Column("source", sa.String(50), nullable=False, default="seed"),
        sa.Column("extra_data", postgresql.JSONB, nullable=False, default=dict),
        sa.Column("created_at", sa.DateTime, nullable=False, default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("cost_items")
