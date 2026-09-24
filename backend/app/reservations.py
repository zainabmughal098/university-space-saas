"""Reservation state machine sharing the scheduling workspace-lock protocol."""
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from app import models, schemas
from app.errors import APIError
from app.reservation_schemas import ReservationRead
from app.scheduling import SchedulingService
from app.services import WorkspaceService


class ReservationService:
    def __init__(self, session, workspace_id):
        self.session, self.workspace_id = session, workspace_id
        self.workspace = WorkspaceService(session, workspace_id)
        self.scheduling = SchedulingService(session, workspace_id)

    def member(self, user_id: UUID, *, active=True):
        query = select(models.Membership).where(models.Membership.workspace_id == self.workspace_id,
                                                models.Membership.user_id == user_id)
        if active:
            query = query.where(models.Membership.is_active.is_(True)).with_for_update()
        if self.session.scalar(query) is None:
            raise APIError(422, "invalid_member", "User must have a membership in this workspace" + (" that is active." if active else "."))

    def room(self, room_id, attendees):
        room = self.scheduling.parent(models.Room, room_id, "room_id", lock=True)
        if not room.is_active:
            raise APIError(422, "inactive_parent", "Reservations require an active room.")
        if attendees > room.capacity:
            raise APIError(422, "insufficient_capacity", f"Room capacity ({room.capacity}) is less than expected attendees ({attendees}).")

    def persist(self, record=None, *, reservation_id=None, values=None):
        try:
            if record is not None:
                self.session.add(record)
                self.session.flush()
                result = ReservationRead.model_validate(record)
            else:
                row = self.session.execute(update(models.Reservation).where(
                    models.Reservation.workspace_id == self.workspace_id, models.Reservation.id == reservation_id,
                ).values(**values, updated_at=datetime.now(timezone.utc)).returning(*models.Reservation.__table__.columns),
                    execution_options={"synchronize_session": False}).mappings().one()
                result = ReservationRead.model_validate(row)
            self.session.commit()
            return result
        except IntegrityError:
            self.session.rollback()
            raise APIError(409, "integrity_conflict", "Reservation conflicts with existing data or relationships.") from None

    def create(self, payload):
        self.scheduling.lock_workspace()
        self.member(payload.requested_by_user_id)
        self.room(payload.room_id, payload.expected_attendees)
        # Pending requests do not compete with approved reservations until review.
        result = self.scheduling.conflicts(payload.starts_at, payload.ends_at, room_id=payload.room_id)
        result.reservation_conflicts = []
        result.has_conflicts = bool(result.conflicts)
        self.scheduling.reject_conflicts(result)
        return self.persist(models.Reservation(workspace_id=self.workspace_id,
                            status=models.ReservationStatus.PENDING, **payload.model_dump()))

    def get(self, reservation_id):
        return ReservationRead.model_validate(self.workspace.find(models.Reservation, reservation_id))

    def list(self, filters):
        if filters.room_id is not None:
            self.scheduling.parent(models.Room, filters.room_id, "room_id")
        if filters.requested_by_user_id is not None:
            self.member(filters.requested_by_user_id, active=False)
        model = models.Reservation
        query = select(model).where(model.workspace_id == self.workspace_id)
        for field in ["status", "room_id", "requested_by_user_id"]:
            value = getattr(filters, field)
            if value is not None:
                query = query.where(getattr(model, field) == value)
        return [ReservationRead.model_validate(row) for row in self.session.scalars(
            query.order_by(model.created_at, model.id).limit(filters.limit).offset(filters.offset))]

    def transition(self, reservation_id, action, reviewer=None, rejection_reason=None):
        self.scheduling.lock_workspace()
        record = self.workspace.find(models.Reservation, reservation_id, lock=True)
        status = models.ReservationStatus
        permitted = {"approve": {status.PENDING}, "reject": {status.PENDING},
                     "cancel": {status.PENDING, status.APPROVED}}
        if record.status not in permitted[action]:
            raise APIError(409, "invalid_state_transition", f"Cannot {action} a {record.status.value} reservation.")
        values = {"status": {"approve": status.APPROVED, "reject": status.REJECTED, "cancel": status.CANCELLED}[action]}
        if action != "cancel":
            self.member(reviewer)
            values.update(reviewed_by_user_id=reviewer, reviewed_at=datetime.now(timezone.utc))
        if action == "approve":
            self.member(record.requested_by_user_id)
            self.room(record.room_id, record.expected_attendees)
            self.scheduling.reject_conflicts(self.scheduling.conflicts(
                schemas.stored_utc(record.starts_at), schemas.stored_utc(record.ends_at), room_id=record.room_id))
        if action == "reject":
            values["rejection_reason"] = rejection_reason
        return self.persist(reservation_id=record.id, values=values)
