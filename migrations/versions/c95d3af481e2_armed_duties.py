"""Add armed-duty requirement

Revision ID: c95d3af481e2
Revises: b84c19e7d2a6
Create Date: 2026-09-19
"""
from alembic import op
import sqlalchemy as sa


revision = 'c95d3af481e2'
down_revision = 'b84c19e7d2a6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('duty_type', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'requires_weapon', sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ))


def downgrade():
    with op.batch_alter_table('duty_type', schema=None) as batch_op:
        batch_op.drop_column('requires_weapon')
