"""Reservation API, workflow, tenant constraints, and offline migration tests."""
from datetime import datetime, timezone
import io
import unittest
from uuid import UUID, uuid4
from unittest.mock import patch

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Membership, MembershipRole, Reservation, ReservationStatus, User, Workspace
from test_academic_api import AcademicAPIFixture
from test_infrastructure import BACKEND, migration


class ReservationTests(AcademicAPIFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        with Session(self.engine) as session:
            users = [User(email=f"user{i}@example.test", display_name=f"User {i}") for i in range(4)]
            session.add_all(users)
            session.flush()
            self.requester, self.reviewer, self.foreign, self.inactive = [str(user.id) for user in users]
            for user, wid, active in [(users[0], self.a, True), (users[1], self.a, True),
                                      (users[2], self.b, True), (users[3], self.a, False)]:
                session.add(Membership(user=user, workspace_id=UUID(wid), role=MembershipRole.MEMBER, is_active=active))
            session.commit()

    def booking(self, **changes):
        return dict(room_id=self.data[self.a]["rooms"]["id"], requested_by_user_id=self.requester,
                    title="Meeting", starts_at="2026-10-01T09:00:00Z", ends_at="2026-10-01T10:00:00Z",
                    expected_attendees=20) | changes

    def create(self, **changes):
        return self.client.post(self.url(self.a, "reservations"), json=self.booking(**changes))

    def action(self, reservation_id, action, **body):
        payload = {"reviewed_by_user_id": self.reviewer} | body if action != "cancel" else None
        return self.client.post(self.url(self.a, "reservations", reservation_id) + "/" + action, json=payload)

    def check(self):
        return self.client.get(self.url(self.a, "rooms", self.data[self.a]["rooms"]["id"]) + "/availability",
                               params={key: self.booking()[key] for key in ["starts_at", "ends_at"]})

    def search(self):
        return self.client.get(self.url(self.a, "rooms") + "/availability",
                               params={key: self.booking()[key] for key in ["starts_at", "ends_at"]})

    def test_create_read_pending_and_body_fields(self):
        response = self.create(description="Test")
        self.assertEqual(response.status_code, 201, response.text)
        data = response.json()
        self.assertEqual(data["status"], "pending")
        self.assertIsNone(data["reviewed_by_user_id"])
        self.assertIsNone(data["reviewed_at"])
        self.assertEqual(data["workspace_id"], self.a)
        for field in ["starts_at", "ends_at", "created_at", "updated_at"]:
            self.assertIsNotNone(datetime.fromisoformat(data[field]).utcoffset())
        path = self.url(self.a, "reservations", data["id"])
        self.assertEqual(self.client.get(path).json(), data)
        self.error(self.client.patch(path, json={"status": "approved"}), 405)
        for field, value in [("status", "approved"), ("workspace_id", self.b), ("reviewed_by_user_id", self.reviewer),
                             ("reviewed_at", "2026-01-01T00:00:00Z"), ("id", str(uuid4())), ("updated_at", "x")]:
            self.error(self.create(**{field: value}), 422)
        self.assertTrue(self.check().json()["available"])
        self.assertEqual(len(self.search().json()), 1)

    def test_invalid_times_attendees_capacity(self):
        for values in [{"ends_at": "2026-10-01T09:00:00Z"}, {"ends_at": "2026-10-01T08:00:00Z"},
                       {"starts_at": "2026-10-01T09:00:00"}, {"ends_at": None}]:
            self.error(self.create(**values), 422)
        for count in [0, -1, None, True, "20", 1.5, 2147483648]:
            self.error(self.create(expected_attendees=count), 422)
        self.error(self.create(expected_attendees=31), 422, "insufficient_capacity")
        self.assertEqual(self.create(expected_attendees=30).status_code, 201)

    def test_reference_and_workspace_isolation(self):
        for user in [self.foreign, self.inactive, str(uuid4())]:
            self.error(self.create(requested_by_user_id=user), 422, "invalid_member")
        self.error(self.create(room_id=self.data[self.b]["rooms"]["id"]), 422, "invalid_parent")
        data = self.create().json()
        for wid in [self.b, str(uuid4())]:
            path = self.url(wid, "reservations", data["id"])
            self.error(self.client.get(path), 404)
            for action in ["approve", "reject", "cancel"]:
                self.error(self.client.post(path + "/" + action, json={"reviewed_by_user_id": self.reviewer}), 404)
        self.assertEqual(self.client.get(self.url(self.b, "reservations")).json(), [])
        # A global User can request in another workspace only after gaining membership there.
        with Session(self.engine) as session:
            session.add(Membership(user_id=UUID(self.foreign), workspace_id=UUID(self.a), role=MembershipRole.VIEWER))
            session.commit()
        self.assertEqual(self.create(requested_by_user_id=self.foreign).status_code, 201)

    def test_approval_blocks_availability_and_records_reviewer(self):
        pending = self.create().json()
        response = self.action(pending["id"], "approve")
        self.assertEqual(response.status_code, 200, response.text)
        approved = response.json()
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["reviewed_by_user_id"], self.reviewer)
        self.assertIsNotNone(approved["reviewed_at"])
        self.assertGreaterEqual(datetime.fromisoformat(approved["updated_at"]), datetime.fromisoformat(pending["updated_at"]))
        self.assertEqual(self.search().json(), [])
        check = self.check().json()
        self.assertFalse(check["available"])
        self.assertEqual(check["reason"], "reservation_conflict")
        self.assertEqual(check["conflicts"], [])
        self.assertEqual(check["reservation_conflicts"][0]["reservation_id"], approved["id"])

    def test_create_and_approval_schedule_conflicts(self):
        failed = self.create(starts_at="2026-10-01T07:30:00Z", ends_at="2026-10-01T08:30:00Z")
        self.assertEqual(failed.status_code, 409)
        self.assertEqual(failed.json()["detail"]["code"], "schedule_conflict")
        pending = self.create().json()
        # Pending requests do not prevent a new official class booking.
        schedule = self.client.post(self.url(self.a, "schedule-entries"), json=self.payload(self.a, "schedule-entries") | {
            "starts_at": self.booking()["starts_at"], "ends_at": self.booking()["ends_at"]})
        self.assertEqual(schedule.status_code, 201, schedule.text)
        failed = self.action(pending["id"], "approve")
        self.assertEqual(failed.status_code, 409)
        self.assertEqual(failed.json()["detail"]["conflicts"][0]["schedule_entry_id"], schedule.json()["id"])
        self.assertEqual(self.client.get(self.url(self.a, "reservations", pending["id"])).json()["status"], "pending")
        self.assertEqual(self.check().json()["reason"], "schedule_conflict")

    def test_overlapping_approvals_and_back_to_back(self):
        first, second = self.create().json(), self.create().json()
        self.assertEqual(self.action(first["id"], "approve").status_code, 200)
        failed = self.action(second["id"], "approve")
        self.assertEqual(failed.status_code, 409)
        self.assertEqual(failed.json()["detail"]["code"], "reservation_conflict")
        self.assertEqual(failed.json()["detail"]["reservation_conflicts"][0]["reservation_id"], first["id"])
        # Creating pending against an approved reservation is deliberately allowed.
        self.assertEqual(self.create().status_code, 201)
        adjacent = self.create(starts_at="2026-10-01T12:00:00+02:00", ends_at="2026-10-01T13:00:00+02:00").json()
        self.assertEqual(self.action(adjacent["id"], "approve").status_code, 200)
        self.error(self.action(first["id"], "approve"), 409, "invalid_state_transition")

    def test_schedule_create_update_and_reactivation_respect_reservations(self):
        reservation = self.create().json()
        self.action(reservation["id"], "approve")
        times = {key: self.booking()[key] for key in ["starts_at", "ends_at"]}
        response = self.client.post(self.url(self.a, "schedule-entries"), json=self.payload(self.a, "schedule-entries") | times)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "reservation_conflict")
        response = self.client.patch(self.item("schedule-entries"), json=times)
        self.assertEqual(response.status_code, 409)
        inactive = self.client.post(self.url(self.a, "schedule-entries"), json=self.payload(self.a, "schedule-entries") | times | {"is_active": False}).json()
        response = self.client.patch(self.url(self.a, "schedule-entries", inactive["id"]), json={"is_active": True})
        self.assertEqual(response.status_code, 409)

    def test_rejection_cancellation_and_state_machine(self):
        rejected = self.create().json()
        result = self.action(rejected["id"], "reject", rejection_reason="Unavailable for this purpose")
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["rejection_reason"], "Unavailable for this purpose")
        self.assertEqual(result.json()["reviewed_by_user_id"], self.reviewer)
        self.assertTrue(self.check().json()["available"])
        for action in ["approve", "reject", "cancel"]:
            self.error(self.action(rejected["id"], action), 409, "invalid_state_transition")
        for approve in [False, True]:
            record = self.create().json()
            if approve:
                self.action(record["id"], "approve")
                self.error(self.action(record["id"], "reject"), 409, "invalid_state_transition")
            response = self.action(record["id"], "cancel")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "cancelled")
            self.assertEqual(response.json()["reviewed_by_user_id"], self.reviewer if approve else None)
            self.assertTrue(self.check().json()["available"])
            for action in ["approve", "reject", "cancel"]:
                self.error(self.action(record["id"], action), 409, "invalid_state_transition")

    def test_review_membership_and_approval_rechecks_capacity(self):
        pending = self.create().json()
        for user in [self.foreign, self.inactive, str(uuid4())]:
            for action in ["approve", "reject"]:
                self.error(self.action(pending["id"], action, reviewed_by_user_id=user), 422, "invalid_member")
        self.client.patch(self.url(self.a, "rooms", pending["room_id"]), json={"capacity": 10})
        self.error(self.action(pending["id"], "approve"), 422, "insufficient_capacity")

    def test_list_filters(self):
        pending = self.create().json()
        rejected = self.create(title="Rejected").json()
        self.action(rejected["id"], "reject")
        path = self.url(self.a, "reservations")
        for filters in [{"status": "pending"}, {"status": "pending", "room_id": pending["room_id"], "requested_by_user_id": self.requester}]:
            response = self.client.get(path, params=filters)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual([r["id"] for r in response.json()], [pending["id"]])
        self.assertEqual(len(self.client.get(path, params={"limit": 1, "offset": 1}).json()), 1)
        for filters in [{"room_id": self.data[self.b]["rooms"]["id"]}, {"requested_by_user_id": self.foreign}, {"status": "invalid"}]:
            self.error(self.client.get(path, params=filters), 422)

    def test_lock_order_scoped_writes_and_rollback(self):
        pending = self.create().json()
        statements = []
        def capture(conn, clause, multiparams, params, options):
            statements.append(str(clause.compile(dialect=postgresql.dialect())))
        event.listen(self.engine, "before_execute", capture)
        with patch.object(Session, "commit", side_effect=IntegrityError("secret", {}, Exception("secret"))):
            result = self.action(pending["id"], "approve")
        self.error(result, 409, "integrity_conflict")
        self.assertNotIn("secret", result.text)
        self.assertEqual(self.client.get(self.url(self.a, "reservations", pending["id"])).json()["status"], "pending")
        locks = [sql for sql in statements if "FOR UPDATE" in sql]
        self.assertIn("workspaces.id", locks[0])
        self.assertIn("reservations.workspace_id", locks[1])
        for sql in statements:
            if sql.startswith("UPDATE reservations"):
                self.assertIn("workspace_id", sql.split("WHERE")[1])
        self.assertEqual(self.action(pending["id"], "approve").status_code, 200)

    def test_database_tenant_foreign_keys_and_constraints(self):
        record = self.create().json()
        with Session(self.engine) as session:
            row = session.scalar(select(Reservation).where(Reservation.id == UUID(record["id"])))
            self.assertEqual(str(row.requester.id), self.requester)
            self.assertEqual(str(row.room.id), record["room_id"])
            values = {c.name: getattr(row, c.name) for c in Reservation.__table__.columns if c.name not in {"id", "created_at", "updated_at"}}
            for change in [{"requested_by_user_id": UUID(self.foreign)}, {"room_id": UUID(self.data[self.b]["rooms"]["id"])},
                           {"reviewed_by_user_id": UUID(self.foreign), "reviewed_at": datetime.now(timezone.utc)},
                           {"expected_attendees": 0}, {"ends_at": row.starts_at}, {"status": "approved"},
                           {"workspace_id": uuid4()}]:
                with self.subTest(change=change), self.assertRaises(IntegrityError):
                    with session.begin_nested():
                        session.execute(Reservation.__table__.insert().values(**(values | change)))


