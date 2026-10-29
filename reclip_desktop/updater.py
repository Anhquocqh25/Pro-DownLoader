from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path
from typing import Any, Callable

from .core import APP_NAME, APP_VERSION, GITHUB_REPO, is_frozen_app, log_event

logger = logging.getLogger("pro_downloader.updater")


def get_git_executable() -> str:
    """Finds git executable path."""
    mingit = Path(r"C:\Users\TC6\AppData\Local\MinGit\cmd\git.exe")
    if mingit.exists():
        return str(mingit)
    # Check PATH
    import shutil
    git_in_path = shutil.which("git")
    if git_in_path:
        return git_in_path
    return "git"


def is_git_repository() -> bool:
    """Checks if running inside a git repository."""
    root_dir = Path(__file__).resolve().parents[1]
    return (root_dir / ".git").is_dir()


def get_local_git_commit() -> str:
    """Gets the current short commit SHA."""
    try:
        git_exe = get_git_executable()
        root_dir = Path(__file__).resolve().parents[1]
        res = subprocess.run(
            [git_exe, "rev-parse", "--short", "HEAD"],
            cwd=str(root_dir),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return ""


def check_for_updates() -> dict[str, Any]:
    """
    Checks GitHub for the latest release or commits.
    Returns update information dictionary.
    """
    info: dict[str, Any] = {
        "update_available": False,
        "current_version": APP_VERSION,
        "latest_version": APP_VERSION,
        "release_title": "",
        "changelog": "",
        "download_url": None,
        "is_git": is_git_repository(),
        "commit_hash": "",
    }

    headers = {
        "User-Agent": "Pro-Downloader-App",
        "Accept": "application/vnd.github.v3+json",
    }

    # 1. Check GitHub Latest Release
    releases_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    release_found = False
    try:
        req = urllib.request.Request(releases_url, headers=headers)
        with urllib.request.urlopen(req, timeout=7) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            tag = str(data.get("tag_name", "")).lstrip("v")
            if tag:
                info["latest_version"] = tag
                info["release_title"] = data.get("name") or f"Phiên bản {tag}"
                info["changelog"] = data.get("body") or "Bản cập nhật tối ưu hóa hiệu năng và sửa lỗi."
                for asset in data.get("assets", []):
                    name = asset.get("name", "").lower()
                    if name.endswith(".exe") or name.endswith(".zip"):
                        info["download_url"] = asset.get("browser_download_url")
                        break

                # Compare version numbers (e.g. 1.2.1 > 1.2.0)
                if _is_version_newer(tag, APP_VERSION):
                    info["update_available"] = True
                    release_found = True
    except Exception as exc:
        logger.debug("Failed to fetch GitHub release: %s", exc)

    # 2. Check Git Commits on main if running in git repo and no newer release tag
    if info["is_git"] and not release_found:
        try:
            commits_url = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"
            req = urllib.request.Request(commits_url, headers=headers)
            with urllib.request.urlopen(req, timeout=7) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                remote_sha = data.get("sha", "")[:7]
                commit_msg = data.get("commit", {}).get("message", "").strip()
                local_sha = get_local_git_commit()
                info["commit_hash"] = remote_sha

                if remote_sha and local_sha and remote_sha != local_sha:
                    info["update_available"] = True
                    info["latest_version"] = f"commit {remote_sha}"
                    info["release_title"] = f"Bản cập nhật mới ({remote_sha})"
                    info["changelog"] = commit_msg or "Cập nhật mã nguồn mới nhất từ GitHub."
        except Exception as exc:
            logger.debug("Failed to fetch GitHub commits: %s", exc)

    return info


def _is_version_newer(remote: str, local: str) -> bool:
    """Compares semantic versions like '1.2.1' > '1.2.0'."""
    try:
        r_parts = [int(p) for p in remote.split(".") if p.isdigit()]
        l_parts = [int(p) for p in local.split(".") if p.isdigit()]
        return r_parts > l_parts
    except Exception:
        return remote > local


def perform_one_click_update(
    progress_callback: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    """
    Executes the 1-click update.
    Returns (success, message).
    """
    is_git = is_git_repository()

    if is_git:
        if progress_callback:
            progress_callback("Đang kéo mã nguồn mới từ GitHub (git pull)...")
        git_exe = get_git_executable()
        root_dir = Path(__file__).resolve().parents[1]

        try:
            res = subprocess.run(
                [git_exe, "pull", "origin", "main"],
                cwd=str(root_dir),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if res.returncode != 0:
                err_msg = res.stderr.strip() or res.stdout.strip()
                return False, f"Lỗi khi pull mã nguồn: {err_msg}"

            if progress_callback:
                progress_callback("✅ Cập nhật thành công! Đang chuẩn bị khởi động lại...")

            log_event(f"UPDATE git pull success: {res.stdout.strip()[:100]}")
            return True, "Cập nhật mã nguồn thành công."
        except Exception as exc:
            return False, f"Lỗi thực thi cập nhật: {exc}"

    # Standalone executable mode (.exe)
    if is_frozen_app():
        if progress_callback:
            progress_callback("Đang tìm gói cài đặt phiên bản mới...")
        info = check_for_updates()
        download_url = info.get("download_url")
        if not download_url:
            return False, "Không tìm thấy file cập nhật tải về trên GitHub Releases."

        try:
            import tempfile
            temp_dir = Path(tempfile.gettempdir()) / "pro_downloader_update"
            temp_dir.mkdir(parents=True, exist_ok=True)
            target_exe = temp_dir / "Pro-Downloader-Update.exe"

            if progress_callback:
                progress_callback("Đang tải bản cập nhật mới...")

            urllib.request.urlretrieve(download_url, target_exe)

            # Generate batch helper to swap and launch
            current_exe = Path(sys.executable)
            bat_path = temp_dir / "apply_update.bat"
            bat_content = f"""@echo off
timeout /t 2 /nobreak >nul
copy /y "{target_exe}" "{current_exe}"
del "{target_exe}"
start "" "{current_exe}"
del "%~f0"
"""
            bat_path.write_text(bat_content, encoding="utf-8")
            subprocess.Popen(["cmd.exe", "/c", str(bat_path)], shell=True)
            return True, "Đang áp dụng bản cập nhật..."
        except Exception as exc:
            return False, f"Lỗi tải bản cập nhật: {exc}"

    return False, "Chế độ chạy hiện tại không hỗ trợ tự động ghi đè."


def restart_application() -> None:
    """Restarts the running application cleanly."""
    try:
        if is_frozen_app():
            subprocess.Popen([sys.executable])
        else:
            root_dir = Path(__file__).resolve().parents[1]
            bat_launcher = root_dir / "Pro Downloader.bat"
            if bat_launcher.exists():
                subprocess.Popen(["cmd.exe", "/c", str(bat_launcher)], cwd=str(root_dir))
            else:
                subprocess.Popen([sys.executable, "-m", "reclip_desktop"], cwd=str(root_dir))
    except Exception as exc:
        logger.error("Failed to spawn new process: %s", exc)
    finally:
        os._exit(0)
