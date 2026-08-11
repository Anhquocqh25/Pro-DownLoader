from __future__ import annotations

import ctypes
import os
import queue
import re
import sys
import threading
import time
import uuid
import webbrowser
from pathlib import Path
from tkinter import BooleanVar, END, StringVar, Text, Tk, filedialog, messagebox
from tkinter import ttk

from .core import (
    ARCHIVE_FILE,
    APP_NAME,
    AdvancedOptions,
    cleanup_temp_files,
    download_media,
    fetch_channel_videos,
    fetch_video_info,
    find_history_entry,
    find_ffmpeg_location,
    friendly_error,
    is_channel_or_playlist_url,
    is_douyin_url,
    is_frozen_app,
    load_history,
    log_event,
    normalize_url,
    record_history,
    update_ytdlp,
    validate_url_input,
    yt_dlp_command,
)



class ProDownloaderApp:
    def __init__(self, root: Tk, lock_handle: object | None = None) -> None:
        self.root = root
        self.root.title(APP_NAME)
        self._set_window_icon()
        self.root.geometry("1280x740")
        self.root.minsize(1040, 600)

        self.media_format = StringVar(value="video")
        self.quality = StringVar(value="Best")
        self.status = StringVar(value="Ready")
        self.details = StringVar(value="Select a row to see full status, URL, and saved file.")
        self.cookie_browser = StringVar(value="Auto")
        self.proxy = StringVar(value="")
        self.max_quality = StringVar(value="Best")
        self.douyin_engine = StringVar(value="Auto")
        self.subtitle_languages = StringVar(value="all")
        self.impersonate = StringVar(value="Off")
        self.subtitles = BooleanVar(value=False)
        self.metadata = BooleanVar(value=False)
        self.thumbnail = BooleanVar(value=False)
        self.channel_url_var = StringVar(value="")
        self.channel_limit_var = StringVar(value="30")
        self.channel_keyword_var = StringVar(value="")
        self.channel_items: list[dict[str, object]] = []
        self.download_dir = Path.home() / "Downloads" / APP_NAME

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.items: dict[str, dict[str, object]] = {}
        self.fetch_in_progress = False
        self.auto_fetch_after_id: str | None = None
        self.lock_handle = lock_handle

        self._build_ui()
        self._check_tools()
        cleanup_temp_files(self.download_dir, max_age_seconds=0)
        log_event("APP start")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._poll_events()

    def _set_window_icon(self) -> None:
        base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
        icon_path = base_dir / "assets" / "pro-downloader.ico"
        if icon_path.exists():
            try:
                self.root.iconbitmap(default=str(icon_path))
            except Exception:
                pass

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)

        title = ttk.Label(outer, text=APP_NAME, font=("Segoe UI", 22, "bold"))
        title.grid(row=0, column=0, sticky="w")

        subtitle = ttk.Label(outer, text="Paste URLs, fetch exact metadata/options, then download MP4 or MP3.")
        subtitle.grid(row=1, column=0, sticky="w", pady=(2, 14))

        url_frame = ttk.Frame(outer)
        url_frame.grid(row=2, column=0, sticky="ew")
        url_frame.columnconfigure(0, weight=1)
        self.url_text = Text(url_frame, height=4, wrap="word", font=("Consolas", 10))
        self.url_text.grid(row=0, column=0, sticky="ew")
        ttk.Button(url_frame, text="Paste", command=self.paste_and_fetch).grid(row=0, column=1, sticky="ns", padx=(8, 0))
        self.url_text.bind("<<Paste>>", self.on_url_paste)

        table_frame = ttk.Frame(outer)
        table_frame.grid(row=3, column=0, sticky="nsew", pady=14)
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        columns = ("title", "uploader", "duration", "provider", "quality", "progress", "status", "file")
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="extended")
        self.table.heading("title", text="Title")
        self.table.heading("uploader", text="Uploader")
        self.table.heading("duration", text="Duration")
        self.table.heading("provider", text="Provider")
        self.table.heading("quality", text="Option")
        self.table.heading("progress", text="Progress")
        self.table.heading("status", text="Status")
        self.table.heading("file", text="File")
        self.table.column("title", width=330)
        self.table.column("uploader", width=130)
        self.table.column("duration", width=80, anchor="center")
        self.table.column("provider", width=90, anchor="center")
        self.table.column("quality", width=130, anchor="center")
        self.table.column("progress", width=80, anchor="center")
        self.table.column("status", width=100, anchor="center")
        self.table.column("file", width=250)
        self.table.grid(row=0, column=0, sticky="nsew")

        scroll_y = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scroll_y.set)
        scroll_y.grid(row=0, column=1, sticky="ns")

        details_label = ttk.Label(outer, textvariable=self.details, wraplength=1200, justify="left")
        details_label.grid(row=4, column=0, sticky="ew", pady=(0, 10))

        controls = ttk.Frame(outer)
        controls.grid(row=5, column=0, sticky="ew")
        controls.columnconfigure(9, weight=1)

        ttk.Radiobutton(controls, text="MP4", variable=self.media_format, value="video").grid(row=0, column=0)
        ttk.Radiobutton(controls, text="MP3", variable=self.media_format, value="audio").grid(row=0, column=1, padx=(4, 14))

        ttk.Button(controls, text="Fetch", command=self.fetch_all).grid(row=0, column=2, padx=4)
        ttk.Button(controls, text="Download Selected", command=self.download_selected).grid(row=0, column=3, padx=4)
        ttk.Button(controls, text="Download All", command=self.download_all).grid(row=0, column=4, padx=4)
        ttk.Button(controls, text="Choose Folder", command=self.choose_folder).grid(row=0, column=5, padx=4)
        ttk.Button(controls, text="Open Folder", command=self.open_folder).grid(row=0, column=6, padx=4)
        ttk.Button(controls, text="Open Video", command=self.open_selected_file).grid(row=0, column=7, padx=4)

        self.quality_box = ttk.Combobox(controls, textvariable=self.quality, width=24, state="readonly", values=["Best"])
        self.quality_box.grid(row=0, column=8, padx=(14, 4))
        ttk.Button(controls, text="Set Option", command=self.set_quality).grid(row=0, column=9, padx=4)

        tabs = ttk.Notebook(outer)
        tabs.grid(row=6, column=0, sticky="ew", pady=(10, 0))
        advanced_tab = ttk.Frame(tabs, padding=8)
        channel_tab = ttk.Frame(tabs, padding=8)
        history_tab = ttk.Frame(tabs, padding=8)
        tabs.add(advanced_tab, text="Advanced Options")
        tabs.add(channel_tab, text="Channel / Batch Extractor")
        tabs.add(history_tab, text="History")
        self._build_advanced_tab(advanced_tab)
        self._build_channel_tab(channel_tab)
        self._build_history_tab(history_tab)


        ttk.Label(outer, textvariable=self.status).grid(row=7, column=0, sticky="w", pady=(10, 0))
        self.table.bind("<<TreeviewSelect>>", self.on_selection_changed)

    def _build_advanced_tab(self, frame: ttk.Frame) -> None:
        frame.columnconfigure(9, weight=1)
        ttk.Label(frame, text="Cookies").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            frame,
            textvariable=self.cookie_browser,
            width=10,
            state="readonly",
            values=["Auto", "None", "Chrome", "Edge", "Firefox", "Brave"],
        ).grid(row=0, column=1, padx=(4, 14), sticky="w")

        ttk.Label(frame, text="Proxy").grid(row=0, column=2, sticky="w")
        ttk.Entry(frame, textvariable=self.proxy, width=28).grid(row=0, column=3, padx=(4, 14), sticky="w")

        ttk.Label(frame, text="Max quality").grid(row=0, column=4, sticky="w")
        self.max_quality_box = ttk.Combobox(
            frame,
            textvariable=self.max_quality,
            width=10,
            state="readonly",
            values=["Best", "2160p", "1440p", "1080p", "720p", "480p", "360p"],
        )
        self.max_quality_box.grid(row=0, column=5, padx=(4, 14), sticky="w")

        self.subtitles_check = ttk.Checkbutton(frame, text="Subtitles", variable=self.subtitles)
        self.subtitles_check.grid(row=0, column=6, padx=4, sticky="w")
        ttk.Label(frame, text="Sub lang").grid(row=0, column=7, sticky="w")
        self.subtitle_languages_box = ttk.Combobox(
            frame,
            textvariable=self.subtitle_languages,
            width=10,
            state="disabled",
            values=["all"],
        )
        self.subtitle_languages_box.grid(row=0, column=8, padx=(4, 14), sticky="w")

        ttk.Label(frame, text="Douyin engine").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(
            frame,
            textvariable=self.douyin_engine,
            width=14,
            state="readonly",
            values=["Auto", "jiji262 local", "SnapDouyin", "yt-dlp"],
        ).grid(row=1, column=1, padx=(4, 14), sticky="w", pady=(8, 0))
        ttk.Button(frame, text="Setup Douyin Cookies", command=self.setup_douyin_cookies).grid(row=1, column=2, padx=4, sticky="w", pady=(8, 0))
        ttk.Label(frame, text="Impersonate").grid(row=1, column=3, sticky="w", padx=(14, 0), pady=(8, 0))
        self.impersonate_box = ttk.Combobox(
            frame,
            textvariable=self.impersonate,
            width=10,
            state="readonly",
            values=["Off", "Chrome", "Edge", "Safari", "Firefox"],
        )
        self.impersonate_box.grid(row=1, column=4, padx=(4, 14), sticky="w", pady=(8, 0))
        self.metadata_check = ttk.Checkbutton(frame, text="Metadata", variable=self.metadata)
        self.metadata_check.grid(row=1, column=5, padx=4, sticky="w", pady=(8, 0))
        self.thumbnail_check = ttk.Checkbutton(frame, text="Thumbnail", variable=self.thumbnail)
        self.thumbnail_check.grid(row=1, column=6, padx=4, sticky="w", pady=(8, 0))
        self.update_ytdlp_button = ttk.Button(frame, text="Update yt-dlp", command=lambda: self.update_ytdlp_ui(False))
        self.update_ytdlp_button.grid(row=1, column=7, padx=(14, 4), pady=(8, 0))
        self.update_nightly_button = ttk.Button(frame, text="Update nightly", command=lambda: self.update_ytdlp_ui(True))
        self.update_nightly_button.grid(row=1, column=8, padx=4, pady=(8, 0))
        if is_frozen_app():
            self.update_ytdlp_button.configure(state="disabled")
            self.update_nightly_button.configure(state="disabled")
        self.update_advanced_control_states()

    def _build_channel_tab(self, frame: ttk.Frame) -> None:
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        top_frame = ttk.Frame(frame)
        top_frame.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        top_frame.columnconfigure(1, weight=1)

        ttk.Label(top_frame, text="Channel/Playlist URL:").grid(row=0, column=0, sticky="w")
        self.channel_url_entry = ttk.Entry(top_frame, textvariable=self.channel_url_var)
        self.channel_url_entry.grid(row=0, column=1, sticky="ew", padx=(4, 10))

        ttk.Label(top_frame, text="Limit:").grid(row=0, column=2, sticky="w")
        self.channel_limit_box = ttk.Combobox(
            top_frame,
            textvariable=self.channel_limit_var,
            width=6,
            state="readonly",
            values=["10", "20", "30", "50", "100", "All"],
        )
        self.channel_limit_box.grid(row=0, column=3, padx=(4, 10), sticky="w")

        ttk.Label(top_frame, text="Filter:").grid(row=0, column=4, sticky="w")
        self.channel_keyword_entry = ttk.Entry(top_frame, textvariable=self.channel_keyword_var, width=15)
        self.channel_keyword_entry.grid(row=0, column=5, padx=(4, 10), sticky="w")

        ttk.Button(top_frame, text="Fetch Channel Videos", command=self.fetch_channel_videos_ui).grid(
            row=0, column=6, sticky="e"
        )

        table_frame = ttk.Frame(frame)
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        columns = ("select", "title", "uploader", "duration", "url")
        self.channel_table = ttk.Treeview(table_frame, columns=columns, show="headings", height=5)
        self.channel_table.heading("select", text="[x]")
        self.channel_table.heading("title", text="Title")
        self.channel_table.heading("uploader", text="Uploader")
        self.channel_table.heading("duration", text="Duration")
        self.channel_table.heading("url", text="URL")
        self.channel_table.column("select", width=50, anchor="center")
        self.channel_table.column("title", width=380)
        self.channel_table.column("uploader", width=140)
        self.channel_table.column("duration", width=90, anchor="center")
        self.channel_table.column("url", width=320)
        self.channel_table.grid(row=0, column=0, sticky="nsew")

        scroll_y = ttk.Scrollbar(table_frame, orient="vertical", command=self.channel_table.yview)
        self.channel_table.configure(yscrollcommand=scroll_y.set)
        scroll_y.grid(row=0, column=1, sticky="ns")

        self.channel_table.bind("<Button-1>", self.on_channel_table_click)

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(btn_frame, text="Select All", command=self.channel_select_all).grid(row=0, column=0, sticky="w", padx=(0, 4))
        ttk.Button(btn_frame, text="Deselect All", command=self.channel_deselect_all).grid(row=0, column=1, sticky="w", padx=4)
        ttk.Button(btn_frame, text="Add Selected to Download Queue", command=self.add_channel_selected_to_queue).grid(
            row=0, column=2, sticky="e", padx=(10, 0)
        )

    def fetch_channel_videos_ui(self) -> None:
        url = self.channel_url_var.get().strip()
        if not url:
            messagebox.showinfo("Channel URL Required", "Please enter a YouTube channel/playlist or Douyin user URL.")
            return

        limit_str = self.channel_limit_var.get().strip().lower()
        limit = 0 if limit_str == "all" else (int(limit_str) if limit_str.isdigit() else 30)
        keyword = self.channel_keyword_var.get().strip()

        self.status.set("Fetching channel videos...")
        self.details.set(f"Scanning channel '{url}' for videos...")
        threading.Thread(
            target=self._channel_fetch_worker, args=(url, limit, keyword, self.advanced_options()), daemon=True
        ).start()

    def _channel_fetch_worker(self, url: str, limit: int, keyword: str, advanced: AdvancedOptions) -> None:
        try:
            items = fetch_channel_videos(url, limit=limit, keyword=keyword, advanced=advanced)
            self.events.put(("channel_fetch_done", items))
        except Exception as exc:
            log_event(f"UI channel fetch error url={url} error={exc}")
            self.events.put(("channel_fetch_error", friendly_error(str(exc))))

    def _populate_channel_table(self, items: list[dict[str, Any]]) -> None:
        self.channel_table.delete(*self.channel_table.get_children())
        for idx, item in enumerate(items):
            dur = format_duration(item.get("duration")) if isinstance(item.get("duration"), (int, float)) else str(item.get("duration") or "--:--")
            self.channel_table.insert(
                "",
                "end",
                iid=f"channel-item-{idx}",
                values=(
                    "[x]",
                    item.get("title", ""),
                    item.get("uploader", ""),
                    dur,
                    item.get("url", ""),
                ),
            )

    def on_channel_table_click(self, event: object) -> None:
        region = self.channel_table.identify("region", event.x, event.y)
        if region == "cell":
            column = self.channel_table.identify_column(event.x)
            if column == "#1":
                item_id = self.channel_table.identify_row(event.y)
                if item_id:
                    vals = list(self.channel_table.item(item_id, "values"))
                    vals[0] = "[ ]" if vals[0] == "[x]" else "[x]"
                    self.channel_table.item(item_id, values=vals)

    def channel_select_all(self) -> None:
        for item_id in self.channel_table.get_children():
            vals = list(self.channel_table.item(item_id, "values"))
            vals[0] = "[x]"
            self.channel_table.item(item_id, values=vals)

    def channel_deselect_all(self) -> None:
        for item_id in self.channel_table.get_children():
            vals = list(self.channel_table.item(item_id, "values"))
            vals[0] = "[ ]"
            self.channel_table.item(item_id, values=vals)

    def add_channel_selected_to_queue(self) -> None:
        selected_urls = []
        for item_id in self.channel_table.get_children():
            vals = self.channel_table.item(item_id, "values")
            if vals and vals[0] == "[x]" and len(vals) >= 5:
                selected_urls.append(vals[4])

        if not selected_urls:
            messagebox.showinfo("No Videos Selected", "Please check at least one video in the table.")
            return

        current_text = self.url_text.get("1.0", END).strip()
        new_text = "\n".join(selected_urls)
        if current_text:
            combined = current_text + "\n" + new_text
        else:
            combined = new_text

        self.url_text.delete("1.0", END)
        self.url_text.insert("1.0", combined)
        self.fetch_all()
        messagebox.showinfo("Added to Queue", f"Added {len(selected_urls)} video(s) to the download queue!")

    def _build_history_tab(self, frame: ttk.Frame) -> None:

        frame.columnconfigure(0, weight=1)
        self.history_table = ttk.Treeview(frame, columns=("title", "format", "provider", "date", "file"), show="headings", height=5)
        self.history_table.heading("title", text="Title")
        self.history_table.heading("format", text="Format")
        self.history_table.heading("provider", text="Provider")
        self.history_table.heading("date", text="Downloaded")
        self.history_table.heading("file", text="File")
        self.history_table.column("title", width=300)
        self.history_table.column("format", width=70, anchor="center")
        self.history_table.column("provider", width=100, anchor="center")
        self.history_table.column("date", width=140, anchor="center")
        self.history_table.column("file", width=420)
        self.history_table.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Button(frame, text="Refresh History", command=self.refresh_history).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Button(frame, text="Open History File", command=self.open_history_file).grid(row=1, column=1, sticky="e", pady=(6, 0))
        self.refresh_history()

    def _check_tools(self) -> None:
        missing = []
        if yt_dlp_command() == ["yt-dlp"]:
            missing.append("yt-dlp")
        if not find_ffmpeg_location():
            missing.append("ffmpeg")
        if missing:
            self.status.set("Missing tools: " + ", ".join(missing))
            messagebox.showwarning(
                "Missing tools",
                f"Double-click {APP_NAME}.bat so it can install bundled dependencies, then restart the app.",
            )

    def advanced_options(self) -> AdvancedOptions:
        return AdvancedOptions(
            cookie_browser=self.cookie_browser.get(),
            proxy=self.proxy.get().strip(),
            max_quality=self.max_quality.get(),
            subtitles=bool(self.subtitles.get()),
            subtitle_languages=self.subtitle_languages.get(),
            metadata=bool(self.metadata.get()),
            thumbnail=bool(self.thumbnail.get()),
            douyin_engine=self.douyin_engine.get(),
            impersonate=self.impersonate.get(),
        )

    def fetch_all(self) -> None:
        urls, error = validate_url_input(self.url_text.get("1.0", END))
        if error:
            self.status.set(error)
            self.details.set(error)
            messagebox.showinfo("Check URL", error)
            return
        if self.fetch_in_progress:
            self.status.set("Fetch is already running...")
            return

        self.fetch_in_progress = True
        self.table.delete(*self.table.get_children())
        self.items.clear()
        self.details.set("Fetching metadata and provider options...")
        self.status.set(f"Fetching {len(urls)} URL(s)...")
        threading.Thread(target=self._fetch_worker, args=(urls, self.advanced_options()), daemon=True).start()

    def paste_and_fetch(self) -> None:
        try:
            clipboard_text = self.root.clipboard_get()
        except Exception:
            messagebox.showinfo("Clipboard", "Clipboard does not contain text.")
            return

        self.url_text.delete("1.0", END)
        self.url_text.insert("1.0", clipboard_text.strip())
        self.schedule_auto_fetch()

    def on_url_paste(self, _event: object) -> None:
        self.root.after(50, self.schedule_auto_fetch)

    def schedule_auto_fetch(self) -> None:
        if self.auto_fetch_after_id:
            self.root.after_cancel(self.auto_fetch_after_id)
        self.auto_fetch_after_id = self.root.after(250, self.auto_fetch_current_input)

    def auto_fetch_current_input(self) -> None:
        self.auto_fetch_after_id = None
        urls, error = validate_url_input(self.url_text.get("1.0", END))
        if error:
            self.status.set(error)
            self.details.set(error)
            messagebox.showinfo("Check URL", error)
            return
        if urls:
            self.fetch_all()

    def _fetch_worker(self, urls: list[str], advanced: AdvancedOptions) -> None:
        for url in urls:
            item_id = uuid.uuid4().hex[:10]
            self.events.put(("insert", {"id": item_id, "url": url}))
            try:
                info = fetch_video_info(url, advanced=advanced)
                self.events.put(("info", {"id": item_id, "info": info}))
            except Exception as exc:
                log_event(f"UI fetch error url={url} error={exc}")
                retry_info = self._retry_douyin_after_browser_refresh(item_id, url, str(exc), advanced)
                if retry_info:
                    self.events.put(("info", {"id": item_id, "info": retry_info}))
                else:
                    self.events.put(("error", {"id": item_id, "error": friendly_error(str(exc))}))
        self.events.put(("status", "Ready"))
        self.events.put(("fetch_done", None))

    def _retry_douyin_after_browser_refresh(
        self,
        item_id: str,
        url: str,
        error: str,
        advanced: AdvancedOptions,
    ) -> dict[str, object] | None:
        normalized_url = normalize_url(url)
        if not is_douyin_url(normalized_url) or not should_refresh_douyin_cookie(error):
            return None

        detail = "Douyin needs fresh browser cookies. Opening the video in your browser and retrying automatically..."
        self.events.put(("row_status", {"id": item_id, "status": "Cookie refresh", "detail": detail}))
        log_event(f"DOUYIN auto browser refresh url={normalized_url}")
        webbrowser.open(normalized_url)

        last_error = error
        for attempt in range(1, 4):
            time.sleep(10)
            self.events.put(
                (
                    "row_status",
                    {
                        "id": item_id,
                        "status": f"Retry {attempt}/3",
                        "detail": "Waiting for browser cookies, then retrying Douyin fetch automatically.",
                    },
                )
            )
            try:
                return fetch_video_info(normalized_url, advanced=advanced)
            except Exception as exc:
                last_error = str(exc)
                log_event(f"DOUYIN auto retry failed attempt={attempt} error={last_error}")

        self.events.put(
            (
                "row_status",
                {
                    "id": item_id,
                    "status": "Cookie needed",
                    "detail": (
                        "Auto retry could not read fresh Douyin cookies. Keep the Douyin video opened, pass any check, "
                        "then close Chrome/Edge and press Fetch again."
                    ),
                },
            )
        )
        log_event(f"DOUYIN auto refresh failed final_error={last_error}")
        return None

    def refresh_history(self) -> None:
        if not hasattr(self, "history_table"):
            return
        self.history_table.delete(*self.history_table.get_children())
        for index, entry in enumerate(reversed(load_history()[-100:])):
            self.history_table.insert(
                "",
                "end",
                iid=f"history-{index}",
                values=(
                    entry.get("title", ""),
                    entry.get("media_format", ""),
                    entry.get("provider", ""),
                    entry.get("downloaded_at", ""),
                    Path(str(entry.get("path", ""))).name,
                ),
            )

    def open_history_file(self) -> None:
        for entry in reversed(load_history()):
            path = Path(str(entry.get("path") or ""))
            if path.exists():
                os.startfile(str(path))
                return
        messagebox.showinfo("History", "No downloaded history file exists yet.")

    def update_ytdlp_ui(self, nightly: bool) -> None:
        label = "nightly" if nightly else "stable"
        self.status.set(f"Updating yt-dlp {label}...")
        threading.Thread(target=self._update_ytdlp_worker, args=(nightly,), daemon=True).start()

    def _update_ytdlp_worker(self, nightly: bool) -> None:
        try:
            output = update_ytdlp(nightly=nightly)
            self.events.put(("status", "yt-dlp updated."))
            self.events.put(("detail", output or "yt-dlp updated."))
        except Exception as exc:
            self.events.put(("status", "yt-dlp update failed."))
            self.events.put(("detail", friendly_error(str(exc))))

    def setup_douyin_cookies(self) -> None:
        try:
            from .douyin_engine import run_setup_cookies

            run_setup_cookies()
            self.status.set("Douyin cookie setup opened. Log in, then press Enter in that helper window.")
            self.details.set("A browser/helper process was opened for Douyin cookies. Complete login/check once, then retry download.")
        except Exception as exc:
            self.status.set("Douyin cookie setup failed.")
            self.details.set(friendly_error(str(exc)))

    def download_selected(self) -> None:
        selected = list(self.table.selection())
        if not selected:
            messagebox.showinfo("No selection", "Select one or more rows first.")
            return
        self._download_items(selected)

    def download_all(self) -> None:
        item_ids = list(self.items.keys())
        if not item_ids:
            messagebox.showinfo("Nothing to download", "Fetch URLs first.")
            return
        self._download_items(item_ids)

    def _download_items(self, item_ids: list[str]) -> None:
        self.download_dir.mkdir(parents=True, exist_ok=True)
        media_format = self.media_format.get()
        if media_format not in {"video", "audio"}:
            media_format = "video"
        label = "MP3" if media_format == "audio" else "MP4"
        log_event(f"UI download requested count={len(item_ids)} media_format={media_format}")
        self.status.set(f"Downloading {len(item_ids)} item(s) as {label}...")
        threading.Thread(target=self._download_worker, args=(item_ids, media_format, self.advanced_options()), daemon=True).start()

    def _download_worker(self, item_ids: list[str], media_format: str, advanced: AdvancedOptions) -> None:
        for item_id in item_ids:
            item = self.items[item_id]
            if item.get("status") == "Error" and not item.get("formats"):
                continue
            matching_formats = [fmt for fmt in item.get("formats") or [] if is_format_compatible(fmt, media_format)]
            if media_format == "video" and not matching_formats:
                self.events.put(("row_status", {"id": item_id, "status": "Audio only", "detail": "Only audio is available for this URL."}))
                log_event(f"UI skipped video download item={item_id} reason=no_video_formats url={item.get('url', '')}")
                continue
            history_entry = find_history_entry(str(item["url"]), media_format)
            if history_entry:
                self.events.put(
                    (
                        "row_done",
                        {
                            "id": item_id,
                            "path": str(history_entry["path"]),
                            "detail": "Already downloaded. Reused the history entry.",
                        },
                    )
                )
                continue
            provider_name = str((selected_matching_format(item, media_format) or {}).get("provider") or item.get("provider") or "")
            self.events.put(
                (
                    "row_status",
                    {
                        "id": item_id,
                        "status": "Downloading",
                        "detail": f"Download started{f' with {provider_name}' if provider_name else ''}.",
                    },
                )
            )
            try:
                selected_format = selected_matching_format(item, media_format)
                format_id = selected_format.get("id") if selected_format else None
                path = download_media(
                    url=str(item["url"]),
                    download_dir=self.download_dir,
                    job_id=uuid.uuid4().hex[:10],
                    media_format=media_format,
                    title=str(item.get("title") or ""),
                    format_id=str(format_id) if format_id else None,
                    progress_callback=lambda value, current_item_id=item_id: self.events.put(
                        ("row_progress", {"id": current_item_id, "progress": value})
                    ),
                    cookie_browser=advanced.yt_dlp_cookie_browser(),
                    advanced=advanced,
                    archive_file=ARCHIVE_FILE,
                )
                record_history(
                    str(item["url"]),
                    media_format,
                    path,
                    title=str(item.get("title") or ""),
                    provider=str((selected_format or {}).get("provider") or item.get("provider") or ""),
                    option=str((selected_format or {}).get("label") or item.get("quality") or ""),
                )
                self.events.put(("row_done", {"id": item_id, "path": str(path), "detail": "Download completed."}))
            except Exception as exc:
                log_event(f"UI download error item={item_id} url={item.get('url', '')} error={exc}")
                recovered = self.recover_downloaded_file(str(item.get("url") or ""), media_format)
                if recovered:
                    record_history(
                        str(item["url"]),
                        media_format,
                        recovered,
                        title=str(item.get("title") or ""),
                        provider=str(item.get("provider") or ""),
                        option=str(item.get("quality") or ""),
                    )
                    self.events.put(
                        (
                            "row_done",
                            {
                                "id": item_id,
                                "path": str(recovered),
                                "detail": "Download completed. Recovered the file after a validation retry.",
                            },
                        )
                    )
                    continue
                self.events.put(("row_status", {"id": item_id, "status": "Error", "detail": friendly_error(str(exc))}))
        self.events.put(("status", f"Done. Folder: {self.download_dir}"))
        cleanup_temp_files(self.download_dir, max_age_seconds=0)
        self.events.put(("history_refresh", {}))

    def recover_downloaded_file(self, url: str, media_format: str) -> Path | None:
        if media_format != "video" or not is_douyin_url(normalize_url(url)):
            return None
        try:
            from .douyin_engine import find_existing_media_for_url

            path = find_existing_media_for_url(self.download_dir, url)
            return path if path and path.exists() else None
        except Exception as exc:
            log_event(f"UI recovery skipped url={url} error={exc}")
            return None

    def choose_folder(self) -> None:
        folder = filedialog.askdirectory(initialdir=str(self.download_dir.parent))
        if folder:
            self.download_dir = Path(folder)
            self.status.set(f"Folder: {self.download_dir}")

    def open_folder(self) -> None:
        self.download_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(self.download_dir)

    def open_selected_file(self) -> None:
        selected = self.table.selection()
        if not selected:
            messagebox.showinfo("No selection", "Select a downloaded row first.")
            return
        item = self.items.get(selected[0], {})
        path = item.get("file_path")
        if not path or not Path(str(path)).exists():
            messagebox.showinfo("No file", "This row does not have a saved file yet.")
            return
        os.startfile(str(path))

    def close(self) -> None:
        log_event("APP close")
        if self.lock_handle:
            ctypes.windll.kernel32.CloseHandle(self.lock_handle)
        self.root.destroy()

    def on_selection_changed(self, _event: object | None = None) -> None:
        self.refresh_quality_box()
        self.update_advanced_control_states()
        selected = self.table.selection()
        if not selected:
            self.details.set("Select a row to see full status, URL, and saved file.")
            return
        item = self.items.get(selected[0], {})
        detail = str(item.get("detail") or item.get("error") or item.get("status") or "")
        url = str(item.get("url") or "")
        file_path = str(item.get("file_path") or "")
        parts = [part for part in (detail, f"URL: {url}" if url else "", f"File: {file_path}" if file_path else "") if part]
        self.details.set(" | ".join(parts) if parts else "No details.")

    def selected_items(self) -> list[dict[str, object]]:
        return [self.items[item_id] for item_id in self.table.selection() if item_id in self.items]

    def update_advanced_control_states(self) -> None:
        if not hasattr(self, "subtitle_languages_box"):
            return
        items = self.selected_items()
        capabilities = selected_capabilities(items, self.media_format.get())

        subtitle_languages = capabilities["subtitle_languages"]
        if subtitle_languages:
            values = ["all", *subtitle_languages]
            self.subtitle_languages_box.configure(values=values, state="readonly")
            self.subtitles_check.configure(state="normal")
            if self.subtitle_languages.get() not in values:
                self.subtitle_languages.set(values[0])
        else:
            self.subtitles.set(False)
            self.subtitle_languages.set("all")
            self.subtitle_languages_box.configure(values=["all"], state="disabled")
            self.subtitles_check.configure(state="disabled")

        quality_values = capabilities["max_quality_values"]
        if quality_values:
            values = ["Best", *quality_values]
            self.max_quality_box.configure(values=values, state="readonly")
            if self.max_quality.get() not in values:
                self.max_quality.set("Best")
        else:
            self.max_quality.set("Best")
            self.max_quality_box.configure(values=["Best"], state="disabled")

        if capabilities["supports_metadata"]:
            self.metadata_check.configure(state="normal")
        else:
            self.metadata.set(False)
            self.metadata_check.configure(state="disabled")

        if capabilities["supports_thumbnail"]:
            self.thumbnail_check.configure(state="normal")
        else:
            self.thumbnail.set(False)
            self.thumbnail_check.configure(state="disabled")

        if capabilities["supports_impersonate"]:
            self.impersonate_box.configure(state="readonly")
        else:
            self.impersonate.set("Off")
            self.impersonate_box.configure(state="disabled")

    def refresh_quality_box(self) -> None:
        selected = self.table.selection()
        if not selected:
            self.quality_box.configure(values=["Best"])
            self.quality.set("Best")
            return

        item = self.items.get(selected[0], {})
        formats = item.get("formats") or []
        labels = [format_option_label(fmt) for fmt in formats if is_format_compatible(fmt, self.media_format.get())] or ["Best"]
        self.quality_box.configure(values=labels)
        current = str(item.get("quality_label") or "")
        self.quality.set(current if current in labels else labels[0])

    def set_quality(self) -> None:
        selected = self.table.selection()
        if not selected:
            return
        label = self.quality.get()
        for item_id in selected:
            item = self.items[item_id]
            item["quality_label"] = label
            item["format_id"] = None
            for fmt in item.get("formats") or []:
                if format_option_label(fmt) == label and is_format_compatible(fmt, self.media_format.get()):
                    item["format_id"] = fmt["id"]
                    item["provider"] = fmt.get("provider", "")
                    item["quality"] = fmt.get("label", label)
            self._update_row(item_id)
        self.on_selection_changed()

    def _poll_events(self) -> None:
        while True:
            try:
                event, payload = self.events.get_nowait()
            except queue.Empty:
                break
            self._handle_event(event, payload)
        self.root.after(120, self._poll_events)

    def _handle_event(self, event: str, payload: object) -> None:
        if event == "insert":
            data = dict(payload)  # type: ignore[arg-type]
            item_id = str(data["id"])
            self.items[item_id] = {
                "url": data["url"],
                "title": data["url"],
                "status": "Fetching",
                "detail": "Fetching metadata...",
            }
            self.table.insert("", "end", iid=item_id, values=(data["url"], "", "", "", "Best", "", "Fetching", ""))
        elif event == "info":
            data = dict(payload)  # type: ignore[arg-type]
            item_id = str(data["id"])
            info = dict(data["info"])
            formats = list(info.get("formats") or [])
            url = str(self.items[item_id].get("url") or "")
            if should_offer_jiji262_option(url, self.advanced_options()):
                formats.insert(
                    0,
                    {
                        "id": "jiji262-local",
                        "label": "jiji262 local no-watermark",
                        "height": 0,
                        "provider": "jiji262",
                        "media_format": "video",
                    },
                )
            first_format = formats[0] if formats else {}
            quality = first_format.get("label", "Best")
            provider = first_format.get("provider", "yt-dlp" if formats else "")
            detail = f"Fetched {len(formats)} option(s)."
            if not formats:
                detail = "No video options were found. Audio may still be available."
            self.items[item_id].update(
                {
                    "title": info.get("title") or self.items[item_id]["url"],
                    "uploader": info.get("uploader") or "",
                    "duration": format_duration(info.get("duration")),
                    "formats": formats,
                    "subtitle_languages": list(info.get("subtitle_languages") or []),
                    "supports_metadata": bool(info.get("supports_metadata")),
                    "supports_thumbnail": bool(info.get("supports_thumbnail")),
                    "quality": quality,
                    "quality_label": format_option_label(first_format) if first_format else "Best",
                    "provider": provider,
                    "format_id": first_format.get("id") if first_format else None,
                    "progress": "",
                    "status": "Ready",
                    "detail": detail,
                    "file_name": "",
                }
            )
            self._update_row(item_id)
        elif event == "error":
            data = dict(payload)  # type: ignore[arg-type]
            item_id = str(data["id"])
            self.items[item_id]["status"] = "Error"
            self.items[item_id]["error"] = data["error"]
            self.items[item_id]["detail"] = data["error"]
            self.items[item_id]["file_name"] = ""
            self._update_row(item_id)
        elif event == "row_status":
            data = dict(payload)  # type: ignore[arg-type]
            item_id = str(data["id"])
            self.items[item_id]["status"] = data["status"]
            if data.get("detail"):
                self.items[item_id]["detail"] = data["detail"]
            self._update_row(item_id)
        elif event == "row_progress":
            data = dict(payload)  # type: ignore[arg-type]
            item_id = str(data["id"])
            progress = f"{int(data['progress'])}%"
            self.items[item_id]["progress"] = progress
            self.table.set(item_id, "progress", progress)
        elif event == "row_done":
            data = dict(payload)  # type: ignore[arg-type]
            item_id = str(data["id"])
            path = Path(str(data["path"]))
            self.items[item_id]["file_path"] = str(path)
            self.items[item_id]["file_name"] = path.name
            self.items[item_id]["progress"] = "100%"
            self.items[item_id]["status"] = "Done"
            self.items[item_id]["detail"] = data.get("detail") or "Download completed."
            self._update_row(item_id)
        elif event == "detail":
            self.details.set(str(payload))
        elif event == "history_refresh":
            self.refresh_history()
        elif event == "channel_fetch_done":
            items = list(payload) if isinstance(payload, list) else []
            self.channel_items = items
            self._populate_channel_table(items)
            self.status.set(f"Channel fetch completed. Found {len(items)} video(s).")
            self.details.set(f"Fetched {len(items)} video(s). Tích chọn các video cần tải và bấm 'Add Selected to Download Queue'.")
        elif event == "channel_fetch_error":
            err_msg = str(payload)
            self.status.set("Channel fetch failed.")
            self.details.set(err_msg)
            messagebox.showerror("Channel Fetch Error", err_msg)
        elif event == "status":
            self.status.set(str(payload))
        elif event == "fetch_done":
            self.fetch_in_progress = False
        self.on_selection_changed()


    def _update_row(self, item_id: str) -> None:
        item = self.items[item_id]
        self.table.item(
            item_id,
            values=(
                item.get("title", ""),
                item.get("uploader", ""),
                item.get("duration", ""),
                item.get("provider", ""),
                item.get("quality", "Best"),
                item.get("progress", ""),
                item.get("status", ""),
                item.get("file_name", ""),
            ),
        )


