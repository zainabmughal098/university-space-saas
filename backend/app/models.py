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
