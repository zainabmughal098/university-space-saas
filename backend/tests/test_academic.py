"""Academic constraints on migrated SQLite plus offline PostgreSQL DDL checks."""

from datetime import datetime, timedelta, timezone
import io
import unittest
import uuid

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import DateTime, Integer, MetaData, create_engine, event, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (Building, Campus, Course, Department, Faculty, Floor,
                        Room, RoomType, ScheduleEntry, Section, Workspace)
from scripts.validate_database import validate_academic_schema
from test_infrastructure import BACKEND, migration

ACADEMIC = {"departments", "faculty", "courses", "sections", "schedule_entries"}
REVISIONS = ["0001_initial_tenants", "0002_university_infrastructure", "0003_academic_scheduling"]
LINKS = [("faculty", "department_id", "department"), ("course", "department_id", "department"),
         ("section", "course_id", "course"), ("entry", "room_id", "room"),
         ("entry", "section_id", "section"), ("entry", "faculty_id", "faculty")]


class AcademicTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        event.listen(self.engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
        self.addCleanup(self.engine.dispose)
        with self.engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                for revision in REVISIONS:
                    migration(revision).upgrade()
        self.session = Session(self.engine)
        self.addCleanup(self.session.close)
        self.a, self.b = self.university("a"), self.university("b")
        self.session.commit()

    def university(self, slug):
        workspace = Workspace(name=slug, slug=slug)
        self.session.add(workspace)
        self.session.flush()
        wid = workspace.id
        campus = Campus(workspace_id=wid, name="Main", code="MAIN")
        building = Building(workspace_id=wid, campus=campus, name="Building", code="B")
        floor = Floor(workspace_id=wid, building=building, name="Ground", floor_number=0)
        room_type = RoomType(workspace_id=wid, name="Custom")
        room = Room(workspace_id=wid, floor=floor, room_type=room_type, name="Room", code="R", capacity=20)
        department = Department(workspace_id=wid, name="Department", code="DEP")
        faculty = Faculty(workspace_id=wid, department=department, name="Teacher", email="teacher@example.test")
        course = Course(workspace_id=wid, department=department, name="Course", code="C101")
        section = Section(workspace_id=wid, course=course, name="A", student_count=25)
        entry = ScheduleEntry(workspace_id=wid, room=room, section=section, faculty=faculty,
                              starts_at=datetime(2026, 10, 1, 9, tzinfo=timezone.utc),
                              ends_at=datetime(2026, 10, 1, 10, tzinfo=timezone.utc))
        self.session.add_all([campus, building, floor, room_type, room, department, faculty, course, section, entry])
        self.session.flush()
        return dict(workspace=workspace, room=room, department=department, faculty=faculty,
                    course=course, section=section, entry=entry)

    def rejected(self, operation):
        with self.assertRaises(IntegrityError):
            with self.session.begin_nested():
                operation()
                self.session.flush()

    def values(self, record):
        return {column.name: getattr(record, column.name) for column in record.__table__.columns
                if column.name not in {"id", "created_at"}}

    def test_definitions_defaults_and_indexes(self):
        common = {"id", "workspace_id", "created_at", "is_active"}
        for model, extra in [
            (Department, {"name", "code"}), (Faculty, {"department_id", "name", "email"}),
            (Course, {"department_id", "code", "name"}), (Section, {"course_id", "name", "student_count"}),
            (ScheduleEntry, {"room_id", "section_id", "faculty_id", "starts_at", "ends_at"}),
        ]:
            table = model.__table__
            self.assertEqual(set(table.columns.keys()), common | extra)
            self.assertTrue(all(not column.nullable for column in table.columns))
            self.assertEqual(list(table.primary_key.columns.keys()), ["id"])
            self.assertTrue(table.c.created_at.type.timezone)
        self.assertIsInstance(Section.__table__.c.student_count.type, Integer)
        for field in ["starts_at", "ends_at"]:
            self.assertIsInstance(ScheduleEntry.__table__.c[field].type, DateTime)
            self.assertTrue(ScheduleEntry.__table__.c[field].type.timezone)
        for name in ["department", "faculty", "course", "section", "entry"]:
            self.assertIsInstance(self.a[name].id, uuid.UUID)
            self.assertTrue(self.a[name].is_active)
            self.assertIsNotNone(self.a[name].created_at)
        validate_academic_schema(self.session.connection())

    def test_relationships_load_only_same_workspace(self):
        self.session.expire_all()
        for data in [self.a, self.b]:
            self.assertEqual(data["workspace"].departments, [data["department"]])
            self.assertEqual(data["department"].faculty, [data["faculty"]])
            self.assertEqual(data["department"].courses, [data["course"]])
            self.assertEqual(data["course"].sections, [data["section"]])
            for name in ["room", "section", "faculty"]:
                self.assertEqual(data[name].schedule_entries, [data["entry"]])
                self.assertIs(getattr(data["entry"], name), data[name])

    def test_uniqueness_insert_update_and_scopes(self):
        for name, field in [("department", "code"), ("faculty", "email"), ("course", "code"), ("section", "name")]:
            source = self.a[name]
            table = source.__table__
            values = self.values(source)
            with self.subTest(model=name):
                self.rejected(lambda: self.session.execute(table.insert().values(**values)))
                values[field] = "different"
                other = type(source)(**values)
                self.session.add(other)
                self.session.flush()
                self.rejected(lambda: self.session.execute(table.update().where(table.c.id == other.id)
                                                           .values({field: getattr(source, field)})))
        # Same identifiers in university B succeeded; section names may repeat across courses.
        other_course = Course(workspace_id=self.a["workspace"].id, department=self.a["department"], name="Other", code="OTHER")
        self.session.add(Section(workspace_id=self.a["workspace"].id, course=other_course, name="A", student_count=1))
        self.session.flush()

    def test_cross_workspace_and_missing_parent_inserts_updates(self):
        for name, column, target in LINKS:
            source = self.a[name]
            table = source.__table__
            for foreign_id in [self.b[target].id, uuid.uuid4()]:
                values = self.values(source)
                values[column] = foreign_id
                for unique in ["code", "email", "name"]:
                    if unique in values:
                        values[unique] = "new"
                with self.subTest(model=name, parent=column):
                    self.rejected(lambda: self.session.execute(table.insert().values(**values)))
                    self.rejected(lambda: self.session.execute(table.update().where(table.c.id == source.id).values({column: foreign_id})))

    def test_orm_parent_assignments_preserve_tenant(self):
        for name, column, target in LINKS:
            attribute = column.removesuffix("_id")
            with self.subTest(model=name, relationship=attribute):
                self.rejected(lambda: setattr(self.a[name], attribute, self.b[target]))
                self.assertEqual(self.a[name].workspace_id, self.a["workspace"].id)

    def test_workspace_required_and_must_exist(self):
        for name in ["department", "faculty", "course", "section", "entry"]:
            source = self.a[name]
            for workspace_id in [None, uuid.uuid4()]:
                values = self.values(source) | {"workspace_id": workspace_id}
                with self.subTest(model=name, workspace_id=workspace_id):
                    self.rejected(lambda: self.session.execute(source.__table__.insert().values(**values)))

    def test_positive_student_count_on_insert_and_update(self):
        for count in [0, -1, None]:
            values = self.values(self.a["section"]) | {"name": "Invalid", "student_count": count}
            self.rejected(lambda: self.session.execute(Section.__table__.insert().values(**values)))
            self.rejected(lambda: self.session.execute(Section.__table__.update()
                                                       .where(Section.id == self.a["section"].id).values(student_count=count)))

    def test_interval_order_and_required_endpoints(self):
        original = self.values(self.a["entry"])
        for values in [original | {"ends_at": original["starts_at"]},
                       original | {"ends_at": original["starts_at"] - timedelta(seconds=1)},
                       original | {"starts_at": None}, original | {"ends_at": None}]:
            with self.subTest(starts_at=values["starts_at"], ends_at=values["ends_at"]):
                self.rejected(lambda: self.session.execute(ScheduleEntry.__table__.insert().values(**values)))
                self.rejected(lambda: self.session.execute(ScheduleEntry.__table__.update()
                                                           .where(ScheduleEntry.id == self.a["entry"].id).values(**values)))

    def test_adjacent_and_overlapping_intervals_allowed_in_this_phase(self):
        values = self.values(self.a["entry"])
        for start, end in [(values["ends_at"], values["ends_at"] + timedelta(hours=1)),
                           (values["starts_at"] + timedelta(minutes=15), values["ends_at"])]:
            self.session.add(ScheduleEntry(**(values | {"starts_at": start, "ends_at": end})))
        self.session.flush()
        self.assertEqual(len(self.session.scalars(select(ScheduleEntry).where(ScheduleEntry.workspace_id == self.a["workspace"].id)).all()), 3)

    def test_referenced_parents_cannot_be_deleted(self):
        for name in ["workspace", "department", "course", "section", "faculty", "room"]:
            with self.subTest(parent=name):
                self.rejected(lambda: self.session.delete(self.a[name]))
        self.a["entry"].is_active = False
        self.session.flush()
        self.rejected(lambda: self.session.delete(self.a["room"]))

    def test_migration_consistency_roundtrip_and_phase2_data_preserved(self):
        self.session.close()
        third = migration(REVISIONS[-1])
        phase3 = MetaData()
        for table in Base.metadata.sorted_tables:
            if table.name != "reservations":
                table.to_metadata(phase3)
        with self.engine.begin() as connection:
            context = MigrationContext.configure(connection)
            self.assertEqual(compare_metadata(context, phase3), [])
            validate_academic_schema(connection)
            with Operations.context(context):
                third.downgrade()
                self.assertEqual(set(inspect(connection).get_table_names()), set(phase3.tables) - ACADEMIC)
                self.assertEqual(len(connection.execute(select(Room)).all()), 2)
                self.assertEqual(len(connection.execute(select(Workspace)).all()), 2)
                third.upgrade()
            self.assertEqual(compare_metadata(context, phase3), [])
            validate_academic_schema(connection)

    def test_incremental_postgresql_sql(self):
        output = io.StringIO()
        config = Config(str(BACKEND / "alembic.ini"), output_buffer=output)
        command.upgrade(config, "0002_university_infrastructure:0003_academic_scheduling", sql=True)
        sql = output.getvalue()
        self.assertEqual(sql.count("CREATE TABLE "), 5)
        for table in ACADEMIC:
            self.assertIn(f"CREATE TABLE {table}", sql)
        for fragment in ["CHECK (student_count > 0)", "CHECK (ends_at > starts_at)",
                         "starts_at TIMESTAMP WITH TIME ZONE NOT NULL", "ends_at TIMESTAMP WITH TIME ZONE NOT NULL",
                         "BOOLEAN DEFAULT true NOT NULL", "UUID NOT NULL"]:
            self.assertIn(fragment, sql)
        for fragment in ["EXCLUDE", "ROW LEVEL SECURITY", "ALTER TABLE rooms", "CREATE TABLE rooms"]:
            self.assertNotIn(fragment, sql)
        for _, column, target in LINKS:
            target_table = {"department": "departments", "course": "courses", "room": "rooms", "section": "sections", "faculty": "faculty"}[target]
            self.assertIn(f"FOREIGN KEY(workspace_id, {column}) REFERENCES {target_table} (workspace_id, id)", sql)
        output.seek(0)
        output.truncate()
        command.downgrade(config, "0003_academic_scheduling:0002_university_infrastructure", sql=True)
        self.assertEqual(output.getvalue().count("DROP TABLE "), 5)
        self.assertNotIn("DROP TABLE rooms", output.getvalue())
