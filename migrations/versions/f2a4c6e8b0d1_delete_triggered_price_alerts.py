"""delete triggered price alerts

Triggered alerts are no longer kept (the /alerts history was removed; the notification is the record).

Revision ID: f2a4c6e8b0d1
Revises: e9a2c4b6d8f0
Create Date: 2026-10-15 12:00:00

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'f2a4c6e8b0d1'
down_revision: Union[str, None] = 'e9a2c4b6d8f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DELETE FROM price_alerts WHERE triggered_at IS NOT NULL")


def downgrade() -> None:
    pass  # deleted rows cannot be restored
