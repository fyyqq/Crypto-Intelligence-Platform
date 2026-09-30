"""create user_watchlist table

Revision ID: a3b9c1d2e4f5
Revises: 880523e449fb
Create Date: 2026-10-01 02:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a3b9c1d2e4f5'
down_revision: Union[str, None] = '880523e449fb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('user_watchlist',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('cmc_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'cmc_id')
    )


def downgrade() -> None:
    op.drop_table('user_watchlist')
