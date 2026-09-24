"""Explicit reservation actions; identities are not authenticated yet."""
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_session
from app.reservations import ReservationService
from app.reservation_schemas import ReservationCreate, ReservationRead, ReservationFilters, ReviewRequest, RejectRequest
from app.schemas import ErrorResponse
from app.scheduling_schemas import ScheduleConflictResponse

router = APIRouter(prefix="/api/workspaces/{workspace_id}/reservations", tags=["reservations"],
                   responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse},
                              409: {"model": ScheduleConflictResponse | ErrorResponse}})


def service(workspace_id: UUID, session: Annotated[Session, Depends(get_session)]):
    return ReservationService(session, workspace_id)


Service = Annotated[ReservationService, Depends(service)]


@router.post("", response_model=ReservationRead, status_code=201)
def create(payload: ReservationCreate, service: Service):
    return service.create(payload)


@router.get("", response_model=list[ReservationRead])
def listing(filters: Annotated[ReservationFilters, Query()], service: Service):
    return service.list(filters)


@router.get("/{reservation_id}", response_model=ReservationRead)
def get(reservation_id: UUID, service: Service):
    return service.get(reservation_id)


@router.post("/{reservation_id}/approve", response_model=ReservationRead)
def approve(reservation_id: UUID, payload: ReviewRequest, service: Service):
    return service.transition(reservation_id, "approve", payload.reviewed_by_user_id)


@router.post("/{reservation_id}/reject", response_model=ReservationRead)
def reject(reservation_id: UUID, payload: RejectRequest, service: Service):
    return service.transition(reservation_id, "reject", payload.reviewed_by_user_id, payload.rejection_reason)


@router.post("/{reservation_id}/cancel", response_model=ReservationRead)
def cancel(reservation_id: UUID, service: Service):
    return service.transition(reservation_id, "cancel")
