"""add_supabase_uid_to_users

Revision ID: f88f49db60e7
Revises: e9e2e4dd81be
Create Date: 2026-06-22 09:15:57.279081

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f88f49db60e7'
down_revision: str | Sequence[str] | None = 'e9e2e4dd81be'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('supabase_uid', sa.String(length=255), nullable=True))
    op.create_index(op.f('ix_users_supabase_uid'), 'users', ['supabase_uid'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_users_supabase_uid'), table_name='users')
    op.drop_column('users', 'supabase_uid')
