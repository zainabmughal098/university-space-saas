"""Workspace timezone metadata reads use only the isolated fixture database."""
import unittest
from uuid import UUID, uuid4
from sqlalchemy.orm import Session
from app.models import Workspace
from test_academic_api import AcademicAPIFixture


class WorkspaceMetadataTests(AcademicAPIFixture, unittest.TestCase):
    def test_scoped_metadata_and_missing_workspace(self):
        with Session(self.engine) as session:
            workspace = session.get(Workspace, UUID(self.a))
            workspace.default_timezone = "America/New_York"
            session.commit()
        first = self.client.get(f"/api/workspaces/{self.a}")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["id"], self.a)
        self.assertEqual(first.json()["default_timezone"], "America/New_York")
        self.assertEqual(set(first.json()), {"id", "name", "slug", "default_timezone", "created_at"})
        second = self.client.get(f"/api/workspaces/{self.b}")
        self.assertEqual(second.json()["id"], self.b)
        self.assertEqual(second.json()["default_timezone"], "UTC")
        self.assertEqual(self.client.get(f"/api/workspaces/{uuid4()}").status_code, 404)
        self.assertEqual(self.client.get("/api/workspaces/invalid").status_code, 422)
