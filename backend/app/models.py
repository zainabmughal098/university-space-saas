"""A workspace is one university; membership is the tenant association.

Infrastructure composite foreign keys enforce same-workspace associations.
Queries still need explicit workspace filters; authorization and RLS are deferred.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (Boolean, CheckConstraint, DateTime, Enum, ForeignKey,
                        ForeignKeyConstraint, Index, Integer, String, Text,
                        UniqueConstraint, func, true)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MembershipRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), unique=True)
    default_timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan", passive_deletes=True
    )
    campuses: Mapped[list["Campus"]] = relationship(back_populates="workspace", passive_deletes="all")
    departments: Mapped[list["Department"]] = relationship(back_populates="workspace", passive_deletes="all")


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "workspace_id", name="uq_memberships_user_workspace"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # The unique index above also covers lookups by user_id.
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[MembershipRole] = mapped_column(Enum(
        MembershipRole, values_callable=lambda roles: [role.value for role in roles],
        native_enum=False, create_constraint=True, validate_strings=True,
        name="membership_role",
    ))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user: Mapped[User] = relationship(back_populates="memberships")
    workspace: Mapped[Workspace] = relationship(back_populates="memberships")


class InfrastructureRecord:
    """Explicit ownership; infrastructure parent assignment preserves workspace_id."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Campus(InfrastructureRecord, Base):
    __tablename__ = "campuses"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "code", name="uq_campuses_workspace_code"),
    )
    code: Mapped[str] = mapped_column(String(64))
    address: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    workspace: Mapped[Workspace] = relationship(back_populates="campuses")
    buildings: Mapped[list["Building"]] = relationship(
        primaryjoin="and_(Campus.workspace_id == Building.workspace_id, Campus.id == foreign(Building.campus_id))",
        back_populates="campus", passive_deletes="all",
    )


class Building(InfrastructureRecord, Base):
    __tablename__ = "buildings"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "campus_id", "code", name="uq_buildings_campus_code"),
        ForeignKeyConstraint(["workspace_id", "campus_id"], ["campuses.workspace_id", "campuses.id"]),
    )
    campus_id: Mapped[uuid.UUID] = mapped_column()
    code: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    campus: Mapped[Campus] = relationship(
        primaryjoin="and_(Building.workspace_id == Campus.workspace_id, foreign(Building.campus_id) == Campus.id)",
        back_populates="buildings",
    )
    floors: Mapped[list["Floor"]] = relationship(
        primaryjoin="and_(Building.workspace_id == Floor.workspace_id, Building.id == foreign(Floor.building_id))",
        back_populates="building", passive_deletes="all",
    )


class Floor(InfrastructureRecord, Base):
    __tablename__ = "floors"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "building_id", "floor_number", name="uq_floors_building_number"),
        ForeignKeyConstraint(["workspace_id", "building_id"], ["buildings.workspace_id", "buildings.id"]),
    )
    building_id: Mapped[uuid.UUID] = mapped_column()
    floor_number: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    building: Mapped[Building] = relationship(
        primaryjoin="and_(Floor.workspace_id == Building.workspace_id, foreign(Floor.building_id) == Building.id)",
        back_populates="floors",
    )
    rooms: Mapped[list["Room"]] = relationship(
        primaryjoin="and_(Floor.workspace_id == Room.workspace_id, Floor.id == foreign(Room.floor_id))",
        back_populates="floor", passive_deletes="all",
    )


class RoomType(InfrastructureRecord, Base):
    __tablename__ = "room_types"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "name", name="uq_room_types_workspace_name"),
    )
    description: Mapped[str | None] = mapped_column(Text)
    rooms: Mapped[list["Room"]] = relationship(
        primaryjoin="and_(RoomType.workspace_id == Room.workspace_id, RoomType.id == foreign(Room.room_type_id))",
        back_populates="room_type", passive_deletes="all",
    )


class Room(InfrastructureRecord, Base):
    __tablename__ = "rooms"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "code", name="uq_rooms_workspace_code"),
        ForeignKeyConstraint(["workspace_id", "floor_id"], ["floors.workspace_id", "floors.id"]),
        ForeignKeyConstraint(["workspace_id", "room_type_id"], ["room_types.workspace_id", "room_types.id"]),
        CheckConstraint("capacity > 0", name="positive_capacity"),
        Index("ix_rooms_workspace_floor", "workspace_id", "floor_id"),
        Index("ix_rooms_workspace_room_type", "workspace_id", "room_type_id"),
    )
    floor_id: Mapped[uuid.UUID] = mapped_column()
    room_type_id: Mapped[uuid.UUID] = mapped_column()
    code: Mapped[str] = mapped_column(String(64))
    capacity: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    floor: Mapped[Floor] = relationship(
        primaryjoin="and_(Room.workspace_id == Floor.workspace_id, foreign(Room.floor_id) == Floor.id)",
        back_populates="rooms",
    )
    room_type: Mapped[RoomType] = relationship(
        primaryjoin="and_(Room.workspace_id == RoomType.workspace_id, foreign(Room.room_type_id) == RoomType.id)",
        back_populates="rooms",
    )
    facility_links: Mapped[list["RoomFacility"]] = relationship(
        primaryjoin="and_(Room.workspace_id == RoomFacility.workspace_id, Room.id == foreign(RoomFacility.room_id))",
        back_populates="room", cascade="all, delete-orphan", passive_deletes=True,
    )
    facilities: Mapped[list["Facility"]] = relationship(
        secondary="room_facilities", viewonly=True, back_populates="rooms",
    )
    schedule_entries: Mapped[list["ScheduleEntry"]] = relationship(
        primaryjoin="and_(Room.workspace_id == ScheduleEntry.workspace_id, Room.id == foreign(ScheduleEntry.room_id))",
        back_populates="room", passive_deletes="all",
    )


