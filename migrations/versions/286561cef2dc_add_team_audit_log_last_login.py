"""add team audit_log last_login

Revision ID: 286561cef2dc
Revises: bc365bd0b9e9
Create Date: 2026-05-22 19:01:36.988095

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '286561cef2dc'
down_revision = 'bc365bd0b9e9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_login', sa.DateTime(), nullable=True))

    op.create_table('team',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('team_members',
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['team_id'], ['team.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('team_id', 'user_id')
    )
    op.create_table('audit_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=20), nullable=False),
        sa.Column('changed_by', sa.Integer(), nullable=True),
        sa.Column('changes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['changed_by'], ['user.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.create_index('ix_audit_log_user_id', ['user_id'])


def downgrade():
    op.drop_table('audit_log')
    op.drop_table('team_members')
    op.drop_table('team')
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('last_login')
