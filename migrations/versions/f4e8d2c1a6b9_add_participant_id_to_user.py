"""add participant_id to user

Revision ID: f4e8d2c1a6b9
Revises: 3620d656ee10
Create Date: 2026-05-22 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f4e8d2c1a6b9'
down_revision = '3620d656ee10'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('participant_id', sa.String(length=20), nullable=True))
        batch_op.create_unique_constraint('uq_user_participant_id', ['participant_id'])


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_constraint('uq_user_participant_id', type_='unique')
        batch_op.drop_column('participant_id')
