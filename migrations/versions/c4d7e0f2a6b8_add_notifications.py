"""add notifications

Revision ID: c4d7e0f2a6b8
Revises: b3c6d9e1f5a7
Create Date: 2026-10-12 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c4d7e0f2a6b8'
down_revision: Union[str, None] = 'b3c6d9e1f5a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('kind', sa.String(length=40), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('link_url', sa.String(length=300), nullable=True),
        sa.Column('image_url', sa.String(length=300), nullable=True),
        sa.Column('tone', sa.String(length=10), nullable=False, server_default='info'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_notifications_user_created', 'notifications', ['user_id', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_notifications_user_created', table_name='notifications')
    op.drop_table('notifications')
