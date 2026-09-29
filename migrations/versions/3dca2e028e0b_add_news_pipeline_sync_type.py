"""add news_pipeline sync type

Revision ID: 3dca2e028e0b
Revises: ee0b064b67d3
Create Date: 2026-09-29 17:47:52.293669

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3dca2e028e0b'
down_revision: Union[str, None] = 'ee0b064b67d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres native enum (see app/models/sync_log.py::SyncType) — a new
    # scheduler job (jobs.py::run_news_pipeline_sync) needs this value to
    # gate the news pipeline to once-per-24h via the same SyncLog table
    # every other scheduled job already uses.
    op.execute("ALTER TYPE synctype ADD VALUE IF NOT EXISTS 'NEWS_PIPELINE'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE — removing an enum value
    # would require rebuilding the type and every column/row that
    # references it. Left as a no-op, same accepted tradeoff any additive
    # native-enum migration makes; an unused enum value is harmless.
    pass
