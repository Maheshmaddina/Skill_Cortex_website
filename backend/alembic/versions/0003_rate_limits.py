"""rate limit counters

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-14 14:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('rate_limit_counters',
    sa.Column('key', sa.String(length=100), nullable=False),
    sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('count', sa.Integer(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('key', 'window_start', name=op.f('pk_rate_limit_counters'))
    )
    op.create_index('ix_rate_limit_counters_expires_at', 'rate_limit_counters', ['expires_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_rate_limit_counters_expires_at', table_name='rate_limit_counters')
    op.drop_table('rate_limit_counters')
