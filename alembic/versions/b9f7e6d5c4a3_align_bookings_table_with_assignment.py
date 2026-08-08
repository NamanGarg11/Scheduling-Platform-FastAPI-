"""Align bookings table with assignment contract

Revision ID: b2f7e6d5c4a3
Revises: a1b2c3d4e5f6
Create Date: 2026-08-09 00:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2f7e6d5c4a3'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Replace attendee FK with invitee details and add scheduling fields."""
    op.drop_index('ix_bookings_attendee_id', table_name='bookings')
    op.drop_constraint('bookings_attendee_id_fkey', 'bookings', type_='foreignkey')

    op.drop_column('bookings', 'attendee_id')

    op.add_column('bookings', sa.Column('event_type_id', sa.UUID(), nullable=False))
    op.add_column('bookings', sa.Column('invitee_email', sa.String(length=255), nullable=False))
    op.add_column('bookings', sa.Column('invitee_name', sa.String(length=100), nullable=False))
    op.add_column('bookings', sa.Column('invitee_notes', sa.Text(), nullable=True))
    op.add_column('bookings', sa.Column('meet_link', sa.String(length=500), nullable=True))
    op.add_column('bookings', sa.Column('calendar_event_id', sa.String(length=255), nullable=True))
    op.add_column('bookings', sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True))

    op.create_foreign_key(
        'bookings_event_type_id_fkey',
        'bookings',
        'event_types',
        ['event_type_id'],
        ['id'],
        ondelete='RESTRICT',
    )
    op.create_index('ix_bookings_event_type_id', 'bookings', ['event_type_id'], unique=False)


def downgrade() -> None:
    """Restore the attendee FK and remove the contract fields."""
    op.drop_index('ix_bookings_event_type_id', table_name='bookings')
    op.drop_constraint('bookings_event_type_id_fkey', 'bookings', type_='foreignkey')

    op.drop_column('bookings', 'cancelled_at')
    op.drop_column('bookings', 'calendar_event_id')
    op.drop_column('bookings', 'meet_link')
    op.drop_column('bookings', 'invitee_notes')
    op.drop_column('bookings', 'invitee_name')
    op.drop_column('bookings', 'invitee_email')
    op.drop_column('bookings', 'event_type_id')

    op.add_column('bookings', sa.Column('attendee_id', sa.UUID(), nullable=False))
    op.create_foreign_key(
        'bookings_attendee_id_fkey',
        'bookings',
        'users',
        ['attendee_id'],
        ['id'],
        ondelete='RESTRICT',
    )
    op.create_index('ix_bookings_attendee_id', 'bookings', ['attendee_id'], unique=False)