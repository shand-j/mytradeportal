"""add_bill_of_quantities

Revision ID: 75e833e344cf
Revises: f88f49db60e7
Create Date: 2026-06-22 15:37:18.335696

"""
from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '75e833e344cf'
down_revision: str | Sequence[str] | None = 'f88f49db60e7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # The API container auto-creates tables on startup, so the BoQ tables may
    # already exist in development environments. Drop them first to ensure the
    # migration produces the correct schema.
    op.execute("DROP TABLE IF EXISTS boq_line_items CASCADE")
    op.execute("DROP TABLE IF EXISTS bills_of_quantities CASCADE")

    op.create_table(
        "bills_of_quantities",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            default=uuid4,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "quote_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("quotes.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column("status", sa.String(50), nullable=False, default="draft"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False, default=0),
        sa.Column("vat_rate", sa.Numeric(5, 2), nullable=False, default=0.20),
        sa.Column("vat_amount", sa.Numeric(12, 2), nullable=False, default=0),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, default=0),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False, default=0),
        sa.Column("warnings", postgresql.JSONB, nullable=False, default=list),
        sa.Column("standard", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    op.create_table(
        "boq_line_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            default=uuid4,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "boq_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bills_of_quantities.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "cost_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cost_items.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("code", sa.String(63), nullable=False, index=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("unit", sa.String(50), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False, default=1),
        sa.Column("labour_hours", sa.Numeric(10, 2), nullable=False, default=0),
        sa.Column("labour_rate", sa.Numeric(12, 2), nullable=False, default=0),
        sa.Column("labour_total", sa.Numeric(12, 2), nullable=False, default=0),
        sa.Column("material_cost", sa.Numeric(12, 2), nullable=False, default=0),
        sa.Column("material_total", sa.Numeric(12, 2), nullable=False, default=0),
        sa.Column("plant_cost", sa.Numeric(12, 2), nullable=False, default=0),
        sa.Column("plant_total", sa.Numeric(12, 2), nullable=False, default=0),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False, default=0),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, default=0),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    op.add_column(
        "quote_line_items",
        sa.Column(
            "cost_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cost_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "quote_line_items",
        sa.Column(
            "boq_line_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("boq_line_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_quote_line_items_cost_item_id"),
        "quote_line_items",
        ["cost_item_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_quote_line_items_boq_line_item_id"),
        "quote_line_items",
        ["boq_line_item_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_quote_line_items_boq_line_item_id"), table_name="quote_line_items"
    )
    op.drop_index(
        op.f("ix_quote_line_items_cost_item_id"), table_name="quote_line_items"
    )
    op.drop_column("quote_line_items", "boq_line_item_id")
    op.drop_column("quote_line_items", "cost_item_id")
    op.drop_table("boq_line_items")
    op.drop_table("bills_of_quantities")
