"""Workspace-scoped infrastructure/academic operations and transaction boundaries."""

from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.errors import APIError


@dataclass(frozen=True)
class Resource:
    model: type
    create: type[BaseModel]
    update: type[BaseModel]
    response: type[BaseModel]
    unique_fields: tuple[str, ...]
    parents: tuple[tuple[str, type], ...] = ()
    active: bool = False


RESOURCES = {
    "campuses": Resource(models.Campus, schemas.CampusCreate, schemas.CampusUpdate, schemas.CampusRead, ("code",), active=True),
    "buildings": Resource(models.Building, schemas.BuildingCreate, schemas.BuildingUpdate, schemas.BuildingRead,
                          ("campus_id", "code"), (("campus_id", models.Campus),), True),
    "floors": Resource(models.Floor, schemas.FloorCreate, schemas.FloorUpdate, schemas.FloorRead,
                       ("building_id", "floor_number"), (("building_id", models.Building),), True),
    "room-types": Resource(models.RoomType, schemas.RoomTypeCreate, schemas.RoomTypeUpdate, schemas.RoomTypeRead, ("name",)),
    "facilities": Resource(models.Facility, schemas.FacilityCreate, schemas.FacilityUpdate, schemas.FacilityRead, ("name",)),
    "rooms": Resource(models.Room, schemas.RoomCreate, schemas.RoomUpdate, schemas.RoomRead, ("code",),
                      (("floor_id", models.Floor), ("room_type_id", models.RoomType)), True),
    "departments": Resource(models.Department, schemas.DepartmentCreate, schemas.DepartmentUpdate,
                            schemas.DepartmentRead, ("code",), active=True),
    "faculty": Resource(models.Faculty, schemas.FacultyCreate, schemas.FacultyUpdate, schemas.FacultyRead,
                        ("email",), (("department_id", models.Department),), True),
    "courses": Resource(models.Course, schemas.CourseCreate, schemas.CourseUpdate, schemas.CourseRead,
                        ("code",), (("department_id", models.Department),), True),
    "sections": Resource(models.Section, schemas.SectionCreate, schemas.SectionUpdate, schemas.SectionRead,
                         ("course_id", "name"), (("course_id", models.Course),), True),
    "schedule-entries": Resource(models.ScheduleEntry, schemas.ScheduleEntryCreate, schemas.ScheduleEntryUpdate,
                                 schemas.ScheduleEntryRead, (), (("room_id", models.Room),
                                 ("section_id", models.Section), ("faculty_id", models.Faculty)), True),
}


