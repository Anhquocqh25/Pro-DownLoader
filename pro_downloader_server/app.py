from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from reclip_desktop.core import (
    APP_NAME,
    AdvancedOptions,
    ARCHIVE_FILE,
    DATA_DIR,
    download_media,
    fetch_channel_videos,
    fetch_video_info,
    find_history_entry,
    friendly_error,
    is_douyin_url,
    load_history,
    normalize_url,
    record_history,
    validate_url_input,
)
from reclip_desktop.douyin_engine import download_channel_with_jiji262

SERVER_DOWNLOAD_DIR = Path(os.environ.get("PRO_DOWNLOADER_DOWNLOAD_DIR", str(Path.home() / "Downloads" / f"{APP_NAME} Server")))
STATIC_DIR = Path(__file__).resolve().parent / "static"
MEDIA_EXTENSIONS = {".mp4", ".mp3", ".m4a", ".webm", ".mkv", ".mov", ".part", ".ytdl"}


class AdvancedOptionsPayload(BaseModel):
    cookie_browser: str = "Auto"
    proxy: str = ""
    max_quality: str = "Best"
    subtitles: bool = False
    subtitle_languages: str = "all"
    metadata: bool = False
    thumbnail: bool = False
    douyin_engine: str = "Auto"
    impersonate: str = "Off"

    def to_core(self) -> AdvancedOptions:
        return AdvancedOptions(
            cookie_browser=self.cookie_browser,
            proxy=self.proxy,
            max_quality=self.max_quality,
            subtitles=self.subtitles,
            subtitle_languages=self.subtitle_languages,
            metadata=self.metadata,
            thumbnail=self.thumbnail,
            douyin_engine=self.douyin_engine,
            impersonate=self.impersonate,
        )


class FetchRequest(BaseModel):
    url: str = Field(min_length=1)
    options: AdvancedOptionsPayload = Field(default_factory=AdvancedOptionsPayload)


class FetchResponse(BaseModel):
    url: str
    title: str = ""
    thumbnail: str = ""
    uploader: str = ""
    duration: int | None = None
    formats: list[dict[str, Any]] = Field(default_factory=list)
    subtitle_languages: list[str] = Field(default_factory=list)
    supports_metadata: bool = False
    supports_thumbnail: bool = False


class DownloadRequest(BaseModel):
    url: str = Field(min_length=1)
    media_format: Literal["video", "audio"] = "video"
    format_id: str | None = None
    title: str = ""
    provider: str = ""
    option: str = ""
    reuse_history: bool = True
    options: AdvancedOptionsPayload = Field(default_factory=AdvancedOptionsPayload)


class ChannelFetchRequest(BaseModel):
    url: str = Field(min_length=1)
    limit: int = 30
    keyword: str = ""
    options: AdvancedOptionsPayload = Field(default_factory=AdvancedOptionsPayload)


class ChannelVideoItem(BaseModel):
    id: str
    url: str
    title: str
    duration: float | None = None
    uploader: str = ""
    thumbnail: str = ""


class ChannelFetchResponse(BaseModel):
    url: str
    total: int
    items: list[ChannelVideoItem]


class ChannelDownloadRequest(BaseModel):
    url: str = Field(min_length=1)
    limit: int = 0
    options: AdvancedOptionsPayload = Field(default_factory=AdvancedOptionsPayload)


class DownloadCreated(BaseModel):
    job_id: str
    status: str


class JobResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    url: str
    media_format: str
    title: str = ""
    provider: str = ""
    option: str = ""
    error: str = ""
    file_url: str | None = None
    file_name: str = ""
    created_at: str
    updated_at: str


@dataclass
class DownloadJob:
    job_id: str
    url: str
    media_format: str
    title: str = ""
    provider: str = ""
    option: str = ""
    status: str = "queued"
    progress: int = 0
    error: str = ""
    file_path: Path | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, DownloadJob] = {}
        self._lock = threading.Lock()

    def create(self, request: DownloadRequest) -> DownloadJob:
        job = DownloadJob(
            job_id=uuid.uuid4().hex,
            url=normalize_url(request.url),
            media_format=request.media_format,
            title=request.title,
            provider=request.provider,
            option=request.option,
        )
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> DownloadJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[DownloadJob]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)

    def update(self, job_id: str, **changes: object) -> DownloadJob:
        with self._lock:
            job = self._jobs[job_id]
            for key, value in changes.items():
                setattr(job, key, value)
            job.updated_at = datetime.now()
            return job


