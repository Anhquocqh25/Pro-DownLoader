from __future__ import annotations

import glob
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import base64
import uuid
import http.cookiejar
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


URL_SPLIT_RE = re.compile(r"[\s,]+")
WINDOWS_RESERVED_CHARS = set(r'\/:*?"<>|')
APP_NAME = "Pro Downloader"
APP_DIR = Path(__file__).resolve().parents[1]
APP_STATE_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / APP_NAME if os.name == "nt" else Path.home() / ".local" / "share" / APP_NAME
LOG_DIR = APP_STATE_DIR / "logs"
LOG_FILE = LOG_DIR / "reclip.log"
DATA_DIR = APP_STATE_DIR / "data"
HISTORY_FILE = DATA_DIR / "history.json"
ARCHIVE_FILE = DATA_DIR / "yt-dlp-archive.txt"
TIKWM_API = "https://www.tikwm.com/api/"
TIKMATE_API = "https://api.tikmate.app/api/lookup"
SNAPDOUYIN_HOME = "https://snapdouyin.app/"
SNAPDOUYIN_API = "https://snapdouyin.app/wp-json/mx-downloader/video-data/"
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0 Safari/537.36",
}
SUPPORTED_COOKIE_BROWSERS = ["chrome", "edge", "firefox", "brave"]


def hidden_subprocess_kwargs() -> dict[str, Any]:
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {
        "startupinfo": startupinfo,
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
    }


@dataclass(frozen=True)
class AdvancedOptions:
    cookie_browser: str = "Auto"
    proxy: str = ""
    max_quality: str = "Best"
    subtitles: bool = False
    subtitle_languages: str = "all"
    metadata: bool = False
    thumbnail: bool = False
    douyin_engine: str = "Auto"
    impersonate: str = "Off"

    def yt_dlp_cookie_browser(self) -> str | None:
        value = (self.cookie_browser or "Auto").strip().lower()
        if value in {"", "auto", "none"}:
            return None
        if value in SUPPORTED_COOKIE_BROWSERS:
            return value
        return None

    def max_height(self) -> int | None:
        match = re.search(r"(\d{3,4})", self.max_quality or "")
        return int(match.group(1)) if match else None

    def normalized_douyin_engine(self) -> str:
        value = (self.douyin_engine or "Auto").strip().lower()
        if value in {"jiji262", "jiji262 local", "local"}:
            return "jiji262"
        if value in {"snapdouyin", "snap"}:
            return "snapdouyin"
        if value in {"yt-dlp", "ytdlp"}:
            return "yt-dlp"
        return "auto"

    def normalized_impersonate(self) -> str | None:
        value = (self.impersonate or "Off").strip().lower()
        if value in {"", "off", "none", "auto"}:
            return None
        aliases = {
            "chrome": "chrome",
            "edge": "edge",
            "safari": "safari",
            "firefox": "firefox",
        }
        return aliases.get(value, value)

    def normalized_subtitle_languages(self) -> str:
        value = (self.subtitle_languages or "all").strip()
        return value or "all"


@dataclass(frozen=True)
class DownloadRequest:
    url: str
    output_template: str
    media_format: str = "video"
    format_id: str | None = None
    cookie_browser: str | None = None
    proxy: str = ""
    max_quality: str = "Best"
    subtitles: bool = False
    subtitle_languages: str = "all"
    metadata: bool = False
    thumbnail: bool = False
    archive_file: str | None = None
    advanced: AdvancedOptions | None = None


def extract_urls(text: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for item in URL_SPLIT_RE.split(text):
        url = item.strip()
        if not url.startswith(("http://", "https://")) or url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def is_valid_http_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_known_video_url(url: str) -> str | None:
    parsed = urllib.parse.urlparse(url.strip())
    host = parsed.netloc.lower()
    path = parsed.path.strip("/")
    query = urllib.parse.parse_qs(parsed.query)

    if "douyin.com" in host:
        modal_id = (query.get("modal_id") or [""])[0]
        if "modal_id" in query and (not modal_id.isdigit() or len(modal_id) < 16):
            return "Douyin link looks incomplete. Check the modal_id/video ID and paste the full link again."

        match = re.search(r"(?:^|/)video/([^/?#]+)", path)
        if match:
            video_id = match.group(1)
            if not video_id.isdigit() or len(video_id) < 16:
                return "Douyin link looks incomplete. Check the video ID and paste the full link again."

        if path.startswith("jingxuan") and "modal_id" not in query:
            return "Douyin Jingxuan link is missing modal_id. Open the video and paste the full share/page link again."

    if "tiktok.com" in host or "tiktokv.com" in host:
        match = re.search(r"(?:^|/)video/([^/?#]+)", path)
        if match:
            video_id = match.group(1)
            if not video_id.isdigit() or len(video_id) < 8:
                return "TikTok link looks incomplete. Check the video ID and paste the full link again."

    return None


def validate_url_input(text: str) -> tuple[list[str], str | None]:
    raw = text.strip()
    if not raw:
        return [], "Paste at least one URL."

    urls = extract_urls(raw)
    if not urls:
        return [], "No valid URL found. URL must start with http:// or https://."

    invalid_urls = [url for url in urls if not is_valid_http_url(url)]
    if invalid_urls:
        return [], f"Invalid URL: {invalid_urls[0]}"

    for url in urls:
        known_url_error = validate_known_video_url(url)
        if known_url_error:
            return [], known_url_error

    return urls, None


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url.strip())
    host = parsed.netloc.lower()
    query = urllib.parse.parse_qs(parsed.query)
    modal_id = (query.get("modal_id") or [""])[0]
    if "douyin.com" in host and modal_id.isdigit():
        return f"https://www.douyin.com/video/{modal_id}"
    return url.strip()


def select_formats(info: dict[str, Any]) -> list[dict[str, Any]]:
    best_by_height: dict[int, dict[str, Any]] = {}
    for fmt in info.get("formats", []):
        height = fmt.get("height")
        if not height or fmt.get("vcodec", "none") == "none":
            continue

        tbr = fmt.get("tbr") or 0
        current = best_by_height.get(height)
        if current is None or tbr > (current.get("tbr") or 0):
            best_by_height[height] = fmt

    formats = [
        {"id": fmt["format_id"], "label": f"yt-dlp {height}p", "height": height, "provider": "yt-dlp"}
        for height, fmt in best_by_height.items()
    ]
    formats.sort(key=lambda item: item["height"], reverse=True)
    return formats


def extract_subtitle_languages(info: dict[str, Any]) -> list[str]:
    languages: set[str] = set()
    for key in ("subtitles", "automatic_captions"):
        value = info.get(key)
        if isinstance(value, dict):
            languages.update(str(lang) for lang in value if lang)
    return sorted(languages)


