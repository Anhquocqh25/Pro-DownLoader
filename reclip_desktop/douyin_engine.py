from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from .core import APP_DIR, DATA_DIR, AdvancedOptions, assert_downloaded_file_has_expected_stream, log_event, normalize_url


VENDOR_DIR = APP_DIR / "vendors" / "douyin_downloader"
ENGINE_DATA_DIR = DATA_DIR / "douyin-engine"
ENGINE_CONFIG_FILE = ENGINE_DATA_DIR / "config.yml"
MEDIA_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv"}


def engine_cookie_file() -> Path:
    return ENGINE_DATA_DIR / "config" / "cookies.json"


class CallbackProgressReporter:
    def __init__(self, progress_callback: Callable[[int], None] | None = None) -> None:
        self.progress_callback = progress_callback
        self._progress = 5
        self._emit(self._progress)

    def _emit(self, value: int) -> None:
        self._progress = max(self._progress, min(99, value))
        if self.progress_callback:
            self.progress_callback(self._progress)

    def advance_step(self, step: str, detail: str = "") -> None:
        self._emit(self._progress + 8)
        return None

    def update_step(self, step: str, detail: str = "") -> None:
        lowered = f"{step} {detail}".lower()
        if "下载" in lowered or "download" in lowered:
            self._emit(35)
        elif "获取" in lowered or "fetch" in lowered:
            self._emit(20)
        else:
            self._emit(self._progress + 3)
        return None

    def set_item_total(self, total: int, detail: str = "") -> None:
        self._emit(25)
        return None

    def advance_item(self, status: str, detail: str = "") -> None:
        self._emit(90 if status == "success" else self._progress + 5)
        return None

    def on_author(self, nickname: str | None = None, sec_uid: str | None = None) -> None:
        self._emit(15)
        return None


@contextmanager
def vendor_path_context(vendor_dir: Path = VENDOR_DIR) -> Iterator[None]:
    path = str(vendor_dir.resolve())
    inserted = False
    if path not in sys.path:
        sys.path.insert(0, path)
        inserted = True
    try:
        yield
    finally:
        if inserted:
            try:
                sys.path.remove(path)
            except ValueError:
                pass


def ensure_vendor_available() -> None:
    if not (VENDOR_DIR / "cli" / "main.py").exists():
        raise RuntimeError("jiji262 Douyin engine is not installed in vendors/douyin_downloader")


def build_engine_config(url: str, download_dir: Path, advanced: AdvancedOptions | None = None) -> dict[str, Any]:
    advanced = advanced or AdvancedOptions()
    max_quality = advanced.max_quality if advanced.max_quality and advanced.max_quality != "Best" else "highest"
    return {
        "path": str(download_dir),
        "link": [normalize_url(url)],
        "thread": 1,
        "retry_times": 2,
        "rate_limit": 2,
        "proxy": advanced.proxy.strip(),
        "video_quality": max_quality,
        "folderstyle": False,
        "filename_template": "{title}_{id}",
        "folder_template": "{title}_{id}",
        "music": False,
        "cover": bool(advanced.thumbnail),
        "avatar": False,
        "json": bool(advanced.metadata),
        "database": False,
        "auto_cookie": True,
        "transcript": {"enabled": False},
        "comments": {"enabled": False},
    }


