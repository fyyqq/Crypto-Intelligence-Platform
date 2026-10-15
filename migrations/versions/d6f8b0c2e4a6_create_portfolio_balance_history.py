"""create portfolio_balance_history

Revision ID: d6f8b0c2e4a6
Revises: c4e6a8b0d2f3
Create Date: 2026-10-16 05:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd6f8b0c2e4a6'
down_revision: Union[str, None] = 'c4e6a8b0d2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'portfolio_balance_history',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('total_usd', sa.Float(), nullable=False),
    )
    op.create_index('ix_portfolio_balance_history_at', 'portfolio_balance_history', ['at'])


def downgrade() -> None:
    op.drop_index('ix_portfolio_balance_history_at', table_name='portfolio_balance_history')
    op.drop_table('portfolio_balance_history')