def format_duration(seconds: object) -> str:
    if not seconds:
        return ""
    total = int(seconds)
    minutes, secs = divmod(total, 60)
    return f"{minutes}:{secs:02d}"


def is_format_compatible(fmt: object, media_format: str) -> bool:
    if not isinstance(fmt, dict):
        return False
    provider_media = fmt.get("media_format")
    if provider_media:
        return provider_media == ("audio" if media_format == "audio" else "video")
    return media_format == "video"


def selected_matching_format(item: dict[str, object], media_format: str) -> dict[str, object] | None:
    formats = [fmt for fmt in item.get("formats") or [] if isinstance(fmt, dict) and is_format_compatible(fmt, media_format)]
    if not formats:
        return None
    current_id = item.get("format_id")
    for fmt in formats:
        if fmt.get("id") == current_id:
            return fmt
    return formats[0]


def selected_capabilities(items: list[dict[str, object]], media_format: str) -> dict[str, object]:
    if not items:
        return {
            "subtitle_languages": [],
            "max_quality_values": [],
            "supports_metadata": False,
            "supports_thumbnail": False,
            "supports_impersonate": False,
        }

    subtitle_sets = [
        set(str(lang) for lang in item.get("subtitle_languages") or [] if str(lang))
        for item in items
    ]
    subtitle_languages = sorted(set.intersection(*subtitle_sets)) if subtitle_sets else []

    height_sets: list[set[str]] = []
    for item in items:
        heights = {
            f"{int(fmt['height'])}p"
            for fmt in item.get("formats") or []
            if isinstance(fmt, dict)
            and is_format_compatible(fmt, media_format)
            and isinstance(fmt.get("height"), int)
            and int(fmt.get("height") or 0) > 0
        }
        height_sets.append(heights)
    max_quality_values = sorted(set.intersection(*height_sets), key=quality_sort_key, reverse=True) if height_sets else []

    selected_formats = [selected_matching_format(item, media_format) or {} for item in items]
    selected_providers = [str(fmt.get("provider") or item.get("provider") or "").lower() for item, fmt in zip(items, selected_formats)]
    provider_supports_yt_dlp_options = all(provider in {"yt-dlp", "jiji262"} for provider in selected_providers if provider)

    return {
        "subtitle_languages": subtitle_languages,
        "max_quality_values": max_quality_values,
        "supports_metadata": provider_supports_yt_dlp_options
        and all(bool(item.get("supports_metadata")) or provider == "jiji262" for item, provider in zip(items, selected_providers)),
        "supports_thumbnail": all(bool(item.get("supports_thumbnail")) for item in items),
        "supports_impersonate": all(provider == "yt-dlp" for provider in selected_providers if provider),
    }