class WorkspaceService:
    def __init__(self, session: Session, workspace_id: UUID):
        self.session = session
        self.workspace_id = workspace_id
        if session.scalar(select(models.Workspace.id).where(models.Workspace.id == workspace_id)) is None:
            raise APIError(404, "workspace_not_found", "Workspace not found.")

    def find(self, model, resource_id: UUID, *, lock: bool = False):
        query = select(model).where(
            model.workspace_id == self.workspace_id, model.id == resource_id,
        )
        if lock:
            query = query.with_for_update()
        record = self.session.scalar(query)
        if record is None:
            # Deliberately identical for missing IDs and IDs owned by another workspace.
            raise APIError(404, "resource_not_found", "Resource not found in this workspace.")
        return record

    def validate_values(self, resource: Resource, values: dict, record=None):
        for field, parent in resource.parents:
            if field in values:
                found = self.session.scalar(select(parent.id).where(
                    parent.workspace_id == self.workspace_id, parent.id == values[field],
                ))
                if found is None:
                    raise APIError(422, "invalid_parent", f"{field} must reference a resource in this workspace.")
        if resource.model is models.ScheduleEntry:
            # Compare the resulting interval, including stored values omitted by PATCH.
            start = values["starts_at"] if "starts_at" in values else record.starts_at
            end = values["ends_at"] if "ends_at" in values else record.ends_at
            if schemas.stored_utc(end) <= schemas.stored_utc(start):
                raise APIError(422, "validation_error", "ends_at must be later than starts_at.")
        if not resource.unique_fields:
            # Schedule overlaps and duplicate occupancy entries are allowed in this phase.
            return
        query = select(resource.model.id).where(resource.model.workspace_id == self.workspace_id)
        for field in resource.unique_fields:
            value = values[field] if field in values else getattr(record, field)
            query = query.where(getattr(resource.model, field) == value)
        if record is not None:
            query = query.where(resource.model.id != record.id)
        if self.session.scalar(query) is not None:
            raise APIError(409, "duplicate_resource", "The unique resource identifier already exists in its scope.")

    def save(self, record, response_schema):
        try:
            self.session.flush()
            # Serialize before commit expires ORM state: no unscoped refresh queries.
            response = response_schema.model_validate(record)
            self.session.commit()
            return response
        except IntegrityError:
            self.session.rollback()
            # Constraints remain the final authority if a concurrent request races validation.
            raise APIError(409, "integrity_conflict", "The change conflicts with existing data or relationships.") from None

    def create(self, resource: Resource, payload: BaseModel):
        values = payload.model_dump()
        self.validate_values(resource, values)
        record = resource.model(workspace_id=self.workspace_id, **values)
        self.session.add(record)
        return self.save(record, resource.response)

    def list(self, resource: Resource, limit: int, offset: int):
        records = self.session.scalars(select(resource.model).where(
            resource.model.workspace_id == self.workspace_id,
        ).order_by(resource.model.created_at, resource.model.id).limit(limit).offset(offset))
        return [resource.response.model_validate(record) for record in records]

    def get(self, resource: Resource, resource_id: UUID):
        return resource.response.model_validate(self.find(resource.model, resource_id))

    def update(self, resource: Resource, resource_id: UUID, payload: BaseModel):
        # Serialize concurrent partial schedule changes before checking the merged interval.
        record = self.find(resource.model, resource_id, lock=resource.model is models.ScheduleEntry)
        values = payload.model_dump(exclude_unset=True)
        self.validate_values(resource, values, record)
        return self.update_values(resource, resource_id, values)

    def update_values(self, resource: Resource, resource_id: UUID, values: dict):
        try:
            # Explicit tenant predicates apply to the write itself, not just its lookup.
            row = self.session.execute(update(resource.model).where(
                resource.model.workspace_id == self.workspace_id, resource.model.id == resource_id,
            ).values(**values).returning(*resource.model.__table__.columns),
                execution_options={"synchronize_session": False}).mappings().one_or_none()
            if row is None:
                raise APIError(404, "resource_not_found", "Resource not found in this workspace.")
            response = resource.response.model_validate(row)
            self.session.commit()
            return response
        except IntegrityError:
            self.session.rollback()
            raise APIError(409, "integrity_conflict", "The change conflicts with existing data or relationships.") from None

    def deactivate(self, resource: Resource, resource_id: UUID):
        self.find(resource.model, resource_id)
        return self.update_values(resource, resource_id, {"is_active": False})

    def facilities(self, room_id: UUID, limit: int, offset: int):
        self.find(models.Room, room_id)
        records = self.session.scalars(select(models.Facility).join(models.RoomFacility,
            (models.RoomFacility.facility_id == models.Facility.id)
            & (models.RoomFacility.workspace_id == models.Facility.workspace_id),
        ).where(
            models.Facility.workspace_id == self.workspace_id,
            models.RoomFacility.workspace_id == self.workspace_id,
            models.RoomFacility.room_id == room_id,
        ).order_by(models.Facility.created_at, models.Facility.id).limit(limit).offset(offset))
        return [schemas.FacilityRead.model_validate(record) for record in records]

    def facility_link(self, room_id: UUID, facility_id: UUID):
        self.find(models.Room, room_id)
        self.find(models.Facility, facility_id)
        return self.session.scalar(select(models.RoomFacility).where(
            models.RoomFacility.workspace_id == self.workspace_id,
            models.RoomFacility.room_id == room_id,
            models.RoomFacility.facility_id == facility_id,
        ))

    def assign_facility(self, room_id: UUID, facility_id: UUID):
        if self.facility_link(room_id, facility_id) is not None:
            raise APIError(409, "duplicate_assignment", "Facility is already assigned to this room.")
        record = models.RoomFacility(workspace_id=self.workspace_id, room_id=room_id, facility_id=facility_id)
        self.session.add(record)
        return self.save(record, schemas.RoomFacilityRead)

    def remove_facility(self, room_id: UUID, facility_id: UUID):
        record = self.facility_link(room_id, facility_id)
        if record is None:
            raise APIError(404, "assignment_not_found", "Facility is not assigned to this room.")
        try:
            self.session.execute(delete(models.RoomFacility).where(
                models.RoomFacility.workspace_id == self.workspace_id,
                models.RoomFacility.room_id == room_id,
                models.RoomFacility.facility_id == facility_id,
            ), execution_options={"synchronize_session": False})
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise APIError(409, "integrity_conflict", "The assignment could not be removed.") from None
