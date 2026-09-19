"""Add medical cases

Revision ID: 9b22a6c781d4
Revises: 67faa6f11eff
Create Date: 2026-09-16
"""
from alembic import op
import sqlalchemy as sa


revision = '9b22a6c781d4'
down_revision = '67faa6f11eff'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'medical_case',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('soldier_id', sa.Integer(), nullable=False),
        sa.Column('illness', sa.String(length=200), nullable=False),
        sa.Column('location', sa.String(length=20), nullable=False),
        sa.Column('attends_roll_call', sa.Boolean(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['user.id']),
        sa.ForeignKeyConstraint(['soldier_id'], ['soldier.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_medical_case_active_dates', 'medical_case',
        ['start_date', 'end_date'], unique=False
    )


def downgrade():
    op.drop_index('ix_medical_case_active_dates', table_name='medical_case')
    op.drop_table('medical_case')
