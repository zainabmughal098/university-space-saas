"""Demo seed tests use only SQLite; private configuration access is forbidden."""
import contextlib
import io
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from app.database import Base
from app.models import Membership, MembershipRole, User, Workspace
from scripts.seed_demo_member import (DEMO_EMAIL, DEMO_NAME, WORKSPACE_ID,
                                      MissingDemoWorkspace, main, seed_demo_member)


class DemoMemberSeedTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        event.listen(self.engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        guard = patch("app.database.get_settings", side_effect=AssertionError("Private configuration forbidden"))
        guard.start()
        self.addCleanup(guard.stop)
        with Session(self.engine) as session, session.begin():
            session.add(Workspace(id=WORKSPACE_ID, name="Nova University", slug="nova"))

    def test_first_run_and_repeat_are_idempotent(self):
        self.assertIn("user created", seed_demo_member(self.engine))
        with Session(self.engine) as session:
            first_id = session.scalar(select(User.id))
            membership_id = session.scalar(select(Membership.id))
        self.assertIn("user reused", seed_demo_member(self.engine))
        with Session(self.engine) as session:
            users = session.scalars(select(User)).all()
            memberships = session.scalars(select(Membership)).all()
            self.assertEqual(len(users), 1)
            self.assertEqual(len(memberships), 1)
            self.assertEqual(users[0].id, first_id)
            self.assertEqual(users[0].email, DEMO_EMAIL)
            self.assertEqual(users[0].display_name, DEMO_NAME)
            self.assertEqual(memberships[0].id, membership_id)
            self.assertEqual(memberships[0].role, MembershipRole.OWNER)
            self.assertTrue(memberships[0].is_active)

    def test_existing_user_without_membership_is_reused(self):
        with Session(self.engine) as session, session.begin():
            session.add(User(email=DEMO_EMAIL, display_name="Old demo label"))
        self.assertIn("user reused; membership created", seed_demo_member(self.engine))
        with Session(self.engine) as session:
            self.assertEqual(len(session.scalars(select(User)).all()), 1)
            self.assertEqual(session.scalar(select(User)).display_name, DEMO_NAME)

    def test_reactivate_and_promote_only_target_membership(self):
        seed_demo_member(self.engine)
        other_workspace = uuid4()
        with Session(self.engine) as session, session.begin():
            user = session.scalar(select(User))
            target = session.scalar(select(Membership))
            target.is_active = False
            target.role = MembershipRole.VIEWER
            session.add(Workspace(id=other_workspace, name="Other", slug="other"))
            other = User(email="untouched@example.test", display_name="Untouched")
            session.add(other)
            session.flush()
            session.add_all([
                Membership(user_id=user.id, workspace_id=other_workspace, role=MembershipRole.MEMBER, is_active=False),
                Membership(user_id=other.id, workspace_id=WORKSPACE_ID, role=MembershipRole.ADMIN, is_active=False),
            ])
        seed_demo_member(self.engine)
        with Session(self.engine) as session:
            user = session.scalar(select(User).where(User.email == DEMO_EMAIL))
            for row in session.scalars(select(Membership)):
                if row.user_id == user.id and row.workspace_id == WORKSPACE_ID:
                    self.assertTrue(row.is_active)
                    self.assertEqual(row.role, MembershipRole.OWNER)
                else:
                    self.assertFalse(row.is_active)
                    self.assertIn(row.role, [MembershipRole.MEMBER, MembershipRole.ADMIN])
            self.assertEqual(session.scalar(select(User.display_name).where(User.email == "untouched@example.test")), "Untouched")

    def test_missing_workspace_does_not_create_user(self):
        with Session(self.engine) as session, session.begin():
            session.delete(session.get(Workspace, WORKSPACE_ID))
        with self.assertRaises(MissingDemoWorkspace):
            seed_demo_member(self.engine)
        with Session(self.engine) as session:
            self.assertEqual(session.scalars(select(User)).all(), [])
            self.assertEqual(session.scalars(select(Membership)).all(), [])

    def test_failure_rolls_back_user_and_membership(self):
        def reject_membership(mapper, connection, target):
            raise RuntimeError("Simulated membership failure")
        event.listen(Membership, "before_insert", reject_membership)
        try:
            with self.assertRaises(RuntimeError):
                seed_demo_member(self.engine)
        finally:
            event.remove(Membership, "before_insert", reject_membership)
        with Session(self.engine) as session:
            self.assertEqual(session.scalars(select(User)).all(), [])
            self.assertEqual(session.scalars(select(Membership)).all(), [])

    def test_cli_suppresses_connection_errors_and_reports_missing_workspace(self):
        for error, expected in [(RuntimeError("sensitive connection diagnostics"), "connection details suppressed"),
                                (MissingDemoWorkspace(), "does not exist")]:
            output = io.StringIO()
            with patch("scripts.seed_demo_member.get_engine", side_effect=error), contextlib.redirect_stdout(output):
                self.assertEqual(main(), 1)
            self.assertIn(expected, output.getvalue())
            self.assertNotIn("sensitive connection diagnostics", output.getvalue())
