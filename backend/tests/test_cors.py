"""Local browser access must not widen the API to arbitrary origins."""
import unittest
from fastapi.testclient import TestClient
from app.main import app


class CORSTests(unittest.TestCase):
    def test_local_read_origin_and_health(self):
        with TestClient(app) as client:
            for origin in ["http://localhost:3000", "http://127.0.0.1:3000"]:
                response = client.get("/health", headers={"Origin": origin})
                self.assertEqual(response.json(), {"status": "ok"})
                self.assertEqual(response.headers["access-control-allow-origin"], origin)
                self.assertNotIn("access-control-allow-credentials", response.headers)
                preflight = client.options("/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
                self.assertEqual(preflight.status_code, 200)

    def test_other_origins_and_write_preflights_rejected(self):
        with TestClient(app) as client:
            for origin, method in [("https://untrusted.example", "GET"), ("http://localhost:3000", "POST")]:
                response = client.options("/health", headers={"Origin": origin, "Access-Control-Request-Method": method})
                self.assertEqual(response.status_code, 400)
            response = client.get("/health", headers={"Origin": "https://untrusted.example"})
            self.assertNotIn("access-control-allow-origin", response.headers)
