"""Tenant-scoped university infrastructure."""

from alembic import op
import sqlalchemy as sa

revision = "0002_university_infrastructure"
down_revision = "0001_initial_tenants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('campuses',
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('address', sa.Text(), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_campuses_workspace_id_workspaces')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_campuses')),
    sa.UniqueConstraint('workspace_id', 'code', name='uq_campuses_workspace_code'),
    sa.UniqueConstraint('workspace_id', 'id', name=op.f('uq_campuses_workspace_id'))
    )
    op.create_table('facilities',
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_facilities_workspace_id_workspaces')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_facilities')),
    sa.UniqueConstraint('workspace_id', 'id', name=op.f('uq_facilities_workspace_id')),
    sa.UniqueConstraint('workspace_id', 'name', name='uq_facilities_workspace_name')
    )
    op.create_table('room_types',
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_room_types_workspace_id_workspaces')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_room_types')),
    sa.UniqueConstraint('workspace_id', 'id', name=op.f('uq_room_types_workspace_id')),
    sa.UniqueConstraint('workspace_id', 'name', name='uq_room_types_workspace_name')
    )
    op.create_table('buildings',
    sa.Column('campus_id', sa.Uuid(), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id', 'campus_id'], ['campuses.workspace_id', 'campuses.id'], name=op.f('fk_buildings_workspace_id_campuses')),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_buildings_workspace_id_workspaces')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_buildings')),
    sa.UniqueConstraint('workspace_id', 'campus_id', 'code', name='uq_buildings_campus_code'),
    sa.UniqueConstraint('workspace_id', 'id', name=op.f('uq_buildings_workspace_id'))
    )
    op.create_table('floors',
    sa.Column('building_id', sa.Uuid(), nullable=False),
    sa.Column('floor_number', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id', 'building_id'], ['buildings.workspace_id', 'buildings.id'], name=op.f('fk_floors_workspace_id_buildings')),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_floors_workspace_id_workspaces')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_floors')),
    sa.UniqueConstraint('workspace_id', 'building_id', 'floor_number', name='uq_floors_building_number'),
    sa.UniqueConstraint('workspace_id', 'id', name=op.f('uq_floors_workspace_id'))
    )
    op.create_table('rooms',
    sa.Column('floor_id', sa.Uuid(), nullable=False),
    sa.Column('room_type_id', sa.Uuid(), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('capacity', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint('capacity > 0', name=op.f('ck_rooms_positive_capacity')),
    sa.ForeignKeyConstraint(['workspace_id', 'floor_id'], ['floors.workspace_id', 'floors.id'], name=op.f('fk_rooms_workspace_id_floors')),
    sa.ForeignKeyConstraint(['workspace_id', 'room_type_id'], ['room_types.workspace_id', 'room_types.id'], name=op.f('fk_rooms_workspace_id_room_types')),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_rooms_workspace_id_workspaces')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_rooms')),
    sa.UniqueConstraint('workspace_id', 'code', name='uq_rooms_workspace_code'),
    sa.UniqueConstraint('workspace_id', 'id', name=op.f('uq_rooms_workspace_id'))
    )
    op.create_index('ix_rooms_workspace_floor', 'rooms', ['workspace_id', 'floor_id'], unique=False)
    op.create_index('ix_rooms_workspace_room_type', 'rooms', ['workspace_id', 'room_type_id'], unique=False)
    op.create_table('room_facilities',
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('room_id', sa.Uuid(), nullable=False),
    sa.Column('facility_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id', 'facility_id'], ['facilities.workspace_id', 'facilities.id'], name=op.f('fk_room_facilities_workspace_id_facilities'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id', 'room_id'], ['rooms.workspace_id', 'rooms.id'], name=op.f('fk_room_facilities_workspace_id_rooms'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_room_facilities_workspace_id_workspaces')),
    sa.PrimaryKeyConstraint('room_id', 'facility_id', name=op.f('pk_room_facilities'))
    )
    op.create_index('ix_room_facilities_workspace_facility', 'room_facilities', ['workspace_id', 'facility_id'], unique=False)
    op.create_index('ix_room_facilities_workspace_room', 'room_facilities', ['workspace_id', 'room_id'], unique=False)

def downgrade() -> None:
    op.drop_index('ix_room_facilities_workspace_room', table_name='room_facilities')
    op.drop_index('ix_room_facilities_workspace_facility', table_name='room_facilities')
    op.drop_table('room_facilities')
    op.drop_index('ix_rooms_workspace_room_type', table_name='rooms')
    op.drop_index('ix_rooms_workspace_floor', table_name='rooms')
    op.drop_table('rooms')
    op.drop_table('floors')
    op.drop_table('buildings')
    op.drop_table('room_types')
    op.drop_table('facilities')
    op.drop_table('campuses')
