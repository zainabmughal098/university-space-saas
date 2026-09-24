"""Tenant-owned room reservations and review metadata."""
from alembic import op
import sqlalchemy as sa

revision = "0004_room_reservations"
down_revision = "0003_academic_scheduling"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table('reservations',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('room_id', sa.Uuid(), nullable=False),
    sa.Column('requested_by_user_id', sa.Uuid(), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expected_attendees', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('pending', 'approved', 'rejected', 'cancelled', name='reservation_status', native_enum=False, create_constraint=True), server_default='pending', nullable=False),
    sa.Column('reviewed_by_user_id', sa.Uuid(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('rejection_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("status NOT IN ('approved', 'rejected') OR reviewed_by_user_id IS NOT NULL", name=op.f('ck_reservations_review_required')),
    sa.CheckConstraint('(reviewed_by_user_id IS NULL AND reviewed_at IS NULL) OR (reviewed_by_user_id IS NOT NULL AND reviewed_at IS NOT NULL)', name=op.f('ck_reservations_review_pair')),
    sa.CheckConstraint('ends_at > starts_at', name=op.f('ck_reservations_positive_interval')),
    sa.CheckConstraint('expected_attendees > 0', name=op.f('ck_reservations_positive_attendees')),
    sa.ForeignKeyConstraint(['requested_by_user_id', 'workspace_id'], ['memberships.user_id', 'memberships.workspace_id'], name=op.f('fk_reservations_requested_by_user_id_memberships')),
    sa.ForeignKeyConstraint(['requested_by_user_id'], ['users.id'], name=op.f('fk_reservations_requested_by_user_id_users')),
    sa.ForeignKeyConstraint(['reviewed_by_user_id', 'workspace_id'], ['memberships.user_id', 'memberships.workspace_id'], name=op.f('fk_reservations_reviewed_by_user_id_memberships')),
    sa.ForeignKeyConstraint(['reviewed_by_user_id'], ['users.id'], name=op.f('fk_reservations_reviewed_by_user_id_users')),
    sa.ForeignKeyConstraint(['workspace_id', 'room_id'], ['rooms.workspace_id', 'rooms.id'], name=op.f('fk_reservations_workspace_id_rooms')),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_reservations_workspace_id_workspaces')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reservations'))
    )
    op.create_index('ix_reservations_requester_workspace', 'reservations', ['requested_by_user_id', 'workspace_id'], unique=False)
    op.create_index('ix_reservations_reviewer_workspace', 'reservations', ['reviewed_by_user_id', 'workspace_id'], unique=False)
    op.create_index('ix_reservations_workspace_room_start', 'reservations', ['workspace_id', 'room_id', 'starts_at'], unique=False)
    op.create_index('ix_reservations_workspace_status', 'reservations', ['workspace_id', 'status'], unique=False)

def downgrade() -> None:
    op.drop_index('ix_reservations_workspace_status', table_name='reservations')
    op.drop_index('ix_reservations_workspace_room_start', table_name='reservations')
    op.drop_index('ix_reservations_reviewer_workspace', table_name='reservations')
    op.drop_index('ix_reservations_requester_workspace', table_name='reservations')
    op.drop_table('reservations')
