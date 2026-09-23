"""add listings_range sync type

Revision ID: 9fbab21ed2d3
Revises: 2e238570ef98
Create Date: 2026-09-23 22:29:45.614291

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9fbab21ed2d3'
down_revision: Union[str, None] = '2e238570ef98'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New SyncType.LISTINGS_RANGE enum value — ADD VALUE can't run inside the
    # migration's normal transaction on Postgres, so it needs its own
    # autocommit block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE synctype ADD VALUE IF NOT EXISTS 'LISTINGS_RANGE'")


def downgrade() -> None:
    # Postgres has no DROP VALUE for enums; nothing to reverse.
    pass
