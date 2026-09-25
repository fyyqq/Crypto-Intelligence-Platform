"""add listings_hot sync type

Revision ID: 2e238570ef98
Revises: fbe2103efbc2
Create Date: 2026-09-23 18:17:49.522070

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2e238570ef98'
down_revision: Union[str, None] = 'fbe2103efbc2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New SyncType.LISTINGS_HOT enum value — ADD VALUE can't run inside the
    # migration's normal transaction on Postgres, so it needs its own
    # autocommit block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE synctype ADD VALUE IF NOT EXISTS 'LISTINGS_HOT'")


def downgrade() -> None:
    # Postgres has no DROP VALUE for enums; nothing to reverse.
    pass
