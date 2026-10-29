import unittest
from pathlib import Path
from unittest.mock import patch

from reclip_desktop.core import DATA_DIR, AdvancedOptions
from reclip_desktop.douyin_engine import (
    CallbackProgressReporter,
    ChannelProgressReporter,
    build_channel_engine_config,
    build_engine_config,
    engine_cookie_file,
    find_existing_media_for_url,
    find_new_media_file,
    save_douyin_cookie_string,
    vendor_path_context,
)


class DouyinEngineTests(unittest.TestCase):
    def test_build_engine_config_is_single_video_and_lightweight(self):
        config = build_engine_config(
            url="https://www.douyin.com/video/123",
            download_dir=Path("downloads"),
            advanced=AdvancedOptions(proxy="http://127.0.0.1:7890", max_quality="720p", metadata=True, thumbnail=True),
        )

        self.assertEqual(config["link"], ["https://www.douyin.com/video/123"])
        self.assertEqual(config["path"], "downloads")
        self.assertEqual(config["thread"], 1)
        self.assertEqual(config["video_quality"], "720p")
        self.assertEqual(config["proxy"], "http://127.0.0.1:7890")
        self.assertFalse(config["music"])
        self.assertTrue(config["cover"])
        self.assertTrue(config["json"])
        self.assertFalse(config["database"])

    def test_engine_cookie_file_matches_setup_output(self):
        self.assertEqual(engine_cookie_file(), DATA_DIR / "douyin-engine" / "config" / "cookies.json")

    def test_find_new_media_file_prefers_new_mp4(self):
        before = {Path("old.mp4")}
        files = [Path("old.mp4"), Path("new.mp3"), Path("new.mp4")]

        class FakeStat:
            st_mtime = 10
            st_size = 1

        with (
            patch("pathlib.Path.rglob", return_value=files),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.is_file", return_value=True),
            patch("pathlib.Path.stat", return_value=FakeStat()),
        ):
            self.assertEqual(find_new_media_file(Path("downloads"), before), Path("new.mp4"))

    def test_find_new_media_file_accepts_overwritten_existing_file(self):
        before = {Path("same.mp4"): (5, 100)}
        files = [Path("same.mp4")]

        class FakeStat:
            st_mtime = 10
            st_size = 200

        with (
            patch("pathlib.Path.rglob", return_value=files),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.is_file", return_value=True),
            patch("pathlib.Path.stat", return_value=FakeStat()),
        ):
            self.assertEqual(find_new_media_file(Path("downloads"), before), Path("same.mp4"))

    def test_find_existing_media_for_url_uses_aweme_id(self):
        files = [Path("downloads/creator/title_123.mp4"), Path("downloads/creator/title_456.mp4")]

        class FakeStat:
            st_mtime = 10
            st_size = 1

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.rglob", return_value=files),
            patch("pathlib.Path.is_file", return_value=True),
            patch("pathlib.Path.stat", return_value=FakeStat()),
        ):
            self.assertEqual(find_existing_media_for_url(Path("downloads"), "https://www.douyin.com/video/123"), Path("downloads/creator/title_123.mp4"))

    def test_callback_progress_reporter_emits_progress(self):
        values = []
        reporter = CallbackProgressReporter(values.append)
        reporter.on_author("creator")
        reporter.update_step("下载作品", "单视频资源下载中")
        reporter.advance_item("success", "123")

        self.assertEqual(values[0], 5)
        self.assertEqual(values[-1], 90)

    def test_vendor_path_context_adds_and_removes_path(self):
        fake_path = str(Path("vendor").resolve())
        with vendor_path_context(Path(fake_path)):
            import sys

            self.assertEqual(sys.path[0], fake_path)
        self.assertNotEqual(__import__("sys").path[0], fake_path)

    def test_build_channel_engine_config(self):
        config = build_channel_engine_config(
            url="https://www.douyin.com/user/MS4wLjABAAAA...",
            download_dir=Path("downloads"),
            advanced=AdvancedOptions(proxy="http://127.0.0.1:7890"),
            limit=50,
        )
        self.assertEqual(config["link"], ["https://www.douyin.com/user/MS4wLjABAAAA..."])
        self.assertTrue(config["folderstyle"])
        self.assertTrue(config["database"])
        self.assertEqual(config["mode"], ["post"])
        self.assertEqual(config["number"]["post"], 50)
        self.assertEqual(config["thread"], 3)

    def test_channel_progress_reporter(self):
        records = []
        reporter = ChannelProgressReporter(lambda pct, msg: records.append((pct, msg)))
        reporter.on_author("TestAuthor")
        reporter.set_item_total(10)
        reporter.advance_item("success", "video_1")
        reporter.advance_item("skipped", "video_2")

        self.assertEqual(reporter.author_nickname, "TestAuthor")
        self.assertEqual(reporter.success_count, 1)
        self.assertEqual(reporter.skipped_count, 1)
        self.assertEqual(reporter.completed_items, 2)
        self.assertTrue(len(records) >= 4)

    def test_save_douyin_cookie_string(self):
        import tempfile
        import json
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_cookie = Path(tmp_dir) / "cookies.json"
            with patch("reclip_desktop.douyin_engine.engine_cookie_file", return_value=fake_cookie):
                res = save_douyin_cookie_string("msToken=abc123xyz; ttwid=test_ttwid; sessionid=sess_123")
                self.assertTrue(res.exists())
                data = json.loads(res.read_text(encoding="utf-8"))
                self.assertEqual(data["msToken"], "abc123xyz")
                self.assertEqual(data["ttwid"], "test_ttwid")
                self.assertEqual(data["sessionid"], "sess_123")


if __name__ == "__main__":
    unittest.main()
