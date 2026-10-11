"""add movers_daily

Revision ID: b3c6d9e1f5a7
Revises: a9b5c7d8e2f4
Create Date: 2026-10-12 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b3c6d9e1f5a7'
down_revision: Union[str, None] = 'a9b5c7d8e2f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'movers_daily',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('window', sa.String(length=8), nullable=False),
        sa.Column('coin_id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('cmc_rank', sa.Integer(), nullable=False),
        sa.Column('price_now', sa.Numeric(38, 18), nullable=False),
        sa.Column('price_then', sa.Numeric(38, 18), nullable=False),
        sa.Column('pct_change', sa.Float(), nullable=False),
        sa.Column('volume_24h', sa.Numeric(24, 2), nullable=False),
        sa.Column('then_at', sa.DateTime(), nullable=False),
        sa.Column('now_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('day', 'window', 'coin_id', name='uq_movers_daily_day_window_coin'),
    )
    op.create_index('ix_movers_daily_day_window', 'movers_daily', ['day', 'window'])


def downgrade() -> None:
    op.drop_index('ix_movers_daily_day_window', table_name='movers_daily')
    op.drop_table('movers_daily')
