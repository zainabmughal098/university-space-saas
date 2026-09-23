"""HTTP tests use an isolated in-memory database; production access is forbidden."""

import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_session
from app.main import app
from app.models import Workspace

ACTIVE = {"campuses", "buildings", "floors", "rooms"}
RESOURCES = ["campuses", "buildings", "floors", "room-types", "facilities", "rooms"]


class InfrastructureAPITests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        event.listen(self.engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        # Fail closed even if a route accidentally bypasses the overridden dependency.
        self.addCleanup(patch.stopall)
        patch("app.database.get_engine", side_effect=AssertionError("Production database access forbidden")).start()
        patch("app.config.get_settings", side_effect=AssertionError("Private settings access forbidden")).start()
        self.original_overrides = app.dependency_overrides.copy()
        self.addCleanup(self.restore_overrides)

        def test_session():
            with Session(self.engine) as session:
                yield session

        app.dependency_overrides[get_session] = test_session
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.a, self.b = str(uuid4()), str(uuid4())
        with Session(self.engine) as session:
            from uuid import UUID
            session.add_all([Workspace(id=UUID(self.a), name="A", slug="a"), Workspace(id=UUID(self.b), name="B", slug="b")])
            session.commit()
        self.data = {}
        for workspace in [self.a, self.b]:
            self.data[workspace] = {}
            for resource in RESOURCES:
                result = self.client.post(self.url(workspace, resource), json=self.payload(workspace, resource))
                self.assertEqual(result.status_code, 201, result.text)
                self.data[workspace][resource] = result.json()

    def restore_overrides(self):
        app.dependency_overrides.clear()
        app.dependency_overrides.update(self.original_overrides)

    def url(self, workspace, resource, suffix=""):
        return f"/api/workspaces/{workspace}/{resource}{suffix}"

    def payload(self, workspace, resource):
        data = self.data[workspace]
        payload = {"name": "Example"}
        if resource in {"campuses", "buildings", "rooms"}:
            payload["code"] = "CODE"
        if resource == "buildings":
            payload["campus_id"] = data["campuses"]["id"]
        if resource == "floors":
            payload.update(building_id=data["buildings"]["id"], floor_number=-1)
        if resource == "rooms":
            payload.update(floor_id=data["floors"]["id"], room_type_id=data["room-types"]["id"], capacity=20)
        return payload

    def error(self, response, status, code=None):
        self.assertEqual(response.status_code, status, response.text)
        detail = response.json()["detail"]
        self.assertEqual(set(detail), {"code", "message"})
        if code:
            self.assertEqual(detail["code"], code)

    def test_create_list_get_update_all_resources(self):
        for resource in RESOURCES:
            with self.subTest(resource=resource):
                created = self.data[self.a][resource]
                self.assertEqual(created["workspace_id"], self.a)
                self.assertIn("created_at", created)
                listing = self.client.get(self.url(self.a, resource))
                self.assertEqual(listing.status_code, 200)
                self.assertEqual(listing.json(), [created])
                path = self.url(self.a, resource, "/" + created["id"])
                self.assertEqual(self.client.get(path).json(), created)
                changed = self.client.patch(path, json={"name": " Updated "})
                self.assertEqual(changed.status_code, 200, changed.text)
                self.assertEqual(changed.json()["name"], "Updated")
                self.assertEqual(self.client.get(path).json()["name"], "Updated")
                other = self.client.get(self.url(self.b, resource, "/" + self.data[self.b][resource]["id"]))
                self.assertEqual(other.json()["name"], "Example")

    def test_deactivate_is_idempotent_preserves_records_and_can_reactivate(self):
        for resource in ACTIVE:
            path = self.url(self.a, resource, "/" + self.data[self.a][resource]["id"])
            for _ in range(2):
                result = self.client.post(path + "/deactivate")
                self.assertEqual(result.status_code, 200, result.text)
                self.assertFalse(result.json()["is_active"])
            self.assertFalse(self.client.get(path).json()["is_active"])
            self.assertEqual(len(self.client.get(self.url(self.a, resource)).json()), 1)
            self.assertTrue(self.client.patch(path, json={"is_active": True}).json()["is_active"])
        for resource in RESOURCES:
            path = self.url(self.a, resource, "/" + self.data[self.a][resource]["id"])
            self.error(self.client.delete(path), 405)
        for resource in ["room-types", "facilities"]:
            self.error(self.client.post(self.url(self.a, resource, "/" + self.data[self.a][resource]["id"] + "/deactivate")), 404)

    def test_cross_workspace_and_missing_resources_are_indistinguishable(self):
        for resource in RESOURCES:
            for resource_id in [self.data[self.b][resource]["id"], str(uuid4())]:
                with self.subTest(resource=resource, id=resource_id):
                    path = self.url(self.a, resource, "/" + resource_id)
                    self.error(self.client.get(path), 404, "resource_not_found")
                    self.error(self.client.patch(path, json={"name": "Attack"}), 404, "resource_not_found")
                    if resource in ACTIVE:
                        self.error(self.client.post(path + "/deactivate"), 404, "resource_not_found")
            actual = self.client.get(self.url(self.b, resource, "/" + self.data[self.b][resource]["id"]))
            self.assertEqual(actual.json(), self.data[self.b][resource])

    def test_nonexistent_workspace_on_every_operation(self):
        missing = str(uuid4())
        for resource in RESOURCES:
            path = self.url(missing, resource)
            self.error(self.client.get(path), 404, "workspace_not_found")
            self.error(self.client.post(path, json=self.payload(self.a, resource)), 404, "workspace_not_found")
            item = path + "/" + self.data[self.a][resource]["id"]
            self.error(self.client.get(item), 404, "workspace_not_found")
            self.error(self.client.patch(item, json={"name": "Changed"}), 404, "workspace_not_found")
            if resource in ACTIVE:
                self.error(self.client.post(item + "/deactivate"), 404, "workspace_not_found")
        path = self.url(missing, "rooms", "/" + self.data[self.a]["rooms"]["id"] + "/facilities")
        self.error(self.client.get(path), 404, "workspace_not_found")
        path += "/" + self.data[self.a]["facilities"]["id"]
        self.error(self.client.post(path), 404, "workspace_not_found")
        self.error(self.client.delete(path), 404, "workspace_not_found")

    def test_parent_validation_on_create_and_update(self):
        for resource, field, parent in [("buildings", "campus_id", "campuses"), ("floors", "building_id", "buildings"),
                                         ("rooms", "floor_id", "floors"), ("rooms", "room_type_id", "room-types")]:
            for invalid_id in [self.data[self.b][parent]["id"], str(uuid4())]:
                with self.subTest(resource=resource, field=field):
                    payload = self.payload(self.a, resource)
                    payload[field] = invalid_id
                    path = self.url(self.a, resource)
                    self.error(self.client.post(path, json=payload), 422, "invalid_parent")
                    item = path + "/" + self.data[self.a][resource]["id"]
                    self.error(self.client.patch(item, json={field: invalid_id}), 422, "invalid_parent")
                    self.assertEqual(self.client.get(item).json()[field], self.data[self.a][resource][field])

    def test_valid_parent_changes(self):
        for resource, field, parent in [("buildings", "campus_id", "campuses"), ("floors", "building_id", "buildings"),
                                         ("rooms", "floor_id", "floors"), ("rooms", "room_type_id", "room-types")]:
            payload = self.payload(self.a, parent)
            if "code" in payload:
                payload["code"] = "OTHER"
            elif "floor_number" in payload:
                payload["floor_number"] = 4
            else:
                payload["name"] = "Other"
            created = self.client.post(self.url(self.a, parent), json=payload)
            self.assertEqual(created.status_code, 201, created.text)
            result = self.client.patch(self.url(self.a, resource, "/" + self.data[self.a][resource]["id"]),
                                       json={field: created.json()["id"]})
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()[field], created.json()["id"])

    def test_duplicates_create_and_update_and_recovery(self):
        for resource in RESOURCES:
            path = self.url(self.a, resource)
            self.error(self.client.post(path, json=self.payload(self.a, resource)), 409, "duplicate_resource")
            payload = self.payload(self.a, resource)
            field = "code" if "code" in payload else "floor_number" if "floor_number" in payload else "name"
            original = payload[field]
            payload[field] = 2 if field == "floor_number" else "SECOND"
            created = self.client.post(path, json=payload)
            self.assertEqual(created.status_code, 201, created.text)
            item = path + "/" + created.json()["id"]
            self.error(self.client.patch(item, json={field: original}), 409, "duplicate_resource")
            self.assertEqual(self.client.get(item).json()[field], payload[field])
            self.assertEqual(self.client.patch(item, json={"name": "After failure"}).status_code, 200)

    def test_invalid_capacity_and_floor_numbers(self):
        for capacity in [0, -1, 1.5, True, "20", None, 2147483648]:
            with self.subTest(capacity=capacity):
                payload = self.payload(self.a, "rooms") | {"capacity": capacity, "code": "NEW"}
                self.error(self.client.post(self.url(self.a, "rooms"), json=payload), 422, "validation_error")
                self.error(self.client.patch(self.url(self.a, "rooms", "/" + self.data[self.a]["rooms"]["id"]),
                                             json={"capacity": capacity}), 422, "validation_error")
        for number in [1.5, True, "2", None, 2147483648, -2147483649]:
            self.error(self.client.post(self.url(self.a, "floors"), json=self.payload(self.a, "floors") | {"floor_number": number}), 422)

    def test_reject_ownership_injection_unknown_fields_and_invalid_patch(self):
        for resource in RESOURCES:
            path = self.url(self.a, resource)
            for field, value in [("workspace_id", self.b), ("id", str(uuid4())), ("created_at", "2026-01-01"), ("unknown", "x")]:
                self.error(self.client.post(path, json=self.payload(self.a, resource) | {field: value}), 422)
                self.error(self.client.patch(path + "/" + self.data[self.a][resource]["id"], json={field: value}), 422)
            for payload in [{}, {"name": None}, {"name": "  "}, {"name": "x" * 256}]:
                self.error(self.client.patch(path + "/" + self.data[self.a][resource]["id"], json=payload), 422)
        self.error(self.client.post(self.url(self.a, "campuses"), json={"name": "X", "code": "x" * 65}), 422)

    def test_nullable_patch_fields_can_be_cleared(self):
        for resource, field in [("campuses", "address"), ("room-types", "description"), ("facilities", "description")]:
            path = self.url(self.a, resource, "/" + self.data[self.a][resource]["id"])
            self.assertEqual(self.client.patch(path, json={field: "Text"}).json()[field], "Text")
            result = self.client.patch(path, json={field: None})
            self.assertEqual(result.status_code, 200)
            self.assertIsNone(result.json()[field])

    def test_room_facility_lifecycle_and_duplicate(self):
        room = self.data[self.a]["rooms"]["id"]
        facility = self.data[self.a]["facilities"]["id"]
        path = self.url(self.a, "rooms", f"/{room}/facilities")
        self.assertEqual(self.client.get(path).json(), [])
        assigned = self.client.post(path + "/" + facility)
        self.assertEqual(assigned.status_code, 201, assigned.text)
        self.assertEqual(assigned.json(), {"workspace_id": self.a, "room_id": room, "facility_id": facility})
        self.error(self.client.post(path + "/" + facility), 409, "duplicate_assignment")
        self.assertEqual(self.client.get(path).json(), [self.data[self.a]["facilities"]])
        removed = self.client.delete(path + "/" + facility)
        self.assertEqual(removed.status_code, 204)
        self.assertEqual(removed.content, b"")
        self.assertEqual(self.client.get(path).json(), [])
        self.error(self.client.delete(path + "/" + facility), 404, "assignment_not_found")
        self.assertEqual(self.client.get(self.url(self.a, "facilities", "/" + facility)).status_code, 200)

    def test_room_facility_cross_workspace_attempts(self):
        a_room, b_room = (self.data[w]["rooms"]["id"] for w in [self.a, self.b])
        a_facility, b_facility = (self.data[w]["facilities"]["id"] for w in [self.a, self.b])
        b_path = self.url(self.b, "rooms", f"/{b_room}/facilities/{b_facility}")
        self.assertEqual(self.client.post(b_path).status_code, 201)
        for room, facility in [(a_room, b_facility), (b_room, a_facility), (b_room, b_facility),
                                (a_room, str(uuid4())), (str(uuid4()), a_facility)]:
            path = self.url(self.a, "rooms", f"/{room}/facilities/{facility}")
            self.error(self.client.post(path), 404, "resource_not_found")
            self.error(self.client.delete(path), 404, "resource_not_found")
        self.error(self.client.get(self.url(self.a, "rooms", f"/{b_room}/facilities")), 404)
        self.assertEqual(len(self.client.get(self.url(self.b, "rooms", f"/{b_room}/facilities")).json()), 1)

    def test_pagination_and_invalid_ids(self):
        for resource in RESOURCES:
            path = self.url(self.a, resource)
            self.assertEqual(self.client.get(path + "?limit=1&offset=0").json(), [self.data[self.a][resource]])
            self.assertEqual(self.client.get(path + "?offset=1").json(), [])
            for query in ["limit=0", "limit=201", "offset=-1", "limit=bad"]:
                self.error(self.client.get(path + "?" + query), 422)
            self.error(self.client.get(path + "/not-a-uuid"), 422)
        self.error(self.client.get(self.url("not-a-uuid", "campuses")), 422)

    def test_database_failures_are_sanitized_and_writes_rollback(self):
        # Simulate a race after pre-validation; no database diagnostics escape.
        failure = IntegrityError("SECRET SQL", {}, Exception("SECRET connection data"))
        with patch.object(Session, "commit", side_effect=failure):
            result = self.client.post(self.url(self.a, "campuses"), json={"name": "Race", "code": "RACE"})
        self.error(result, 409, "integrity_conflict")
        self.assertNotIn("SECRET", result.text)
        self.assertEqual(len(self.client.get(self.url(self.a, "campuses")).json()), 1)
        with patch.object(Session, "scalar", side_effect=OperationalError("SECRET SQL", {}, Exception("SECRET URL"))):
            result = self.client.get(self.url(self.a, "campuses"))
        self.error(result, 503, "database_unavailable")
        self.assertNotIn("SECRET", result.text)

    def test_mutation_sql_includes_workspace_predicates(self):
        statements = []
        def capture(conn, cursor, statement, params, context, many):
            statements.append(statement)
        event.listen(self.engine, "before_cursor_execute", capture)
        for resource in RESOURCES:
            item = self.url(self.a, resource, "/" + self.data[self.a][resource]["id"])
            self.assertEqual(self.client.patch(item, json={"name": "Updated"}).status_code, 200)
            if resource in ACTIVE:
                self.assertEqual(self.client.post(item + "/deactivate").status_code, 200)
        path = self.url(self.a, "rooms", "/" + self.data[self.a]["rooms"]["id"] + "/facilities/" + self.data[self.a]["facilities"]["id"])
        self.assertEqual(self.client.post(path).status_code, 201)
        self.assertEqual(self.client.delete(path).status_code, 204)
        writes = [sql for sql in statements if sql.startswith(("UPDATE", "DELETE"))]
        self.assertEqual(len(writes), 11)
        for statement in writes:
            self.assertIn("workspace_id", statement.split("WHERE", 1)[1])

    def test_health_and_openapi(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        schema = self.client.get("/openapi.json").json()
        self.assertIn("CampusCreate", schema["components"]["schemas"])
        self.assertIn("RoomUpdate", schema["components"]["schemas"])
        for resource in RESOURCES:
            self.assertIn(f"/api/workspaces/{{workspace_id}}/{resource}", schema["paths"])