def build_download_command(request: DownloadRequest) -> list[str]:
    advanced = request.advanced or AdvancedOptions(
        cookie_browser=request.cookie_browser or "Auto",
        proxy=request.proxy,
        max_quality=request.max_quality,
        subtitles=request.subtitles,
        subtitle_languages=request.subtitle_languages,
        metadata=request.metadata,
        thumbnail=request.thumbnail,
    )
    command = yt_dlp_command() + [
        "--no-playlist",
        "--newline",
        "--progress-template",
        "download:%(progress._percent_str)s",
        "-o",
        request.output_template,
    ]
    if request.archive_file:
        command += ["--download-archive", request.archive_file]
    if advanced.proxy.strip():
        command += ["--proxy", advanced.proxy.strip()]
    max_height = advanced.max_height()
    if max_height:
        command += ["-S", f"res:{max_height}"]
    if advanced.subtitles:
        command += ["--write-subs", "--write-auto-subs", "--sub-langs", advanced.normalized_subtitle_languages()]
    if advanced.metadata:
        command += ["--embed-metadata", "--write-info-json"]
    if advanced.thumbnail:
        command += ["--write-thumbnail"]
    impersonate = advanced.normalized_impersonate()
    if impersonate:
        command += ["--impersonate", impersonate]

    ffmpeg_location = find_ffmpeg_location()
    if ffmpeg_location:
        command += ["--ffmpeg-location", ffmpeg_location]

    if request.media_format == "audio":
        command += ["-x", "--audio-format", "mp3"]
    elif request.format_id and not is_provider_format_id(request.format_id):
        command += [
            "-f",
            f"{request.format_id}+bestaudio/{request.format_id}/bestvideo*+bestaudio/bestvideo*/best*[vcodec!=none]",
            "--merge-output-format",
            "mp4",
            "--remux-video",
            "mp4",
        ]
    else:
        command += [
            "-f",
            "bestvideo*+bestaudio/bestvideo*/best*[vcodec!=none]",
            "--merge-output-format",
            "mp4",
            "--remux-video",
            "mp4",
        ]

    command = append_cookie_args(command, request.cookie_browser or advanced.yt_dlp_cookie_browser())
    command.append(request.url)
    return command


def build_info_command(url: str, cookie_browser: str | None = None, advanced: AdvancedOptions | None = None) -> list[str]:
    command = yt_dlp_command() + ["--no-playlist", "-j"]
    cookie = cookie_browser or (advanced.yt_dlp_cookie_browser() if advanced else None)
    if advanced and advanced.proxy.strip():
        command += ["--proxy", advanced.proxy.strip()]
    if advanced:
        impersonate = advanced.normalized_impersonate()
        if impersonate:
            command += ["--impersonate", impersonate]
    command = append_cookie_args(command, cookie)
    command.append(url)
    return command


def append_cookie_args(command: list[str], cookie_browser: str | None) -> list[str]:
    if cookie_browser in set(SUPPORTED_COOKIE_BROWSERS):
        return command + ["--cookies-from-browser", cookie_browser]
    return command


def auto_cookie_browsers() -> list[str]:
    return list(SUPPORTED_COOKIE_BROWSERS)


