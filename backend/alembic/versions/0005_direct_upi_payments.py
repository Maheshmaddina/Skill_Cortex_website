"""direct upi payments

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-16 16:52:48.711903

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


payment_method = sa.Enum('RAZORPAY', 'UPI', name='payment_method')


def upgrade() -> None:
    payment_method.create(op.get_bind(), checkfirst=True)
    op.add_column('payments', sa.Column('method', payment_method, server_default='RAZORPAY', nullable=False))
    op.add_column('payments', sa.Column('upi_reference', sa.String(length=32), nullable=True))
    op.alter_column('payments', 'razorpay_order_id', existing_type=sa.VARCHAR(length=64), nullable=True)
    op.create_unique_constraint(op.f('uq_payments_upi_reference'), 'payments', ['upi_reference'])
    op.create_check_constraint(
        op.f('ck_payments_razorpay_order_matches_method'),
        'payments',
        "(method = 'RAZORPAY') = (razorpay_order_id IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f('ck_payments_upi_reference_matches_method'),
        'payments',
        "(method = 'UPI') = (upi_reference IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_payments_upi_reference_matches_method'), 'payments', type_='check')
    op.drop_constraint(op.f('ck_payments_razorpay_order_matches_method'), 'payments', type_='check')
    op.drop_constraint(op.f('uq_payments_upi_reference'), 'payments', type_='unique')
    op.execute("DELETE FROM payments WHERE method = 'UPI'")
    op.alter_column('payments', 'razorpay_order_id', existing_type=sa.VARCHAR(length=64), nullable=False)
    op.drop_column('payments', 'upi_reference')
    op.drop_column('payments', 'method')
    payment_method.drop(op.get_bind(), checkfirst=True)
