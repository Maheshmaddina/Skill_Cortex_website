"""learner set webinars

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-16 11:44:42.004777

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('slots', sa.Column('set_by_user_id', sa.UUID(), nullable=True))
    op.add_column('slots', sa.Column('learner_note', sa.String(length=500), nullable=True))
    op.create_index(op.f('ix_slots_set_by_user_id'), 'slots', ['set_by_user_id'], unique=False)
    op.create_foreign_key(op.f('fk_slots_set_by_user_id_users'), 'slots', 'users', ['set_by_user_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint(op.f('fk_slots_set_by_user_id_users'), 'slots', type_='foreignkey')
    op.drop_index(op.f('ix_slots_set_by_user_id'), table_name='slots')
    op.drop_column('slots', 'learner_note')
    op.drop_column('slots', 'set_by_user_id')
