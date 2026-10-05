"""add price_snapshot.market_cap

Revision ID: a9b5c7d8e2f4
Revises: f8a4b6c7d1e3
Create Date: 2026-10-05 14:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a9b5c7d8e2f4'
down_revision: Union[str, None] = 'f8a4b6c7d1e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('price_snapshot', sa.Column('market_cap', sa.Numeric(36, 2), nullable=True))


def downgrade() -> None:
    op.drop_column('price_snapshot', 'market_cap')
