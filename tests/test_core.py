import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reclip_desktop.core import (
    AdvancedOptions,
    DownloadRequest,
    assert_downloaded_file_has_expected_stream,
    auto_cookie_browsers,
    build_info_command,
    build_download_command,
    choose_downloaded_file,
    cleanup_job_files,
    cleanup_temp_files,
    download_media,
    download_snapdouyin_media,
    extract_subtitle_languages,
    extract_urls,
    fetch_channel_videos,
    fetch_douyin_channel_videos,
    finalize_downloaded_job_file,
    friendly_error,
    is_channel_or_playlist_url,
    is_douyin_url,
    load_douyin_cookies,
    APP_NAME,
    normalize_url,
    parse_snapdouyin_response,
    parse_info_json_output,
    parse_tikmate_response,
    parse_tikwm_response,
    parse_yt_dlp_progress,
    select_formats,
    sanitize_filename,
    update_ytdlp,
    validate_known_video_url,
    validate_url_input,
)



class CoreTests(unittest.TestCase):
    def test_app_name_is_pro_downloader(self):
        self.assertEqual(APP_NAME, "Pro Downloader")

    def test_extract_urls_deduplicates_and_ignores_non_urls(self):
        text = "hello https://a.test/watch?v=1, https://b.test/x\nhttps://a.test/watch?v=1"

        self.assertEqual(
            extract_urls(text),
            ["https://a.test/watch?v=1", "https://b.test/x"],
        )

    def test_validate_url_input_accepts_valid_urls(self):
        urls, error = validate_url_input("https://a.test/watch?v=1\nhttps://b.test/x")

        self.assertIsNone(error)
        self.assertEqual(urls, ["https://a.test/watch?v=1", "https://b.test/x"])

    def test_validate_url_input_rejects_missing_scheme(self):
        urls, error = validate_url_input("www.douyin.com/video/123")

        self.assertEqual(urls, [])
        self.assertIn("http:// or https://", error or "")

    def test_validate_url_input_rejects_missing_host(self):
        urls, error = validate_url_input("https://")

        self.assertEqual(urls, [])
        self.assertIn("Invalid URL", error or "")

    def test_validate_url_input_rejects_short_douyin_video_id(self):
        urls, error = validate_url_input("https://www.douyin.com/video/123")

        self.assertEqual(urls, [])
        self.assertIn("Douyin link looks incomplete", error or "")

    def test_validate_url_input_rejects_short_douyin_modal_id(self):
        urls, error = validate_url_input("https://www.douyin.com/jingxuan?modal_id=123")

        self.assertEqual(urls, [])
        self.assertIn("Douyin link looks incomplete", error or "")

    def test_validate_known_video_url_allows_short_douyin_share_links(self):
        self.assertIsNone(validate_known_video_url("https://v.douyin.com/vL0Sq6GP7Yk/"))

    def test_friendly_error_identifies_missing_provider_media_as_bad_link(self):
        self.assertEqual(
            friendly_error("SnapDouyin did not return media options"),
            "Invalid link or video not found. Check that the URL is complete and the video is public.",
        )

    def test_friendly_error_identifies_douyin_cookie_anti_bot_error(self):
        self.assertIn("Douyin requires browser cookies", friendly_error("ERROR: [Douyin] Fresh cookies (not necessarily logged in) are needed"))
        self.assertIn("Douyin requires browser cookies", friendly_error("jiji262 engine did not download a video. Douyin requires browser cookies"))



    def test_update_ytdlp_refuses_frozen_app_self_update(self):
        with patch("reclip_desktop.core.is_frozen_app", return_value=True):
            with self.assertRaises(RuntimeError):
                update_ytdlp()

    def test_normalize_url_converts_douyin_modal_id(self):
        self.assertEqual(
            normalize_url("https://www.douyin.com/jingxuan?modal_id=7621183643477642536"),
            "https://www.douyin.com/video/7621183643477642536",
        )

    def test_is_douyin_url(self):
        self.assertTrue(is_douyin_url("https://v.douyin.com/vL0Sq6GP7Yk/"))
        self.assertTrue(is_douyin_url("https://www.douyin.com/video/7621183643477642536"))
        self.assertFalse(is_douyin_url("https://www.tiktok.com/@user/video/123"))

    def test_is_channel_or_playlist_url(self):
        self.assertTrue(is_channel_or_playlist_url("https://www.youtube.com/@channelname/videos"))
        self.assertTrue(is_channel_or_playlist_url("https://www.youtube.com/playlist?list=PL12345"))
        self.assertTrue(is_channel_or_playlist_url("https://www.douyin.com/user/MS4wLjABAAAA123"))
        self.assertFalse(is_channel_or_playlist_url("https://www.youtube.com/watch?v=12345"))

    def test_fetch_channel_videos_filters_by_keyword_and_limit(self):
        mock_items = [
            {"id": "1", "url": "https://www.youtube.com/watch?v=1", "title": "Python Tutorial 1", "uploader": "Dev"},
            {"id": "2", "url": "https://www.youtube.com/watch?v=2", "title": "Java Guide", "uploader": "Dev"},
            {"id": "3", "url": "https://www.youtube.com/watch?v=3", "title": "Python Advanced", "uploader": "Dev"},
        ]
        with patch("reclip_desktop.core.fetch_youtube_channel_videos", return_value=mock_items):
            res = fetch_channel_videos("https://www.youtube.com/@Dev/videos", limit=1, keyword="python")
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["title"], "Python Tutorial 1")

    def test_load_douyin_cookies_reads_file_and_env(self):
        import json
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_cookie = Path(tmp_dir) / "cookies.json"
            fake_cookie.write_text(json.dumps({"msToken": "tok_123", "ttwid": "wid_456"}), encoding="utf-8")
            with (
                patch("pathlib.Path.exists", side_effect=lambda: True),
                patch("pathlib.Path.read_text", return_value=fake_cookie.read_text(encoding="utf-8")),
            ):
                cookies = load_douyin_cookies()
                self.assertEqual(cookies.get("msToken"), "tok_123")
                self.assertEqual(cookies.get("ttwid"), "wid_456")

    def test_fetch_douyin_channel_videos_paginates(self):
        import sys
        import types

        page1 = {
            "has_more": True,
            "max_cursor": 100,
            "aweme_list": [{"aweme_id": "vid1", "desc": "Video 1", "author": {"nickname": "User"}}],
        }
        page2 = {
            "has_more": False,
            "max_cursor": 0,
            "aweme_list": [{"aweme_id": "vid2", "desc": "Video 2", "author": {"nickname": "User"}}],
        }

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            async def get_user_post(self, sec_uid, count=20, max_cursor=0):
                if max_cursor == 0:
                    return page1
                return page2

        fake_core = types.ModuleType("core")
        fake_api_client = types.ModuleType("core.api_client")
        fake_api_client.DouyinAPIClient = FakeClient
        fake_core.api_client = fake_api_client

        with patch.dict(sys.modules, {"core": fake_core, "core.api_client": fake_api_client}):
            with patch("reclip_desktop.core.load_douyin_cookies", return_value={"msToken": "test"}):
                results = fetch_douyin_channel_videos("https://www.douyin.com/user/MS4wLjABAAAA_test", limit=0)
                self.assertEqual(len(results), 2)
                self.assertEqual(results[0]["id"], "vid1")
                self.assertEqual(results[1]["id"], "vid2")


    def test_select_formats_keeps_best_bitrate_per_height(self):
        info = {
            "formats": [
                {"format_id": "low", "height": 720, "vcodec": "avc1", "tbr": 1000},
                {"format_id": "best", "height": 720, "vcodec": "avc1", "tbr": 2500},
                {"format_id": "audio", "height": None, "vcodec": "none", "tbr": 128},
                {"format_id": "hd", "height": 1080, "vcodec": "vp9", "tbr": 2000},
            ]
        }

        self.assertEqual(
            select_formats(info),
            [
                {"id": "hd", "label": "yt-dlp 1080p", "height": 1080, "provider": "yt-dlp"},
                {"id": "best", "label": "yt-dlp 720p", "height": 720, "provider": "yt-dlp"},
            ],
        )

    def test_extract_subtitle_languages_merges_manual_and_auto(self):
        info = {
            "subtitles": {"en": [], "vi": []},
            "automatic_captions": {"zh-Hans": [], "en": []},
        }

        self.assertEqual(extract_subtitle_languages(info), ["en", "vi", "zh-Hans"])

    def test_build_download_command_for_video_quality(self):
        request = DownloadRequest(
            url="https://example.com/video",
            output_template="downloads/job.%(ext)s",
            media_format="video",
            format_id="137",
            archive_file="downloads/archive.txt",
            advanced=AdvancedOptions(proxy="http://127.0.0.1:7890", max_quality="720p", subtitles=True, metadata=True, thumbnail=True),
        )

        with (
            patch("reclip_desktop.core.yt_dlp_command", return_value=["python", "-m", "yt_dlp"]),
            patch("reclip_desktop.core.find_ffmpeg_location", return_value="C:/ffmpeg/ffmpeg.exe"),
        ):
            self.assertEqual(
                build_download_command(request),
                [
                    "python",
                    "-m",
                    "yt_dlp",
                    "--no-playlist",
                    "--newline",
                    "--progress-template",
                    "download:%(progress._percent_str)s",
                    "-o",
                    "downloads/job.%(ext)s",
                    "--download-archive",
                    "downloads/archive.txt",
                    "--proxy",
                    "http://127.0.0.1:7890",
                    "-S",
                    "res:720",
                    "--write-subs",
                    "--write-auto-subs",
                    "--sub-langs",
                    "all",
                    "--embed-metadata",
                    "--write-info-json",
                    "--write-thumbnail",
                    "--ffmpeg-location",
                    "C:/ffmpeg/ffmpeg.exe",
                    "-f",
                    "137+bestaudio/137/bestvideo*+bestaudio/bestvideo*/best*[vcodec!=none]",
                    "--merge-output-format",
                    "mp4",
                    "--remux-video",
                    "mp4",
                    "https://example.com/video",
                ],
            )

    def test_build_download_command_can_set_subtitle_language_and_impersonate(self):
        request = DownloadRequest(
            url="https://example.com/video",
            output_template="downloads/job.%(ext)s",
            media_format="video",
            advanced=AdvancedOptions(subtitles=True, subtitle_languages="en,vi", impersonate="Chrome"),
        )

        with (
            patch("reclip_desktop.core.yt_dlp_command", return_value=["python", "-m", "yt_dlp"]),
            patch("reclip_desktop.core.find_ffmpeg_location", return_value=None),
        ):
            command = build_download_command(request)

        self.assertEqual(command[command.index("--sub-langs") + 1], "en,vi")
        self.assertEqual(command[command.index("--impersonate") + 1], "chrome")

    def test_build_info_command_can_use_impersonate(self):
        with patch("reclip_desktop.core.yt_dlp_command", return_value=["python", "-m", "yt_dlp"]):
            command = build_info_command(
                "https://www.tiktok.com/@user/video/123",
                advanced=AdvancedOptions(impersonate="Safari"),
            )

        self.assertEqual(command[command.index("--impersonate") + 1], "safari")

    def test_fetch_douyin_auto_uses_provider_before_ytdlp(self):
        provider_info = {"title": "douyin", "formats": [{"id": "snapdouyin-1", "media_format": "video"}]}
        with (
            patch("reclip_desktop.core.fetch_douyin_provider_info", return_value=provider_info) as provider_fetch,
            patch("reclip_desktop.core.fetch_info_result_with_auto_cookies") as ytdlp_fetch,
        ):
            from reclip_desktop.core import fetch_video_info

            self.assertEqual(fetch_video_info("https://www.douyin.com/video/123", advanced=AdvancedOptions()), provider_info)

        provider_fetch.assert_called_once()
        ytdlp_fetch.assert_not_called()

    def test_fetch_tiktok_falls_back_to_provider_when_ytdlp_stdout_is_not_json(self):
        provider_info = {"title": "tiktok", "formats": [{"id": "tikwm-play", "provider": "TikWM"}]}
        result = subprocess.CompletedProcess(["yt-dlp"], 0, "", "")
        with (
            patch("reclip_desktop.core.fetch_info_result_with_auto_cookies", return_value=result),
            patch("reclip_desktop.core.fetch_tiktok_provider_info", return_value=provider_info) as provider_fetch,
        ):
            from reclip_desktop.core import fetch_video_info

            self.assertEqual(
                fetch_video_info("https://www.tiktok.com/@user/video/7642961251777236245", advanced=AdvancedOptions()),
                provider_info,
            )

        provider_fetch.assert_called_once()

    def test_parse_info_json_output_uses_json_line_when_output_has_noise(self):
        self.assertEqual(parse_info_json_output("warning\n{\"title\":\"ok\"}\n"), {"title": "ok"})

    def test_build_download_command_for_audio(self):
        request = DownloadRequest(
            url="https://example.com/video",
            output_template="downloads/job.%(ext)s",
            media_format="audio",
        )

        with (
            patch("reclip_desktop.core.yt_dlp_command", return_value=["python", "-m", "yt_dlp"]),
            patch("reclip_desktop.core.find_ffmpeg_location", return_value=None),
        ):
            command = build_download_command(request)

        self.assertIn("-x", command)
        self.assertIn("--audio-format", command)
        self.assertIn("mp3", command)

    def test_build_info_command_can_use_browser_cookies(self):
        with patch("reclip_desktop.core.yt_dlp_command", return_value=["python", "-m", "yt_dlp"]):
            self.assertEqual(
                build_info_command("https://www.douyin.com/video/123", cookie_browser="chrome"),
                [
                    "python",
                    "-m",
                    "yt_dlp",
                    "--no-playlist",
                    "-j",
                    "--cookies-from-browser",
                    "chrome",
                    "https://www.douyin.com/video/123",
                ],
            )

    def test_build_download_command_can_use_browser_cookies(self):
        request = DownloadRequest(
            url="https://www.douyin.com/video/123",
            output_template="downloads/job.%(ext)s",
            media_format="video",
            cookie_browser="edge",
        )

        with (
            patch("reclip_desktop.core.yt_dlp_command", return_value=["python", "-m", "yt_dlp"]),
            patch("reclip_desktop.core.find_ffmpeg_location", return_value=None),
        ):
            command = build_download_command(request)

        self.assertIn("--cookies-from-browser", command)
        self.assertIn("edge", command)

    def test_advanced_options_cookie_browser_auto_maps_to_none(self):
        self.assertIsNone(AdvancedOptions(cookie_browser="Auto").yt_dlp_cookie_browser())
        self.assertEqual(AdvancedOptions(cookie_browser="Chrome").yt_dlp_cookie_browser(), "chrome")

    def test_auto_cookie_browsers_returns_supported_order(self):
        self.assertEqual(auto_cookie_browsers(), ["chrome", "edge", "firefox", "brave"])

    def test_build_download_command_for_video_never_extracts_mp3(self):
        request = DownloadRequest(
            url="https://example.com/video",
            output_template="downloads/job.%(ext)s",
            media_format="video",
        )

        with (
            patch("reclip_desktop.core.yt_dlp_command", return_value=["python", "-m", "yt_dlp"]),
            patch("reclip_desktop.core.find_ffmpeg_location", return_value=None),
        ):
            command = build_download_command(request)

        self.assertNotIn("-x", command)
        self.assertNotIn("--audio-format", command)
        self.assertEqual(command[command.index("--merge-output-format") + 1], "mp4")
        self.assertEqual(command[command.index("--remux-video") + 1], "mp4")
        self.assertIn("best*[vcodec!=none]", " ".join(command))

    def test_build_download_command_ignores_tikwm_marker_for_yt_dlp_selector(self):
        request = DownloadRequest(
            url="https://www.tiktok.com/@user/video/123",
            output_template="downloads/job.%(ext)s",
            media_format="video",
            format_id="tikwm-play",
        )

        with (
            patch("reclip_desktop.core.yt_dlp_command", return_value=["python", "-m", "yt_dlp"]),
            patch("reclip_desktop.core.find_ffmpeg_location", return_value=None),
        ):
            command = build_download_command(request)

        self.assertNotIn("tikwm-play", " ".join(command))

    def test_douyin_auto_jiji262_virtual_option_falls_back_to_provider(self):
        provider_info = {
            "title": "douyin",
            "formats": [{"id": "snapdouyin-2", "media_format": "video"}],
        }
        expected_path = Path("downloads/fallback.mp4")

        with (
            patch("reclip_desktop.douyin_engine.download_with_jiji262", side_effect=RuntimeError("jiji failed")),
            patch("reclip_desktop.core.fetch_douyin_provider_info", return_value=provider_info),
            patch("reclip_desktop.core.download_snapdouyin_media", return_value=expected_path) as snap_download,
        ):
            result = download_media(
                url="https://www.douyin.com/video/123",
                download_dir=Path("downloads"),
                job_id="job",
                media_format="video",
                title="douyin",
                format_id="jiji262-local",
                advanced=AdvancedOptions(douyin_engine="Auto"),
            )

        self.assertEqual(result, expected_path)
        snap_download.assert_called_once()

    def test_download_media_creates_archive_parent_before_ytdlp(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            archive_file = root / "state" / "data" / "archive.txt"
            expected_path = root / "video.mp4"

            def run_command(command, **_kwargs):
                self.assertTrue(archive_file.parent.exists())
                return subprocess.CompletedProcess(command, 0, "", "")

            with (
                patch("reclip_desktop.core.yt_dlp_command", return_value=["python", "-m", "yt_dlp"]),
                patch("reclip_desktop.core.find_ffmpeg_location", return_value=None),
                patch("reclip_desktop.core.run_command_with_progress", side_effect=run_command),
                patch("reclip_desktop.core.finalize_downloaded_job_file", return_value=expected_path),
            ):
                result = download_media(
                    url="https://example.com/video/123",
                    download_dir=root / "downloads",
                    job_id="job",
                    media_format="video",
                    archive_file=archive_file,
                )

            self.assertEqual(result, expected_path)

    def test_snapdouyin_audio_only_mp4_can_be_converted_to_still_video(self):
        provider_info = {
            "title": "douyin music",
            "thumbnail": "https://cdn.example/cover.jpg",
            "formats": [
                {
                    "id": "snapdouyin-1",
                    "media_format": "video",
                    "extension": "mp4",
                }
            ],
            "snapdouyin_media": {"snapdouyin-1": "https://cdn.example/audio-only.mp4"},
        }
        expected_path = Path("downloads/douyin music.mp4")

        with (
            patch("reclip_desktop.core.download_url_to_file") as download_file,
            patch("reclip_desktop.core.assert_downloaded_file_has_expected_stream", side_effect=ValueError("no video")),
            patch("reclip_desktop.core.probe_media_streams", return_value="Stream #0:0: Audio: aac"),
            patch("reclip_desktop.core.create_still_video_from_audio", return_value=expected_path) as create_still_video,
        ):

            result = download_snapdouyin_media(
                url="https://www.douyin.com/video/123",
                download_dir=Path("downloads"),
                job_id="job",
                title="douyin music",
                format_id="snapdouyin-1",
                media_format="video",
                provider_info=provider_info,
            )

        self.assertEqual(result, expected_path)
        download_file.assert_called_once()
        create_still_video.assert_called_once()

    def test_choose_downloaded_file_requires_mp4_for_video(self):
        with self.assertRaises(ValueError):
            choose_downloaded_file(["job.mp3"], "video")

        self.assertEqual(choose_downloaded_file(["job.webm", "job.mp4"], "video"), "job.mp4")

    def test_cleanup_job_files_removes_only_matching_job_files(self):
        tmp = Path("tmp-cleanup-job")
        tmp.mkdir(exist_ok=True)
        try:
            (tmp / "abc123.mp4").write_bytes(b"1")
            (tmp / "abc123.webm").write_bytes(b"1")
            (tmp / "other.mp4").write_bytes(b"1")

            cleanup_job_files(tmp, "abc123")

            self.assertFalse((tmp / "abc123.mp4").exists())
            self.assertFalse((tmp / "abc123.webm").exists())
            self.assertTrue((tmp / "other.mp4").exists())
        finally:
            for path in tmp.glob("*"):
                path.unlink(missing_ok=True)
            tmp.rmdir()

    def test_finalize_downloaded_job_file_reuses_valid_job_file_and_cleans_siblings(self):
        tmp = Path("tmp-finalize-job")
        tmp.mkdir(exist_ok=True)
        try:
            (tmp / "abc123.mp4").write_bytes(b"video")
            (tmp / "abc123.webm").write_bytes(b"video")

            with patch("reclip_desktop.core.assert_downloaded_file_has_expected_stream"):
                final_path = finalize_downloaded_job_file(tmp, "abc123", "video", "Nice Title")

            self.assertEqual(final_path, tmp / "Nice Title.mp4")
            self.assertTrue((tmp / "Nice Title.mp4").exists())
            self.assertFalse((tmp / "abc123.mp4").exists())
            self.assertFalse((tmp / "abc123.webm").exists())
        finally:
            for path in tmp.glob("*"):
                path.unlink(missing_ok=True)
            tmp.rmdir()

    def test_assert_downloaded_file_rejects_video_file_without_video_stream(self):
        ffmpeg_output = "Input #0\n  Stream #0:0: Audio: mp3"
        with patch("reclip_desktop.core.probe_media_streams", return_value=ffmpeg_output):
            with self.assertRaises(ValueError):
                assert_downloaded_file_has_expected_stream("job.mp4", "video")

    def test_assert_downloaded_file_accepts_video_stream(self):
        ffmpeg_output = "Input #0\n  Stream #0:0: Video: h264\n  Stream #0:1: Audio: aac"
        with patch("reclip_desktop.core.probe_media_streams", return_value=ffmpeg_output):
            assert_downloaded_file_has_expected_stream("job.mp4", "video")

    def test_assert_downloaded_file_retries_until_video_stream_is_visible(self):
        outputs = [
            "Input #0\n  Stream #0:0: Audio: aac",
            "Input #0\n  Stream #0:0: Video: h264\n  Stream #0:1: Audio: aac",
        ]
        with (
            patch("reclip_desktop.core.probe_media_streams", side_effect=outputs),
            patch("reclip_desktop.core.time.sleep"),
        ):
            assert_downloaded_file_has_expected_stream("job.mp4", "video", retries=2, delay=0.01)

    def test_parse_tikwm_response_returns_video_info(self):
        info = parse_tikwm_response(
            {
                "code": 0,
                "data": {
                    "title": "hello",
                    "duration": 12,
                    "play": "https://cdn.example/video.mp4",
                    "wmplay": "https://cdn.example/wm.mp4",
                    "music": "https://cdn.example/music.mp3",
                    "cover": "https://cdn.example/cover.jpg",
                    "author": {"unique_id": "creator"},
                },
            }
        )

        self.assertEqual(info["title"], "hello")
        self.assertEqual(info["uploader"], "creator")
        self.assertEqual(info["subtitle_languages"], [])
        self.assertFalse(info["supports_metadata"])
        self.assertTrue(info["supports_thumbnail"])
        self.assertEqual(
            info["formats"],
            [
                {"id": "tikwm-play", "label": "TikWM No WM", "height": 0, "provider": "TikWM"},
                {"id": "tikwm-wmplay", "label": "TikWM Watermark", "height": 0, "provider": "TikWM"},
            ],
        )
        self.assertEqual(info["tikwm_play"], "https://cdn.example/video.mp4")

    def test_parse_tikwm_response_rejects_missing_video(self):
        with self.assertRaises(ValueError):
            parse_tikwm_response({"code": 0, "data": {"music": "https://cdn.example/music.mp3"}})

    def test_parse_snapdouyin_response_returns_all_media_options(self):
        info = parse_snapdouyin_response(
            {
                "title": "douyin title",
                "thumbnail": "https://cdn.example/cover.jpg",
                "duration": "02:03",
                "source": "douyin",
                "medias": [
                    {
                        "url": "https://snapdouyin.app/download?media=0",
                        "quality": "hd",
                        "extension": "mp4",
                        "formattedSize": "15 MB",
                        "videoAvailable": True,
                        "audioAvailable": True,
                    },
                    {
                        "url": "https://snapdouyin.app/download?media=1",
                        "quality": "128kbps",
                        "extension": "mp3",
                        "formattedSize": "4 MB",
                        "videoAvailable": False,
                        "audioAvailable": True,
                    },
                ],
            }
        )

        self.assertEqual(info["title"], "douyin title")
        self.assertEqual(info["duration"], 123)
        self.assertEqual(info["subtitle_languages"], [])
        self.assertFalse(info["supports_metadata"])
        self.assertTrue(info["supports_thumbnail"])
        self.assertEqual(
            info["formats"],
            [
                {
                    "id": "snapdouyin-0",
                    "label": "SnapDouyin hd mp4 (15 MB)",
                    "height": 0,
                    "provider": "SnapDouyin",
                    "extension": "mp4",
                    "media_format": "video",
                },
                {
                    "id": "snapdouyin-1",
                    "label": "SnapDouyin 128kbps mp3 (4 MB)",
                    "height": 0,
                    "provider": "SnapDouyin",
                    "extension": "mp3",
                    "media_format": "audio",
                },
            ],
        )
        self.assertEqual(info["snapdouyin_media"]["snapdouyin-0"], "https://snapdouyin.app/download?media=0")

    def test_parse_tikmate_response_returns_video_info(self):
        info = parse_tikmate_response(
            {
                "success": True,
                "id": "123",
                "token": "abc",
                "desc": "hello",
                "author_id": "creator",
                "cover": "https://cdn.example/cover.jpg",
            }
        )

        self.assertEqual(info["title"], "hello")
        self.assertEqual(info["uploader"], "creator")
        self.assertEqual(info["subtitle_languages"], [])
        self.assertFalse(info["supports_metadata"])
        self.assertTrue(info["supports_thumbnail"])
        self.assertEqual(info["formats"], [{"id": "tikmate", "label": "TikMate MP4", "height": 0, "provider": "TikMate"}])
        self.assertEqual(info["tikmate_play"], "https://tikmate.app/download/abc/123.mp4")

    def test_parse_yt_dlp_progress(self):
        self.assertEqual(parse_yt_dlp_progress("[download]  42.7% of 1.00MiB at 1MiB/s"), 42)
        self.assertEqual(parse_yt_dlp_progress("download: 42.7%"), 42)
        self.assertIsNone(parse_yt_dlp_progress("[download] Destination: file.mp4"))

    def test_sanitize_filename_strips_windows_reserved_chars(self):
        self.assertEqual(sanitize_filename('bad:/name*?"<>| long title', ".mp4"), "badname long title.mp4")

    def test_friendly_error_shortens_common_messages(self):
        self.assertEqual(friendly_error("ERROR: Unsupported URL: nope"), "This URL is not supported")
        self.assertEqual(
            friendly_error("ERROR: [Douyin] 7621183643477642536: Fresh cookies (not necessarily logged in) are needed"),
            "Douyin requires browser cookies. Please select a Cookie Browser (Chrome/Edge/Firefox) in Advanced Options.",
        )

        self.assertEqual(friendly_error("x" * 90), "x" * 80 + "...")

    def test_download_with_auto_cookies_accepts_cancel_event(self):
        import threading
        from reclip_desktop.core import download_with_auto_cookies
        cancel_evt = threading.Event()
        cancel_evt.set()
        # Should return None cleanly when cancelled
        res = download_with_auto_cookies(
            url="https://www.douyin.com/video/123",
            download_dir=Path("."),
            job_id="job",
            media_format="video",
            title="test",
            format_id=None,
            output_template="out.mp4",
            timeout=10,
            cancel_event=cancel_evt,
        )
        self.assertIsNone(res)

    def test_download_url_to_file_zero_bytes_raises(self):
        from reclip_desktop.core import download_url_to_file
        import io
        from unittest.mock import MagicMock
        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Length": "0"}
        mock_resp.read.side_effect = [b""]
        mock_opener = MagicMock()
        mock_opener.open.return_value.__enter__.return_value = mock_resp
        tmp_target = Path("tmp_zero_test.mp4")
        try:
            with self.assertRaises(RuntimeError) as ctx:
                download_url_to_file("http://fake.url", tmp_target, opener=mock_opener)
            self.assertIn("0 bytes", str(ctx.exception))
        finally:
            if tmp_target.exists():
                tmp_target.unlink()

    def test_assert_downloaded_file_accepts_lowercase_video(self):
        from reclip_desktop.core import assert_downloaded_file_has_expected_stream
        ffmpeg_output = "input #0\n  stream #0:0: video: h264\n  stream #0:1: audio: aac"
        with patch("reclip_desktop.core.probe_media_streams", return_value=ffmpeg_output):
            assert_downloaded_file_has_expected_stream("job.mp4", "video")


if __name__ == "__main__":
    unittest.main()
