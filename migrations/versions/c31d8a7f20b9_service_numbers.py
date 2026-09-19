"""Use canonical service numbers

Revision ID: c31d8a7f20b9
Revises: 9b22a6c781d4
Create Date: 2026-09-16
"""
from alembic import op
import sqlalchemy as sa


revision = 'c31d8a7f20b9'
down_revision = '9b22a6c781d4'
branch_labels = None
depends_on = None


def upgrade():
    # Preserve every assignment; only clarify the meaning of the existing value.
    with op.batch_alter_table('duty_assignment', schema=None) as batch_op:
        batch_op.alter_column(
            'shift_number', new_column_name='service_number',
            existing_type=sa.Integer(), existing_nullable=True,
            nullable=False, existing_server_default=None,
        )
        batch_op.create_check_constraint(
            'ck_duty_assignment_service_number',
            'service_number IN (1, 2, 3)',
        )

    # These values are now compatibility metadata only. The application always
    # creates one assignment for each of the three canonical service numbers.
    op.execute('UPDATE duty_type SET team_size = 1, shifts_per_day = 3')
    op.drop_table('duty_time_slot')


def downgrade():
    op.create_table(
        'duty_time_slot',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('duty_type_id', sa.Integer(), nullable=False),
        sa.Column('shift_number', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.String(length=5), nullable=False),
        sa.Column('end_time', sa.String(length=5), nullable=False),
        sa.ForeignKeyConstraint(['duty_type_id'], ['duty_type.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('duty_assignment', schema=None) as batch_op:
        batch_op.drop_constraint('ck_duty_assignment_service_number', type_='check')
        batch_op.alter_column(
            'service_number', new_column_name='shift_number',
            existing_type=sa.Integer(), existing_nullable=False,
            nullable=True,
        )
