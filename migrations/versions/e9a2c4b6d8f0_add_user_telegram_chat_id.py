"""add users.telegram_chat_id

Revision ID: e9a2c4b6d8f0
Revises: d5e8f1a3b7c9
Create Date: 2026-10-14 20:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e9a2c4b6d8f0'
down_revision: Union[str, None] = 'd5e8f1a3b7c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('telegram_chat_id', sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'telegram_chat_id')
