import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient
except Exception:  # pragma: no cover - dependency is installed for server tests
    TestClient = None


class ServerApiTests(unittest.TestCase):
    def setUp(self):
        if TestClient is None:
            self.skipTest("FastAPI TestClient is not installed")

    def test_health_endpoint(self):
        from pro_downloader_server.app import create_app

        client = TestClient(create_app())

        response = client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_fetch_endpoint_returns_metadata_and_formats(self):
        from pro_downloader_server.app import create_app

        metadata = {
            "title": "Sample",
            "uploader": "creator",
            "duration": 12,
            "formats": [{"id": "best", "label": "Best", "provider": "yt-dlp", "media_format": "video"}],
            "subtitle_languages": ["en"],
            "supports_metadata": True,
            "supports_thumbnail": False,
        }
        client = TestClient(create_app())

        with patch("pro_downloader_server.app.fetch_video_info", return_value=metadata):
            response = client.post("/api/fetch", json={"url": "https://example.com/video/123"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["title"], "Sample")
        self.assertEqual(body["formats"][0]["id"], "best")
        self.assertEqual(body["subtitle_languages"], ["en"])

    def test_fetch_endpoint_rejects_invalid_url(self):
        from pro_downloader_server.app import create_app

        client = TestClient(create_app())

        response = client.post("/api/fetch", json={"url": "not-a-url"})

        self.assertEqual(response.status_code, 422)

    def test_download_job_completes_and_serves_file(self):
        from pro_downloader_server.app import create_app

        with tempfile.TemporaryDirectory() as tmp_dir:
            download_dir = Path(tmp_dir)
            output_path = download_dir / "sample.mp4"
            output_path.write_bytes(b"video")
            client = TestClient(create_app(download_dir=download_dir, run_jobs_inline=True))

            with (
                patch("pro_downloader_server.app.download_media", return_value=output_path),
                patch("pro_downloader_server.app.record_history"),
            ):
                response = client.post(
                    "/api/download",
                    json={
                        "url": "https://example.com/video/123",
                        "title": "Sample",
                        "format_id": "best",
                        "provider": "yt-dlp",
                        "option": "Best",
                    },
                )

            self.assertEqual(response.status_code, 200)
            job_id = response.json()["job_id"]

            status = client.get(f"/api/jobs/{job_id}")
            self.assertEqual(status.status_code, 200)
            self.assertEqual(status.json()["status"], "done")
            self.assertEqual(status.json()["progress"], 100)

            file_response = client.get(f"/api/files/{job_id}")
            self.assertEqual(file_response.status_code, 200)
            self.assertEqual(file_response.content, b"video")

    def test_api_key_is_required_when_configured(self):
        from pro_downloader_server.app import create_app

        client = TestClient(create_app(api_key="secret"))

        self.assertEqual(client.get("/api/health").status_code, 401)
        self.assertEqual(client.get("/api/health", headers={"X-API-Key": "secret"}).status_code, 200)

    def test_pwa_home_is_served_without_api_key(self):
        from pro_downloader_server.app import create_app

        client = TestClient(create_app(api_key="secret"))

        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Pro Downloader", response.text)
        self.assertIn('rel="manifest"', response.text)

    def test_pwa_manifest_is_installable(self):
        from pro_downloader_server.app import create_app

        client = TestClient(create_app())

        response = client.get("/manifest.webmanifest")

        self.assertEqual(response.status_code, 200)
        self.assertIn("application/manifest+json", response.headers["content-type"])
        manifest = response.json()
        self.assertEqual(manifest["name"], "Pro Downloader")
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(manifest["start_url"], "/")
        self.assertTrue(manifest["icons"])

    def test_service_worker_is_available_at_root_scope(self):
        from pro_downloader_server.app import create_app

        client = TestClient(create_app())

        response = client.get("/sw.js")

        self.assertEqual(response.status_code, 200)
        self.assertIn("javascript", response.headers["content-type"])
        self.assertIn("self.addEventListener", response.text)

    def test_cleanup_expired_downloads_removes_old_media_only(self):
        from pro_downloader_server.app import cleanup_expired_downloads

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            old_video = root / "old.mp4"
            recent_video = root / "recent.mp4"
            note = root / "keep.txt"
            old_video.write_bytes(b"old")
            recent_video.write_bytes(b"recent")
            note.write_text("keep", encoding="utf-8")

            old_timestamp = (datetime.now() - timedelta(hours=48)).timestamp()
            old_video.touch()
            import os

            os.utime(old_video, (old_timestamp, old_timestamp))

            removed = cleanup_expired_downloads(root, retention_hours=24)

            self.assertEqual(removed, 1)
            self.assertFalse(old_video.exists())
            self.assertTrue(recent_video.exists())
            self.assertTrue(note.exists())


if __name__ == "__main__":
    unittest.main()