def log_event(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def yt_dlp_command() -> list[str]:
    if importlib.util.find_spec("yt_dlp") is not None:
        return [sys.executable, "-m", "yt_dlp"]
    return ["yt-dlp"]


def is_frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def find_ffmpeg_location() -> str | None:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        ffmpeg = shutil.which("ffmpeg")
        return ffmpeg


def sanitize_filename(title: str, extension: str, max_length: int = 80) -> str:
    safe_title = "".join(c for c in title if c not in WINDOWS_RESERVED_CHARS).strip()
    safe_title = " ".join(safe_title.split())
    if not safe_title:
        safe_title = "download"
    return f"{safe_title[:max_length].strip()}{extension}"


def friendly_error(error: str) -> str:
    if "Douyin" in error and "Fresh cookies" in error:
        return "Douyin needs fresh browser cookies. Open the video once in Chrome or Edge, pass any check, then retry."
    lowered = error.lower()
    if (
        "did not return media" in lowered
        or "did not return downloadable media" in lowered
        or "did not return a video url" in lowered
        or "did not return a download token" in lowered
        or "no video formats" in lowered
        or "not enough values to unpack" in lowered
    ):
        return "Invalid link or video not found. Check that the URL is complete and the video is public."
    if "Requested format is not available" in error:
        return "Video format is not available from this provider"
    if "Unsupported URL" in error:
        return "This URL is not supported"
    if "Video unavailable" in error:
        return "Video is unavailable or private"
    if "Private video" in error:
        return "This video is private"
    if "HTTP Error 403" in error:
        return "Access denied by the platform"
    if "HTTP Error 404" in error:
        return "Video not found"
    if "copyright" in error.lower():
        return "Video blocked due to copyright"
    if "geo" in error.lower():
        return "Video not available in your region"
    if "timed out" in error.lower():
        return "Request timed out - try again"
    if "network" in error.lower():
        return "Network error - check your connection"
    return error[:80] + "..." if len(error) > 80 else error


def fetch_video_info(
    url: str,
    timeout: int = 60,
    cookie_browser: str | None = None,
    advanced: AdvancedOptions | None = None,
) -> dict[str, Any]:
    url = normalize_url(url)
    log_event(f"INFO start url={url}")
    if is_douyin_url(url) and should_fetch_douyin_provider_first(advanced):
        provider_info = fetch_douyin_provider_info(url, timeout=timeout)
        if provider_info.get("formats"):
            log_event(f"INFO douyin provider first ok url={url} formats={len(provider_info['formats'])}")
            return provider_info

    if is_frozen_app() and importlib.util.find_spec("yt_dlp") is not None:
        try:
            info = fetch_info_with_ytdlp_api(url, cookie_browser=cookie_browser, advanced=advanced)
            selected_formats = select_formats(info)
            if is_tiktok_url(url) and not selected_formats:
                provider_info = fetch_tiktok_provider_info(url, timeout=timeout)
                if provider_info.get("formats"):
                    log_event(f"INFO provider api fallback ok url={url} formats={len(provider_info['formats'])}")
                    return provider_info
            log_event(f"INFO api ok url={url} title={info.get('title', '')}")
            return info_result_from_ytdlp_info(info, selected_formats)
        except Exception as exc:
            log_event(f"INFO api error url={url} error={exc}")
            if is_tiktok_url(url):
                provider_info = fetch_tiktok_provider_info(url, timeout=timeout)
                if provider_info.get("formats"):
                    log_event(f"INFO provider api error fallback ok url={url} formats={len(provider_info['formats'])}")
                    return provider_info
            if is_douyin_url(url):
                provider_info = fetch_douyin_provider_info(url, timeout=timeout)
                if provider_info.get("formats"):
                    log_event(f"INFO douyin provider api fallback ok url={url} formats={len(provider_info['formats'])}")
                    return provider_info
            raise

    try:
        result = fetch_info_result_with_auto_cookies(url, timeout=timeout, cookie_browser=cookie_browser, advanced=advanced)
    except Exception:
        if is_douyin_url(url):
            provider_info = fetch_douyin_provider_info(url, timeout=timeout)
            if provider_info.get("formats"):
                log_event(f"INFO douyin provider ok url={url} formats={len(provider_info['formats'])}")
                return provider_info
        raise

    try:
        info = parse_info_json_output(result.stdout)
    except json.JSONDecodeError as exc:
        log_event(
            "INFO json error "
            f"url={url} error={exc} stdout={safe_log_snippet(result.stdout)} stderr={safe_log_snippet(result.stderr)}"
        )
        if is_tiktok_url(url):
            provider_info = fetch_tiktok_provider_info(url, timeout=timeout)
            if provider_info.get("formats"):
                log_event(f"INFO provider json fallback ok url={url} formats={len(provider_info['formats'])}")
                return provider_info
        if is_douyin_url(url):
            provider_info = fetch_douyin_provider_info(url, timeout=timeout)
            if provider_info.get("formats"):
                log_event(f"INFO douyin provider json fallback ok url={url} formats={len(provider_info['formats'])}")
                return provider_info
        raise

    selected_formats = select_formats(info)
    if is_tiktok_url(url) and not selected_formats:
        provider_info = fetch_tiktok_provider_info(url, timeout=timeout)
        if provider_info.get("formats"):
            log_event(f"INFO provider ok url={url} formats={len(provider_info['formats'])}")
            return provider_info

    log_event(f"INFO ok url={url} title={info.get('title', '')}")
    return info_result_from_ytdlp_info(info, selected_formats)


def parse_info_json_output(output: str) -> dict[str, Any]:
    text = (output or "").strip()
    if not text:
        raise json.JSONDecodeError("empty yt-dlp JSON output", output or "", 0)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        for line in text.splitlines():
            candidate = line.strip()
            if candidate.startswith("{") and candidate.endswith("}"):
                value = json.loads(candidate)
                break
        else:
            raise
    if not isinstance(value, dict):
        raise json.JSONDecodeError("yt-dlp JSON output is not an object", text, 0)
    return value


def info_result_from_ytdlp_info(info: dict[str, Any], selected_formats: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "title": info.get("title", ""),
        "thumbnail": info.get("thumbnail", ""),
        "duration": info.get("duration"),
        "uploader": info.get("uploader", ""),
        "formats": selected_formats,
        "subtitle_languages": extract_subtitle_languages(info),
        "supports_metadata": True,
        "supports_thumbnail": bool(info.get("thumbnail")),
    }


def fetch_info_with_ytdlp_api(
    url: str,
    cookie_browser: str | None = None,
    advanced: AdvancedOptions | None = None,
) -> dict[str, Any]:
    import yt_dlp

    options = ytdlp_base_api_options(cookie_browser=cookie_browser, advanced=advanced)
    options["skip_download"] = True
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
    if not isinstance(info, dict):
        raise RuntimeError("yt-dlp API did not return metadata")
    return info


def ytdlp_base_api_options(cookie_browser: str | None = None, advanced: AdvancedOptions | None = None) -> dict[str, Any]:
    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    cookie = cookie_browser or (advanced.yt_dlp_cookie_browser() if advanced else None)
    if cookie:
        options["cookiesfrombrowser"] = (cookie,)
    if advanced and advanced.proxy.strip():
        options["proxy"] = advanced.proxy.strip()
    if advanced:
        impersonate = advanced.normalized_impersonate()
        if impersonate:
            options["impersonate"] = impersonate
    return options


def safe_log_snippet(text: str, limit: int = 240) -> str:
    snippet = (text or "").replace("\r", "\\r").replace("\n", "\\n")
    return snippet[:limit]


def should_fetch_douyin_provider_first(advanced: AdvancedOptions | None) -> bool:
    engine = (advanced or AdvancedOptions()).normalized_douyin_engine()
    return engine in {"auto", "jiji262", "snapdouyin"}


def fetch_info_result_with_auto_cookies(
    url: str,
    timeout: int,
    cookie_browser: str | None = None,
    advanced: AdvancedOptions | None = None,
) -> subprocess.CompletedProcess[str]:
    requested_cookie = cookie_browser or (advanced.yt_dlp_cookie_browser() if advanced else None)
    browsers = [requested_cookie] if requested_cookie else [None]
    if is_douyin_url(url) and not cookie_browser:
        browsers.extend(auto_cookie_browsers())

    last_error = ""
    for browser in browsers:
        result = subprocess.run(
            build_info_command(url, cookie_browser=browser, advanced=advanced),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            **hidden_subprocess_kwargs(),
        )
        if result.returncode == 0:
            if browser:
                log_event(f"INFO cookie ok url={url} browser={browser}")
            return result

        last_error = last_error_line(result.stderr)
        log_event(f"INFO error url={url} browser={browser or 'none'} error={last_error}")
        if is_tiktok_url(url):
            provider_info = fetch_tiktok_provider_info(url, timeout=timeout)
            if provider_info.get("formats"):
                return subprocess.CompletedProcess(
                    build_info_command(url, cookie_browser=browser, advanced=advanced),
                    0,
                    json.dumps(provider_info),
                    "",
                )

    raise RuntimeError(last_error)


def download_media(
    url: str,
    download_dir: Path,
    job_id: str,
    media_format: str,
    title: str = "",
    format_id: str | None = None,
    timeout: int = 300,
    progress_callback: Callable[[int], None] | None = None,
    cookie_browser: str | None = None,
    advanced: AdvancedOptions | None = None,
    archive_file: Path | None = None,
) -> Path:
    url = normalize_url(url)
    download_dir.mkdir(parents=True, exist_ok=True)
    douyin_engine = (advanced or AdvancedOptions()).normalized_douyin_engine()
    if media_format == "video" and is_douyin_url(url) and douyin_engine in {"auto", "jiji262"}:
        try:
            from .douyin_engine import download_with_jiji262

            return download_with_jiji262(url, download_dir, advanced=advanced, progress_callback=progress_callback)
        except Exception as exc:
            log_event(f"JIJI262 fallback url={url} error={exc}")
            if douyin_engine == "jiji262":
                raise
            if format_id == "jiji262-local":
                provider_info = fetch_douyin_provider_info(url, timeout=min(timeout, 60))
                video_formats = [fmt for fmt in provider_info.get("formats", []) if fmt.get("media_format") == "video"]
                if video_formats:
                    return download_snapdouyin_media(
                        url,
                        download_dir,
                        job_id,
                        title or str(provider_info.get("title") or ""),
                        timeout,
                        progress_callback,
                        str(video_formats[0]["id"]),
                        media_format,
                        provider_info=provider_info,
                    )
                format_id = None
    if media_format == "video" and is_douyin_url(url) and douyin_engine == "yt-dlp" and format_id and format_id.startswith("snapdouyin-"):
        format_id = None

    if is_provider_format_id(format_id):
        if format_id == "tikmate":
            return download_tikmate_video(url, download_dir, job_id, title, timeout, progress_callback)
        if format_id and format_id.startswith("tikwm-"):
            return download_tikwm_video(url, download_dir, job_id, title, timeout, progress_callback, format_id)
        if format_id == "jiji262-local":
            if media_format != "video":
                raise RuntimeError("jiji262 local engine only supports video downloads")
            from .douyin_engine import download_with_jiji262

            return download_with_jiji262(url, download_dir, advanced=advanced, progress_callback=progress_callback)
        if format_id and format_id.startswith("snapdouyin-"):
            return download_snapdouyin_media(url, download_dir, job_id, title, timeout, progress_callback, format_id, media_format)

    if media_format == "video" and is_tiktok_url(url) and is_provider_format_id(format_id):
        if format_id == "tikmate":
            return download_tikmate_video(url, download_dir, job_id, title, timeout, progress_callback)
        return download_tikwm_video(url, download_dir, job_id, title, timeout, progress_callback, format_id)

    if archive_file:
        archive_file.parent.mkdir(parents=True, exist_ok=True)

    if is_frozen_app() and importlib.util.find_spec("yt_dlp") is not None:
        try:
            return download_with_ytdlp_api(
                url=url,
                download_dir=download_dir,
                job_id=job_id,
                media_format=media_format,
                title=title,
                format_id=format_id,
                timeout=timeout,
                progress_callback=progress_callback,
                cookie_browser=cookie_browser,
                advanced=advanced,
                archive_file=archive_file,
            )
        except Exception as exc:
            log_event(f"DOWNLOAD api error job={job_id} url={url} error={exc}")
            recovered_path = finalize_downloaded_job_file(download_dir, job_id, media_format, title)
            if recovered_path:
                log_event(f"DOWNLOAD api recovered job={job_id} final={recovered_path}")
                return recovered_path
            cleanup_job_files(download_dir, job_id)
            if media_format == "video" and is_tiktok_url(url):
                return download_tikwm_video(url, download_dir, job_id, title, timeout, progress_callback)
            if media_format == "video" and is_douyin_url(url):
                provider_info = fetch_douyin_provider_info(url, timeout=min(timeout, 60))
                video_formats = [fmt for fmt in provider_info.get("formats", []) if fmt.get("media_format") == "video"]
                if video_formats:
                    return download_snapdouyin_media(
                        url,
                        download_dir,
                        job_id,
                        title or str(provider_info.get("title") or ""),
                        timeout,
                        progress_callback,
                        str(video_formats[0]["id"]),
                        media_format,
                        provider_info=provider_info,
                    )
            raise

    output_template = str(download_dir / f"{job_id}.%(ext)s")
    command = build_download_command(
        DownloadRequest(
            url=url,
            output_template=output_template,
            media_format=media_format,
            format_id=format_id,
            cookie_browser=cookie_browser,
            archive_file=str(archive_file) if archive_file else None,
            advanced=advanced,
        )
    )
    log_event(
        "DOWNLOAD start "
        f"job={job_id} media_format={media_format} format_id={format_id or ''} "
        f"title={title} url={url} command={json.dumps(command, ensure_ascii=False)}"
    )

    result = run_command_with_progress(command, timeout=timeout, progress_callback=progress_callback)
    if result.returncode != 0:
        error = last_error_line(result.stderr)
        log_event(f"DOWNLOAD error job={job_id} error={error}")
        if is_douyin_url(url) and not cookie_browser:
            cookie_path = download_with_auto_cookies(
                url=url,
                download_dir=download_dir,
                job_id=job_id,
                media_format=media_format,
                title=title,
                format_id=format_id,
                output_template=output_template,
                timeout=timeout,
                progress_callback=progress_callback,
            )
            if cookie_path:
                return cookie_path
        if media_format == "video" and is_douyin_url(url):
            provider_info = fetch_douyin_provider_info(url, timeout=min(timeout, 60))
            video_formats = [fmt for fmt in provider_info.get("formats", []) if fmt.get("media_format") == "video"]
            if video_formats:
                return download_snapdouyin_media(
                    url,
                    download_dir,
                    job_id,
                    title or str(provider_info.get("title") or ""),
                    timeout,
                    progress_callback,
                    str(video_formats[0]["id"]),
                    media_format,
                    provider_info=provider_info,
                )
        if media_format == "video" and is_tiktok_url(url):
            return download_tikwm_video(url, download_dir, job_id, title, timeout, progress_callback)
        raise RuntimeError(error)

    try:
        final_path = finalize_downloaded_job_file(download_dir, job_id, media_format, title)
    except Exception as exc:
        cleanup_job_files(download_dir, job_id)
        log_event(f"DOWNLOAD rejected job={job_id} reason={exc}")
        if media_format == "video" and is_tiktok_url(url):
            return download_tikwm_video(url, download_dir, job_id, title, timeout, progress_callback)
        raise
    if not final_path:
        raise RuntimeError("Download completed but no file was found")
    log_event(f"DOWNLOAD done job={job_id} final={final_path}")
    return final_path


def download_with_auto_cookies(
    url: str,
    download_dir: Path,
    job_id: str,
    media_format: str,
    title: str,
    format_id: str | None,
    output_template: str,
    timeout: int,
    progress_callback: Callable[[int], None] | None = None,
) -> Path | None:
    for browser in auto_cookie_browsers():
        request = DownloadRequest(
            url=url,
            output_template=output_template,
            media_format=media_format,
            format_id=format_id,
            cookie_browser=browser,
        )
        command = build_download_command(request)
        log_event(f"DOWNLOAD retry cookies job={job_id} browser={browser} command={json.dumps(command, ensure_ascii=False)}")
        result = run_command_with_progress(command, timeout=timeout, progress_callback=progress_callback)
        if result.returncode != 0:
            log_event(f"DOWNLOAD cookie error job={job_id} browser={browser} error={last_error_line(result.stderr)}")
            continue

        final_path = finalize_downloaded_job_file(download_dir, job_id, media_format, title)
        if not final_path:
            continue
        log_event(f"DOWNLOAD cookie done job={job_id} browser={browser} final={final_path}")
        return final_path
    return None


def download_with_ytdlp_api(
    url: str,
    download_dir: Path,
    job_id: str,
    media_format: str,
    title: str = "",
    format_id: str | None = None,
    timeout: int = 300,
    progress_callback: Callable[[int], None] | None = None,
    cookie_browser: str | None = None,
    advanced: AdvancedOptions | None = None,
    archive_file: Path | None = None,
) -> Path:
    import yt_dlp

    output_template = str(download_dir / f"{job_id}.%(ext)s")
    options = ytdlp_base_api_options(cookie_browser=cookie_browser, advanced=advanced)
    options.update(
        {
            "outtmpl": output_template,
            "progress_hooks": [ytdlp_api_progress_hook(progress_callback)] if progress_callback else [],
            "ignoreerrors": False,
        }
    )
    if archive_file:
        archive_file.parent.mkdir(parents=True, exist_ok=True)
        options["download_archive"] = str(archive_file)
    ffmpeg = find_ffmpeg_location()
    if ffmpeg:
        options["ffmpeg_location"] = ffmpeg

    advanced = advanced or AdvancedOptions(cookie_browser=cookie_browser or "Auto")
    if media_format == "audio":
        options["format"] = "bestaudio/best"
        options["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}]
    elif format_id and not is_provider_format_id(format_id):
        options["format"] = f"{format_id}+bestaudio/{format_id}/bestvideo*+bestaudio/bestvideo*/best*[vcodec!=none]"
        options["merge_output_format"] = "mp4"
    else:
        options["format"] = "bestvideo*+bestaudio/bestvideo*/best*[vcodec!=none]"
        options["merge_output_format"] = "mp4"

    if advanced.max_height():
        options["format_sort"] = [f"res:{advanced.max_height()}"]
    if advanced.subtitles:
        options["writesubtitles"] = True
        options["writeautomaticsub"] = True
        options["subtitleslangs"] = [part.strip() for part in advanced.normalized_subtitle_languages().split(",") if part.strip()]
    if advanced.metadata:
        options["addmetadata"] = True
        options["writeinfojson"] = True
    if advanced.thumbnail:
        options["writethumbnail"] = True

    log_event(f"DOWNLOAD api start job={job_id} media_format={media_format} format_id={format_id or ''} url={url}")
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])

    final_path = finalize_downloaded_job_file(download_dir, job_id, media_format, title)
    if not final_path:
        raise RuntimeError("Download completed but no file was found")
    log_event(f"DOWNLOAD api done job={job_id} final={final_path}")
    return final_path


