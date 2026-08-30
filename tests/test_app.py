from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class FlaskRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import app

        app.config["TESTING"] = True
        cls.client = app.test_client()

    def test_index_ok(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Download Content", resp.data)

    def test_settings_page_is_html_not_json(self):
        resp = self.client.get("/settings")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Settings", resp.data)
        self.assertFalse(resp.is_json)

    def test_settings_api_json(self):
        resp = self.client.get("/api/settings")
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertIn("filename_pattern", payload)
        self.assertIn("thread_count", payload)
        self.assertIn("auth_token_set", payload)
        self.assertNotIn("auth_token", payload)

    def test_download_requires_target(self):
        resp = self.client.post("/download", json={})
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
