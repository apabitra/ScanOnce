import io
import unittest

from fastapi.testclient import TestClient

from app import app


class UploadNotificationTests(unittest.TestCase):
    def test_upload_returns_json_share_details(self):
        client = TestClient(app)
        response = client.post(
            "/upload",
            files={"file": ("sample.txt", io.BytesIO(b"hello world"), "text/plain")},
            data={"pin": "1234"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"].split(";")[0], "application/json")

        payload = response.json()
        self.assertEqual(payload["filename"], "sample.txt")
        self.assertEqual(payload["pin"], "1234")
        self.assertIn("/portal/", payload["portal_url"])


if __name__ == "__main__":
    unittest.main()