def finalize_downloaded_job_file(download_dir: Path, job_id: str, media_format: str, title: str = "") -> Path | None:
    files = [Path(path) for path in glob.glob(str(download_dir / f"{job_id}.*"))]
    log_event(f"DOWNLOAD files job={job_id} files={json.dumps([str(path) for path in files], ensure_ascii=False)}")
    if not files:
        return None

    chosen = Path(choose_downloaded_file(files, media_format))
    assert_downloaded_file_has_expected_stream(chosen, media_format)
    final_path = chosen
    if title:
        final_name = sanitize_filename(title, chosen.suffix)
        candidate = download_dir / final_name
        if candidate.resolve() != chosen.resolve():
            final_path = unique_path(candidate)
            os.replace(chosen, final_path)

    for path in files:
        if path != chosen and path.exists():
            path.unlink(missing_ok=True)
    return final_path


def cleanup_job_files(download_dir: Path, job_id: str) -> None:
    for path in [Path(item) for item in glob.glob(str(download_dir / f"{job_id}.*"))]:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            log_event(f"CLEANUP job file failed job={job_id} file={path} error={exc}")


def ytdlp_api_progress_hook(progress_callback: Callable[[int], None] | None) -> Callable[[dict[str, Any]], None]:
    def hook(data: dict[str, Any]) -> None:
        if not progress_callback:
            return
        if data.get("status") == "finished":
            progress_callback(100)
            return
        total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
        downloaded = data.get("downloaded_bytes") or 0
        if total:
            progress_callback(max(0, min(100, int(downloaded * 100 / total))))

    return hook


