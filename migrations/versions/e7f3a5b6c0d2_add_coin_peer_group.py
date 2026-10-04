"""add coin peer_group

Revision ID: e7f3a5b6c0d2
Revises: d6e2f4a5b9c1
Create Date: 2026-10-05 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e7f3a5b6c0d2'
down_revision: Union[str, None] = 'd6e2f4a5b9c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('coins', sa.Column('peer_group', sa.String(length=60), nullable=True))


def downgrade() -> None:
    op.drop_column('coins', 'peer_group')