def write_engine_config(config: dict[str, Any], path: Path = ENGINE_CONFIG_FILE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def snapshot_media_files(download_dir: Path) -> dict[Path, tuple[float, int]]:
    if not download_dir.exists():
        return {}
    return {
        path: (path.stat().st_mtime, path.stat().st_size)
        for path in download_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES and path.stat().st_size > 0
    }


def find_new_media_file(download_dir: Path, before: dict[Path, tuple[float, int]] | set[Path]) -> Path | None:
    if not download_dir.exists():
        return None
    before_paths = set(before.keys()) if isinstance(before, dict) else set(before)
    candidates: list[Path] = []
    for path in download_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in MEDIA_SUFFIXES:
            continue
        stat = path.stat()
        if stat.st_size <= 0:
            continue
        if path not in before_paths:
            candidates.append(path)
            continue
        if isinstance(before, dict) and before.get(path) != (stat.st_mtime, stat.st_size):
            candidates.append(path)
    candidates.sort(key=lambda item: (item.suffix.lower() != ".mp4", -item.stat().st_mtime))
    return candidates[0] if candidates else None


def douyin_aweme_id(url: str) -> str:
    normalized = normalize_url(url)
    return normalized.rstrip("/").split("/")[-1] if "/video/" in normalized else ""


def find_existing_media_for_url(download_dir: Path, url: str) -> Path | None:
    aweme_id = douyin_aweme_id(url)
    if not aweme_id or not download_dir.exists():
        return None
    candidates = [
        path
        for path in download_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower() in MEDIA_SUFFIXES
        and aweme_id in path.name
        and path.stat().st_size > 0
    ]
    candidates.sort(key=lambda item: (item.suffix.lower() != ".mp4", -item.stat().st_mtime))
    return candidates[0] if candidates else None


def download_with_jiji262(
    url: str,
    download_dir: Path,
    advanced: AdvancedOptions | None = None,
    progress_callback: Callable[[int], None] | None = None,
) -> Path:
    ensure_vendor_available()
    download_dir.mkdir(parents=True, exist_ok=True)
    before = snapshot_media_files(download_dir)
    config = build_engine_config(url, download_dir, advanced)
    config_path = write_engine_config(config)
    log_event(f"JIJI262 start url={url} config={config_path}")

    with vendor_path_context():
        from auth import CookieManager  # type: ignore
        from cli.main import download_url  # type: ignore
        from config import ConfigLoader  # type: ignore

        async def run() -> Any:
            loader = ConfigLoader(str(config_path))
            cookie_file = str(engine_cookie_file())
            cookie_manager = CookieManager(cookie_file=cookie_file)
            initial_cookies = loader.get_cookies()
            if initial_cookies:
                cookie_manager.set_cookies(initial_cookies)
            else:
                cookie_manager.get_cookies()
            return await download_url(
                normalize_url(url),
                loader,
                cookie_manager,
                database=None,
                progress_reporter=CallbackProgressReporter(progress_callback),
            )

        result = asyncio.run(run())

    if not result or getattr(result, "success", 0) < 1:
        raise RuntimeError("jiji262 engine did not download a video. Set up Douyin cookies, then retry.")

    new_file = find_new_media_file(download_dir, before)
    if not new_file:
        # jiji262 may skip/rewrite a same-name file or finish just after the manifest
        # is updated. Give the filesystem a moment, then accept a matching aweme file.
        for _ in range(5):
            new_file = find_new_media_file(download_dir, before) or find_existing_media_for_url(download_dir, url)
            if new_file:
                break
            time.sleep(0.5)
    if not new_file:
        raise RuntimeError("jiji262 engine finished but no matching video file was found")
    assert_downloaded_file_has_expected_stream(new_file, "video", retries=8, delay=1.0)
    log_event(f"JIJI262 done url={url} file={new_file}")
    if progress_callback:
        progress_callback(100)
    return new_file


def setup_cookie_command() -> list[str]:
    ensure_vendor_available()
    config = build_engine_config("https://www.douyin.com/", ENGINE_DATA_DIR / "downloads", AdvancedOptions())
    config["link"] = []
    config["auto_cookie"] = True
    config_path = write_engine_config(config)
    python_exe = Path(sys.executable)
    if python_exe.name.lower() == "pythonw.exe":
        candidate = python_exe.with_name("python.exe")
        if candidate.exists():
            python_exe = candidate
    return [
        str(python_exe),
        "-m",
        "tools.cookie_fetcher",
        "--config",
        str(config_path),
        "--output",
        str(engine_cookie_file()),
    ]


def run_setup_cookies() -> None:
    ensure_vendor_available()
    command = setup_cookie_command()
    log_event(f"JIJI262 cookie setup command={command}")
    import subprocess

    if os.name == "nt":
        bat_path = write_setup_cookie_bat(command)
        subprocess.Popen(["cmd.exe", "/k", str(bat_path)], cwd=str(VENDOR_DIR))
    else:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(VENDOR_DIR.resolve()) + os.pathsep + env.get("PYTHONPATH", "")
        subprocess.Popen(command, cwd=str(VENDOR_DIR), env=env)


def write_setup_cookie_bat(command: list[str]) -> Path:
    python_exe = command[0]
    args = " ".join(quote_bat_arg(part) for part in command[1:])
    bat_path = ENGINE_DATA_DIR / "setup_cookies.bat"
    bat_path.parent.mkdir(parents=True, exist_ok=True)
    content = "\r\n".join(
        [
            "@echo off",
            "setlocal",
            "chcp 65001 >nul",
            f'cd /d "{VENDOR_DIR}"',
            f'set "PYTHONPATH={VENDOR_DIR};%PYTHONPATH%"',
            f'call "{python_exe}" -m playwright install chromium',
            "if errorlevel 1 goto error",
            f'call "{python_exe}" {args}',
            "if errorlevel 1 goto error",
            "echo.",
            "echo Douyin cookies saved. You can close this window.",
            "pause",
            "exit /b 0",
            ":error",
            "echo.",
            "echo Douyin cookie setup failed. Copy this window text and send it to Codex.",
            "pause",
            "exit /b 1",
        ]
    )
    bat_path.write_text(content, encoding="utf-8")
    return bat_path


def quote_bat_arg(value: str) -> str:
    escaped = value.replace('"', '\\"')
    return f'"{escaped}"'
