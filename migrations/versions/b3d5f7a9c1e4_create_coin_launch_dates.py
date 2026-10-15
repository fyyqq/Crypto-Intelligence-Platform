"""create coin_launch_dates

Revision ID: b3d5f7a9c1e4
Revises: a7c9e1b3d5f2
Create Date: 2026-10-15 16:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b3d5f7a9c1e4'
down_revision: Union[str, None] = 'a7c9e1b3d5f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'coin_launch_dates',
        sa.Column('cmc_id', sa.Integer(), primary_key=True),
        sa.Column('launch_date', sa.Date(), nullable=True),
        sa.Column('source', sa.String(length=20), nullable=False, server_default=''),
        sa.Column('checked_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('coin_launch_dates')
