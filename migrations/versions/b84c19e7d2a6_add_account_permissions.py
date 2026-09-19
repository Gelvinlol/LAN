"""Add account permissions

Revision ID: b84c19e7d2a6
Revises: a72e54dc9031
Create Date: 2026-09-19
"""
from alembic import op
import sqlalchemy as sa

from permissions import ALL_PERMISSION_KEYS


revision = 'b84c19e7d2a6'
down_revision = 'a72e54dc9031'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'user_permission',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('permission_key', sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'permission_key', name='uq_user_permission'),
    )
    op.create_index(
        'ix_user_permission_user_id', 'user_permission', ['user_id'], unique=False
    )

    # Existing accounts retain their current access. The commander can then
    # narrow it from the new account-management screen.
    connection = op.get_bind()
    for permission_key in ALL_PERMISSION_KEYS:
        connection.execute(sa.text(
            'INSERT INTO user_permission (user_id, permission_key) '
            'SELECT id, :permission_key FROM "user"'
        ), {'permission_key': permission_key})


def downgrade():
    op.drop_index('ix_user_permission_user_id', table_name='user_permission')
    op.drop_table('user_permission')
