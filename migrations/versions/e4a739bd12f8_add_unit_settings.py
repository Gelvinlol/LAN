"""Add unit settings

Revision ID: e4a739bd12f8
Revises: c31d8a7f20b9
Create Date: 2026-09-19
"""
from alembic import op
import sqlalchemy as sa


revision = 'e4a739bd12f8'
down_revision = 'c31d8a7f20b9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'unit_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('camp_name', sa.String(length=150), nullable=False),
        sa.Column('unit_name', sa.String(length=150), nullable=False),
        sa.Column('battalion_name', sa.String(length=150), nullable=False),
        sa.Column('branch', sa.String(length=100), nullable=False),
        sa.Column('formation_name', sa.String(length=150), nullable=True),
        sa.Column('unit_code', sa.String(length=50), nullable=True),
        sa.Column('location', sa.String(length=200), nullable=True),
        sa.Column('commander_rank', sa.String(length=80), nullable=True),
        sa.Column('commander_name', sa.String(length=120), nullable=True),
        sa.Column('contact_phone', sa.String(length=30), nullable=True),
        sa.Column('contact_email', sa.String(length=120), nullable=True),
        sa.Column('motto', sa.String(length=200), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('updated_by', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['updated_by'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('unit_settings')
