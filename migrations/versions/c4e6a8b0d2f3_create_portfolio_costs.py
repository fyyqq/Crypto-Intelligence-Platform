"""create portfolio_costs

Revision ID: c4e6a8b0d2f3
Revises: b3d5f7a9c1e4
Create Date: 2026-10-16 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c4e6a8b0d2f3'
down_revision: Union[str, None] = 'b3d5f7a9c1e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'portfolio_costs',
        sa.Column('user_id', sa.Integer(), primary_key=True),
        sa.Column('asset', sa.String(length=30), primary_key=True),
        sa.Column('avg_price', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('portfolio_costs')
