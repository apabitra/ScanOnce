import io
import unittest

from fastapi.testclient import TestClient

from app import app
from src.services.file_service import file_service


class ScanOnceAppTests(unittest.TestCase):
    def setUp(self):
        file_service.FILES.clear()
        self.client = TestClient(app)

    def test_upload_returns_notification_details(self):
        response = self.client.post(
            "/upload",
            files={"file": ("sample.txt", io.BytesIO(b"hello world"), "text/plain")},
            data={"pin": "1234"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Notification-Type"], "success")
        self.assertEqual(response.headers["X-Notification-Message"], "Upload complete.")
        self.assertEqual(response.headers["X-Share-PIN"], "1234")
        self.assertIn("/portal/", response.headers["X-Share-URL"])

    def test_upload_requires_pin(self):
        response = self.client.post(
            "/upload",
            files={"file": ("sample.txt", io.BytesIO(b"hello world"), "text/plain")},
            data={"pin": "   "},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers["X-Notification-Type"], "error")
        self.assertEqual(response.text, "PIN is required for every file upload")

    def test_upload_rejects_oversized_files(self):
        oversized = b"x" * (500 * 1024 + 1)
        response = self.client.post(
            "/upload",
            files={"file": ("big.bin", io.BytesIO(oversized), "application/octet-stream")},
            data={"pin": "1234"},
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.headers["X-Notification-Type"], "error")
        self.assertIn("File too large", response.text)

    def test_portal_requires_pin_and_unlocks_qr(self):
        upload_response = self.client.post(
            "/upload",
            files={"file": ("sample.txt", io.BytesIO(b"hello world"), "text/plain")},
            data={"pin": "1234"},
        )
        file_id = upload_response.headers["X-Share-URL"].split("/portal/")[-1]

        portal_get = self.client.get(f"/portal/{file_id}")
        self.assertEqual(portal_get.status_code, 200)
        self.assertIn("Enter the PIN", portal_get.text)

        wrong_pin = self.client.post(f"/portal/{file_id}", data={"pin": "9999"})
        self.assertEqual(wrong_pin.status_code, 403)
        self.assertEqual(wrong_pin.headers["X-Notification-Type"], "error")
        self.assertEqual(wrong_pin.text, "Incorrect PIN")

        unlocked = self.client.post(f"/portal/{file_id}", data={"pin": "1234"})
        self.assertEqual(unlocked.status_code, 200)
        self.assertIn("QR code unlocked", unlocked.text)
        self.assertIn(f"/qr/{file_id}", unlocked.text)

    def test_qr_and_download_endpoints_work(self):
        upload_response = self.client.post(
            "/upload",
            files={"file": ("sample.txt", io.BytesIO(b"hello world"), "text/plain")},
            data={"pin": "1234"},
        )
        file_id = upload_response.headers["X-Share-URL"].split("/portal/")[-1]

        qr_response = self.client.get(f"/qr/{file_id}")
        self.assertEqual(qr_response.status_code, 200)
        self.assertEqual(qr_response.headers["content-type"], "image/png")

        redeem_response = self.client.get(f"/redeem/{file_id}")
        self.assertEqual(redeem_response.status_code, 200)
        self.assertIn("Preparing download", redeem_response.text)

        file_response = self.client.get(f"/file/{file_id}")
        self.assertEqual(file_response.status_code, 200)
        self.assertEqual(file_response.content, b"hello world")

    def test_frontend_assets_are_served(self):
        response = self.client.get("/frontend/app.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("upload-form", response.text)

    def test_health_endpoint_reports_status(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")


if __name__ == "__main__":
    unittest.main()