def cleanup_expired_downloads(download_dir: Path, retention_hours: int) -> int:
    if retention_hours <= 0 or not download_dir.exists():
        return 0
    cutoff = time.time() - (retention_hours * 3600)
    removed = 0
    for path in download_dir.iterdir():
        try:
            if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS and path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def create_app(
    api_key: str | None = None,
    download_dir: Path | None = None,
    run_jobs_inline: bool = False,
    job_store: JobStore | None = None,
) -> FastAPI:
    configured_api_key = api_key if api_key is not None else os.environ.get("PRO_DOWNLOADER_API_KEY", "").strip() or None
    download_root = download_dir or SERVER_DOWNLOAD_DIR
    retention_hours = max(0, int(os.environ.get("PRO_DOWNLOADER_RETENTION_HOURS", "24")))
    store = job_store or JobStore()
    download_root.mkdir(parents=True, exist_ok=True)
    cleanup_expired_downloads(download_root, retention_hours)

    def require_api_key(x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None) -> None:
        if configured_api_key and x_api_key != configured_api_key:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

    router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "app": APP_NAME}

    @router.post("/fetch", response_model=FetchResponse)
    def fetch(request: FetchRequest) -> FetchResponse:
        urls, error = validate_url_input(request.url)
        if error or not urls:
            raise HTTPException(status_code=422, detail=error or "Invalid URL")
        url = normalize_url(urls[0])
        try:
            info = fetch_video_info(url, advanced=request.options.to_core())
        except Exception as exc:
            raise HTTPException(status_code=502, detail=friendly_error(str(exc))) from exc
        return FetchResponse(
            url=url,
            title=str(info.get("title") or ""),
            thumbnail=str(info.get("thumbnail") or ""),
            uploader=str(info.get("uploader") or ""),
            duration=info.get("duration") if isinstance(info.get("duration"), int) else None,
            formats=list(info.get("formats") or []),
            subtitle_languages=list(info.get("subtitle_languages") or []),
            supports_metadata=bool(info.get("supports_metadata")),
            supports_thumbnail=bool(info.get("supports_thumbnail")),
        )

    @router.post("/download", response_model=DownloadCreated)
    def download(request: DownloadRequest) -> DownloadCreated:
        cleanup_expired_downloads(download_root, retention_hours)
        urls, error = validate_url_input(request.url)
        if error or not urls:
            raise HTTPException(status_code=422, detail=error or "Invalid URL")
        request.url = normalize_url(urls[0])
        job = store.create(request)

        if run_jobs_inline:
            run_download_job(store, job.job_id, request, download_root)
        else:
            thread = threading.Thread(target=run_download_job, args=(store, job.job_id, request, download_root), daemon=True)
            thread.start()

        return DownloadCreated(job_id=job.job_id, status=store.get(job.job_id).status if store.get(job.job_id) else job.status)

    @router.post("/channel/fetch", response_model=ChannelFetchResponse)
    def channel_fetch(request: ChannelFetchRequest) -> ChannelFetchResponse:
        urls, error = validate_url_input(request.url)
        if error or not urls:
            raise HTTPException(status_code=422, detail=error or "Invalid URL")
        url = normalize_url(urls[0])
        try:
            items = fetch_channel_videos(
                url,
                limit=request.limit,
                keyword=request.keyword,
                advanced=request.options.to_core(),
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=friendly_error(str(exc))) from exc

        parsed_items = [
            ChannelVideoItem(
                id=str(item.get("id") or ""),
                url=str(item.get("url") or ""),
                title=str(item.get("title") or ""),
                duration=float(item.get("duration")) if isinstance(item.get("duration"), (int, float)) else None,
                uploader=str(item.get("uploader") or ""),
                thumbnail=str(item.get("thumbnail") or ""),
            )
            for item in items
        ]
        return ChannelFetchResponse(url=url, total=len(parsed_items), items=parsed_items)

    @router.post("/channel/download", response_model=DownloadCreated)
    def channel_download(request: ChannelDownloadRequest) -> DownloadCreated:
        cleanup_expired_downloads(download_root, retention_hours)
        urls, error = validate_url_input(request.url)
        if error or not urls:
            raise HTTPException(status_code=422, detail=error or "Invalid URL")
        url = normalize_url(urls[0])
        job_req = DownloadRequest(
            url=url,
            media_format="video",
            title=f"Channel Batch: {url}",
            provider="jiji262" if is_douyin_url(url) else "yt-dlp",
            options=request.options,
        )
        job = store.create(job_req)

        def run_channel_job() -> None:
            store.update(job.job_id, status="running", progress=1)
            try:
                def progress_cb(pct: int, msg: str) -> None:
                    store.update(job.job_id, progress=pct, option=msg)

                if is_douyin_url(url):
                    summary = download_channel_with_jiji262(
                        url=url,
                        download_dir=download_root,
                        advanced=request.options.to_core(),
                        limit=request.limit,
                        progress_callback=progress_cb,
                    )
                    store.update(
                        job.job_id,
                        status="done",
                        progress=100,
                        title=f"Kênh: {summary.get('author', 'Douyin')}",
                        option=f"Xong {summary.get('success', 0)}/{summary.get('total', 0)} video (Bỏ qua: {summary.get('skipped', 0)})",
                    )
                else:
                    store.update(job.job_id, status="error", error="Direct 1-Click channel download currently supports Douyin.")
            except Exception as exc:
                store.update(job.job_id, status="error", error=friendly_error(str(exc)))

        thread = threading.Thread(target=run_channel_job, daemon=True)
        thread.start()
        return DownloadCreated(job_id=job.job_id, status="queued")

    @router.get("/jobs", response_model=list[JobResponse])
    def list_jobs() -> list[JobResponse]:
        return [job_to_response(job) for job in store.list()]

    @router.get("/jobs/{job_id}", response_model=JobResponse)
    def get_job(job_id: str) -> JobResponse:
        job = store.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job_to_response(job)

    @router.get("/files/{job_id}")
    def get_file(job_id: str) -> FileResponse:
        job = store.get(job_id)
        if not job or job.status != "done" or not job.file_path or not job.file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(job.file_path, filename=job.file_path.name)

    @router.get("/history")
    def history() -> list[dict[str, Any]]:
        return load_history()

    app = FastAPI(title="Pro Downloader API", version="1.0.0")
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def pwa_home() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html")

    @app.get("/manifest.webmanifest", include_in_schema=False)
    def pwa_manifest() -> FileResponse:
        return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")

    @app.get("/sw.js", include_in_schema=False)
    def service_worker() -> FileResponse:
        return FileResponse(
            STATIC_DIR / "sw.js",
            media_type="application/javascript",
            headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
        )

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(STATIC_DIR / "icons" / "icon.svg", media_type="image/svg+xml")

    return app


