"""Temporary explicit identities are membership-validated, not authenticated."""
from uuid import UUID
from pydantic import ConfigDict, Field
from app.models import ReservationStatus
from app.schemas import Name, Request, StudentCount, StoredTime
from app.scheduling_schemas import IntervalQuery


class ReservationCreate(IntervalQuery):
    room_id: UUID
    requested_by_user_id: UUID
    title: Name
    description: str | None = None
    expected_attendees: StudentCount


class ReviewRequest(Request):
    reviewed_by_user_id: UUID


class RejectRequest(ReviewRequest):
    rejection_reason: str | None = None


class ReservationFilters(Request):
    status: ReservationStatus | None = None
    room_id: UUID | None = None
    requested_by_user_id: UUID | None = None
    limit: int = Field(default=100, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ReservationRead(ReservationCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    workspace_id: UUID
    status: ReservationStatus
    starts_at: StoredTime
    ends_at: StoredTime
    reviewed_by_user_id: UUID | None
    reviewed_at: StoredTime | None
    rejection_reason: str | None
    created_at: StoredTime
    updated_at: StoredTime
