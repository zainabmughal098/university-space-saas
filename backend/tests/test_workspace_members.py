"""The development directory reads only the isolated API fixture database."""
import unittest
from uuid import UUID, uuid4
from sqlalchemy.orm import Session
from app.models import Membership, MembershipRole, User
from test_academic_api import AcademicAPIFixture


class WorkspaceMemberTests(AcademicAPIFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        with Session(self.engine) as session:
            users = [User(display_name="Same name", email=f"member{i}@example.test") for i in range(3)]
            session.add_all(users)
            session.flush()
            self.ids = [str(user.id) for user in users]
            session.add_all([
                Membership(user=users[0], workspace_id=UUID(self.a), role=MembershipRole.OWNER, is_active=True),
                Membership(user=users[1], workspace_id=UUID(self.a), role=MembershipRole.VIEWER, is_active=False),
                Membership(user=users[2], workspace_id=UUID(self.b), role=MembershipRole.MEMBER, is_active=True),
                Membership(user=users[0], workspace_id=UUID(self.b), role=MembershipRole.ADMIN, is_active=False),
            ])
            session.commit()

    def test_safe_fields_active_status_and_isolation(self):
        response = self.client.get(f"/api/workspaces/{self.a}/members")
        self.assertEqual(response.status_code, 200)
        rows = response.json()
        self.assertEqual({row["user_id"] for row in rows}, set(self.ids[:2]))
        for row in rows:
            self.assertEqual(set(row), {"user_id", "display_name", "email", "role", "is_active"})
            self.assertEqual(row["display_name"], "Same name")
        owner = next(row for row in rows if row["user_id"] == self.ids[0])
        self.assertEqual(owner["email"], "member0@example.test")
        self.assertEqual(owner["role"], "owner")
        self.assertTrue(owner["is_active"])
        self.assertFalse(next(row for row in rows if row["user_id"] == self.ids[1])["is_active"])
        other = self.client.get(f"/api/workspaces/{self.b}/members").json()
        self.assertEqual({row["user_id"] for row in other}, {self.ids[0], self.ids[2]})
        shared = next(row for row in other if row["user_id"] == self.ids[0])
        self.assertEqual(shared["role"], "admin")
        self.assertFalse(shared["is_active"])

    def test_deterministic_pagination_and_invalid_queries(self):
        path = f"/api/workspaces/{self.a}/members"
        rows = self.client.get(path).json()
        self.assertEqual([row["user_id"] for row in rows], sorted(self.ids[:2]))
        self.assertEqual(self.client.get(path).json(), rows)
        for offset in range(2):
            self.assertEqual(self.client.get(path, params={"limit": 1, "offset": offset}).json(), rows[offset:offset + 1])
        self.assertEqual(self.client.get(path, params={"offset": 2}).json(), [])
        for query in [{"limit": 0}, {"limit": 201}, {"offset": -1}]:
            self.assertEqual(self.client.get(path, params=query).status_code, 422)

    def test_unknown_workspace_and_no_mutation_endpoint(self):
        response = self.client.get(f"/api/workspaces/{uuid4()}/members")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"]["code"], "workspace_not_found")
        self.assertEqual(self.client.get("/api/workspaces/invalid/members").status_code, 422)
        self.assertEqual(self.client.post(f"/api/workspaces/{self.a}/members", json={}).status_code, 405)