def choose_downloaded_file(files: list[Path] | list[str], media_format: str) -> Path | str:
    preferred_ext = ".mp3" if media_format == "audio" else ".mp4"
    for path in files:
        suffix = Path(path).suffix.lower()
        if suffix == preferred_ext:
            return path

    expected = "MP3 audio" if media_format == "audio" else "MP4 video"
    raise ValueError(f"Download finished, but no {expected} file was created")


def assert_downloaded_file_has_expected_stream(
    path: Path | str,
    media_format: str,
    retries: int = 1,
    delay: float = 0.5,
) -> None:
    probe_output = ""
    attempts = max(1, retries)
    for attempt in range(attempts):
        probe_output = probe_media_streams(path)
        if media_format == "video" and "Video:" in probe_output:
            return
        if media_format == "audio" and "Audio:" in probe_output:
            return
        if attempt < attempts - 1:
            time.sleep(delay)
    if media_format == "video":
        raise ValueError("Downloaded MP4 has no video stream. The site only returned audio for this URL.")
    if media_format == "audio":
        raise ValueError("Downloaded MP3 has no audio stream.")


def probe_media_streams(path: Path | str) -> str:
    ffmpeg = find_ffmpeg_location()
    if not ffmpeg:
        return ""

    probe_path, cleanup = ffmpeg_safe_input_path(path)
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", probe_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            **hidden_subprocess_kwargs(),
        )
        return f"{result.stdout}\n{result.stderr}"
    finally:
        cleanup()


def ffmpeg_safe_input_path(path: Path | str) -> tuple[str, Callable[[], None]]:
    source = Path(path)
    if os.name != "nt" or is_ascii_path(source):
        return str(source), lambda: None

    safe_parent = first_ascii_parent(source)
    if not safe_parent:
        return str(source), lambda: None

    temp_dir = safe_parent / ".pro_downloader_probe"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"probe-{os.getpid()}-{uuid.uuid4().hex}{source.suffix or '.media'}"
    try:
        os.link(source, temp_path)
    except OSError:
        shutil.copy2(source, temp_path)

    def cleanup() -> None:
        temp_path.unlink(missing_ok=True)
        try:
            temp_dir.rmdir()
        except OSError:
            pass

    return str(temp_path), cleanup


def is_ascii_path(path: Path | str) -> bool:
    try:
        str(path).encode("ascii")
    except UnicodeEncodeError:
        return False
    return True


def first_ascii_parent(path: Path) -> Path | None:
    for parent in (path.parent, *path.parents):
        if is_ascii_path(parent):
            return parent
    return None


