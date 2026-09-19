"""Add configurable duty shifts

Revision ID: f61c83a04d27
Revises: e4a739bd12f8
Create Date: 2026-09-19
"""
from alembic import op
import sqlalchemy as sa
import json


revision = 'f61c83a04d27'
down_revision = 'e4a739bd12f8'
branch_labels = None
depends_on = None


DEFAULTS = {
    1: [("15:00", "18:00"), ("00:00", "02:00"), ("06:00", "09:00")],
    2: [("18:00", "21:00"), ("02:00", "04:00"), ("09:00", "12:00")],
    3: [("21:00", "00:00"), ("04:00", "06:00"), ("12:00", "15:00")],
}


def upgrade():
    op.create_table(
        'duty_service_shift',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('duty_type_id', sa.Integer(), nullable=False),
        sa.Column('service_number', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.String(length=5), nullable=False),
        sa.Column('end_time', sa.String(length=5), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.CheckConstraint(
            'service_number IN (1, 2, 3)',
            name='ck_duty_service_shift_number',
        ),
        sa.ForeignKeyConstraint(['duty_type_id'], ['duty_type.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_duty_service_shift_duty_type_id',
        'duty_service_shift', ['duty_type_id'], unique=False
    )
    with op.batch_alter_table('duty_assignment', schema=None) as batch_op:
        batch_op.add_column(sa.Column('shift_snapshot', sa.Text(), nullable=True))

    connection = op.get_bind()
    duty_ids = [row[0] for row in connection.execute(sa.text('SELECT id FROM duty_type'))]
    shift_table = sa.table(
        'duty_service_shift',
        sa.column('duty_type_id', sa.Integer()),
        sa.column('service_number', sa.Integer()),
        sa.column('start_time', sa.String()),
        sa.column('end_time', sa.String()),
        sa.column('sequence', sa.Integer()),
    )
    rows = []
    for duty_id in duty_ids:
        for service_number, shifts in DEFAULTS.items():
            for sequence, (start, end) in enumerate(shifts):
                rows.append({
                    'duty_type_id': duty_id,
                    'service_number': service_number,
                    'start_time': start,
                    'end_time': end,
                    'sequence': sequence,
                })
    if rows:
        op.bulk_insert(shift_table, rows)

    for service_number, shifts in DEFAULTS.items():
        snapshot = json.dumps(
            [{'start': start, 'end': end} for start, end in shifts],
            ensure_ascii=False, separators=(',', ':'),
        )
        connection.execute(
            sa.text(
                'UPDATE duty_assignment SET shift_snapshot = :snapshot '
                'WHERE service_number = :service_number'
            ),
            {'snapshot': snapshot, 'service_number': service_number},
        )


def downgrade():
    with op.batch_alter_table('duty_assignment', schema=None) as batch_op:
        batch_op.drop_column('shift_snapshot')
    op.drop_index(
        'ix_duty_service_shift_duty_type_id',
        table_name='duty_service_shift'
    )
    op.drop_table('duty_service_shift')
