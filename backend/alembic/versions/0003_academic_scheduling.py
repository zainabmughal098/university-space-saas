"""Tenant-scoped academic scheduling foundation; no conflict detection."""

from alembic import op
import sqlalchemy as sa

revision = "0003_academic_scheduling"
down_revision = "0002_university_infrastructure"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('departments',
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_departments_workspace_id_workspaces')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_departments')),
    sa.UniqueConstraint('workspace_id', 'code', name='uq_departments_workspace_code'),
    sa.UniqueConstraint('workspace_id', 'id', name=op.f('uq_departments_workspace_id'))
    )
    op.create_table('courses',
    sa.Column('department_id', sa.Uuid(), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id', 'department_id'], ['departments.workspace_id', 'departments.id'], name=op.f('fk_courses_workspace_id_departments')),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_courses_workspace_id_workspaces')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_courses')),
    sa.UniqueConstraint('workspace_id', 'code', name='uq_courses_workspace_code'),
    sa.UniqueConstraint('workspace_id', 'id', name=op.f('uq_courses_workspace_id'))
    )
    op.create_index('ix_courses_workspace_department', 'courses', ['workspace_id', 'department_id'], unique=False)
    op.create_table('faculty',
    sa.Column('department_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id', 'department_id'], ['departments.workspace_id', 'departments.id'], name=op.f('fk_faculty_workspace_id_departments')),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_faculty_workspace_id_workspaces')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_faculty')),
    sa.UniqueConstraint('workspace_id', 'email', name='uq_faculty_workspace_email'),
    sa.UniqueConstraint('workspace_id', 'id', name=op.f('uq_faculty_workspace_id'))
    )
    op.create_index('ix_faculty_workspace_department', 'faculty', ['workspace_id', 'department_id'], unique=False)
    op.create_table('sections',
    sa.Column('course_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('student_count', sa.Integer(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.CheckConstraint('student_count > 0', name=op.f('ck_sections_positive_student_count')),
    sa.ForeignKeyConstraint(['workspace_id', 'course_id'], ['courses.workspace_id', 'courses.id'], name=op.f('fk_sections_workspace_id_courses')),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_sections_workspace_id_workspaces')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sections')),
    sa.UniqueConstraint('workspace_id', 'course_id', 'name', name='uq_sections_course_name'),
    sa.UniqueConstraint('workspace_id', 'id', name=op.f('uq_sections_workspace_id'))
    )
    op.create_table('schedule_entries',
    sa.Column('room_id', sa.Uuid(), nullable=False),
    sa.Column('section_id', sa.Uuid(), nullable=False),
    sa.Column('faculty_id', sa.Uuid(), nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.CheckConstraint('ends_at > starts_at', name=op.f('ck_schedule_entries_positive_interval')),
    sa.ForeignKeyConstraint(['workspace_id', 'faculty_id'], ['faculty.workspace_id', 'faculty.id'], name=op.f('fk_schedule_entries_workspace_id_faculty')),
    sa.ForeignKeyConstraint(['workspace_id', 'room_id'], ['rooms.workspace_id', 'rooms.id'], name=op.f('fk_schedule_entries_workspace_id_rooms')),
    sa.ForeignKeyConstraint(['workspace_id', 'section_id'], ['sections.workspace_id', 'sections.id'], name=op.f('fk_schedule_entries_workspace_id_sections')),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_schedule_entries_workspace_id_workspaces')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_schedule_entries'))
    )
    op.create_index('ix_schedule_entries_workspace_faculty_start', 'schedule_entries', ['workspace_id', 'faculty_id', 'starts_at'], unique=False)
    op.create_index('ix_schedule_entries_workspace_room_start', 'schedule_entries', ['workspace_id', 'room_id', 'starts_at'], unique=False)
    op.create_index('ix_schedule_entries_workspace_section_start', 'schedule_entries', ['workspace_id', 'section_id', 'starts_at'], unique=False)
    op.create_index('ix_schedule_entries_workspace_start', 'schedule_entries', ['workspace_id', 'starts_at'], unique=False)

def downgrade() -> None:
    op.drop_index('ix_schedule_entries_workspace_start', table_name='schedule_entries')
    op.drop_index('ix_schedule_entries_workspace_section_start', table_name='schedule_entries')
    op.drop_index('ix_schedule_entries_workspace_room_start', table_name='schedule_entries')
    op.drop_index('ix_schedule_entries_workspace_faculty_start', table_name='schedule_entries')
    op.drop_table('schedule_entries')
    op.drop_table('sections')
    op.drop_index('ix_faculty_workspace_department', table_name='faculty')
    op.drop_table('faculty')
    op.drop_index('ix_courses_workspace_department', table_name='courses')
    op.drop_table('courses')
    op.drop_table('departments')
