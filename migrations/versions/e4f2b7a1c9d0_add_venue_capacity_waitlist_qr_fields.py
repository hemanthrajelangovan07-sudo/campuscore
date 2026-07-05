"""add venue, capacity/waitlist, qr check-in fields

Revision ID: e4f2b7a1c9d0
Revises: 8d9ee78a6c5e
Create Date: 2026-07-04 21:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e4f2b7a1c9d0'
down_revision = '8d9ee78a6c5e'
branch_labels = None
depends_on = None


def upgrade():
    # ── Venue table ──────────────────────────────────────────────────
    op.create_table('venue',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('capacity', sa.Integer(), nullable=False),
        sa.Column('location', sa.String(length=200), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # ── Event additions ──────────────────────────────────────────────
    with op.batch_alter_table('event') as batch_op:
        batch_op.add_column(sa.Column('venue_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('start_time', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('end_time', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('pdf_file', sa.String(length=255), nullable=True))
        batch_op.create_foreign_key('fk_event_venue_id', 'venue', ['venue_id'], ['id'])

    # ── Registration additions ───────────────────────────────────────
    with op.batch_alter_table('registration') as batch_op:
        batch_op.add_column(sa.Column('status', sa.String(length=20), nullable=True,
                                       server_default='confirmed'))
        batch_op.add_column(sa.Column('waitlist_position', sa.Integer(), nullable=True))

    # ── Attendance additions ─────────────────────────────────────────
    with op.batch_alter_table('attendance') as batch_op:
        batch_op.add_column(sa.Column('registration_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('method', sa.String(length=20), nullable=True,
                                       server_default='manual'))
        batch_op.add_column(sa.Column('checked_in_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('checked_in_by', sa.Integer(), nullable=True))
        batch_op.create_unique_constraint('uq_attendance_registration_id', ['registration_id'])
        batch_op.create_foreign_key('fk_attendance_registration_id', 'registration',
                                     ['registration_id'], ['id'])
        batch_op.create_foreign_key('fk_attendance_checked_in_by', 'user',
                                     ['checked_in_by'], ['id'])


def downgrade():
    # ── Attendance reversals ─────────────────────────────────────────
    with op.batch_alter_table('attendance') as batch_op:
        batch_op.drop_constraint('fk_attendance_checked_in_by', type_='foreignkey')
        batch_op.drop_constraint('fk_attendance_registration_id', type_='foreignkey')
        batch_op.drop_constraint('uq_attendance_registration_id', type_='unique')
        batch_op.drop_column('checked_in_by')
        batch_op.drop_column('checked_in_at')
        batch_op.drop_column('method')
        batch_op.drop_column('registration_id')

    # ── Registration reversals ───────────────────────────────────────
    with op.batch_alter_table('registration') as batch_op:
        batch_op.drop_column('waitlist_position')
        batch_op.drop_column('status')

    # ── Event reversals ──────────────────────────────────────────────
    with op.batch_alter_table('event') as batch_op:
        batch_op.drop_constraint('fk_event_venue_id', type_='foreignkey')
        batch_op.drop_column('pdf_file')
        batch_op.drop_column('end_time')
        batch_op.drop_column('start_time')
        batch_op.drop_column('venue_id')

    # ── Venue table ──────────────────────────────────────────────────
    op.drop_table('venue')
