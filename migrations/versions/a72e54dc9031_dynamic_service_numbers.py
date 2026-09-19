"""Add dynamic service numbers and staffing counts

Revision ID: a72e54dc9031
Revises: f61c83a04d27
Create Date: 2026-09-19
"""
from alembic import op
import sqlalchemy as sa


revision = 'a72e54dc9031'
down_revision = 'f61c83a04d27'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'duty_number_requirement',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('duty_type_id', sa.Integer(), nullable=False),
        sa.Column('service_number', sa.Integer(), nullable=False),
        sa.Column('staff_count', sa.Integer(), nullable=False),
        sa.CheckConstraint('service_number > 0', name='ck_duty_number_positive'),
        sa.CheckConstraint('staff_count > 0', name='ck_duty_staff_count_positive'),
        sa.ForeignKeyConstraint(['duty_type_id'], ['duty_type.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'duty_type_id', 'service_number',
            name='uq_duty_number_requirement',
        ),
    )
    op.create_index(
        'ix_duty_number_requirement_duty_type_id',
        'duty_number_requirement', ['duty_type_id'], unique=False
    )

    connection = op.get_bind()
    connection.execute(sa.text(
        'INSERT INTO duty_number_requirement '
        '(duty_type_id, service_number, staff_count) '
        'SELECT DISTINCT duty_type_id, service_number, 1 '
        'FROM duty_service_shift'
    ))
    for service_number in (1, 2, 3):
        connection.execute(sa.text(
            'INSERT INTO duty_number_requirement '
            '(duty_type_id, service_number, staff_count) '
            'SELECT id, :service_number, 1 FROM duty_type '
            'WHERE NOT EXISTS ('
            'SELECT 1 FROM duty_service_shift '
            'WHERE duty_service_shift.duty_type_id = duty_type.id'
            ')'
        ), {'service_number': service_number})

    with op.batch_alter_table('duty_service_shift', schema=None) as batch_op:
        batch_op.drop_constraint('ck_duty_service_shift_number', type_='check')
    with op.batch_alter_table('duty_assignment', schema=None) as batch_op:
        batch_op.drop_constraint('ck_duty_assignment_service_number', type_='check')


def downgrade():
    # Values above 3 cannot be represented by the old schema.
    connection = op.get_bind()
    connection.execute(sa.text(
        'DELETE FROM duty_service_shift WHERE service_number NOT IN (1, 2, 3)'
    ))
    connection.execute(sa.text(
        'DELETE FROM duty_assignment WHERE service_number NOT IN (1, 2, 3)'
    ))
    with op.batch_alter_table('duty_assignment', schema=None) as batch_op:
        batch_op.create_check_constraint(
            'ck_duty_assignment_service_number',
            'service_number IN (1, 2, 3)',
        )
    with op.batch_alter_table('duty_service_shift', schema=None) as batch_op:
        batch_op.create_check_constraint(
            'ck_duty_service_shift_number',
            'service_number IN (1, 2, 3)',
        )
    op.drop_index(
        'ix_duty_number_requirement_duty_type_id',
        table_name='duty_number_requirement'
    )
    op.drop_table('duty_number_requirement')
