"""Conflict and availability API contracts."""

from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas import (BuildingRead, CampusRead, ErrorDetail, FacilityRead, FloorRead,
                         Request, RoomRead, RoomTypeRead, ScheduleTime, StoredTime)


class IntervalQuery(Request):
    starts_at: ScheduleTime
    ends_at: ScheduleTime

    @model_validator(mode="after")
    def positive_interval(self) -> Self:
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be later than starts_at")
        return self


class AvailabilityQuery(IntervalQuery):
    minimum_capacity: int | None = Field(default=None, ge=1, le=2147483647)
    room_type_id: UUID | None = None
    facility_ids: list[UUID] = Field(default_factory=list, max_length=100)
    limit: int = Field(default=100, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ScheduleConflict(BaseModel):
    schedule_entry_id: UUID
    conflict_types: list[Literal["room", "faculty", "section"]]
    room_id: UUID
    faculty_id: UUID
    section_id: UUID
    starts_at: StoredTime
    ends_at: StoredTime


class ReservationConflict(BaseModel):
    reservation_id: UUID
    room_id: UUID
    starts_at: StoredTime
    ends_at: StoredTime


class ConflictResult(BaseModel):
    has_conflicts: bool
    conflicts: list[ScheduleConflict]
    reservation_conflicts: list[ReservationConflict] = Field(default_factory=list)


class ScheduleConflictDetail(ErrorDetail, ConflictResult):
    pass


class ScheduleConflictResponse(BaseModel):
    detail: ScheduleConflictDetail


class AvailableRoom(RoomRead):
    room_type: RoomTypeRead
    floor: FloorRead
    building: BuildingRead
    campus: CampusRead
    facilities: list[FacilityRead]


class RoomAvailability(ConflictResult):
    room_id: UUID
    starts_at: StoredTime
    ends_at: StoredTime
    available: bool
    reason: Literal["inactive_room", "schedule_conflict", "reservation_conflict", "schedule_and_reservation_conflict"] | None = None