def quality_sort_key(value: str) -> int:
    match = re.search(r"(\d+)", value)
    return int(match.group(1)) if match else 0


def should_offer_jiji262_option(url: str, advanced: AdvancedOptions) -> bool:
    if not is_douyin_url(normalize_url(url)):
        return False
    return advanced.normalized_douyin_engine() in {"auto", "jiji262"}


def format_option_label(fmt: dict[str, object]) -> str:
    if not fmt:
        return "Best"
    provider = str(fmt.get("provider") or "")
    label = str(fmt.get("label") or fmt.get("id") or "Best")
    return f"{provider} - {label}" if provider and not label.startswith(provider) else label


def should_refresh_douyin_cookie(error: str) -> bool:
    lowered = error.lower()
    return (
        "fresh cookies" in lowered
        or "could not copy chrome cookie database" in lowered
        or "failed to decrypt with dpapi" in lowered
        or "cookies database" in lowered
    )


def acquire_single_instance_lock():
    mutex_name = "Local\\ProDownloaderSingleInstance"
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
    already_exists = ctypes.windll.kernel32.GetLastError() == 183
    if already_exists:
        return None
    return handle


def main() -> None:
    lock_handle = acquire_single_instance_lock()
    if lock_handle is None:
        return

    root = Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    ProDownloaderApp(root, lock_handle=lock_handle)
    root.mainloop()


if __name__ == "__main__":
    main()
