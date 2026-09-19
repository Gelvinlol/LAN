"""Add safe duty deletion

Revision ID: d06e8c5b291f
Revises: c95d3af481e2
Create Date: 2026-09-20
"""
from alembic import op
import sqlalchemy as sa


revision = 'd06e8c5b291f'
down_revision = 'c95d3af481e2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('duty_type', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'is_deleted', sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ))


def downgrade():
    with op.batch_alter_table('duty_type', schema=None) as batch_op:
        batch_op.drop_column('is_deleted')
