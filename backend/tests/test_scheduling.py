"""Conflict and availability HTTP checks against disposable SQLite only."""

from datetime import datetime
import unittest
from uuid import UUID, uuid4

from sqlalchemy import event
from sqlalchemy.dialects import postgresql

from test_academic_api import AcademicAPIFixture


class SchedulingTests(AcademicAPIFixture, unittest.TestCase):
    def room(self, code, capacity=30, room_type_id=None, is_active=True):
        base = self.client.get(self.url(self.a, "rooms", self.data[self.a]["rooms"]["id"])).json()
        response = self.client.post(self.url(self.a, "rooms"), json={
            "name": code, "code": code, "floor_id": base["floor_id"],
            "room_type_id": room_type_id or base["room_type_id"], "capacity": capacity, "is_active": is_active,
        })
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def faculty(self, name="Other"):
        response = self.client.post(self.url(self.a, "faculty"), json={
            "name": name, "email": name + "@example.test", "department_id": self.data[self.a]["departments"]["id"],
        })
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def section(self, name="Other", count=20):
        response = self.client.post(self.url(self.a, "sections"), json={
            "name": name, "course_id": self.data[self.a]["courses"]["id"], "student_count": count,
        })
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def schedule(self, **changes):
        return self.client.post(self.url(self.a, "schedule-entries"),
                                json=self.payload(self.a, "schedule-entries") | changes)

    def interval(self, start="07:00:00Z", end="08:00:00Z"):
        return {"starts_at": "2026-10-01T" + start, "ends_at": "2026-10-01T" + end}

    def search(self, *, wid=None, **filters):
        return self.client.get(self.url(wid or self.a, "rooms") + "/availability", params=self.interval() | filters)

    def check(self, room_id=None, *, wid=None, **filters):
        return self.client.get(self.url(wid or self.a, "rooms", room_id or self.data[self.a]["rooms"]["id"]) + "/availability",
                               params=self.interval() | filters)

    def conflict(self, response, kinds, entry_id=None):
        self.assertEqual(response.status_code, 409, response.text)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "schedule_conflict")
        self.assertTrue(detail["has_conflicts"])
        self.assertTrue(detail["conflicts"])
        conflict = detail["conflicts"][0]
        self.assertEqual(conflict["conflict_types"], kinds)
        self.assertEqual(conflict["schedule_entry_id"], entry_id or self.data[self.a]["schedule-entries"]["id"])
        for field in ["room_id", "faculty_id", "section_id"]:
            UUID(conflict[field])
        for field in ["starts_at", "ends_at"]:
            self.assertIsNotNone(datetime.fromisoformat(conflict[field]).utcoffset())

    def test_all_overlap_shapes(self):
        for start, end in [("07:00:00Z", "08:00:00Z"), ("06:30:00Z", "07:30:00Z"),
                           ("07:30:00Z", "08:30:00Z"), ("07:15:00Z", "07:45:00Z"),
                           ("06:00:00Z", "09:00:00Z")]:
            with self.subTest(start=start, end=end):
                self.conflict(self.schedule(**self.interval(start, end)), ["room", "faculty", "section"])
        self.assertEqual(len(self.client.get(self.url(self.a, "schedule-entries")).json()), 1)

    def test_back_to_back_both_boundaries_and_timezone_offsets(self):
        for times in [self.interval("06:00:00Z", "07:00:00Z"), self.interval("10:00:00+02:00", "11:00:00+02:00")]:
            response = self.schedule(**times)
            self.assertEqual(response.status_code, 201, response.text)
        response = self.check(**self.interval("09:00:00Z", "10:00:00Z"))
        self.assertTrue(response.json()["available"])

    def test_individual_conflict_types(self):
        room = self.room("OTHER")
        faculty = self.faculty()
        section = self.section()
        for changes, kinds in [({"faculty_id": faculty["id"], "section_id": section["id"]}, ["room"]),
                               ({"room_id": room["id"], "section_id": section["id"]}, ["faculty"]),
                               ({"room_id": room["id"], "faculty_id": faculty["id"]}, ["section"])]:
            self.conflict(self.schedule(**changes), kinds)

    def test_multiple_conflicting_entries_deterministic_details(self):
        later = self.schedule(**self.interval("08:00:00Z", "09:00:00Z"))
        self.assertEqual(later.status_code, 201, later.text)
        proposed = self.interval("07:30:00Z", "08:30:00Z")
        first = self.schedule(**proposed)
        second = self.schedule(**proposed)
        self.assertEqual(first.json(), second.json())
        conflicts = first.json()["detail"]["conflicts"]
        self.assertEqual([row["schedule_entry_id"] for row in conflicts],
                         [self.data[self.a]["schedule-entries"]["id"], later.json()["id"]])

    def test_inactive_entries_ignored_and_reactivation_checked(self):
        inactive = self.schedule(is_active=False)
        self.assertEqual(inactive.status_code, 201, inactive.text)
        path = self.url(self.a, "schedule-entries", inactive.json()["id"])
        self.conflict(self.client.patch(path, json={"is_active": True}), ["room", "faculty", "section"])
        self.assertEqual(self.client.post(self.item("schedule-entries") + "/deactivate").status_code, 200)
        self.assertTrue(self.check().json()["available"])
        self.assertEqual(self.client.patch(path, json={"is_active": True}).status_code, 200)
        self.assertFalse(self.check().json()["available"])
        self.conflict(self.client.patch(self.item("schedule-entries"), json={"is_active": True}),
                      ["room", "faculty", "section"], entry_id=inactive.json()["id"])

    def test_update_excludes_self_and_rejects_overlap_without_change(self):
        path = self.item("schedule-entries")
        response = self.client.patch(path, json=self.interval())
        self.assertEqual(response.status_code, 200, response.text)
        later = self.schedule(**self.interval("08:00:00Z", "09:00:00Z"))
        self.assertEqual(later.status_code, 201, later.text)
        self.conflict(self.client.patch(path, json={"ends_at": "2026-10-01T08:30:00Z"}),
                      ["room", "faculty", "section"], entry_id=later.json()["id"])
        self.assertEqual(self.client.get(path).json()["ends_at"], "2026-10-01T08:00:00Z")
        # Disabling an entry permits moving it into an occupied interval.
        self.assertEqual(self.client.patch(path, json=self.interval("08:00:00Z", "09:00:00Z") | {"is_active": False}).status_code, 200)

    def test_capacity_rejected_on_create_room_change_and_section_change(self):
        small = self.room("SMALL", capacity=19)
        times = self.interval("10:00:00Z", "11:00:00Z")
        result = self.schedule(room_id=small["id"], **times)
        self.error(result, 422, "insufficient_capacity")
        self.assertIn("19", result.json()["detail"]["message"])
        self.error(self.client.patch(self.item("schedule-entries"), json={"room_id": small["id"]}), 422, "insufficient_capacity")
        large_section = self.section("Large", count=31)
        self.error(self.client.patch(self.item("schedule-entries"), json={"section_id": large_section["id"]}), 422, "insufficient_capacity")
        exact = self.room("EXACT", capacity=20)
        result = self.schedule(room_id=exact["id"], **times)
        self.assertEqual(result.status_code, 201, result.text)

    def test_inactive_parents_rejected_for_active_schedule(self):
        for resource in ["rooms", "faculty", "sections"]:
            path = self.url(self.a, resource, self.data[self.a][resource]["id"])
            self.assertEqual(self.client.post(path + "/deactivate").status_code, 200)
            self.error(self.schedule(**self.interval("10:00:00Z", "11:00:00Z")), 422, "inactive_parent")
            self.assertEqual(self.client.patch(path, json={"is_active": True}).status_code, 200)

    def test_availability_search_context_active_filter_and_order(self):
        last = self.room("Z-LAST")
        first = self.room("A-FIRST")
        self.room("INACTIVE", is_active=False)
        result = self.search()
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual([room["id"] for room in result.json()], [first["id"], last["id"]])
        for room in result.json():
            self.assertEqual(room["workspace_id"], self.a)
            for context in ["room_type", "floor", "building", "campus"]:
                self.assertEqual(room[context]["workspace_id"], self.a)
            self.assertEqual(room["facilities"], [])
        page = self.search(limit=1, offset=1)
        self.assertEqual([room["id"] for room in page.json()], [last["id"]])
        self.assertEqual(self.search().json(), result.json())
        # Availability only checks room occupancy; faculty/section conflicts are not room filters.
        self.assertTrue(self.check(first["id"]).json()["available"])

    def test_minimum_capacity_and_room_type_filters(self):
        alternate = self.client.post(self.url(self.a, "room-types"), json={"name": "Alternate"}).json()
        self.room("SMALL", capacity=10)
        large = self.room("LARGE", capacity=40, room_type_id=alternate["id"])
        for filters in [{"minimum_capacity": 40}, {"room_type_id": alternate["id"]},
                        {"minimum_capacity": 20, "room_type_id": alternate["id"]}]:
            self.assertEqual([r["id"] for r in self.search(**filters).json()], [large["id"]])
        self.assertEqual(self.search(minimum_capacity=41).json(), [])

    def test_facilities_require_all_and_return_complete_facility_list(self):
        both, one, neither = self.room("BOTH"), self.room("ONE"), self.room("NONE")
        facilities = [self.client.post(self.url(self.a, "facilities"), json={"name": name}).json() for name in ["Projector", "Board", "Extra"]]
        for room, required in [(both, facilities), (one, facilities[:1])]:
            for facility in required:
                result = self.client.post(self.url(self.a, "rooms", room["id"]) + "/facilities/" + facility["id"])
                self.assertEqual(result.status_code, 201, result.text)
        filters = {"facility_ids": [facilities[0]["id"], facilities[1]["id"]]}
        result = self.search(**filters)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual([room["id"] for room in result.json()], [both["id"]])
        self.assertEqual([facility["name"] for facility in result.json()[0]["facilities"]], ["Board", "Extra", "Projector"])
        self.assertEqual(self.search(facility_ids=[facilities[0]["id"]] * 2).json(), self.search(facility_ids=[facilities[0]["id"]]).json())
        # Combining all filters still respects occupancy.
        result = self.schedule(room_id=both["id"], **self.interval("08:00:00Z", "09:00:00Z"))
        self.assertEqual(result.status_code, 201, result.text)
        self.assertEqual(self.search(**filters, **self.interval("08:00:00Z", "09:00:00Z"), minimum_capacity=20).json(), [])

    def test_specific_room_check_conflicts_boundaries_and_inactive_room(self):
        result = self.check()
        self.assertEqual(result.status_code, 200, result.text)
        data = result.json()
        self.assertFalse(data["available"])
        self.assertEqual(data["reason"], "schedule_conflict")
        self.assertTrue(data["has_conflicts"])
        self.assertEqual(data["conflicts"][0]["conflict_types"], ["room"])
        self.assertEqual(data["conflicts"][0]["schedule_entry_id"], self.data[self.a]["schedule-entries"]["id"])
        self.assertTrue(self.check(**self.interval("08:00:00Z", "09:00:00Z")).json()["available"])
        inactive = self.room("OFF", is_active=False)
        data = self.check(inactive["id"]).json()
        self.assertFalse(data["available"])
        self.assertEqual(data["reason"], "inactive_room")
        self.assertEqual(data["conflicts"], [])

    def test_workspace_isolation_and_filter_id_validation(self):
        foreign_room = self.data[self.b]["rooms"]["id"]
        foreign_type = self.client.get(self.url(self.b, "rooms", foreign_room)).json()["room_type_id"]
        foreign_facility = self.client.post(self.url(self.b, "facilities"), json={"name": "Private"}).json()["id"]
        self.error(self.check(foreign_room), 404, "resource_not_found")
        self.error(self.check(str(uuid4())), 404, "resource_not_found")
        for filters in [{"room_type_id": foreign_type}, {"room_type_id": str(uuid4())},
                        {"facility_ids": [foreign_facility]}, {"facility_ids": [str(uuid4())]}]:
            self.error(self.search(**filters), 422, "invalid_parent")
        for field, resource in [("room_id", "rooms"), ("faculty_id", "faculty"), ("section_id", "sections")]:
            value = self.data[self.b][resource]["id"]
            self.error(self.schedule(**{field: value}), 422, "invalid_parent")
            self.error(self.client.patch(self.item("schedule-entries"), json={field: value}), 422, "invalid_parent")
        # Identical intervals in B must never appear in A's conflict details.
        response = self.schedule()
        self.assertNotIn(self.data[self.b]["schedule-entries"]["id"], response.text)
        self.assertEqual(len(response.json()["detail"]["conflicts"]), 1)
        self.client.post(self.item("schedule-entries") + "/deactivate")
        self.assertTrue(self.check().json()["available"])
        self.assertEqual([r["id"] for r in self.search().json()], [self.data[self.a]["rooms"]["id"]])
        self.error(self.search(wid=str(uuid4())), 404, "workspace_not_found")
        self.error(self.check(wid=str(uuid4())), 404, "workspace_not_found")

    def test_invalid_intervals_timezone_and_filters(self):
        for values in [self.interval("08:00:00Z", "08:00:00Z"), self.interval("09:00:00Z", "08:00:00Z"),
                       self.interval("07:00:00", "08:00:00Z"), self.interval("07:00:00Z", "08:00:00"),
                       {"starts_at": "bad"}, self.interval("10:00:00+02:00", "08:00:00Z")]:
            self.error(self.search(**values), 422, "validation_error")
            self.error(self.check(**values), 422, "validation_error")
        for filters in [{"minimum_capacity": 0}, {"minimum_capacity": -1}, {"minimum_capacity": 1.5},
                        {"room_type_id": "bad"}, {"facility_ids": ["bad"]}, {"limit": 201}, {"offset": -1}]:
            self.error(self.search(**filters), 422)
        self.error(self.client.get(self.url(self.a, "rooms") + "/availability"), 422)

    def test_query_scoping_lock_order_and_postgresql_lock_sql(self):
        statements = []
        def capture(conn, clause, multiparams, params, options):
            statements.append(str(clause.compile(dialect=postgresql.dialect())))
        event.listen(self.engine, "before_execute", capture)
        result = self.schedule(**self.interval("08:00:00Z", "09:00:00Z"))
        self.assertEqual(result.status_code, 201, result.text)
        locks = [sql for sql in statements if "FOR UPDATE" in sql]
        self.assertTrue(locks)
        self.assertIn("workspaces.id", locks[0])
        self.assertIn("WHERE", locks[0])
        for sql in locks[1:]:
            self.assertIn("workspace_id", sql.split("WHERE")[1])
        self.assertTrue(any("schedule_entries.is_active IS true" in sql and "workspace_id" in sql.split("WHERE")[1]
                            for sql in statements if "WHERE" in sql))
        statements.clear()
        self.search()
        room_query = next(sql for sql in statements if "NOT (EXISTS" in sql)
        for table in ["rooms", "room_types", "floors", "buildings", "campuses", "schedule_entries"]:
            self.assertIn(table + ".workspace_id", room_query)

    def test_openapi_static_route_and_conflict_schema(self):
        schema = self.client.get("/openapi.json").json()
        path = "/api/workspaces/{workspace_id}/rooms/availability"
        self.assertIn(path, schema["paths"])
        self.assertIn(path.replace("/availability", "/{room_id}/availability"), schema["paths"])
        conflict = schema["paths"]["/api/workspaces/{workspace_id}/schedule-entries"]["post"]["responses"]["409"]
        self.assertIn("ScheduleConflictResponse", str(conflict))
        self.assertEqual(self.search().status_code, 200)  # Must not parse 'availability' as a UUID.
