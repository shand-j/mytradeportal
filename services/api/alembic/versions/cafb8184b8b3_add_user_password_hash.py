"""add user password_hash

Revision ID: cafb8184b8b3
Revises: 95446ea0d0cc
Create Date: 2026-06-22 00:02:11.121802

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cafb8184b8b3"
down_revision: str | Sequence[str] | None = "95446ea0d0cc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "password_hash")
