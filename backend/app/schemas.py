"""API contracts; tenant ownership comes only from the route."""

from datetime import datetime, timezone
from typing import Annotated, Self
from typing import Literal
from uuid import UUID

from pydantic import (AfterValidator, AwareDatetime, BaseModel,
                      ConfigDict, Field, StringConstraints, model_validator)

class WorkspaceMemberRead(BaseModel):
    """Development directory only; membership does not authenticate a caller."""
    user_id: UUID
    display_name: str
    email: str
    role: Literal["owner", "admin", "member", "viewer"]
    is_active: bool


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
Capacity = Annotated[int, Field(strict=True, gt=0, le=2147483647)]
FloorNumber = Annotated[int, Field(strict=True, ge=-2147483648, le=2147483647)]


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Patch(Request):
    @model_validator(mode="after")
    def validate_patch(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update")
        for field in self.model_fields_set:
            if getattr(self, field) is None and field not in {"address", "description"}:
                raise ValueError(f"{field} cannot be null")
        return self


class CampusCreate(Request):
    name: Name
    code: Code
    address: str | None = None
    is_active: bool = True


class CampusUpdate(Patch):
    name: Name | None = None
    code: Code | None = None
    address: str | None = None
    is_active: bool | None = None


class BuildingCreate(Request):
    campus_id: UUID
    name: Name
    code: Code
    is_active: bool = True


class BuildingUpdate(Patch):
    campus_id: UUID | None = None
    name: Name | None = None
    code: Code | None = None
    is_active: bool | None = None


class FloorCreate(Request):
    building_id: UUID
    name: Name
    floor_number: FloorNumber
    is_active: bool = True


class FloorUpdate(Patch):
    building_id: UUID | None = None
    name: Name | None = None
    floor_number: FloorNumber | None = None
    is_active: bool | None = None


class RoomTypeCreate(Request):
    name: Name
    description: str | None = None


class RoomTypeUpdate(Patch):
    name: Name | None = None
    description: str | None = None


class FacilityCreate(RoomTypeCreate):
    pass


class FacilityUpdate(RoomTypeUpdate):
    pass


class RoomCreate(Request):
    floor_id: UUID
    room_type_id: UUID
    name: Name
    code: Code
    capacity: Capacity
    is_active: bool = True


class RoomUpdate(Patch):
    floor_id: UUID | None = None
    room_type_id: UUID | None = None
    name: Name | None = None
    code: Code | None = None
    capacity: Capacity | None = None
    is_active: bool | None = None


class RecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    workspace_id: UUID
    name: str
    created_at: datetime


class WorkspaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    slug: str
    default_timezone: str
    created_at: datetime


class CampusRead(RecordRead):
    code: str
    address: str | None
    is_active: bool


class BuildingRead(RecordRead):
    campus_id: UUID
    code: str
    is_active: bool


class FloorRead(RecordRead):
    building_id: UUID
    floor_number: int
    is_active: bool


class RoomTypeRead(RecordRead):
    description: str | None


class FacilityRead(RoomTypeRead):
    pass


class RoomRead(RecordRead):
    floor_id: UUID
    room_type_id: UUID
    code: str
    capacity: int
    is_active: bool


class RoomFacilityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    workspace_id: UUID
    room_id: UUID
    facility_id: UUID


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    detail: ErrorDetail


StudentCount = Annotated[int, Field(strict=True, gt=0, le=2147483647)]
FacultyEmail = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3,
                                               max_length=320, pattern=r"^[^@\s]+@[^@\s]+$")]
ScheduleTime = Annotated[AwareDatetime, AfterValidator(lambda value: value.astimezone(timezone.utc))]


def stored_utc(value: datetime) -> datetime:
    """Return UTC instants; SQLite loses tzinfo from values stored in UTC.

    PostgreSQL returns aware timestamps. Naive values from the isolated SQLite
    test database are UTC because API writes are normalized before persistence,
    and its created_at server default also uses UTC. Never use this for input.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


StoredTime = Annotated[datetime, AfterValidator(stored_utc)]


class DepartmentCreate(Request):
    name: Name
    code: Code
    is_active: bool = True


class DepartmentUpdate(Patch):
    name: Name | None = None
    code: Code | None = None
    is_active: bool | None = None


class FacultyCreate(Request):
    department_id: UUID
    name: Name
    email: FacultyEmail
    is_active: bool = True


class FacultyUpdate(Patch):
    department_id: UUID | None = None
    name: Name | None = None
    email: FacultyEmail | None = None
    is_active: bool | None = None


class CourseCreate(DepartmentCreate):
    department_id: UUID


class CourseUpdate(DepartmentUpdate):
    department_id: UUID | None = None


class SectionCreate(Request):
    course_id: UUID
    name: Name
    student_count: StudentCount
    is_active: bool = True


class SectionUpdate(Patch):
    course_id: UUID | None = None
    name: Name | None = None
    student_count: StudentCount | None = None
    is_active: bool | None = None


class ScheduleEntryCreate(Request):
    room_id: UUID
    section_id: UUID
    faculty_id: UUID
    starts_at: ScheduleTime
    ends_at: ScheduleTime
    is_active: bool = True


class ScheduleEntryUpdate(Patch):
    room_id: UUID | None = None
    section_id: UUID | None = None
    faculty_id: UUID | None = None
    starts_at: ScheduleTime | None = None
    ends_at: ScheduleTime | None = None
    is_active: bool | None = None


class AcademicRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    workspace_id: UUID
    created_at: StoredTime
    is_active: bool


class DepartmentRead(AcademicRead):
    name: str
    code: str


class FacultyRead(AcademicRead):
    department_id: UUID
    name: str
    email: str


class CourseRead(DepartmentRead):
    department_id: UUID


class SectionRead(AcademicRead):
    course_id: UUID
    name: str
    student_count: int


class ScheduleEntryRead(AcademicRead):
    room_id: UUID
    section_id: UUID
    faculty_id: UUID
    starts_at: StoredTime
    ends_at: StoredTime
