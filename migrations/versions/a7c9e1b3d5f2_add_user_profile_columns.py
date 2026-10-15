"""add users.phone, address, avatar_url, banner_url

Revision ID: a7c9e1b3d5f2
Revises: f2a4c6e8b0d1
Create Date: 2026-10-15 14:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a7c9e1b3d5f2'
down_revision: Union[str, None] = 'f2a4c6e8b0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('phone', sa.String(length=32), nullable=True))
    op.add_column('users', sa.Column('address', sa.String(length=300), nullable=True))
    op.add_column('users', sa.Column('avatar_url', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('banner_url', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'banner_url')
    op.drop_column('users', 'avatar_url')
    op.drop_column('users', 'address')
    op.drop_column('users', 'phone')
