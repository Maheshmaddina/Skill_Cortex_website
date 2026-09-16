"""notification delivery: subject, template payload, retry bookkeeping

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-13 18:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('notifications', sa.Column('subject', sa.String(length=200), nullable=True))
    op.add_column('notifications', sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('notifications', sa.Column('attempts', sa.Integer(), server_default=sa.text('0'), nullable=False))
    op.add_column('notifications', sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_notifications_status_next_attempt_at', 'notifications', ['status', 'next_attempt_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_notifications_status_next_attempt_at', table_name='notifications')
    op.drop_column('notifications', 'next_attempt_at')
    op.drop_column('notifications', 'attempts')
    op.drop_column('notifications', 'payload')
    op.drop_column('notifications', 'subject')
