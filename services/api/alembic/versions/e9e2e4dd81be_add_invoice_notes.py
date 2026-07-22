"""add_invoice_notes

Revision ID: e9e2e4dd81be
Revises: 26de73285547
Create Date: 2026-06-22 06:41:13.758232

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e9e2e4dd81be'
down_revision: str | Sequence[str] | None = '26de73285547'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Idempotent: the 26de73285547 migration may already have added this
    # column on fresh databases, but the dev database was stamped without it.
    op.execute("ALTER TABLE invoices ADD COLUMN IF NOT EXISTS notes TEXT")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE invoices DROP COLUMN IF EXISTS notes")
