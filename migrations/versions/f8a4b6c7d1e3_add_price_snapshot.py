"""add price_snapshot

Revision ID: f8a4b6c7d1e3
Revises: e7f3a5b6c0d2
Create Date: 2026-10-05 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f8a4b6c7d1e3'
down_revision: Union[str, None] = 'e7f3a5b6c0d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'price_snapshot',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('coin_id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=32), nullable=False),
        sa.Column('price_usd', sa.Numeric(38, 18), nullable=False),
        sa.Column('cmc_rank', sa.Integer(), nullable=True),
        sa.Column('volume_24h', sa.Numeric(24, 2), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_price_snapshot_coin_id', 'price_snapshot', ['coin_id'])
    op.create_index('ix_price_snapshot_synced_at', 'price_snapshot', ['synced_at'])
    op.create_index('ix_price_snapshot_coin_synced', 'price_snapshot', ['coin_id', 'synced_at'])


def downgrade() -> None:
    op.drop_index('ix_price_snapshot_coin_synced', table_name='price_snapshot')
    op.drop_index('ix_price_snapshot_synced_at', table_name='price_snapshot')
    op.drop_index('ix_price_snapshot_coin_id', table_name='price_snapshot')
    op.drop_table('price_snapshot')