class ReservationMigrationTests(unittest.TestCase):
    def test_upgrade_downgrade_and_model_consistency(self):
        engine = create_engine("sqlite://")
        event.listen(engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
        try:
            with engine.begin() as connection:
                context = MigrationContext.configure(connection)
                with Operations.context(context):
                    for revision in ["0001_initial_tenants", "0002_university_infrastructure", "0003_academic_scheduling"]:
                        migration(revision).upgrade()
                    connection.execute(Workspace.__table__.insert().values(id=uuid4(), name="Preserved", slug="preserved"))
                    fourth = migration("0004_room_reservations")
                    fourth.upgrade()
                    self.assertEqual(compare_metadata(context, Base.metadata), [])
                    fourth.downgrade()
                    self.assertNotIn("reservations", inspect(connection).get_table_names())
                    self.assertEqual(len(connection.execute(select(Workspace)).all()), 1)
                    fourth.upgrade()
                    self.assertEqual(compare_metadata(context, Base.metadata), [])
        finally:
            engine.dispose()

    def test_postgresql_offline_sql(self):
        output = io.StringIO()
        config = Config(str(BACKEND / "alembic.ini"), output_buffer=output)
        command.upgrade(config, "0003_academic_scheduling:head", sql=True)
        sql = output.getvalue()
        self.assertEqual(sql.count("CREATE TABLE "), 1)
        for fragment in ["CREATE TABLE reservations", "TIMESTAMP WITH TIME ZONE", "expected_attendees > 0",
                         "ends_at > starts_at", "FOREIGN KEY(requested_by_user_id, workspace_id)",
                         "FOREIGN KEY(reviewed_by_user_id, workspace_id)", "'pending', 'approved', 'rejected', 'cancelled'"]:
            self.assertIn(fragment, sql)
        output.seek(0); output.truncate()
        command.downgrade(config, "head:0003_academic_scheduling", sql=True)
        self.assertIn("DROP TABLE reservations", output.getvalue())
        self.assertNotIn("DROP TABLE rooms", output.getvalue())