class Facility(InfrastructureRecord, Base):
    __tablename__ = "facilities"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "name", name="uq_facilities_workspace_name"),
    )
    description: Mapped[str | None] = mapped_column(Text)
    room_links: Mapped[list["RoomFacility"]] = relationship(
        primaryjoin="and_(Facility.workspace_id == RoomFacility.workspace_id, Facility.id == foreign(RoomFacility.facility_id))",
        back_populates="facility", cascade="all, delete-orphan", passive_deletes=True,
    )
    rooms: Mapped[list[Room]] = relationship(
        secondary="room_facilities", viewonly=True, back_populates="facilities",
    )


class RoomFacility(Base):
    __tablename__ = "room_facilities"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "room_id"], ["rooms.workspace_id", "rooms.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["workspace_id", "facility_id"], ["facilities.workspace_id", "facilities.id"], ondelete="CASCADE"),
        Index("ix_room_facilities_workspace_room", "workspace_id", "room_id"),
        Index("ix_room_facilities_workspace_facility", "workspace_id", "facility_id"),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    room_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    facility_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    room: Mapped[Room] = relationship(
        primaryjoin="and_(RoomFacility.workspace_id == Room.workspace_id, foreign(RoomFacility.room_id) == Room.id)",
        back_populates="facility_links",
    )
    facility: Mapped[Facility] = relationship(
        primaryjoin="and_(RoomFacility.workspace_id == Facility.workspace_id, foreign(RoomFacility.facility_id) == Facility.id)",
        back_populates="room_links",
    )


class AcademicRecord:
    """Tenant-owned academic data; parent assignment preserves explicit ownership."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())


class Department(AcademicRecord, Base):
    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "code", name="uq_departments_workspace_code"),
    )
    name: Mapped[str] = mapped_column(String(255))
    code: Mapped[str] = mapped_column(String(64))
    workspace: Mapped[Workspace] = relationship(back_populates="departments")
    faculty: Mapped[list["Faculty"]] = relationship(
        primaryjoin="and_(Department.workspace_id == Faculty.workspace_id, Department.id == foreign(Faculty.department_id))",
        back_populates="department", passive_deletes="all",
    )
    courses: Mapped[list["Course"]] = relationship(
        primaryjoin="and_(Department.workspace_id == Course.workspace_id, Department.id == foreign(Course.department_id))",
        back_populates="department", passive_deletes="all",
    )


class Faculty(AcademicRecord, Base):
    __tablename__ = "faculty"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "email", name="uq_faculty_workspace_email"),
        ForeignKeyConstraint(["workspace_id", "department_id"], ["departments.workspace_id", "departments.id"]),
        Index("ix_faculty_workspace_department", "workspace_id", "department_id"),
    )
    department_id: Mapped[uuid.UUID] = mapped_column()
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(320))
    department: Mapped[Department] = relationship(
        primaryjoin="and_(Faculty.workspace_id == Department.workspace_id, foreign(Faculty.department_id) == Department.id)",
        back_populates="faculty",
    )
    schedule_entries: Mapped[list["ScheduleEntry"]] = relationship(
        primaryjoin="and_(Faculty.workspace_id == ScheduleEntry.workspace_id, Faculty.id == foreign(ScheduleEntry.faculty_id))",
        back_populates="faculty", passive_deletes="all",
    )


class Course(AcademicRecord, Base):
    __tablename__ = "courses"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "code", name="uq_courses_workspace_code"),
        ForeignKeyConstraint(["workspace_id", "department_id"], ["departments.workspace_id", "departments.id"]),
        Index("ix_courses_workspace_department", "workspace_id", "department_id"),
    )
    department_id: Mapped[uuid.UUID] = mapped_column()
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    department: Mapped[Department] = relationship(
        primaryjoin="and_(Course.workspace_id == Department.workspace_id, foreign(Course.department_id) == Department.id)",
        back_populates="courses",
    )
    sections: Mapped[list["Section"]] = relationship(
        primaryjoin="and_(Course.workspace_id == Section.workspace_id, Course.id == foreign(Section.course_id))",
        back_populates="course", passive_deletes="all",
    )


class Section(AcademicRecord, Base):
    __tablename__ = "sections"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "course_id", "name", name="uq_sections_course_name"),
        ForeignKeyConstraint(["workspace_id", "course_id"], ["courses.workspace_id", "courses.id"]),
        CheckConstraint("student_count > 0", name="positive_student_count"),
    )
    course_id: Mapped[uuid.UUID] = mapped_column()
    name: Mapped[str] = mapped_column(String(255))
    student_count: Mapped[int] = mapped_column(Integer)
    course: Mapped[Course] = relationship(
        primaryjoin="and_(Section.workspace_id == Course.workspace_id, foreign(Section.course_id) == Course.id)",
        back_populates="sections",
    )
    schedule_entries: Mapped[list["ScheduleEntry"]] = relationship(
        primaryjoin="and_(Section.workspace_id == ScheduleEntry.workspace_id, Section.id == foreign(ScheduleEntry.section_id))",
        back_populates="section", passive_deletes="all",
    )


class ScheduleEntry(AcademicRecord, Base):
    """Actual class occupancy in a room during [starts_at, ends_at).

    Adjacent intervals share no occupied instant. Overlaps are intentionally not
    checked in this phase; no recurrence, reservation, or exclusion semantics.
    """

    __tablename__ = "schedule_entries"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "room_id"], ["rooms.workspace_id", "rooms.id"]),
        ForeignKeyConstraint(["workspace_id", "section_id"], ["sections.workspace_id", "sections.id"]),
        ForeignKeyConstraint(["workspace_id", "faculty_id"], ["faculty.workspace_id", "faculty.id"]),
        CheckConstraint("ends_at > starts_at", name="positive_interval"),
        Index("ix_schedule_entries_workspace_start", "workspace_id", "starts_at"),
        Index("ix_schedule_entries_workspace_room_start", "workspace_id", "room_id", "starts_at"),
        Index("ix_schedule_entries_workspace_section_start", "workspace_id", "section_id", "starts_at"),
        Index("ix_schedule_entries_workspace_faculty_start", "workspace_id", "faculty_id", "starts_at"),
    )
    room_id: Mapped[uuid.UUID] = mapped_column()
    section_id: Mapped[uuid.UUID] = mapped_column()
    faculty_id: Mapped[uuid.UUID] = mapped_column()
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    room: Mapped[Room] = relationship(
        primaryjoin="and_(ScheduleEntry.workspace_id == Room.workspace_id, foreign(ScheduleEntry.room_id) == Room.id)",
        back_populates="schedule_entries",
    )
    section: Mapped[Section] = relationship(
        primaryjoin="and_(ScheduleEntry.workspace_id == Section.workspace_id, foreign(ScheduleEntry.section_id) == Section.id)",
        back_populates="schedule_entries",
    )
    faculty: Mapped[Faculty] = relationship(
        primaryjoin="and_(ScheduleEntry.workspace_id == Faculty.workspace_id, foreign(ScheduleEntry.faculty_id) == Faculty.id)",
        back_populates="schedule_entries",
    )


class ReservationStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class Reservation(Base):
    """Ad-hoc [starts_at, ends_at) booking; membership FKs preserve tenant identity."""
    __tablename__ = "reservations"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "room_id"], ["rooms.workspace_id", "rooms.id"]),
        ForeignKeyConstraint(["requested_by_user_id", "workspace_id"], ["memberships.user_id", "memberships.workspace_id"]),
        ForeignKeyConstraint(["reviewed_by_user_id", "workspace_id"], ["memberships.user_id", "memberships.workspace_id"]),
        CheckConstraint("ends_at > starts_at", name="positive_interval"),
        CheckConstraint("expected_attendees > 0", name="positive_attendees"),
        CheckConstraint("(reviewed_by_user_id IS NULL AND reviewed_at IS NULL) OR (reviewed_by_user_id IS NOT NULL AND reviewed_at IS NOT NULL)", name="review_pair"),
        CheckConstraint("status NOT IN ('approved', 'rejected') OR reviewed_by_user_id IS NOT NULL", name="review_required"),
        Index("ix_reservations_workspace_status", "workspace_id", "status"),
        Index("ix_reservations_workspace_room_start", "workspace_id", "room_id", "starts_at"),
        Index("ix_reservations_requester_workspace", "requested_by_user_id", "workspace_id"),
        Index("ix_reservations_reviewer_workspace", "reviewed_by_user_id", "workspace_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    room_id: Mapped[uuid.UUID] = mapped_column()
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expected_attendees: Mapped[int] = mapped_column(Integer)
    status: Mapped[ReservationStatus] = mapped_column(Enum(
        ReservationStatus, values_callable=lambda values: [value.value for value in values],
        native_enum=False, create_constraint=True, validate_strings=True, name="reservation_status",
    ), default=ReservationStatus.PENDING, server_default="pending")
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    room: Mapped[Room] = relationship(primaryjoin="and_(Reservation.workspace_id == Room.workspace_id, foreign(Reservation.room_id) == Room.id)")
    requester: Mapped[User] = relationship(foreign_keys=[requested_by_user_id])
    reviewer: Mapped[User | None] = relationship(foreign_keys=[reviewed_by_user_id])
