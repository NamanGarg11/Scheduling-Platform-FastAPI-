"""create availability_exceptions table

Revision ID: d4e5f6a7b8c9
Revises: b2f7e6d5c4a3
Create Date: 2026-08-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'b2f7e6d5c4a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('availability_exceptions',
    sa.Column('host_id', sa.UUID(), nullable=False),
    sa.Column('exception_date', sa.Date(), nullable=False),
    sa.Column('kind', sa.Enum('BLOCK_FULL_DAY', 'BLOCK_PARTIAL', 'ADD_WINDOW', name='availabilityexceptionkind'), nullable=False),
    sa.Column('start_time', sa.Time(), nullable=True),
    sa.Column('end_time', sa.Time(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['host_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('host_id', 'exception_date', 'kind', 'start_time', 'end_time', name='uq_availability_exception_host_date_kind_times')
    )
    op.create_index(op.f('ix_availability_exceptions_host_id'), 'availability_exceptions', ['host_id'], unique=False)
    op.create_index(op.f('ix_availability_exceptions_host_date'), 'availability_exceptions', ['host_id', 'exception_date'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_availability_exceptions_host_date'), table_name='availability_exceptions')
    op.drop_index(op.f('ix_availability_exceptions_host_id'), table_name='availability_exceptions')
    op.drop_table('availability_exceptions')
    # Drop the enum type too: Postgres leaves enum types behind when a table is
    # dropped, which would break a subsequent `upgrade` on the same database.
    # (The pre-existing migrations for `dayofweek`/`slotstatus`/`bookingstatus`
    # have the same orphan-type limitation; ours drops it so the new migration's
    # downgrade/upgrade round-trip is clean.)
    op.execute('DROP TYPE IF EXISTS availabilityexceptionkind')
