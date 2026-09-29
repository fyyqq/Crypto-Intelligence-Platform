"""add telegram_pipeline sync type

Revision ID: 8f3c1a9e2b4d
Revises: 3dca2e028e0b
Create Date: 2026-09-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f3c1a9e2b4d'
down_revision: Union[str, None] = '3dca2e028e0b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres native enum (see app/models/sync_log.py::SyncType) — the new
    # scheduler job (jobs.py::run_telegram_pipeline_sync) needs this value
    # to gate the Telegram-group pipeline via the same SyncLog table every
    # other scheduled job already uses.
    op.execute("ALTER TYPE synctype ADD VALUE IF NOT EXISTS 'TELEGRAM_PIPELINE'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE — same accepted no-op
    # tradeoff as the prior additive enum migration (3dca2e028e0b).
    pass
