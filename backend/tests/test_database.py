"""Credential-free checks using SQLite and offline PostgreSQL SQL generation."""

import io
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from importlib.util import module_from_spec, spec_from_file_location
from pydantic import ValidationError
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import Base, get_engine, get_session
from app.models import Membership, MembershipRole, User, Workspace

BACKEND = Path(__file__).resolve().parents[1]
FAKE_URL = "postgresql+psycopg://test:fake_secret@localhost:5432/test_only"


class ConfigurationTests(unittest.TestCase):
    def test_environment_overrides_dotenv_and_secrets_are_hidden(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text("DATABASE_URL=" + FAKE_URL, encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(Settings(_env_file=env_file).database_url.get_secret_value(), FAKE_URL)
            override = FAKE_URL.replace("test_only", "override")
            with patch.dict(os.environ, {"DATABASE_URL": override}, clear=True):
                settings = Settings(_env_file=env_file)
                self.assertEqual(settings.database_url.get_secret_value(), override)
                self.assertNotIn("fake_secret", repr(settings))
                self.assertNotIn("fake_secret", settings.model_dump_json())

    def test_missing_invalid_and_placeholder_urls(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValidationError):
                Settings(_env_file=None)
            for value in ["sqlite:///fake_secret", "postgresql+psycopg://USER:PASSWORD@localhost/db",
                          "postgresql+psycopg://REPLACE_WITH_USER:REPLACE_WITH_PASSWORD@localhost/db"]:
                with self.subTest(value=value), self.assertRaises(ValidationError) as caught:
                    Settings(_env_file=None, database_url=value)
                self.assertNotIn(value, str(caught.exception))

    def test_engine_uses_psycopg_without_connecting(self):
        settings = Settings(_env_file=None, database_url=FAKE_URL)
        get_engine.cache_clear()
        try:
            with patch("app.database.get_settings", return_value=settings):
                engine = get_engine()
                self.assertEqual(engine.dialect.name, "postgresql")
                self.assertEqual(engine.dialect.driver, "psycopg")
                self.assertTrue(engine.hide_parameters)
                self.assertIs(engine, get_engine())
                engine.dispose()
        finally:
            get_engine.cache_clear()


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        event.listen(self.engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.session.close)
        self.user = User(email="user@example.test", display_name="Test User")
        self.workspace = Workspace(name="University One", slug="one")
        self.membership = Membership(user=self.user, workspace=self.workspace, role=MembershipRole.OWNER)
        self.session.add(self.membership)
        self.session.commit()

    def test_relationships_defaults_and_multiple_universities(self):
        second = Workspace(name="University Two", slug="two")
        self.session.add(Membership(user=self.user, workspace=second, role=MembershipRole.VIEWER))
        self.session.commit()
        self.assertEqual(len(self.user.memberships), 2)
        self.assertIs(self.workspace.memberships[0].user, self.user)
        self.assertTrue(self.membership.is_active)
        self.assertEqual(self.workspace.default_timezone, "UTC")
        self.assertIsInstance(self.user.id, uuid.UUID)
        self.assertIsNotNone(self.user.created_at)

    def test_global_and_membership_uniqueness(self):
        for duplicate in [User(email=self.user.email, display_name="Duplicate"),
                          Workspace(name="Duplicate", slug=self.workspace.slug),
                          Membership(user_id=self.user.id, workspace_id=self.workspace.id, role=MembershipRole.MEMBER)]:
            with self.subTest(model=type(duplicate).__name__):
                self.session.add(duplicate)
                with self.assertRaises(IntegrityError):
                    self.session.commit()
                self.session.rollback()

    def test_foreign_keys_and_role_constraint(self):
        for column in ["user_id", "workspace_id"]:
            values = dict(user_id=self.user.id, workspace_id=self.workspace.id, role=MembershipRole.MEMBER)
            values[column] = uuid.uuid4()
            self.session.add(Membership(**values))
            with self.assertRaises(IntegrityError):
                self.session.commit()
            self.session.rollback()
        with self.assertRaises(IntegrityError):
            self.session.execute(text("UPDATE memberships SET role = 'invalid'"))
        self.session.rollback()
        for role in MembershipRole:
            self.membership.role = role
            self.session.commit()

    def test_database_delete_cascade_preserves_user(self):
        self.session.execute(text("DELETE FROM workspaces"))
        self.session.commit()
        self.assertEqual(self.session.query(Membership).count(), 0)
        self.assertEqual(self.session.query(User).count(), 1)

    def test_session_dependency_rolls_back_uncommitted_work(self):
        with patch("app.database.get_engine", return_value=self.engine):
            dependency = get_session()
            session = next(dependency)
            session.add(User(email="rollback@example.test", display_name="Rollback"))
            session.flush()
            dependency.close()
        self.assertEqual(self.session.query(User).count(), 1)


class MigrationTests(unittest.TestCase):
    def test_postgresql_upgrade_and_downgrade_sql(self):
        output = io.StringIO()
        config = Config(str(BACKEND / "alembic.ini"), output_buffer=output)
        command.upgrade(config, "head", sql=True)
        sql = output.getvalue()
        for fragment in ["CREATE TABLE users", "CREATE TABLE workspaces", "CREATE TABLE memberships",
                         "UNIQUE (email)", "UNIQUE (slug)", "UNIQUE (user_id, workspace_id)",
                         "CHECK (role IN ('owner', 'admin', 'member', 'viewer'))",
                         "TIMESTAMP WITH TIME ZONE", "ix_memberships_workspace_id", "UUID"]:
            self.assertIn(fragment, sql)
        self.assertNotIn("ROW LEVEL SECURITY", sql)
        output.seek(0)
        output.truncate()
        command.downgrade(config, "head:base", sql=True)
        self.assertIn("DROP TABLE memberships", output.getvalue())

    def test_migration_matches_models_and_reverses(self):
        spec = spec_from_file_location("initial_migration", BACKEND / "alembic/versions/0001_initial_tenants.py")
        migration = module_from_spec(spec)
        spec.loader.exec_module(migration)
        engine = create_engine("sqlite://")
        try:
            with engine.begin() as connection:
                context = MigrationContext.configure(connection)
                with Operations.context(context):
                    migration.upgrade()
                    self.assertEqual(compare_metadata(context, Base.metadata), [])
                    migration.downgrade()
                self.assertEqual(connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).all(), [])
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