def run_download_job(store: JobStore, job_id: str, request: DownloadRequest, download_dir: Path) -> None:
    store.update(job_id, status="running", progress=1)
    try:
        history_entry = find_history_entry(request.url, request.media_format) if request.reuse_history else None
        if history_entry:
            store.update(
                job_id,
                status="done",
                progress=100,
                file_path=Path(str(history_entry["path"])),
                title=request.title or str(history_entry.get("title") or ""),
                provider=request.provider or str(history_entry.get("provider") or ""),
                option=request.option or str(history_entry.get("option") or ""),
            )
            return

        def progress_callback(value: int) -> None:
            store.update(job_id, progress=max(1, min(99, int(value))))

        path = download_media(
            url=request.url,
            download_dir=download_dir,
            job_id=job_id[:10],
            media_format=request.media_format,
            title=request.title,
            format_id=request.format_id,
            progress_callback=progress_callback,
            cookie_browser=request.options.to_core().yt_dlp_cookie_browser(),
            advanced=request.options.to_core(),
            archive_file=ARCHIVE_FILE,
        )
        record_history(
            request.url,
            request.media_format,
            path,
            title=request.title,
            provider=request.provider,
            option=request.option,
        )
        store.update(job_id, status="done", progress=100, file_path=path)
    except Exception as exc:
        store.update(job_id, status="error", error=friendly_error(str(exc)))


def job_to_response(job: DownloadJob) -> JobResponse:
    file_url = f"/api/files/{job.job_id}" if job.status == "done" and job.file_path else None
    return JobResponse(
        job_id=job.job_id,
        status=job.status,
        progress=job.progress,
        url=job.url,
        media_format=job.media_format,
        title=job.title,
        provider=job.provider,
        option=job.option,
        error=job.error,
        file_url=file_url,
        file_name=job.file_path.name if job.file_path else "",
        created_at=job.created_at.isoformat(timespec="seconds"),
        updated_at=job.updated_at.isoformat(timespec="seconds"),
    )


app = create_app()
