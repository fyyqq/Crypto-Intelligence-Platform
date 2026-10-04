"""add coin category source and checked_at

Revision ID: d6e2f4a5b9c1
Revises: c5d1e3f4a7b8
Create Date: 2026-10-04 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd6e2f4a5b9c1'
down_revision: Union[str, None] = 'c5d1e3f4a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('coins', sa.Column('category_source', sa.String(length=20), nullable=True))
    op.add_column('coins', sa.Column('category_checked_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('coins', 'category_checked_at')
    op.drop_column('coins', 'category_source')
