"""add certificate and notification_preference tables

Revision ID: a795661b7c7d
Revises: e4f2b7a1c9d0
Create Date: 2026-07-04 22:32:45.655219

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a795661b7c7d'
down_revision = 'e4f2b7a1c9d0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('certificate',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('verification_code', sa.String(length=32), nullable=False),
        sa.Column('registration_id', sa.Integer(), nullable=False),
        sa.Column('issued_at', sa.DateTime(), nullable=True),
        sa.Column('pdf_path', sa.String(length=255), nullable=True),
        sa.Column('revoked', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['registration_id'], ['registration.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('verification_code')
    )
    op.create_table('notification_preference',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('event_reminders', sa.Boolean(), nullable=True),
        sa.Column('registration_confirmations', sa.Boolean(), nullable=True),
        sa.Column('waitlist_updates', sa.Boolean(), nullable=True),
        sa.Column('certificate_ready', sa.Boolean(), nullable=True),
        sa.Column('marketing_new_events', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('user_id')
    )


def downgrade():
    op.drop_table('notification_preference')
    op.drop_table('certificate')
