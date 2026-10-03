"""create price_alerts table

Revision ID: c5d1e3f4a7b8
Revises: b4c0d2e3f6a7
Create Date: 2026-10-04 01:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c5d1e3f4a7b8'
down_revision: Union[str, None] = 'b4c0d2e3f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('price_alerts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('cmc_id', sa.Integer(), nullable=False),
    sa.Column('coin_name', sa.String(length=120), nullable=False),
    sa.Column('symbol', sa.String(length=40), nullable=False),
    sa.Column('direction', sa.String(length=5), nullable=False),
    sa.Column('target_price', sa.Float(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('triggered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('triggered_price', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_price_alerts_user_id'), 'price_alerts', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_price_alerts_user_id'), table_name='price_alerts')
    op.drop_table('price_alerts')