def run_command_with_progress(
    command: list[str],
    timeout: int,
    progress_callback: Callable[[int], None] | None = None,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        **hidden_subprocess_kwargs(),
    )
    output_lines: list[str] = []
    try:
        assert process.stdout is not None
        for line in process.stdout:
            output_lines.append(line)
            progress = parse_yt_dlp_progress(line)
            if progress is not None and progress_callback:
                progress_callback(progress)
        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        raise

    output = "".join(output_lines)
    return subprocess.CompletedProcess(command, returncode, output, output)


def parse_yt_dlp_progress(line: str) -> int | None:
    match = re.search(r"(?:\[download\]\s+|download:\s*)(\d+(?:\.\d+)?)%", line)
    if not match:
        return None
    return max(0, min(100, int(float(match.group(1)))))


def is_tiktok_url(url: str) -> bool:
    host = urllib.parse.urlparse(url).netloc.lower()
    return "tiktok.com" in host or "tiktokv.com" in host


def is_douyin_url(url: str) -> bool:
    host = urllib.parse.urlparse(url).netloc.lower()
    return "douyin.com" in host


def fetch_tikwm_info(url: str, timeout: int = 30) -> dict[str, Any]:
    api_url = f"{TIKWM_API}?url={urllib.parse.quote(url, safe='')}&hd=1"
    request = urllib.request.Request(api_url, headers=HTTP_HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return parse_tikwm_response(payload)


def fetch_tikmate_info(url: str, timeout: int = 30) -> dict[str, Any]:
    body = f"url={urllib.parse.quote(url, safe='')}".encode("utf-8")
    request = urllib.request.Request(
        TIKMATE_API,
        data=body,
        headers={**HTTP_HEADERS, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return parse_tikmate_response(payload)


def fetch_tiktok_provider_info(url: str, timeout: int = 30) -> dict[str, Any]:
    merged: dict[str, Any] = {"title": "", "thumbnail": "", "duration": None, "uploader": "", "formats": []}
    for fetcher_name, fetcher in (("TikWM", fetch_tikwm_info), ("TikMate", fetch_tikmate_info)):
        try:
            info = fetcher(url, timeout=timeout)
            for key in ("title", "thumbnail", "duration", "uploader"):
                if not merged.get(key) and info.get(key):
                    merged[key] = info[key]
            for key, value in info.items():
                if key.startswith("tikwm_") or key.startswith("tikmate_"):
                    merged[key] = value
            merged["formats"].extend(info.get("formats") or [])
        except Exception as exc:
            log_event(f"INFO {fetcher_name} error url={url} error={exc}")
    return merged


def fetch_douyin_provider_info(url: str, timeout: int = 30) -> dict[str, Any]:
    try:
        return fetch_snapdouyin_info(url, timeout=timeout)
    except Exception as exc:
        log_event(f"INFO SnapDouyin error url={url} error={exc}")
        return {"title": "", "thumbnail": "", "duration": None, "uploader": "", "formats": []}


def build_cookie_opener() -> urllib.request.OpenerDirector:
    cookie_jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))


def fetch_snapdouyin_info(
    url: str,
    timeout: int = 30,
    opener: urllib.request.OpenerDirector | None = None,
) -> dict[str, Any]:
    url = normalize_url(url)
    opener = opener or build_cookie_opener()
    token = fetch_snapdouyin_token(timeout=timeout, opener=opener)
    hash_value = snapdouyin_hash(url)
    body = urllib.parse.urlencode({"url": url, "token": token, "hash": hash_value}).encode("utf-8")
    request = urllib.request.Request(
        SNAPDOUYIN_API,
        data=body,
        headers={
            **HTTP_HEADERS,
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": SNAPDOUYIN_HOME.rstrip("/"),
            "Referer": SNAPDOUYIN_HOME,
        },
        method="POST",
    )
    with opener.open(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return parse_snapdouyin_response(payload)


def fetch_snapdouyin_token(timeout: int = 30, opener: urllib.request.OpenerDirector | None = None) -> str:
    opener = opener or build_cookie_opener()
    request = urllib.request.Request(SNAPDOUYIN_HOME, headers=HTTP_HEADERS)
    with opener.open(request, timeout=timeout) as response:
        html = response.read().decode("utf-8", errors="replace")
    match = re.search(r'id=["\']token["\'][^>]*value=["\']([^"\']+)["\']', html)
    if not match:
        raise ValueError("SnapDouyin token was not found")
    return match.group(1)


def snapdouyin_hash(url: str) -> str:
    def b64(value: str) -> str:
        return base64.b64encode(value.encode("utf-8")).decode("ascii")

    return f"{b64(url)}{len(url) + 1000}{b64('aio-dl')}"


def parse_snapdouyin_response(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("error"):
        raise ValueError(str(payload["error"]))
    medias = payload.get("medias")
    if not isinstance(medias, list) or not medias:
        raise ValueError("SnapDouyin did not return media options")

    formats: list[dict[str, Any]] = []
    media_by_id: dict[str, str] = {}
    for index, media in enumerate(medias):
        if not isinstance(media, dict) or not media.get("url"):
            continue
        extension = str(media.get("extension") or "").lower()
        if extension not in {"mp4", "mp3", "m4a"}:
            continue
        format_id = f"snapdouyin-{index}"
        quality = str(media.get("quality") or "media")
        size = str(media.get("formattedSize") or "").strip()
        media_format = "video" if media.get("videoAvailable") or extension == "mp4" else "audio"
        label = f"SnapDouyin {quality} {extension}"
        if size:
            label += f" ({size})"
        formats.append(
            {
                "id": format_id,
                "label": label,
                "height": 0,
                "provider": "SnapDouyin",
                "extension": extension,
                "media_format": media_format,
            }
        )
        media_by_id[format_id] = str(media["url"])

    if not formats:
        raise ValueError("SnapDouyin did not return downloadable media")
    formats.sort(key=snapdouyin_format_sort_key)

    return {
        "title": payload.get("title", ""),
        "thumbnail": payload.get("thumbnail", ""),
        "duration": parse_duration_value(payload.get("duration")),
        "uploader": payload.get("source", "Douyin"),
        "formats": formats,
        "snapdouyin_media": media_by_id,
        "subtitle_languages": [],
        "supports_metadata": False,
        "supports_thumbnail": bool(payload.get("thumbnail")),
    }


def snapdouyin_format_sort_key(fmt: dict[str, Any]) -> tuple[int, int, int, str]:
    label = str(fmt.get("label") or "").lower()
    media_rank = 0 if fmt.get("media_format") == "video" else 1
    unstable_rank = 1 if "⭐" in label or "star" in label else 0
    watermark_rank = 1 if "watermark" in label else 0
    return (media_rank, unstable_rank, watermark_rank, label)


def parse_duration_value(value: object) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    parts = text.split(":")
    if all(part.isdigit() for part in parts):
        total = 0
        for part in parts:
            total = total * 60 + int(part)
        return total
    return None


def parse_tikwm_response(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("code") != 0:
        raise ValueError(str(payload.get("msg") or "TikWM request failed"))

    data = payload.get("data") or {}
    format_specs = [
        ("tikwm-hdplay", "TikWM HD", data.get("hdplay")),
        ("tikwm-play", "TikWM No WM", data.get("play")),
        ("tikwm-wmplay", "TikWM Watermark", data.get("wmplay")),
    ]
    formats = [
        {"id": format_id, "label": label, "height": 0, "provider": "TikWM"}
        for format_id, label, value in format_specs
        if value
    ]
    if not formats:
        raise ValueError("TikWM did not return a video URL")
    play_url = data.get("play") or data.get("hdplay") or data.get("wmplay")

    author = data.get("author") or {}
    return {
        "title": data.get("title", ""),
        "thumbnail": data.get("cover") or data.get("origin_cover") or "",
        "duration": data.get("duration"),
        "uploader": author.get("unique_id") or author.get("nickname") or "",
        "formats": formats,
        "subtitle_languages": [],
        "supports_metadata": False,
        "supports_thumbnail": bool(data.get("cover") or data.get("origin_cover")),
        "tikwm_hdplay": data.get("hdplay") or "",
        "tikwm_play": play_url,
        "tikwm_wmplay": data.get("wmplay") or "",
        "tikwm_music": data.get("music") or "",
    }


def parse_tikmate_response(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("success"):
        raise ValueError(str(payload.get("message") or "TikMate request failed"))
    token = payload.get("token")
    video_id = payload.get("id")
    if not token or not video_id:
        raise ValueError("TikMate did not return a download token")
    return {
        "title": payload.get("desc", ""),
        "thumbnail": payload.get("cover", ""),
        "duration": payload.get("duration"),
        "uploader": payload.get("author_id") or payload.get("author_name") or "",
        "formats": [{"id": "tikmate", "label": "TikMate MP4", "height": 0, "provider": "TikMate"}],
        "subtitle_languages": [],
        "supports_metadata": False,
        "supports_thumbnail": bool(payload.get("cover")),
        "tikmate_play": f"https://tikmate.app/download/{token}/{video_id}.mp4",
    }


def is_provider_format_id(format_id: str | None) -> bool:
    return bool(
        format_id
        and (
            format_id.startswith("tikwm-")
            or format_id == "tikmate"
            or format_id == "jiji262-local"
            or format_id.startswith("snapdouyin-")
        )
    )


def download_tikwm_video(
    url: str,
    download_dir: Path,
    job_id: str,
    title: str,
    timeout: int = 300,
    progress_callback: Callable[[int], None] | None = None,
    format_id: str | None = None,
) -> Path:
    info = fetch_tikwm_info(url, timeout=min(timeout, 60))
    key_by_format = {
        "tikwm-hdplay": "tikwm_hdplay",
        "tikwm-play": "tikwm_play",
        "tikwm-wmplay": "tikwm_wmplay",
    }
    video_url = info.get(key_by_format.get(format_id or "", "tikwm_play")) or info.get("tikwm_play") or info.get("tikwm_hdplay")
    temp_path = download_dir / f"{job_id}.tikwm.mp4"
    log_event(f"TIKWM download start job={job_id} url={url} video_url={video_url}")
    download_url_to_file(str(video_url), temp_path, timeout=timeout, progress_callback=progress_callback)
    assert_downloaded_file_has_expected_stream(temp_path, "video")

    final_name = sanitize_filename(title or info.get("title", ""), ".mp4")
    final_path = unique_path(download_dir / final_name)
    os.replace(temp_path, final_path)
    log_event(f"TIKWM download done job={job_id} final={final_path}")
    return final_path


def download_tikmate_video(
    url: str,
    download_dir: Path,
    job_id: str,
    title: str,
    timeout: int = 300,
    progress_callback: Callable[[int], None] | None = None,
) -> Path:
    info = fetch_tikmate_info(url, timeout=min(timeout, 60))
    video_url = info["tikmate_play"]
    temp_path = download_dir / f"{job_id}.tikmate.mp4"
    log_event(f"TIKMATE download start job={job_id} url={url} video_url={video_url}")
    download_url_to_file(video_url, temp_path, timeout=timeout, progress_callback=progress_callback)
    assert_downloaded_file_has_expected_stream(temp_path, "video")

    final_name = sanitize_filename(title or info.get("title", ""), ".mp4")
    final_path = unique_path(download_dir / final_name)
    os.replace(temp_path, final_path)
    log_event(f"TIKMATE download done job={job_id} final={final_path}")
    return final_path


def download_snapdouyin_media(
    url: str,
    download_dir: Path,
    job_id: str,
    title: str,
    timeout: int = 300,
    progress_callback: Callable[[int], None] | None = None,
    format_id: str | None = None,
    media_format: str = "video",
    provider_info: dict[str, Any] | None = None,
) -> Path:
    opener = build_cookie_opener()
    info = provider_info or fetch_snapdouyin_info(url, timeout=min(timeout, 60), opener=opener)
    media_map = info.get("snapdouyin_media") or {}
    selected = str(format_id or "")
    compatible = [
        fmt for fmt in info.get("formats", [])
        if fmt.get("media_format") == ("audio" if media_format == "audio" else "video")
    ]
    if not compatible:
        raise ValueError("SnapDouyin did not return a matching download option")

    ordered: list[dict[str, Any]] = []
    for fmt in compatible:
        if fmt.get("id") == selected:
            ordered.append(fmt)
    ordered.extend(fmt for fmt in compatible if fmt.get("id") != selected)

    last_error = ""
    for fmt in ordered:
        option_id = str(fmt.get("id") or "")
        media_url = media_map.get(option_id)
        if not media_url:
            continue
        extension = str(fmt.get("extension") or (".mp3" if media_format == "audio" else ".mp4")).lstrip(".")
        temp_path = download_dir / f"{job_id}.snapdouyin.{extension}"
        try:
            log_event(f"SNAPDOUYIN download start job={job_id} option={option_id} url={url} media_url={media_url}")
            download_url_to_file(
                add_query_param(str(media_url), "bandwidth_saving", "1"),
                temp_path,
                timeout=timeout,
                progress_callback=progress_callback,
                referer=SNAPDOUYIN_HOME,
                opener=opener,
            )
            try:
                assert_downloaded_file_has_expected_stream(temp_path, "audio" if extension in {"mp3", "m4a"} else "video")
            except Exception:
                thumbnail_url = str(info.get("thumbnail") or "")
                if media_format == "video" and thumbnail_url:
                    final_name = sanitize_filename(title or str(info.get("title") or ""), ".mp4")
                    final_path = unique_path(download_dir / final_name)
                    converted = create_still_video_from_audio(temp_path, thumbnail_url, final_path, timeout=timeout)
                    log_event(f"SNAPDOUYIN still-video done job={job_id} option={option_id} final={converted}")
                    if temp_path.exists():
                        temp_path.unlink(missing_ok=True)
                    if progress_callback:
                        progress_callback(100)
                    return converted
                raise
            suffix = temp_path.suffix
            final_name = sanitize_filename(title or str(info.get("title") or ""), suffix)
            final_path = unique_path(download_dir / final_name)
            os.replace(temp_path, final_path)
            log_event(f"SNAPDOUYIN download done job={job_id} option={option_id} final={final_path}")
            return final_path
        except Exception as exc:
            last_error = str(exc)
            log_event(f"SNAPDOUYIN option error job={job_id} option={option_id} error={last_error}")
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

    raise RuntimeError(last_error or "SnapDouyin download failed")


def create_still_video_from_audio(audio_path: Path, thumbnail_url: str, output_path: Path, timeout: int = 300) -> Path:
    ffmpeg = find_ffmpeg_location()
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to turn audio-only media into MP4 video")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    safe_parent = first_ascii_parent(output_path) or output_path.parent
    temp_dir = safe_parent / ".pro_downloader_probe"
    temp_dir.mkdir(parents=True, exist_ok=True)
    cover_path = temp_dir / f"cover-{os.getpid()}-{uuid.uuid4().hex}{thumbnail_suffix(thumbnail_url)}"
    temp_output = temp_dir / f"still-{os.getpid()}-{uuid.uuid4().hex}.mp4"
    request = urllib.request.Request(thumbnail_url, headers={**HTTP_HEADERS, "Referer": SNAPDOUYIN_HOME})
    with urllib.request.urlopen(request, timeout=min(timeout, 60)) as response:
        cover_path.write_bytes(response.read())

    safe_audio_path, cleanup_audio = ffmpeg_safe_input_path(audio_path)
    safe_cover_path, cleanup_cover = ffmpeg_safe_input_path(cover_path)
    command = [
        ffmpeg,
        "-y",
        "-loop",
        "1",
        "-framerate",
        "1",
        "-i",
        safe_cover_path,
        "-i",
        safe_audio_path,
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-tune",
        "stillimage",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-pix_fmt",
        "yuv420p",
        "-shortest",
        "-movflags",
        "+faststart",
        str(temp_output),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            **hidden_subprocess_kwargs(),
        )
        if result.returncode != 0:
            raise RuntimeError(last_error_line(result.stderr or result.stdout))
        os.replace(temp_output, output_path)
        assert_downloaded_file_has_expected_stream(output_path, "video")
        return output_path
    finally:
        cleanup_audio()
        cleanup_cover()
        cover_path.unlink(missing_ok=True)
        temp_output.unlink(missing_ok=True)
        try:
            temp_dir.rmdir()
        except OSError:
            pass


def thumbnail_suffix(url: str) -> str:
    suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return suffix
    return ".jpg"


def add_query_param(url: str, key: str, value: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(item_key, item_value) for item_key, item_value in query if item_key != key]
    query.append((key, value))
    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))


def download_url_to_file(
    url: str,
    path: Path,
    timeout: int = 300,
    progress_callback: Callable[[int], None] | None = None,
    referer: str = "https://www.tiktok.com/",
    opener: urllib.request.OpenerDirector | None = None,
) -> None:
    request = urllib.request.Request(url, headers={**HTTP_HEADERS, "Referer": referer})
    open_url = opener.open if opener else urllib.request.urlopen
    with open_url(request, timeout=timeout) as response, path.open("wb") as output:
        total = int(response.headers.get("Content-Length") or 0)
        downloaded = 0
        while True:
            chunk = response.read(1024 * 256)
            if not chunk:
                break
            output.write(chunk)
            downloaded += len(chunk)
            if total and progress_callback:
                progress_callback(max(0, min(100, int(downloaded * 100 / total))))
        if progress_callback:
            progress_callback(100)


def last_error_line(stderr: str) -> str:
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    return lines[-1] if lines else "yt-dlp failed"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 2
    while True:
        candidate = parent / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def cleanup_temp_files(download_dir: Path, max_age_seconds: int = 3600) -> None:
    if not download_dir.exists():
        return
    now = time.time()
    for probe_dir in download_dir.rglob(".pro_downloader_probe"):
        if not probe_dir.is_dir():
            continue
        for item in probe_dir.iterdir():
            try:
                if item.is_file() and now - item.stat().st_mtime >= max_age_seconds:
                    item.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            probe_dir.rmdir()
        except OSError:
            pass
    for temp_file in download_dir.rglob("*.tmp"):
        try:
            if temp_file.is_file() and now - temp_file.stat().st_mtime >= max_age_seconds:
                temp_file.unlink(missing_ok=True)
        except OSError:
            pass


def load_history(history_file: Path = HISTORY_FILE) -> list[dict[str, Any]]:
    if not history_file.exists():
        return []
    try:
        data = json.loads(history_file.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def save_history(entries: list[dict[str, Any]], history_file: Path = HISTORY_FILE) -> None:
    history_file.parent.mkdir(parents=True, exist_ok=True)
    history_file.write_text(json.dumps(entries[-500:], ensure_ascii=False, indent=2), encoding="utf-8")


def find_history_entry(url: str, media_format: str, history_file: Path = HISTORY_FILE) -> dict[str, Any] | None:
    normalized = normalize_url(url)
    for entry in reversed(load_history(history_file)):
        if entry.get("url") == normalized and entry.get("media_format") == media_format:
            path = Path(str(entry.get("path") or ""))
            if path.exists():
                return entry
    return None


def record_history(
    url: str,
    media_format: str,
    path: Path,
    title: str = "",
    provider: str = "",
    option: str = "",
    history_file: Path = HISTORY_FILE,
) -> None:
    entries = load_history(history_file)
    entries.append(
        {
            "url": normalize_url(url),
            "media_format": media_format,
            "path": str(path),
            "title": title,
            "provider": provider,
            "option": option,
            "downloaded_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    save_history(entries, history_file)


def update_ytdlp(nightly: bool = False, timeout: int = 300) -> str:
    if is_frozen_app():
        raise RuntimeError("The bundled EXE cannot self-update yt-dlp. Rebuild or replace the app with a newer release.")
    command = [sys.executable, "-m", "pip", "install", "-U"]
    if nightly:
        command += ["--pre"]
    command.append("yt-dlp")
    log_event(f"UPDATE yt-dlp command={json.dumps(command)}")
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        **hidden_subprocess_kwargs(),
    )
    output = (result.stdout + "\n" + result.stderr).strip()
    if result.returncode != 0:
        raise RuntimeError(last_error_line(output))
    return output[-1000:]
