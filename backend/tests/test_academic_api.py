"""Academic HTTP tests: disposable SQLite only, private settings access blocked."""

from datetime import datetime, timezone
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_session
from app.main import app
from app.models import Building, Campus, Floor, Room, RoomType, Workspace
from app.schemas import ScheduleEntryRead

RESOURCES = ["departments", "faculty", "courses", "sections", "schedule-entries"]
PARENTS = [("faculty", "department_id", "departments"), ("courses", "department_id", "departments"),
           ("sections", "course_id", "courses"), ("schedule-entries", "room_id", "rooms"),
           ("schedule-entries", "section_id", "sections"), ("schedule-entries", "faculty_id", "faculty")]


class AcademicAPITests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        event.listen(self.engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        for target in ["app.database.get_engine", "app.database.get_settings", "app.config.get_settings"]:
            guard = patch(target, side_effect=AssertionError("Private database/configuration access forbidden"))
            guard.start()
            self.addCleanup(guard.stop)
        previous = app.dependency_overrides.copy()
        def restore():
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)
        self.addCleanup(restore)
        def test_session():
            with Session(self.engine) as session:
                yield session
        app.dependency_overrides[get_session] = test_session
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.a, self.b = str(uuid4()), str(uuid4())
        self.data = {}
        for wid in [self.a, self.b]:
            with Session(self.engine) as session:
                workspace = Workspace(id=UUID(wid), name=wid, slug=wid)
                session.add(workspace)
                session.flush()
                campus = Campus(workspace_id=workspace.id, name="Campus", code="C")
                building = Building(workspace_id=workspace.id, campus=campus, name="Building", code="B")
                floor = Floor(workspace_id=workspace.id, building=building, name="Floor", floor_number=1)
                room_type = RoomType(workspace_id=workspace.id, name="Type")
                room = Room(workspace_id=workspace.id, floor=floor, room_type=room_type, name="Room", code="R", capacity=10)
                session.add_all([campus, building, floor, room_type, room])
                session.flush()
                self.data[wid] = {"rooms": {"id": str(room.id)}}
                session.commit()
            for resource in RESOURCES:
                result = self.client.post(self.url(wid, resource), json=self.payload(wid, resource))
                self.assertEqual(result.status_code, 201, result.text)
                self.data[wid][resource] = result.json()

    def url(self, wid, resource, resource_id=None):
        return f"/api/workspaces/{wid}/{resource}" + (f"/{resource_id}" if resource_id else "")

    def item(self, resource, wid=None):
        wid = wid or self.a
        return self.url(wid, resource, self.data[wid][resource]["id"])

    def payload(self, wid, resource):
        data = self.data[wid]
        if resource == "schedule-entries":
            return {"room_id": data["rooms"]["id"], "section_id": data["sections"]["id"],
                    "faculty_id": data["faculty"]["id"], "starts_at": "2026-10-01T09:00:00+02:00",
                    "ends_at": "2026-10-01T10:00:00+02:00"}
        values = {"name": "Example"}
        if resource in {"departments", "courses"}:
            values["code"] = "CODE"
        if resource in {"faculty", "courses"}:
            values["department_id"] = data["departments"]["id"]
        if resource == "faculty":
            values["email"] = "teacher@example.test"
        if resource == "sections":
            values.update(course_id=data["courses"]["id"], student_count=20)
        return values

    def error(self, response, status, code=None):
        self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(set(response.json()["detail"]), {"code", "message"})
        if code:
            self.assertEqual(response.json()["detail"]["code"], code)

    def change(self, resource):
        return {"ends_at": "2026-10-01T09:00:00Z"} if resource == "schedule-entries" else {"name": "Changed"}

    def test_create_list_get_patch_all_resources(self):
        for resource in RESOURCES:
            with self.subTest(resource=resource):
                original = self.data[self.a][resource]
                self.assertEqual(original["workspace_id"], self.a)
                self.assertTrue(original["is_active"])
                self.assertIsNotNone(datetime.fromisoformat(original["created_at"]).utcoffset())
                self.assertEqual(self.client.get(self.url(self.a, resource)).json(), [original])
                self.assertEqual(self.client.get(self.item(resource)).json(), original)
                result = self.client.patch(self.item(resource), json=self.change(resource))
                self.assertEqual(result.status_code, 200, result.text)
                for key, value in self.change(resource).items():
                    self.assertEqual(result.json()[key], value)
                self.assertEqual(self.client.get(self.item(resource)).json(), result.json())
                self.assertEqual(self.client.get(self.item(resource, self.b)).json(), self.data[self.b][resource])

    def test_deactivate_reactivate_no_delete(self):
        for resource in RESOURCES:
            for _ in range(2):
                result = self.client.post(self.item(resource) + "/deactivate")
                self.assertEqual(result.status_code, 200, result.text)
                self.assertFalse(result.json()["is_active"])
            self.assertFalse(self.client.get(self.item(resource)).json()["is_active"])
            self.assertEqual(len(self.client.get(self.url(self.a, resource)).json()), 1)
            result = self.client.patch(self.item(resource), json={"is_active": True})
            self.assertTrue(result.json()["is_active"])
            self.error(self.client.delete(self.item(resource)), 405)

    def test_cross_workspace_and_missing_resource_reads_writes(self):
        for resource in RESOURCES:
            for resource_id in [self.data[self.b][resource]["id"], str(uuid4())]:
                path = self.url(self.a, resource, resource_id)
                self.error(self.client.get(path), 404, "resource_not_found")
                self.error(self.client.patch(path, json=self.change(resource)), 404, "resource_not_found")
                self.error(self.client.post(path + "/deactivate"), 404, "resource_not_found")
            self.assertEqual(self.client.get(self.item(resource, self.b)).json(), self.data[self.b][resource])

    def test_missing_workspace_all_operations(self):
        missing = str(uuid4())
        for resource in RESOURCES:
            path = self.url(missing, resource)
            self.error(self.client.post(path, json=self.payload(self.a, resource)), 404, "workspace_not_found")
            self.error(self.client.get(path), 404, "workspace_not_found")
            path += "/" + self.data[self.a][resource]["id"]
            self.error(self.client.get(path), 404, "workspace_not_found")
            self.error(self.client.patch(path, json=self.change(resource)), 404, "workspace_not_found")
            self.error(self.client.post(path + "/deactivate"), 404, "workspace_not_found")

    def test_invalid_and_cross_workspace_parents_create_patch(self):
        for resource, field, parent in PARENTS:
            for invalid in [self.data[self.b][parent]["id"], str(uuid4())]:
                with self.subTest(resource=resource, field=field):
                    values = self.payload(self.a, resource) | {field: invalid}
                    self.error(self.client.post(self.url(self.a, resource), json=values), 422, "invalid_parent")
                    self.error(self.client.patch(self.item(resource), json={field: invalid}), 422, "invalid_parent")
                    self.assertEqual(self.client.get(self.item(resource)).json(), self.data[self.a][resource])

    def test_valid_parent_changes(self):
        for resource, field, parent in PARENTS:
            if parent == "rooms":
                room = self.client.get(self.url(self.a, "rooms", self.data[self.a]["rooms"]["id"])).json()
                payload = {key: room[key] for key in ["name", "floor_id", "room_type_id", "capacity"]} | {"code": "NEW"}
            else:
                payload = self.payload(self.a, parent)
                if "code" in payload:
                    payload["code"] = str(uuid4())
                elif "email" in payload:
                    payload["email"] = f"{uuid4()}@example.test"
                else:
                    payload["name"] = str(uuid4())
            result = self.client.post(self.url(self.a, parent), json=payload)
            self.assertEqual(result.status_code, 201, result.text)
            updated = self.client.patch(self.item(resource), json={field: result.json()["id"]})
            self.assertEqual(updated.status_code, 200, updated.text)
            self.assertEqual(updated.json()[field], result.json()["id"])

    def test_duplicates_and_recovery(self):
        for resource, field in [("departments", "code"), ("faculty", "email"), ("courses", "code"), ("sections", "name")]:
            values = self.payload(self.a, resource)
            self.error(self.client.post(self.url(self.a, resource), json=values), 409, "duplicate_resource")
            other = values | {field: "other@example.test" if field == "email" else "OTHER"}
            result = self.client.post(self.url(self.a, resource), json=other)
            self.assertEqual(result.status_code, 201, result.text)
            path = self.url(self.a, resource, result.json()["id"])
            self.error(self.client.patch(path, json={field: values[field]}), 409, "duplicate_resource")
            self.assertEqual(self.client.get(path).json()[field], other[field])
            self.assertEqual(self.client.patch(path, json={"is_active": False}).status_code, 200)

    def test_section_names_scoped_to_course_and_parent_change_collision(self):
        course = self.client.post(self.url(self.a, "courses"), json=self.payload(self.a, "courses") | {"code": "OTHER"}).json()
        second = self.client.post(self.url(self.a, "sections"), json=self.payload(self.a, "sections") | {"course_id": course["id"]})
        self.assertEqual(second.status_code, 201, second.text)
        self.error(self.client.patch(self.url(self.a, "sections", second.json()["id"]),
                                     json={"course_id": self.data[self.a]["courses"]["id"]}), 409, "duplicate_resource")

    def test_invalid_student_counts(self):
        for value in [0, -1, None, True, 2.5, "20", 2147483648]:
            self.error(self.client.post(self.url(self.a, "sections"), json=self.payload(self.a, "sections") | {"student_count": value}), 422)
            self.error(self.client.patch(self.item("sections"), json={"student_count": value}), 422)
        self.assertEqual(self.client.patch(self.item("sections"), json={"student_count": 1}).status_code, 200)

    def test_invalid_schedule_ranges_and_partial_patches(self):
        for values in [
            {"starts_at": "2026-10-01T10:00:00Z", "ends_at": "2026-10-01T10:00:00Z"},
            {"starts_at": "2026-10-01T11:00:00Z", "ends_at": "2026-10-01T10:00:00Z"},
            {"starts_at": "2026-10-01T10:00:00+02:00", "ends_at": "2026-10-01T08:00:00Z"},
        ]:
            self.error(self.client.post(self.url(self.a, "schedule-entries"), json=self.payload(self.a, "schedule-entries") | values), 422, "validation_error")
            self.error(self.client.patch(self.item("schedule-entries"), json=values), 422, "validation_error")
        for values in [{"starts_at": "2026-10-01T08:00:00Z"}, {"starts_at": "2026-10-01T09:00:00Z"},
                       {"ends_at": "2026-10-01T07:00:00Z"}, {"ends_at": "2026-10-01T06:00:00Z"}]:
            self.error(self.client.patch(self.item("schedule-entries"), json=values), 422, "validation_error")
            self.assertEqual(self.client.get(self.item("schedule-entries")).json(), self.data[self.a]["schedule-entries"])
        for values in [{"starts_at": "2026-10-01T07:30:00Z"}, {"ends_at": "2026-10-01T08:30:00Z"},
                       {"starts_at": "2026-10-02T11:00:00Z", "ends_at": "2026-10-02T12:00:00Z"}]:
            result = self.client.patch(self.item("schedule-entries"), json=values)
            self.assertEqual(result.status_code, 200, result.text)
            for field, value in values.items():
                self.assertEqual(result.json()[field], value)

    def test_naive_malformed_and_null_times_rejected(self):
        for field in ["starts_at", "ends_at"]:
            for value in ["2026-10-01T09:00:00", "2026-10-01", "bad", None]:
                self.error(self.client.post(self.url(self.a, "schedule-entries"),
                                           json=self.payload(self.a, "schedule-entries") | {field: value}), 422)
                self.error(self.client.patch(self.item("schedule-entries"), json={field: value}), 422)

    def test_timezone_serialization_and_offset_ordering(self):
        payload = self.payload(self.a, "schedule-entries") | {
            "starts_at": "2026-10-01T13:15:00.123456+05:45",  # 07:30 UTC
            "ends_at": "2026-10-01T04:00:00.654321-04:00",  # 08:00 UTC
        }
        created = self.client.post(self.url(self.a, "schedule-entries"), json=payload)
        self.assertEqual(created.status_code, 201, created.text)
        path = self.url(self.a, "schedule-entries", created.json()["id"])
        responses = [created.json(), self.client.get(path).json()]
        listed = self.client.get(self.url(self.a, "schedule-entries")).json()
        responses.append(next(record for record in listed if record["id"] == created.json()["id"]))
        self.assertIsNotNone(ScheduleEntryRead.model_validate_json(created.text).starts_at.utcoffset())
        for record in responses:
            for field in ["starts_at", "ends_at"]:
                value = datetime.fromisoformat(record[field])
                self.assertIsNotNone(value.utcoffset())
                self.assertEqual(value, datetime.fromisoformat(payload[field]).astimezone(timezone.utc))
        result = self.client.patch(path, json={"ends_at": "2026-10-01T11:45:00+03:30"})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["ends_at"], "2026-10-01T08:15:00Z")

    def test_overlaps_duplicates_and_adjacent_intervals_allowed(self):
        base = self.payload(self.a, "schedule-entries")
        for values in [{}, {"starts_at": "2026-10-01T07:15:00Z"},
                       {"starts_at": "2026-10-01T08:00:00Z", "ends_at": "2026-10-01T09:00:00Z"}]:
            result = self.client.post(self.url(self.a, "schedule-entries"), json=base | values)
            self.assertEqual(result.status_code, 201, result.text)
            result = self.client.patch(self.url(self.a, "schedule-entries", result.json()["id"]),
                                       json={"starts_at": "2026-10-01T07:00:00Z", "ends_at": "2026-10-01T08:00:00Z"})
            self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(len(self.client.get(self.url(self.a, "schedule-entries")).json()), 4)

    def test_reject_ownership_fields_empty_null_unknown_patches(self):
        for resource in RESOURCES:
            for field, value in [("workspace_id", self.b), ("id", str(uuid4())), ("created_at", "2026-01-01"), ("unknown", "x")]:
                self.error(self.client.post(self.url(self.a, resource), json=self.payload(self.a, resource) | {field: value}), 422)
                self.error(self.client.patch(self.item(resource), json={field: value}), 422)
            self.error(self.client.patch(self.item(resource), json={}), 422)
            for field in self.payload(self.a, resource):
                self.error(self.client.patch(self.item(resource), json={field: None}), 422)
        for email in ["not-an-email", "a b@example.test", "a@@example.test"]:
            self.error(self.client.patch(self.item("faculty"), json={"email": email}), 422)

    def test_pagination_and_malformed_identifiers(self):
        for resource in RESOURCES:
            path = self.url(self.a, resource)
            self.assertEqual(self.client.get(path + "?limit=1").json(), [self.data[self.a][resource]])
            self.assertEqual(self.client.get(path + "?offset=1").json(), [])
            for query in ["limit=0", "limit=201", "offset=-1"]:
                self.error(self.client.get(path + "?" + query), 422)
            self.error(self.client.get(path + "/bad-id"), 422)
            self.error(self.client.get(self.url("bad-workspace", resource)), 422)

    def test_scoped_sql_writes_and_rollback_on_database_failure(self):
        statements = []
        def capture(conn, cursor, statement, parameters, context, many):
            statements.append(statement)
        event.listen(self.engine, "before_cursor_execute", capture)
        for resource in RESOURCES:
            self.assertEqual(self.client.patch(self.item(resource), json=self.change(resource)).status_code, 200)
            self.assertEqual(self.client.post(self.item(resource) + "/deactivate").status_code, 200)
        writes = [sql for sql in statements if sql.startswith("UPDATE")]
        self.assertEqual(len(writes), 10)
        for sql in writes:
            self.assertIn("workspace_id", sql.split("WHERE")[1])
        original = self.client.get(self.item("schedule-entries")).json()
        with patch.object(Session, "commit", side_effect=IntegrityError("PRIVATE SQL", {}, Exception("PRIVATE details"))):
            failed = self.client.patch(self.item("schedule-entries"), json={"ends_at": "2026-10-01T11:00:00Z"})
        self.error(failed, 409, "integrity_conflict")
        self.assertNotIn("PRIVATE", failed.text)
        self.assertEqual(self.client.get(self.item("schedule-entries")).json(), original)

    def test_openapi_and_health(self):
        schema = self.client.get("/openapi.json").json()
        for resource in RESOURCES:
            path = f"/api/workspaces/{{workspace_id}}/{resource}"
            self.assertTrue({"get", "post"} <= schema["paths"][path].keys())
            self.assertTrue({"get", "patch"} <= schema["paths"][path + "/{resource_id}"].keys())
            self.assertIn("post", schema["paths"][path + "/{resource_id}/deactivate"])
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
