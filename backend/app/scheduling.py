"""Deterministic tenant-scoped scheduling and availability; no ranking or AI."""

from collections import defaultdict
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.errors import APIError
from app.scheduling_schemas import (AvailabilityQuery, AvailableRoom, ConflictResult,
                                    IntervalQuery, RoomAvailability, ScheduleConflict)


class SchedulingService:
    def __init__(self, session: Session, workspace_id: UUID):
        self.session = session
        self.workspace_id = workspace_id

    def lock_workspace(self) -> None:
        """Serialize API schedule writes per university until commit/rollback.

        PostgreSQL READ COMMITTED gives the subsequent conflict query a fresh
        snapshot after acquiring this lock. SQLite test databases do not provide
        equivalent row locking. Direct SQL writers must follow the same protocol.
        """
        found = self.session.scalar(select(models.Workspace.id).where(
            models.Workspace.id == self.workspace_id,
        ).with_for_update())
        if found is None:
            raise APIError(404, "workspace_not_found", "Workspace not found.")

    def parent(self, model, resource_id: UUID, field: str, *, lock: bool = False):
        query = select(model).where(model.workspace_id == self.workspace_id, model.id == resource_id)
        if lock:
            query = query.with_for_update()
        record = self.session.scalar(query)
        if record is None:
            raise APIError(422, "invalid_parent", f"{field} must reference a resource in this workspace.")
        return record

    @staticmethod
    def overlap(starts_at: datetime, ends_at: datetime):
        entry = models.ScheduleEntry
        return and_(entry.starts_at < ends_at, entry.ends_at > starts_at)

    def conflicts(self, starts_at: datetime, ends_at: datetime, *, room_id: UUID | None = None,
                  faculty_id: UUID | None = None, section_id: UUID | None = None,
                  exclude_id: UUID | None = None) -> ConflictResult:
        entry = models.ScheduleEntry
        references = [("room", entry.room_id, room_id), ("faculty", entry.faculty_id, faculty_id),
                      ("section", entry.section_id, section_id)]
        matches = [column == value for _, column, value in references if value is not None]
        if not matches:
            return ConflictResult(has_conflicts=False, conflicts=[])
        query = select(entry).where(entry.workspace_id == self.workspace_id, entry.is_active.is_(True),
                                    self.overlap(starts_at, ends_at), or_(*matches))
        if exclude_id is not None:
            query = query.where(entry.id != exclude_id)
        rows = self.session.scalars(query.order_by(entry.starts_at, entry.ends_at, entry.id))
        conflicts = [ScheduleConflict(
            schedule_entry_id=row.id,
            conflict_types=[kind for kind, _, value in references
                            if value is not None and getattr(row, kind + "_id") == value],
            room_id=row.room_id, faculty_id=row.faculty_id, section_id=row.section_id,
            starts_at=row.starts_at, ends_at=row.ends_at,
        ) for row in rows]
        return ConflictResult(has_conflicts=bool(conflicts), conflicts=conflicts)

    def validate_schedule(self, values: dict, record=None) -> None:
        """Validate the merged proposal after the caller locks this workspace."""
        def value(field):
            return values[field] if field in values else getattr(record, field)
        start, end = schemas.stored_utc(value("starts_at")), schemas.stored_utc(value("ends_at"))
        if end <= start:
            raise APIError(422, "validation_error", "ends_at must be later than starts_at.")
        room = self.parent(models.Room, value("room_id"), "room_id", lock=True)
        faculty = self.parent(models.Faculty, value("faculty_id"), "faculty_id", lock=True)
        section = self.parent(models.Section, value("section_id"), "section_id", lock=True)
        if room.capacity < section.student_count:
            raise APIError(422, "insufficient_capacity",
                           f"Room capacity ({room.capacity}) is less than section student count ({section.student_count}).")
        if not value("is_active"):
            return  # An inactive entry does not occupy resources.
        for name, parent in [("room", room), ("faculty", faculty), ("section", section)]:
            if not parent.is_active:
                raise APIError(422, "inactive_parent", f"An active schedule entry requires an active {name}.")
        result = self.conflicts(start, end, room_id=room.id, faculty_id=faculty.id, section_id=section.id,
                                exclude_id=record.id if record is not None else None)
        if result.has_conflicts:
            raise APIError(409, "schedule_conflict", "The requested schedule overlaps active entries.",
                           details=result.model_dump(mode="json"))

    def available_rooms(self, query: AvailabilityQuery) -> list[AvailableRoom]:
        if query.room_type_id is not None:
            self.parent(models.RoomType, query.room_type_id, "room_type_id")
        facility_ids = sorted(set(query.facility_ids), key=str)
        if facility_ids:
            found = set(self.session.scalars(select(models.Facility.id).where(
                models.Facility.workspace_id == self.workspace_id, models.Facility.id.in_(facility_ids),
            )))
            if found != set(facility_ids):
                raise APIError(422, "invalid_parent", "facility_ids must reference facilities in this workspace.")
        room, room_type, floor, building, campus = models.Room, models.RoomType, models.Floor, models.Building, models.Campus
        entry, link = models.ScheduleEntry, models.RoomFacility
        occupied = exists(select(entry.id).where(
            entry.workspace_id == self.workspace_id, entry.room_id == room.id,
            entry.is_active.is_(True), self.overlap(query.starts_at, query.ends_at),
        ))
        statement = select(room, room_type, floor, building, campus).join(room_type, and_(
            room.room_type_id == room_type.id, room.workspace_id == room_type.workspace_id,
        )).join(floor, and_(room.floor_id == floor.id, room.workspace_id == floor.workspace_id)).join(
            building, and_(floor.building_id == building.id, floor.workspace_id == building.workspace_id),
        ).join(campus, and_(building.campus_id == campus.id, building.workspace_id == campus.workspace_id)).where(
            room.workspace_id == self.workspace_id, room_type.workspace_id == self.workspace_id,
            floor.workspace_id == self.workspace_id, building.workspace_id == self.workspace_id,
            campus.workspace_id == self.workspace_id, room.is_active.is_(True), ~occupied,
        )
        if query.minimum_capacity is not None:
            statement = statement.where(room.capacity >= query.minimum_capacity)
        if query.room_type_id is not None:
            statement = statement.where(room.room_type_id == query.room_type_id)
        for facility_id in facility_ids:
            statement = statement.where(exists(select(link.room_id).where(
                link.workspace_id == self.workspace_id, link.room_id == room.id, link.facility_id == facility_id,
            )))
        rows = self.session.execute(statement.order_by(room.code, room.id).limit(query.limit).offset(query.offset)).all()
        if not rows:
            return []
        facilities = defaultdict(list)
        # One bounded, explicitly tenant-scoped query for facilities on the returned page.
        for room_id, facility in self.session.execute(select(link.room_id, models.Facility).join(
            models.Facility, and_(link.facility_id == models.Facility.id, link.workspace_id == models.Facility.workspace_id),
        ).where(link.workspace_id == self.workspace_id, models.Facility.workspace_id == self.workspace_id,
                link.room_id.in_([row[0].id for row in rows])).order_by(models.Facility.name, models.Facility.id)):
            facilities[room_id].append(schemas.FacilityRead.model_validate(facility))
        return [AvailableRoom(
            **schemas.RoomRead.model_validate(room).model_dump(),
            room_type=schemas.RoomTypeRead.model_validate(room_type), floor=schemas.FloorRead.model_validate(floor),
            building=schemas.BuildingRead.model_validate(building), campus=schemas.CampusRead.model_validate(campus),
            facilities=facilities[room.id],
        ) for room, room_type, floor, building, campus in rows]

    def room_availability(self, room_id: UUID, interval: IntervalQuery) -> RoomAvailability:
        room = self.session.scalar(select(models.Room).where(
            models.Room.workspace_id == self.workspace_id, models.Room.id == room_id,
        ))
        if room is None:
            raise APIError(404, "resource_not_found", "Resource not found in this workspace.")
        result = self.conflicts(interval.starts_at, interval.ends_at, room_id=room.id)
        return RoomAvailability(room_id=room.id, starts_at=interval.starts_at, ends_at=interval.ends_at,
                                available=room.is_active and not result.has_conflicts,
                                reason="inactive_room" if not room.is_active else "schedule_conflict" if result.has_conflicts else None,
                                **result.model_dump())
