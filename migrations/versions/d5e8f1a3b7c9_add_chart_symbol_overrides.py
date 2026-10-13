"""add chart_symbol_overrides

Revision ID: d5e8f1a3b7c9
Revises: c4d7e0f2a6b8
Create Date: 2026-10-13 18:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd5e8f1a3b7c9'
down_revision: Union[str, None] = 'c4d7e0f2a6b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'chart_symbol_overrides',
        sa.Column('cmc_id', sa.Integer(), primary_key=True),
        sa.Column('symbol', sa.String(length=120), nullable=False),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('chart_symbol_overrides')
