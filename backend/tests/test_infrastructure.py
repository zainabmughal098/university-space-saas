"""Tenant-integrity tests on a migrated, disposable database; no .env access."""

import io
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest
import uuid
import warnings

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Integer, MetaData, create_engine, event, inspect, select, update
from sqlalchemy.exc import IntegrityError, SAWarning
from sqlalchemy.orm import Session, configure_mappers

from app.database import Base
from app.models import Building, Campus, Facility, Floor, Room, RoomFacility, RoomType, Workspace

BACKEND = Path(__file__).resolve().parents[1]
TABLES = {"campuses", "buildings", "floors", "room_types", "rooms", "facilities", "room_facilities"}


def migration(revision):
    spec = spec_from_file_location(revision, BACKEND / "alembic/versions" / f"{revision}.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InfrastructureTests(unittest.TestCase):
    def setUp(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", SAWarning)
            configure_mappers()
        self.engine = create_engine("sqlite://")
        event.listen(self.engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
        self.addCleanup(self.engine.dispose)
        with self.engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                migration("0001_initial_tenants").upgrade()
                migration("0002_university_infrastructure").upgrade()
        self.session = Session(self.engine)
        self.addCleanup(self.session.close)
        self.a = self.university("a")
        self.b = self.university("b")
        self.session.commit()

    def university(self, slug):
        workspace = Workspace(id=uuid.uuid4(), name=slug, slug=slug)
        self.session.add(workspace)
        self.session.flush()
        campus = Campus(workspace=workspace, name="Main", code="MAIN")
        building = Building(workspace_id=workspace.id, campus=campus, name="Building", code="B")
        floor = Floor(workspace_id=workspace.id, building=building, name="Basement", floor_number=-1)
        room_type = RoomType(workspace_id=workspace.id, name="Custom Type")
        room = Room(workspace_id=workspace.id, floor=floor, room_type=room_type, name="Room", code="R", capacity=1)
        facility = Facility(workspace_id=workspace.id, name="Custom Facility")
        link = RoomFacility(workspace_id=workspace.id, room=room, facility=facility)
        self.session.add_all([workspace, campus, building, floor, room_type, room, facility, link])
        self.session.flush()
        return dict(workspace=workspace, campus=campus, building=building, floor=floor,
                    room_type=room_type, room=room, facility=facility, link=link)

    def assert_rejected(self, operation):
        with self.assertRaises(IntegrityError):
            with self.session.begin_nested():
                operation()
                self.session.flush()

    def test_fields_and_defaults(self):
        expected = {
            Campus: {"id", "workspace_id", "name", "code", "address", "is_active", "created_at"},
            Building: {"id", "workspace_id", "campus_id", "name", "code", "is_active", "created_at"},
            Floor: {"id", "workspace_id", "building_id", "name", "floor_number", "is_active", "created_at"},
            RoomType: {"id", "workspace_id", "name", "description", "created_at"},
            Room: {"id", "workspace_id", "floor_id", "room_type_id", "name", "code", "capacity", "is_active", "created_at"},
            Facility: {"id", "workspace_id", "name", "description", "created_at"},
            RoomFacility: {"workspace_id", "room_id", "facility_id"},
        }
        for model, fields in expected.items():
            self.assertEqual(set(model.__table__.columns.keys()), fields)
            for column in model.__table__.columns:
                self.assertEqual(column.nullable, column.name in {"address", "description"})
        self.assertIsInstance(Room.__table__.c.capacity.type, Integer)
        for name in ["campus", "building", "floor", "room"]:
            self.assertTrue(self.a[name].is_active)
            self.assertIsNotNone(self.a[name].created_at)

    def test_relationships_reload_and_tenant_separation(self):
        self.session.expire_all()
        for university in [self.a, self.b]:
            self.assertEqual(university["workspace"].campuses, [university["campus"]])
            self.assertEqual(university["campus"].buildings, [university["building"]])
            self.assertEqual(university["building"].floors, [university["floor"]])
            self.assertEqual(university["floor"].rooms, [university["room"]])
            self.assertEqual(university["room_type"].rooms, [university["room"]])
            self.assertEqual(university["room"].facilities, [university["facility"]])
            self.assertEqual(university["facility"].rooms, [university["room"]])
            self.assertIs(university["link"].room, university["room"])
            self.assertIs(university["link"].facility, university["facility"])

    def test_all_uniqueness_scopes(self):
        for name in ["campus", "building", "floor", "room_type", "room", "facility", "link"]:
            source = self.a[name]
            values = {column.name: getattr(source, column.name) for column in source.__table__.columns
                      if column.name not in {"id", "created_at"}}
            with self.subTest(table=source.__tablename__):
                self.assert_rejected(lambda: self.session.execute(source.__table__.insert().values(**values)))
        # Reusing every code/name in university B already succeeded in setUp.
        campus = Campus(workspace_id=self.a["workspace"].id, name="Other", code="OTHER")
        building = Building(workspace_id=campus.workspace_id, campus=campus, name="Other", code="B")
        floor = Floor(workspace_id=campus.workspace_id, building=building, name="Other", floor_number=-1)
        self.session.add_all([campus, building, floor])
        self.session.flush()
        # Room codes remain unique across different campuses/floors in one university.
        self.assert_rejected(lambda: self.session.add(Room(
            workspace_id=campus.workspace_id, floor_id=floor.id, room_type_id=self.a["room_type"].id,
            name="Duplicate", code="R", capacity=10)))

    def test_positive_capacity(self):
        for capacity in [0, -1, None]:
            with self.subTest(capacity=capacity):
                self.assert_rejected(lambda: self.session.execute(
                    update(Room).where(Room.id == self.a["room"].id).values(capacity=capacity)))

    def test_many_to_many_links_and_facility_delete_cascade(self):
        workspace_id = self.a["workspace"].id
        facility = Facility(workspace_id=workspace_id, name="Another facility")
        room = Room(workspace_id=workspace_id, floor=self.a["floor"], room_type=self.a["room_type"],
                    name="Another room", code="R2", capacity=20)
        self.session.add_all([
            RoomFacility(workspace_id=workspace_id, room=self.a["room"], facility=facility),
            RoomFacility(workspace_id=workspace_id, room=room, facility=self.a["facility"]),
        ])
        self.session.flush()
        self.session.expire_all()
        self.assertEqual(set(self.a["room"].facilities), {self.a["facility"], facility})
        self.assertEqual(set(self.a["facility"].rooms), {self.a["room"], room})
        self.session.execute(Facility.__table__.delete().where(Facility.id == self.a["facility"].id))
        self.session.flush()
        self.assertEqual(len(self.session.scalars(select(Room)).all()), 3)
        self.assertEqual(len(self.session.scalars(select(RoomFacility)).all()), 2)

    def test_cross_workspace_inserts_and_updates_for_every_link(self):
        for name, field, target in [("building", "campus_id", "campus"),
                                    ("floor", "building_id", "building"),
                                    ("room", "floor_id", "floor"),
                                    ("room", "room_type_id", "room_type"),
                                    ("link", "room_id", "room"),
                                    ("link", "facility_id", "facility")]:
            source = self.a[name]
            table = source.__table__
            foreign_id = self.b[target].id
            values = {column.name: getattr(source, column.name) for column in table.columns
                      if column.name not in {"id", "created_at"}}
            values[field] = foreign_id
            if "code" in values:
                values["code"] = "NEW"
            if "floor_number" in values:
                values["floor_number"] = 99
            with self.subTest(table=table.name, field=field, operation="insert"):
                self.assert_rejected(lambda: self.session.execute(table.insert().values(**values)))
            with self.subTest(table=table.name, field=field, operation="update"):
                self.assert_rejected(lambda: self.session.execute(
                    table.update().where(table.c.workspace_id == self.a["workspace"].id).values({field: foreign_id})))

    def test_orm_assignment_cannot_silently_change_tenant(self):
        for name, attribute, target in [("building", "campus", "campus"), ("floor", "building", "building"),
                                        ("room", "floor", "floor"), ("room", "room_type", "room_type"),
                                        ("link", "room", "room"), ("link", "facility", "facility")]:
            with self.subTest(relationship=attribute):
                self.assert_rejected(lambda: setattr(self.a[name], attribute, self.b[target]))
                self.assertEqual(self.a[name].workspace_id, self.a["workspace"].id)

    def test_missing_workspace_and_parent_are_rejected(self):
        self.assert_rejected(lambda: self.session.add(Campus(workspace_id=uuid.uuid4(), name="Bad", code="BAD")))
        self.assert_rejected(lambda: self.session.add(Building(
            workspace_id=self.a["workspace"].id, campus_id=uuid.uuid4(), name="Bad", code="BAD")))

    def test_deletion_policy(self):
        for name in ["workspace", "campus", "building", "floor", "room_type"]:
            with self.subTest(parent=name):
                self.assert_rejected(lambda: self.session.delete(self.a[name]))
        self.session.execute(Room.__table__.delete().where(Room.id == self.a["room"].id))
        self.session.flush()
        self.assertEqual(len(self.session.scalars(select(RoomFacility)).all()), 1)
        self.assertEqual(len(self.session.scalars(select(Facility)).all()), 2)

    def test_migration_matches_models_and_preserves_phase1_on_downgrade(self):
        self.session.close()
        second = migration("0002_university_infrastructure")
        phase2_metadata = MetaData()
        for table in Base.metadata.sorted_tables:
            if table.name in TABLES | {"users", "workspaces", "memberships"}:
                table.to_metadata(phase2_metadata)
        with self.engine.begin() as connection:
            context = MigrationContext.configure(connection)
            self.assertEqual(compare_metadata(context, phase2_metadata), [])
            with Operations.context(context):
                second.downgrade()
                self.assertEqual(set(inspect(connection).get_table_names()), {"users", "workspaces", "memberships"})
                self.assertEqual(len(connection.execute(select(Workspace)).all()), 2)
                second.upgrade()
                self.assertEqual(compare_metadata(context, phase2_metadata), [])

    def test_offline_postgresql_incremental_migration(self):
        output = io.StringIO()
        config = Config(str(BACKEND / "alembic.ini"), output_buffer=output)
        command.upgrade(config, "0001_initial_tenants:0002_university_infrastructure", sql=True)
        sql = output.getvalue()
        self.assertNotIn("CREATE TABLE users", sql)
        self.assertNotIn("ROW LEVEL SECURITY", sql)
        for table in TABLES:
            self.assertIn(f"CREATE TABLE {table}", sql)
        self.assertIn("CHECK (capacity > 0)", sql)
        self.assertIn("BOOLEAN DEFAULT true NOT NULL", sql)
        self.assertIn("TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL", sql)
        self.assertIn("FOREIGN KEY(workspace_id, room_type_id) REFERENCES room_types (workspace_id, id)", sql)
        self.assertIn("FOREIGN KEY(workspace_id, facility_id) REFERENCES facilities (workspace_id, id)", sql)
        output.seek(0)
        output.truncate()
        command.downgrade(config, "0002_university_infrastructure:0001_initial_tenants", sql=True)
        self.assertNotIn("DROP TABLE users", output.getvalue())
        for table in TABLES:
            self.assertIn(f"DROP TABLE {table}", output.getvalue())
