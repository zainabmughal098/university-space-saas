"""Infrastructure HTTP routes; shared registration keeps CRUD behavior consistent."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_session
from app.schemas import ErrorResponse, FacilityRead, RoomFacilityRead
from app.services import InfrastructureService, RESOURCES, Resource

router = APIRouter(prefix="/api/workspaces/{workspace_id}", responses={
    status: {"model": ErrorResponse} for status in (404, 409, 422, 503)
})


def get_service(workspace_id: UUID, session: Annotated[Session, Depends(get_session)]):
    return InfrastructureService(session, workspace_id)


Service = Annotated[InfrastructureService, Depends(get_service)]
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0)]


def register_resource(path: str, resource: Resource) -> None:
    # Annotations are evaluated here so each generated route has its concrete
    # request schema and full validation/OpenAPI documentation.
    create_schema = resource.create
    update_schema = resource.update

    def create(payload: create_schema, service: Service):
        return service.create(resource, payload)

    def list_records(service: Service, limit: Limit = 100, offset: Offset = 0):
        return service.list(resource, limit, offset)

    def get(resource_id: UUID, service: Service):
        return service.get(resource, resource_id)

    def update(resource_id: UUID, payload: update_schema, service: Service):
        return service.update(resource, resource_id, payload)

    def deactivate(resource_id: UUID, service: Service):
        return service.deactivate(resource, resource_id)

    for suffix, endpoint, method, status, response in [
        ("", create, "POST", 201, resource.response),
        ("", list_records, "GET", 200, list[resource.response]),
        ("/{resource_id}", get, "GET", 200, resource.response),
        ("/{resource_id}", update, "PATCH", 200, resource.response),
    ]:
        router.add_api_route(f"/{path}{suffix}", endpoint, methods=[method], status_code=status,
                             response_model=response, name=f"{method.lower()}_{path}", tags=[path])
    if resource.active:
        router.add_api_route(f"/{path}/{{resource_id}}/deactivate", deactivate, methods=["POST"],
                             response_model=resource.response, name=f"deactivate_{path}", tags=[path])


for path, resource in RESOURCES.items():
    register_resource(path, resource)


@router.get("/rooms/{room_id}/facilities", response_model=list[FacilityRead], tags=["rooms"])
def list_room_facilities(room_id: UUID, service: Service, limit: Limit = 100, offset: Offset = 0):
    return service.facilities(room_id, limit, offset)


@router.post("/rooms/{room_id}/facilities/{facility_id}", response_model=RoomFacilityRead, status_code=201, tags=["rooms"])
def assign_room_facility(room_id: UUID, facility_id: UUID, service: Service):
    return service.assign_facility(room_id, facility_id)


@router.delete("/rooms/{room_id}/facilities/{facility_id}", status_code=204, tags=["rooms"])
def remove_room_facility(room_id: UUID, facility_id: UUID, service: Service):
    service.remove_facility(room_id, facility_id)
    return Response(status_code=204)
