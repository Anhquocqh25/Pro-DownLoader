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
from tkinter import END, StringVar, BooleanVar, filedialog, messagebox
from tkinter import ttk
from typing import Any, Callable

import customtkinter as ctk

from .core import (
    APP_NAME,
    APP_VERSION,
    ARCHIVE_FILE,
    AdvancedOptions,
    cleanup_temp_files,
    download_media,
    fetch_channel_videos,
    fetch_video_info,
    find_ffmpeg_location,
    find_history_entry,
    friendly_error,
    is_channel_or_playlist_url,
    is_douyin_url,
    is_frozen_app,
    load_douyin_cookies,
    load_history,
    log_event,
    normalize_url,
    record_history,
    update_ytdlp,
    validate_url_input,
    yt_dlp_command,
)
from .douyin_engine import (
    download_channel_with_jiji262,
    engine_cookie_file,
    run_setup_cookies,
    save_douyin_cookie_string,
)
from .thumbnail_cache import ThumbnailCache
from .translator import batch_translate_texts, clean_title, translate_text
from .updater import check_for_updates, perform_one_click_update, restart_application


class ProDownloaderApp:
    def __init__(self, root: ctk.CTk, lock_handle: object | None = None) -> None:
        self.root = root
        self.root.title(f"{APP_NAME} - Modern Video Downloader")
        self._set_window_icon()
        self.root.geometry("1300x780")
        self.root.minsize(1060, 640)

        # Theme & Appearance
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        # Variables
        self.media_format = StringVar(value="video")
        self.quality = StringVar(value="Best")
        self.status = StringVar(value="🟢 Sẵn sàng")
        self.details = StringVar(value="Dán link video hoặc link kênh để bắt đầu tải về máy.")
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
        self.channel_limit_var = StringVar(value="All")
        self.channel_keyword_var = StringVar(value="")
        self.channel_view_mode = StringVar(value="grid")  # "grid" or "list"

        self.channel_items: list[dict[str, Any]] = []
        self.channel_selected_indices: set[int] = set()
        self.channel_selected_ids: set[str] = set()
        self.channel_card_widgets: list[ctk.CTkFrame] = []
        self.channel_card_checkbox_vars: list[BooleanVar] = []
        self.channel_card_checkboxes: list[ctk.CTkCheckBox] = []
        self.channel_card_title_labels: list[ctk.CTkLabel] = []
        self.auto_translate = BooleanVar(value=True)

        self.download_dir = Path.home() / "Downloads" / APP_NAME
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.items: dict[str, dict[str, object]] = {}
        self.fetch_in_progress = False
        self.auto_fetch_after_id: str | None = None
        self.lock_handle = lock_handle

        self.thumbnail_cache = ThumbnailCache(target_size=(190, 120))

        self.fetch_cancel_event = threading.Event()
        self.download_cancel_event = threading.Event()
        self.channel_cancel_event = threading.Event()
        self.is_fetching = False
        self.is_downloading = False
        self.is_channel_fetching = False

        self._build_modern_ui()
        self._check_tools()
        cleanup_temp_files(self.download_dir, max_age_seconds=0)
        log_event("APP start modern UI")
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

    def _build_modern_ui(self) -> None:
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        # -----------------------------
        # Left Navigation Sidebar
        # -----------------------------
        self.sidebar = ctk.CTkFrame(self.root, width=230, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(7, weight=1)

        logo_label = ctk.CTkLabel(
            self.sidebar,
            text="⚡ PRO DOWNLOADER",
            font=ctk.CTkFont(size=17, weight="bold"),
        )
        logo_label.grid(row=0, column=0, padx=20, pady=(20, 2), sticky="w")

        sub_logo = ctk.CTkLabel(
            self.sidebar,
            text="Tải Video Không Logo Đa Nền Tảng",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        sub_logo.grid(row=1, column=0, padx=20, pady=(0, 8), sticky="w")

        # Version badge & 1-Click Update button
        ver_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        ver_frame.grid(row=2, column=0, padx=14, pady=(0, 16), sticky="ew")

        ver_pill = ctk.CTkLabel(
            ver_frame,
            text=f"v{APP_VERSION}",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=["#EEF2FF", "#312E81"],
            text_color=["#4F46E5", "#A5B4FC"],
            corner_radius=6,
            padx=8,
            pady=3,
        )
        ver_pill.pack(side="left")

        self.update_btn = ctk.CTkButton(
            ver_frame,
            text="🔄 Cập Nhật 1-Click",
            font=ctk.CTkFont(size=11, weight="bold"),
            height=28,
            fg_color=["#4F46E5", "#4338CA"],
            hover_color=["#4338CA", "#3730A3"],
            text_color="#FFFFFF",
            corner_radius=6,
            command=self.check_and_update_ui,
        )
        self.update_btn.pack(side="right", padx=(6, 0))

        # Navigation buttons
        self.nav_btns: dict[str, ctk.CTkButton] = {}
        nav_items = [
            ("single", "📥 Tải Nhanh (URL/Batch)"),
            ("channel", "📺 Quét Toàn Kênh"),
            ("history", "📜 Lịch Sử Đã Tải"),
            ("settings", "⚙️ Cài Đặt & Cookies"),
        ]

        for idx, (key, label) in enumerate(nav_items, start=3):
            btn = ctk.CTkButton(
                self.sidebar,
                text=label,
                anchor="w",
                font=ctk.CTkFont(size=13, weight="normal"),
                height=38,
                corner_radius=8,
                command=lambda k=key: self.switch_view(k),
            )
            btn.grid(row=idx, column=0, padx=14, pady=4, sticky="ew")
            self.nav_btns[key] = btn

        # Bottom sidebar: Cookie Status & Theme selector
        theme_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        theme_frame.grid(row=8, column=0, padx=14, pady=(0, 14), sticky="ew")

        cookie_count = len(load_douyin_cookies(None))
        cookie_text = f"🟢 Douyin Cookies ({cookie_count})" if cookie_count > 0 else "🟡 Chưa có Cookie"
        self.cookie_status_badge = ctk.CTkLabel(
            theme_frame,
            text=cookie_text,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#10B981" if cookie_count > 0 else "#F59E0B",
        )
        self.cookie_status_badge.pack(anchor="w", pady=(0, 6))

        theme_lbl = ctk.CTkLabel(theme_frame, text="Giao diện:", font=ctk.CTkFont(size=11), text_color="gray")
        theme_lbl.pack(anchor="w")
        self.theme_menu = ctk.CTkOptionMenu(
            theme_frame,
            values=["System", "Dark", "Light"],
            command=self._change_theme,
            height=28,
            font=ctk.CTkFont(size=12),
        )
        self.theme_menu.pack(fill="x", pady=(2, 0))

        # -----------------------------
        # Right Main Content Area
        # -----------------------------
        self.main_container = ctk.CTkFrame(self.root, corner_radius=0, fg_color="transparent")
        self.main_container.grid(row=0, column=1, sticky="nsew", padx=16, pady=16)
        self.main_container.grid_rowconfigure(0, weight=1)
        self.main_container.grid_rowconfigure(1, weight=0)
        self.main_container.grid_columnconfigure(0, weight=1)

        # View frames dictionary
        self.views: dict[str, ctk.CTkFrame] = {}

        self._build_single_view()
        self._build_channel_view()
        self._build_history_view()
        self._build_settings_view()

        # Global Bottom Status & Progress Bar
        self._build_bottom_bar()

        # Start on Single view
        self.switch_view("single")

    def _change_theme(self, mode: str) -> None:
        ctk.set_appearance_mode(mode)
        self.root.after(50, self._style_treeview)

    def switch_view(self, name: str) -> None:
        for key, view in self.views.items():
            if key == name:
                view.grid(row=0, column=0, sticky="nsew")
                if key in self.nav_btns:
                    self.nav_btns[key].configure(
                        fg_color=["#4F46E5", "#4338CA"],
                        text_color="#FFFFFF",
                        font=ctk.CTkFont(size=13, weight="bold"),
                    )
            else:
                view.grid_forget()
                if key in self.nav_btns:
                    self.nav_btns[key].configure(
                        fg_color="transparent",
                        text_color=["#4B5563", "#D1D5DB"],
                        font=ctk.CTkFont(size=13, weight="normal"),
                    )

    # =========================================================================
    # VIEW 1: TẢI NHANH (SINGLE / BATCH URLS)
    # =========================================================================
    def _build_single_view(self) -> None:
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)
        self.views["single"] = frame

        # Top URL input card
        top_card = ctk.CTkFrame(frame, corner_radius=12)
        top_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        top_card.grid_columnconfigure(0, weight=1)

        input_header = ctk.CTkLabel(
            top_card,
            text="Nhập hoặc dán các đường link video (mỗi dòng một link):",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        input_header.grid(row=0, column=0, padx=14, pady=(12, 4), sticky="w")

        text_container = ctk.CTkFrame(top_card, fg_color="transparent")
        text_container.grid(row=1, column=0, padx=14, pady=4, sticky="ew")
        text_container.grid_columnconfigure(0, weight=1)

        self.url_text = ctk.CTkTextbox(text_container, height=75, font=ctk.CTkFont(family="Consolas", size=12))
        self.url_text.grid(row=0, column=0, sticky="ew")
        self.url_text.bind("<<Paste>>", self.on_url_paste)

        btn_box = ctk.CTkFrame(text_container, fg_color="transparent")
        btn_box.grid(row=0, column=1, padx=(10, 0), sticky="ns")

        self.paste_btn = ctk.CTkButton(btn_box, text="📋 Dán & Quét", width=120, height=34, fg_color="#2563EB", hover_color="#1D4ED8", command=self.paste_and_fetch)
        self.paste_btn.pack(pady=(0, 6))

        self.fetch_btn = ctk.CTkButton(btn_box, text="🔍 Quét Link", width=120, height=34, fg_color="#4F46E5", hover_color="#4338CA", command=self.fetch_all)
        self.fetch_btn.pack()

        # Options strip
        opts_strip = ctk.CTkFrame(top_card, fg_color="transparent")
        opts_strip.grid(row=2, column=0, padx=14, pady=(6, 12), sticky="ew")

        fmt_lbl = ctk.CTkLabel(opts_strip, text="Định dạng:", font=ctk.CTkFont(size=12, weight="bold"))
        fmt_lbl.pack(side="left", padx=(0, 6))

        r_mp4 = ctk.CTkRadioButton(opts_strip, text="Video (MP4)", variable=self.media_format, value="video")
        r_mp4.pack(side="left", padx=(0, 10))

        r_mp3 = ctk.CTkRadioButton(opts_strip, text="Âm thanh (MP3)", variable=self.media_format, value="audio")
        r_mp3.pack(side="left", padx=(0, 20))

        q_lbl = ctk.CTkLabel(opts_strip, text="Chất lượng:", font=ctk.CTkFont(size=12, weight="bold"))
        q_lbl.pack(side="left", padx=(0, 6))

        self.quality_box = ctk.CTkOptionMenu(
            opts_strip,
            variable=self.quality,
            values=["Best"],
            width=180,
            height=28,
        )
        self.quality_box.pack(side="left", padx=(0, 8))

        set_q_btn = ctk.CTkButton(opts_strip, text="Áp dụng Option", width=110, height=28, fg_color=["#4B5563", "#3B82F6"], hover_color=["#374151", "#2563EB"], command=self.set_quality)
        set_q_btn.pack(side="left")

        # Translation Controls
        sep_lbl = ctk.CTkLabel(opts_strip, text="|", font=ctk.CTkFont(size=14), text_color="gray")
        sep_lbl.pack(side="left", padx=10)

        trans_btn = ctk.CTkButton(
            opts_strip,
            text="🌐 Dịch Tiếng Việt",
            width=125,
            height=28,
            fg_color="#7C3AED",
            hover_color="#6D28D9",
            command=self.translate_all_queue,
        )
        trans_btn.pack(side="left", padx=(0, 6))

        orig_btn = ctk.CTkButton(
            opts_strip,
            text="↩️ Tên Gốc",
            width=85,
            height=28,
            fg_color=["#4B5563", "#64748B"],
            hover_color=["#374151", "#475569"],
            command=self.revert_all_queue_titles,
        )
        orig_btn.pack(side="left", padx=(0, 10))

        auto_trans_chk = ctk.CTkCheckBox(
            opts_strip,
            text="Tự động dịch",
            variable=self.auto_translate,
            width=90,
            font=ctk.CTkFont(size=11),
        )
        auto_trans_chk.pack(side="left")

        # Middle Table
        table_card = ctk.CTkFrame(frame, corner_radius=12)
        table_card.grid(row=1, column=0, sticky="nsew", pady=(0, 12))
        table_card.grid_columnconfigure(0, weight=1)
        table_card.grid_rowconfigure(0, weight=1)

        columns = ("title", "uploader", "duration", "provider", "quality", "progress", "status", "file")
        self.table = ttk.Treeview(table_card, columns=columns, show="headings", selectmode="extended")
        self.table.heading("title", text="Tiêu Đề Video")
        self.table.heading("uploader", text="Kênh/Tác Giả")
        self.table.heading("duration", text="Thời Lượng")
        self.table.heading("provider", text="Nguồn Tải")
        self.table.heading("quality", text="Chất Lượng")
        self.table.heading("progress", text="Tiến Trình")
        self.table.heading("status", text="Trạng Thái")
        self.table.heading("file", text="File Đã Lưu")

        self.table.column("title", width=340)
        self.table.column("uploader", width=130)
        self.table.column("duration", width=85, anchor="center")
        self.table.column("provider", width=95, anchor="center")
        self.table.column("quality", width=120, anchor="center")
        self.table.column("progress", width=85, anchor="center")
        self.table.column("status", width=110, anchor="center")
        self.table.column("file", width=220)

        self._style_treeview()
        self.table.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        scroll_y = ttk.Scrollbar(table_card, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scroll_y.set)
        scroll_y.grid(row=0, column=1, sticky="ns", pady=10, padx=(0, 10))
        self.table.bind("<<TreeviewSelect>>", self.on_selection_changed)

        # Bottom Actions strip
        act_strip = ctk.CTkFrame(frame, fg_color="transparent")
        act_strip.grid(row=2, column=0, sticky="ew")

        self.dl_sel_btn = ctk.CTkButton(
            act_strip,
            text="⬇️ Tải Mục Đã Chọn",
            height=34,
            fg_color="#2563EB",
            hover_color="#1D4ED8",
            command=self.download_selected,
        )
        self.dl_sel_btn.pack(side="left", padx=(0, 8))

        self.dl_all_btn = ctk.CTkButton(
            act_strip,
            text="⚡ Tải Tất Cả",
            height=34,
            fg_color="#059669",
            hover_color="#047857",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.download_all,
        )
        self.dl_all_btn.pack(side="left", padx=(0, 8))

        self.stop_dl_btn = ctk.CTkButton(
            act_strip,
            text="⏹️ Dừng Tải",
            height=34,
            fg_color="#DC2626",
            hover_color="#B91C1C",
            font=ctk.CTkFont(size=13, weight="bold"),
            state="disabled",
            command=self.cancel_download,
        )
        self.stop_dl_btn.pack(side="left", padx=(0, 14))

        self.clear_q_btn = ctk.CTkButton(
            act_strip,
            text="🗑️ Xóa Hàng Đợi",
            height=34,
            fg_color=["#4B5563", "#475569"],
            hover_color=["#374151", "#334155"],
            command=self.clear_queue,
        )
        self.clear_q_btn.pack(side="left", padx=(0, 14))

        choose_f_btn = ctk.CTkButton(
            act_strip,
            text="📁 Thư Mục Lưu",
            height=34,
            fg_color=["#374151", "#3B4252"],
            hover_color=["#1F2937", "#2E3440"],
            command=self.choose_folder,
        )
        choose_f_btn.pack(side="left", padx=(0, 8))

        open_f_btn = ctk.CTkButton(
            act_strip,
            text="📂 Mở Thư Mục",
            height=34,
            fg_color=["#374151", "#3B4252"],
            hover_color=["#1F2937", "#2E3440"],
            command=self.open_folder,
        )
        open_f_btn.pack(side="left", padx=(0, 8))

        open_v_btn = ctk.CTkButton(
            act_strip,
            text="▶️ Xem File",
            height=34,
            fg_color=["#374151", "#3B4252"],
            hover_color=["#1F2937", "#2E3440"],
            command=self.open_selected_file,
        )
        open_v_btn.pack(side="left")

    def _style_treeview(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        mode = ctk.get_appearance_mode()
        if mode == "Dark":
            bg_color = "#18181B"
            fg_color = "#F4F4F5"
            field_bg = "#18181B"
            header_bg = "#27272A"
            header_fg = "#FFFFFF"
            sel_bg = "#4F46E5"
        else:
            bg_color = "#FFFFFF"
            fg_color = "#0F172A"
            field_bg = "#FFFFFF"
            header_bg = "#F1F5F9"
            header_fg = "#0F172A"
            sel_bg = "#4F46E5"

        style.configure(
            "Treeview",
            background=bg_color,
            foreground=fg_color,
            fieldbackground=field_bg,
            rowheight=30,
            font=("Segoe UI", 10),
            borderwidth=0,
        )
        style.configure(
            "Treeview.Heading",
            background=header_bg,
            foreground=header_fg,
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padding=(6, 6),
        )
        style.map(
            "Treeview",
            background=[("selected", sel_bg)],
            foreground=[("selected", "#FFFFFF")],
        )

    # =========================================================================
    # VIEW 2: QUÉT TOÀN BỘ KÊNH (CHANNEL EXTRACTOR)
    # =========================================================================
    def _build_channel_view(self) -> None:
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)
        self.views["channel"] = frame

        # Top Control Card
        top_card = ctk.CTkFrame(frame, corner_radius=12)
        top_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        top_card.grid_columnconfigure(1, weight=1)

        c_url_lbl = ctk.CTkLabel(top_card, text="Link Kênh / Profile Douyin/YouTube:", font=ctk.CTkFont(size=12, weight="bold"))
        c_url_lbl.grid(row=0, column=0, padx=14, pady=(12, 6), sticky="w")

        self.channel_url_entry = ctk.CTkEntry(
            top_card,
            textvariable=self.channel_url_var,
            placeholder_text="https://www.douyin.com/user/MS4wLjABAAAA...",
            height=34,
        )
        self.channel_url_entry.grid(row=0, column=1, padx=(0, 14), pady=(12, 6), sticky="ew")

        # Filters and actions
        bar = ctk.CTkFrame(top_card, fg_color="transparent")
        bar.grid(row=1, column=0, columnspan=2, padx=14, pady=(0, 12), sticky="ew")

        l_lbl = ctk.CTkLabel(bar, text="Giới hạn:", font=ctk.CTkFont(size=12))
        l_lbl.pack(side="left", padx=(0, 6))

        self.channel_limit_box = ctk.CTkOptionMenu(
            bar,
            variable=self.channel_limit_var,
            values=["All", "10", "20", "30", "50", "100"],
            width=90,
            height=30,
        )
        self.channel_limit_box.pack(side="left", padx=(0, 16))

        k_lbl = ctk.CTkLabel(bar, text="Lọc từ khóa:", font=ctk.CTkFont(size=12))
        k_lbl.pack(side="left", padx=(0, 6))

        self.channel_keyword_entry = ctk.CTkEntry(
            bar,
            textvariable=self.channel_keyword_var,
            placeholder_text="Hashtag / Từ khóa...",
            width=160,
            height=30,
        )
        self.channel_keyword_entry.pack(side="left", padx=(0, 16))

        self.channel_fetch_btn = ctk.CTkButton(
            bar,
            text="🔍 Quét Kênh",
            width=110,
            height=32,
            fg_color="#2563EB",
            hover_color="#1D4ED8",
            command=self.fetch_channel_videos_ui,
        )
        self.channel_fetch_btn.pack(side="left", padx=(0, 8))

        self.channel_stop_btn = ctk.CTkButton(
            bar,
            text="⏹️ Dừng Quét",
            width=110,
            height=32,
            fg_color="#DC2626",
            hover_color="#B91C1C",
            font=ctk.CTkFont(size=12, weight="bold"),
            state="disabled",
            command=self.cancel_channel_fetch,
        )
        self.channel_stop_btn.pack(side="left", padx=(0, 16))

        dl_direct_btn = ctk.CTkButton(
            bar,
            text="⚡ Tải Toàn Kênh (1-Click)",
            fg_color="#059669",
            hover_color="#047857",
            font=ctk.CTkFont(size=12, weight="bold"),
            width=190,
            height=32,
            command=self.download_channel_directly_ui,
        )
        dl_direct_btn.pack(side="left", padx=(0, 10))

        self.channel_trans_btn = ctk.CTkButton(
            bar,
            text="🌐 Dịch Tiếng Việt",
            width=125,
            height=32,
            fg_color="#7C3AED",
            hover_color="#6D28D9",
            command=self.translate_channel_items,
        )
        self.channel_trans_btn.pack(side="left", padx=(0, 16))

        # View mode toggle: Grid vs List
        self.view_mode_seg = ctk.CTkSegmentedButton(
            bar,
            values=["🖼️ Thẻ Video", "📋 Danh Sách"],
            command=self._on_channel_view_mode_change,
            height=30,
        )
        self.view_mode_seg.set("🖼️ Thẻ Video")
        self.view_mode_seg.pack(side="right")

        # Middle Content Area: Dual View (Grid Container & Table Container)
        self.channel_content_card = ctk.CTkFrame(frame, corner_radius=12)
        self.channel_content_card.grid(row=1, column=0, sticky="nsew", pady=(0, 12))
        self.channel_content_card.grid_columnconfigure(0, weight=1)
        self.channel_content_card.grid_rowconfigure(0, weight=1)

        # 1. Grid View (Scrollable Cards)
        self.channel_grid_scroll = ctk.CTkScrollableFrame(self.channel_content_card, corner_radius=10)
        for c in range(4):
            self.channel_grid_scroll.columnconfigure(c, weight=1)

        # 2. List View (Table)
        self.channel_table_frame = ctk.CTkFrame(self.channel_content_card, fg_color="transparent")
        self.channel_table_frame.grid_columnconfigure(0, weight=1)
        self.channel_table_frame.grid_rowconfigure(0, weight=1)

        c_cols = ("select", "title", "uploader", "duration", "url")
        self.channel_table = ttk.Treeview(self.channel_table_frame, columns=c_cols, show="headings", height=8)
        self.channel_table.heading("select", text="[x]")
        self.channel_table.heading("title", text="Tiêu Đề Video")
        self.channel_table.heading("uploader", text="Kênh")
        self.channel_table.heading("duration", text="Thời Lượng")
        self.channel_table.heading("url", text="Đường Dẫn URL")

        self.channel_table.column("select", width=55, anchor="center")
        self.channel_table.column("title", width=420)
        self.channel_table.column("uploader", width=140)
        self.channel_table.column("duration", width=95, anchor="center")
        self.channel_table.column("url", width=330)

        self.channel_table.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        c_scroll = ttk.Scrollbar(self.channel_table_frame, orient="vertical", command=self.channel_table.yview)
        self.channel_table.configure(yscrollcommand=c_scroll.set)
        c_scroll.grid(row=0, column=1, sticky="ns", pady=10, padx=(0, 10))
        self.channel_table.bind("<Button-1>", self.on_channel_table_click)

        # Initial display
        self.channel_grid_scroll.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        # Bottom Selection Toolbar
        c_bottom_bar = ctk.CTkFrame(frame, fg_color="transparent")
        c_bottom_bar.grid(row=2, column=0, sticky="ew")

        sel_all_btn = ctk.CTkButton(c_bottom_bar, text="Chọn Tất Cả", width=110, height=32, fg_color="#2563EB", hover_color="#1D4ED8", command=self.channel_select_all)
        sel_all_btn.pack(side="left", padx=(0, 8))

        desel_all_btn = ctk.CTkButton(c_bottom_bar, text="Bỏ Chọn", width=90, height=32, fg_color=["#4B5563", "#64748B"], hover_color=["#374151", "#475569"], command=self.channel_deselect_all)
        desel_all_btn.pack(side="left", padx=(0, 14))

        add_q_btn = ctk.CTkButton(
            c_bottom_bar,
            text="➕ Thêm Video Đã Chọn Vào Hàng Đợi",
            height=32,
            fg_color="#059669",
            hover_color="#047857",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.add_channel_selected_to_queue,
        )
        add_q_btn.pack(side="left", padx=(0, 14))

        self.channel_selection_info_lbl = ctk.CTkLabel(
            c_bottom_bar,
            text="Đã chọn: 0 video",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#10B981",
        )
        self.channel_selection_info_lbl.pack(side="left")

    def _on_channel_view_mode_change(self, mode_label: str) -> None:
        if "Thẻ" in mode_label:
            self.channel_view_mode.set("grid")
            self.channel_table_frame.grid_forget()
            self.channel_grid_scroll.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        else:
            self.channel_view_mode.set("list")
            self.channel_grid_scroll.grid_forget()
            self.channel_table_frame.grid(row=0, column=0, sticky="nsew")

    # =========================================================================
    # VIEW 3: LỊCH SỬ ĐÃ TẢI (HISTORY)
    # =========================================================================
    def _build_history_view(self) -> None:
        frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)
        self.views["history"] = frame

        # Top search
        top_bar = ctk.CTkFrame(frame, corner_radius=12)
        top_bar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        top_bar.grid_columnconfigure(0, weight=1)

        bar_inner = ctk.CTkFrame(top_bar, fg_color="transparent")
        bar_inner.pack(fill="x", padx=14, pady=12)

        h_title = ctk.CTkLabel(bar_inner, text="📜 Lịch Sử Video & Âm Thanh Đã Tải:", font=ctk.CTkFont(size=14, weight="bold"))
        h_title.pack(side="left")

        refresh_btn = ctk.CTkButton(bar_inner, text="🔄 Làm Mới", width=100, height=30, fg_color="#2563EB", hover_color="#1D4ED8", command=self.refresh_history)
        refresh_btn.pack(side="right", padx=(8, 0))

        open_h_btn = ctk.CTkButton(bar_inner, text="Mở File History.json", width=150, height=30, fg_color=["#4B5563", "#64748B"], hover_color=["#374151", "#475569"], command=self.open_history_file)
        open_h_btn.pack(side="right")

        # History Table Card
        h_card = ctk.CTkFrame(frame, corner_radius=12)
        h_card.grid(row=1, column=0, sticky="nsew", pady=(0, 12))
        h_card.grid_columnconfigure(0, weight=1)
        h_card.grid_rowconfigure(0, weight=1)

        h_cols = ("title", "format", "time", "path", "url")
        self.history_table = ttk.Treeview(h_card, columns=h_cols, show="headings", selectmode="browse")
        self.history_table.heading("title", text="Tên File / Tiêu Đề")
        self.history_table.heading("format", text="Định Dạng")
        self.history_table.heading("time", text="Thời Gian Tải")
        self.history_table.heading("path", text="Đường Dẫn File Trên Máy")
        self.history_table.heading("url", text="Link Gốc")

        self.history_table.column("title", width=320)
        self.history_table.column("format", width=90, anchor="center")
        self.history_table.column("time", width=160, anchor="center")
        self.history_table.column("path", width=340)
        self.history_table.column("url", width=250)

        self.history_table.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        h_scroll = ttk.Scrollbar(h_card, orient="vertical", command=self.history_table.yview)
        self.history_table.configure(yscrollcommand=h_scroll.set)
        h_scroll.grid(row=0, column=1, sticky="ns", pady=10, padx=(0, 10))

        # Bottom Actions
        h_actions = ctk.CTkFrame(frame, fg_color="transparent")
        h_actions.grid(row=2, column=0, sticky="ew")

        open_file_btn = ctk.CTkButton(h_actions, text="▶️ Phát File Đang Chọn", height=32, fg_color="#059669", hover_color="#047857", command=self._open_history_selected_file)
        open_file_btn.pack(side="left", padx=(0, 8))

        open_dir_btn = ctk.CTkButton(h_actions, text="📂 Mở Thư Mục Chứa File", height=32, fg_color=["#4B5563", "#64748B"], hover_color=["#374151", "#475569"], command=self._open_history_selected_dir)
        open_dir_btn.pack(side="left")

    def _open_history_selected_file(self) -> None:
        selected = self.history_table.selection()
        if not selected:
            messagebox.showinfo("Chưa chọn", "Vui lòng click chọn 1 dòng lịch sử trước.")
            return
        vals = self.history_table.item(selected[0], "values")
        if vals and len(vals) >= 4:
            fpath = Path(vals[3])
            if fpath.exists():
                webbrowser.open(str(fpath))
            else:
                messagebox.showerror("Không tìm thấy", f"File không tồn tại trên ổ cứng: {fpath}")

    def _open_history_selected_dir(self) -> None:
        selected = self.history_table.selection()
        if not selected:
            messagebox.showinfo("Chưa chọn", "Vui lòng click chọn 1 dòng lịch sử trước.")
            return
        vals = self.history_table.item(selected[0], "values")
        if vals and len(vals) >= 4:
            fpath = Path(vals[3]).parent
            if fpath.exists():
                webbrowser.open(str(fpath))
            else:
                messagebox.showerror("Không tìm thấy", f"Thư mục không tồn tại: {fpath}")

    # =========================================================================
    # VIEW 4: CÀI ĐẶT & COOKIES (SETTINGS)
    # =========================================================================
    def _build_settings_view(self) -> None:
        frame = ctk.CTkScrollableFrame(self.main_container, corner_radius=12)
        frame.grid_columnconfigure(0, weight=1)
        self.views["settings"] = frame

        # Card 0: 🚀 Cập Nhật Ứng Dụng (1-Click Auto Updater)
        up_card = ctk.CTkFrame(frame, corner_radius=12)
        up_card.pack(fill="x", pady=(0, 14), padx=6)
        up_card.grid_columnconfigure(1, weight=1)

        up_title = ctk.CTkLabel(
            up_card,
            text="🚀 Cập Nhật Ứng Dụng (1-Click Auto Updater)",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        up_title.grid(row=0, column=0, columnspan=2, padx=16, pady=(14, 6), sticky="w")

        up_desc = ctk.CTkLabel(
            up_card,
            text=f"Phiên bản hiện tại: v{APP_VERSION}. Bạn có thể kiểm tra và cập nhật lên phiên bản mới nhất từ GitHub chỉ với 1 cú click chuột.",
            font=ctk.CTkFont(size=12),
            text_color="gray",
            justify="left",
        )
        up_desc.grid(row=1, column=0, columnspan=2, padx=16, pady=(0, 10), sticky="w")

        up_btn_frame = ctk.CTkFrame(up_card, fg_color="transparent")
        up_btn_frame.grid(row=2, column=0, columnspan=2, padx=16, pady=(0, 14), sticky="w")

        self.settings_check_update_btn = ctk.CTkButton(
            up_btn_frame,
            text="🔄 Kiểm Tra Bản Cập Nhật Mới (1-Click)",
            height=34,
            fg_color="#4F46E5",
            hover_color="#4338CA",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.check_and_update_ui,
        )
        self.settings_check_update_btn.pack(side="left", padx=(0, 10))

        # Card 1: Douyin Cookies Management
        c_card = ctk.CTkFrame(frame, corner_radius=12)
        c_card.pack(fill="x", pady=(0, 14), padx=6)
        c_card.grid_columnconfigure(1, weight=1)

        c_title = ctk.CTkLabel(c_card, text="🍪 Quản Lý Douyin Cookies (Khuyên dùng để tải full kênh không watermark)", font=ctk.CTkFont(size=14, weight="bold"))
        c_title.grid(row=0, column=0, columnspan=2, padx=16, pady=(14, 8), sticky="w")

        c_desc = ctk.CTkLabel(
            c_card,
            text="Douyin thường xuyên áp dụng mã kiểm tra chống bot. Bạn có thể dán cookie chuỗi thủ công hoặc mở trình duyệt để tự động lấy cookie phiên đăng nhập.",
            font=ctk.CTkFont(size=12),
            text_color="gray",
            wraplength=800,
            justify="left",
        )
        c_desc.grid(row=1, column=0, columnspan=2, padx=16, pady=(0, 12), sticky="w")

        c_btn_frame = ctk.CTkFrame(c_card, fg_color="transparent")
        c_btn_frame.grid(row=2, column=0, columnspan=2, padx=16, pady=(0, 14), sticky="w")

        paste_c_btn = ctk.CTkButton(
            c_btn_frame,
            text="🔑 Nhập Cookie Thủ Công",
            height=34,
            fg_color="#2563EB",
            hover_color="#1D4ED8",
            command=self.open_douyin_cookie_dialog,
        )
        paste_c_btn.pack(side="left", padx=(0, 10))

        auto_login_btn = ctk.CTkButton(
            c_btn_frame,
            text="🌐 Mở Trình Duyệt Đăng Nhập (Auto Playwright)",
            height=34,
            fg_color="#7C3AED",
            hover_color="#6D28D9",
            command=self.setup_douyin_cookies,
        )
        auto_login_btn.pack(side="left")

        # Card 2: Engine & Network
        e_card = ctk.CTkFrame(frame, corner_radius=12)
        e_card.pack(fill="x", pady=(0, 14), padx=6)
        e_card.grid_columnconfigure(1, weight=1)

        e_title = ctk.CTkLabel(e_card, text="⚙️ Tùy Chọn Động Cơ & Mạng (Engine & Proxy)", font=ctk.CTkFont(size=14, weight="bold"))
        e_title.grid(row=0, column=0, columnspan=2, padx=16, pady=(14, 10), sticky="w")

        # Douyin engine
        d_lbl = ctk.CTkLabel(e_card, text="Động cơ Douyin:", font=ctk.CTkFont(size=12, weight="bold"))
        d_lbl.grid(row=1, column=0, padx=16, pady=6, sticky="w")
        d_menu = ctk.CTkOptionMenu(
            e_card,
            variable=self.douyin_engine,
            values=["Auto", "Jiji262 Local", "SnapDouyin", "yt-dlp"],
            width=200,
        )
        d_menu.grid(row=1, column=1, padx=16, pady=6, sticky="w")

        # Proxy
        p_lbl = ctk.CTkLabel(e_card, text="HTTP Proxy (nếu có):", font=ctk.CTkFont(size=12, weight="bold"))
        p_lbl.grid(row=2, column=0, padx=16, pady=6, sticky="w")
        p_entry = ctk.CTkEntry(
            e_card,
            textvariable=self.proxy,
            placeholder_text="http://127.0.0.1:7890",
            width=320,
        )
        p_entry.grid(row=2, column=1, padx=16, pady=6, sticky="w")

        # Cookie browser
        b_lbl = ctk.CTkLabel(e_card, text="Trình duyệt trích Cookie (yt-dlp):", font=ctk.CTkFont(size=12, weight="bold"))
        b_lbl.grid(row=3, column=0, padx=16, pady=6, sticky="w")
        b_menu = ctk.CTkOptionMenu(
            e_card,
            variable=self.cookie_browser,
            values=["Auto", "Chrome", "Edge", "Firefox", "Brave"],
            width=200,
        )
        b_menu.grid(row=3, column=1, padx=16, pady=6, sticky="w")

        # Card 3: Media Options & Updates
        m_card = ctk.CTkFrame(frame, corner_radius=12)
        m_card.pack(fill="x", pady=(0, 14), padx=6)
        m_card.grid_columnconfigure(1, weight=1)

        m_title = ctk.CTkLabel(m_card, text="📦 Tùy Chọn File & Bản Cập Nhật", font=ctk.CTkFont(size=14, weight="bold"))
        m_title.grid(row=0, column=0, columnspan=2, padx=16, pady=(14, 10), sticky="w")

        # Checkboxes
        chk_frame = ctk.CTkFrame(m_card, fg_color="transparent")
        chk_frame.grid(row=1, column=0, columnspan=2, padx=16, pady=(0, 10), sticky="w")

        c_sub = ctk.CTkCheckBox(chk_frame, text="Tải Phụ Đề (Subtitles)", variable=self.subtitles)
        c_sub.pack(side="left", padx=(0, 16))

        c_meta = ctk.CTkCheckBox(chk_frame, text="Nhúng Metadata", variable=self.metadata)
        c_meta.pack(side="left", padx=(0, 16))

        c_thumb = ctk.CTkCheckBox(chk_frame, text="Tải Ảnh Thumbnail Bìa", variable=self.thumbnail)
        c_thumb.pack(side="left")

        # yt-dlp updater
        upd_lbl = ctk.CTkLabel(m_card, text="Cập nhật yt-dlp Core:", font=ctk.CTkFont(size=12, weight="bold"))
        upd_lbl.grid(row=2, column=0, padx=16, pady=10, sticky="w")

        upd_btns = ctk.CTkFrame(m_card, fg_color="transparent")
        upd_btns.grid(row=2, column=1, padx=16, pady=10, sticky="w")

        u_stable = ctk.CTkButton(
            upd_btns,
            text="Cập Nhật Stable",
            width=130,
            height=30,
            command=lambda: self.update_ytdlp_ui(False),
        )
        u_stable.pack(side="left", padx=(0, 8))

        u_nightly = ctk.CTkButton(
            upd_btns,
            text="Cập Nhật Nightly",
            width=130,
            height=30,
            fg_color="#34495e",
            hover_color="#2c3e50",
            command=lambda: self.update_ytdlp_ui(True),
        )
        u_nightly.pack(side="left")

    # =========================================================================
    # GLOBAL BOTTOM STATUS BAR
    # =========================================================================
    def _build_bottom_bar(self) -> None:
        bar = ctk.CTkFrame(self.main_container, corner_radius=10, fg_color=("gray90", "#1e1e1e"))
        bar.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        bar.grid_columnconfigure(0, weight=1)

        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=8)
        inner.grid_columnconfigure(0, weight=1)

        self.status_lbl = ctk.CTkLabel(
            inner,
            textvariable=self.status,
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        )
        self.status_lbl.grid(row=0, column=0, sticky="w")

        self.progress_bar = ctk.CTkProgressBar(inner, height=8, corner_radius=4, progress_color="#10B981")
        self.progress_bar.set(0.0)
        self.progress_bar.grid(row=1, column=0, sticky="ew", pady=(4, 4))

        self.details_lbl = ctk.CTkLabel(
            inner,
            textvariable=self.details,
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w",
        )
        self.details_lbl.grid(row=2, column=0, sticky="w")

    # =========================================================================
    # LOGIC: SINGLE / BATCH DOWNLOAD
    # =========================================================================
    def advanced_options(self) -> AdvancedOptions:
        return AdvancedOptions(
            cookie_browser=self.cookie_browser.get(),
            proxy=self.proxy.get(),
            max_quality=self.max_quality.get(),
            douyin_engine=self.douyin_engine.get(),
            subtitle_languages=self.subtitle_languages.get(),
            impersonate=self.impersonate.get(),
            subtitles=bool(self.subtitles.get()),
            metadata=bool(self.metadata.get()),
            thumbnail=bool(self.thumbnail.get()),
        )

    def fetch_all(self) -> None:
        content = self.url_text.get("1.0", END).strip()
        urls, err = validate_url_input(content)
        if err:
            self.status.set("Lỗi nhập liệu.")
            self.details.set(err)
            messagebox.showerror("Invalid URL", err)
            return
        if not urls:
            self.status.set("Chưa có link.")
            self.details.set("Vui lòng nhập hoặc dán ít nhất 1 đường link hợp lệ.")
            return

        # Auto-detect channel url
        if len(urls) == 1 and is_channel_or_playlist_url(urls[0]):
            norm_url = normalize_url(urls[0])
            self.channel_url_var.set(norm_url)
            self.switch_view("channel")
            self.status.set("Phát hiện link Kênh / Profile Douyin!")
            self.details.set(f"Đã chuyển sang tab Quét Kênh. Bấm 'Quét Kênh' hoặc 'Tải Toàn Kênh (1-Click)'.")
            return

        # Deduplicate input URLs preserving order
        seen_urls = set()
        unique_urls = []
        for u in urls:
            n = normalize_url(u)
            if n not in seen_urls:
                seen_urls.add(n)
                unique_urls.append(n)

        self.fetch_cancel_event.clear()
        self.fetch_in_progress = True
        self.is_fetching = True
        self.fetch_btn.configure(
            text="⏹️ Dừng Quét",
            fg_color="#c0392b",
            hover_color="#e74c3c",
            command=self.cancel_fetch,
        )

        self.status.set(f"Đang phân tích {len(unique_urls)} đường link...")
        self.progress_bar.set(0.1)
        threading.Thread(target=self._fetch_worker, args=(unique_urls, self.advanced_options()), daemon=True).start()

    def cancel_fetch(self) -> None:
        if self.is_fetching:
            self.fetch_cancel_event.set()
            self.status.set("⛔ Đang dừng quét link...")
            self.details.set("Đang dừng phân tích các liên kết còn lại...")

    def paste_and_fetch(self) -> None:
        try:
            clipboard = self.root.clipboard_get()
        except Exception:
            clipboard = ""
        if clipboard.strip():
            self.url_text.delete("1.0", END)
            self.url_text.insert(END, clipboard.strip())
            self.fetch_all()

    def on_url_paste(self, _event: object) -> None:
        self.root.after(50, self.schedule_auto_fetch)

    def schedule_auto_fetch(self) -> None:
        if self.auto_fetch_after_id:
            self.root.after_cancel(self.auto_fetch_after_id)
        self.auto_fetch_after_id = self.root.after(300, self.auto_fetch_current_input)

    def auto_fetch_current_input(self) -> None:
        self.auto_fetch_after_id = None
        content = self.url_text.get("1.0", END).strip()
        if not content or self.fetch_in_progress or self.is_fetching:
            return
        urls, err = validate_url_input(content)
        if not err and urls:
            if len(urls) == 1 and is_channel_or_playlist_url(urls[0]):
                norm_url = normalize_url(urls[0])
                self.channel_url_var.set(norm_url)
                self.switch_view("channel")
                self.status.set("Phát hiện link Kênh / Profile Douyin!")
                self.details.set(f"Đã chuyển sang tab Quét Kênh: {norm_url}.")
                return
            self.fetch_all()

    def _fetch_worker(self, urls: list[str], advanced: AdvancedOptions) -> None:
        for url in urls:
            if self.fetch_cancel_event.is_set():
                break

            normalized = normalize_url(url)
            # Deduplication: check if URL already exists in self.items
            existing_id = next((iid for iid, data in self.items.items() if data.get("url") == normalized), None)
            if existing_id:
                # If already Done, skip re-scanning
                if self.items[existing_id].get("status") == "Done":
                    continue
                item_id = existing_id
                self.events.put(("row_status", {"id": item_id, "status": "Scanning...", "detail": f"Đang lấy thông tin..."}))
            else:
                item_id = str(uuid.uuid4())
                self.events.put(
                    (
                        "add_row",
                        {
                            "id": item_id,
                            "url": normalized,
                            "status": "Scanning...",
                            "detail": f"Đang lấy thông tin từ {normalized}...",
                        },
                    )
                )

            if self.fetch_cancel_event.is_set():
                break

            try:
                info = fetch_video_info(normalized, timeout=30, advanced=advanced)
                self.events.put(("info", {"id": item_id, "info": info, "advanced": advanced}))
            except Exception as exc:
                err_text = friendly_error(str(exc))
                log_event(f"UI info error url={normalized} error={exc}")
                self.events.put(("error", {"id": item_id, "error": err_text}))

        if self.fetch_cancel_event.is_set():
            self.events.put(("fetch_cancelled", None))
        else:
            self.events.put(("fetch_done", None))

    def clear_queue(self) -> None:
        if self.is_downloading:
            messagebox.showwarning("Đang tải", "Tiến trình tải đang chạy. Vui lòng bấm 'Dừng Tải' trước khi xóa hàng đợi.")
            return
        self.table.delete(*self.table.get_children())
        self.items.clear()
        self.url_text.delete("1.0", END)
        self.status.set("Đã dọn sạch hàng đợi tải.")
        self.details.set("Bạn có thể dán link mới hoặc chuyển video từ tab Quét Kênh sang.")
        self.progress_bar.set(0.0)

    def translate_all_queue(self) -> None:
        if not self.items:
            messagebox.showinfo("Trống", "Hàng đợi đang trống. Vui lòng dán link hoặc quét kênh trước.")
            return

        self.status.set(f"⏳ Đang dịch {len(self.items)} tiêu đề sang Tiếng Việt...")
        self.progress_bar.set(0.1)

        def _worker():
            try:
                titles = [it.get("original_title") or it.get("title", "") for it in self.items.values()]
                translations = batch_translate_texts(titles)
                for item_id, it in self.items.items():
                    orig = it.get("original_title") or it.get("title", "")
                    if orig in translations:
                        it["translated_title"] = translations[orig]
                        it["title"] = translations[orig]
                        it["detail"] = f"Đã sẵn sàng tải: {it['title']}"
                self.events.put(("queue_titles_updated", None))
            except Exception as exc:
                self.events.put(("status", f"Lỗi dịch tiêu đề: {exc}"))

        threading.Thread(target=_worker, daemon=True).start()

    def revert_all_queue_titles(self) -> None:
        for item_id, it in self.items.items():
            if it.get("original_title"):
                it["title"] = it["original_title"]
                it["detail"] = f"Đã sẵn sàng tải: {it['title']}"
                self._update_row(item_id)
        self.status.set("Đã chuyển về tiêu đề gốc.")
        self.details.set("Toàn bộ tiêu đề trong hàng đợi đã được khôi phục về ngôn ngữ gốc.")

    def set_quality(self) -> None:
        selected = self.table.selection()
        if not selected:
            return
        chosen = self.quality.get()
        media_fmt = self.media_format.get()
        for item_id in selected:
            item = self.items[item_id]
            formats = [fmt for fmt in item.get("formats") or [] if is_format_compatible(fmt, media_fmt)]
            matched = next((fmt for fmt in formats if format_option_label(fmt) == chosen), None)
            if matched:
                item["quality"] = chosen
                item["format_id"] = matched.get("id")
                self._update_row(item_id)
        self.status.set(f"Đã đặt tùy chọn: {chosen}")

    def on_selection_changed(self, _event: object = None) -> None:
        selected = self.table.selection()
        if not selected:
            return
        item_id = selected[0]
        item = self.items.get(item_id, {})
        detail_msg = str(item.get("detail") or item.get("title") or "")
        file_path = str(item.get("file_path") or "")
        if file_path:
            detail_msg += f" | File: {file_path}"
        self.details.set(detail_msg)

        # Update quality dropdown for selection
        media_fmt = self.media_format.get()
        formats = [fmt for fmt in item.get("formats") or [] if is_format_compatible(fmt, media_fmt)]
        options = ["Best"]
        for fmt in formats:
            lbl = format_option_label(fmt)
            if lbl not in options:
                options.append(lbl)
        self.quality_box.configure(values=options)

    def download_selected(self) -> None:
        selected = list(self.table.selection())
        if not selected:
            messagebox.showinfo("Chưa chọn", "Vui lòng chọn ít nhất một video trong bảng để tải.")
            return
        self._download_items(selected)

    def download_all(self) -> None:
        if not self.items:
            messagebox.showinfo("Trống", "Vui lòng quét thông tin các đường link trước.")
            return

        # Deduplicate & only download pending/error items (exclude already Done)
        pending_ids = [
            iid for iid, itm in self.items.items()
            if itm.get("status") != "Done"
        ]
        if not pending_ids:
            messagebox.showinfo("Đã hoàn tất", "Tất cả các video trong danh sách đều đã được tải xong!")
            return

        self._download_items(pending_ids)

    def cancel_download(self) -> None:
        self.download_cancel_event.set()
        if self.is_downloading:
            self.status.set("⛔ Đang dừng tải video...")
            self.details.set("Đang hoàn tất ngắt tiến trình tải hiện tại...")

    def _download_items(self, item_ids: list[str]) -> None:
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.download_cancel_event.clear()
        self.is_downloading = True
        self.stop_dl_btn.configure(state="normal")
        self.dl_all_btn.configure(state="disabled")
        self.dl_sel_btn.configure(state="disabled")

        media_fmt = self.media_format.get()
        label = "MP3" if media_fmt == "audio" else "MP4"
        self.status.set(f"Đang tải {len(item_ids)} mục dạng {label}...")
        self.progress_bar.set(0.05)
        threading.Thread(
            target=self._download_worker,
            args=(item_ids, media_fmt, self.advanced_options()),
            daemon=True,
        ).start()

    def _download_worker(self, item_ids: list[str], media_format: str, advanced: AdvancedOptions) -> None:
        total = len(item_ids)
        cancelled = False
        for idx, item_id in enumerate(item_ids, start=1):
            if self.download_cancel_event.is_set():
                cancelled = True
                self.events.put(("row_status", {"id": item_id, "status": "Cancelled", "detail": "Đã dừng tải."}))
                break

            item = self.items[item_id]
            url = str(item.get("url", ""))
            title = str(item.get("title", ""))
            format_id = item.get("format_id")
            fid_str = str(format_id) if format_id is not None else None

            self.events.put(("row_status", {"id": item_id, "status": "Downloading...", "detail": f"Đang tải: {title}"}))
            self.events.put(("status", f"[{idx}/{total}] Đang tải: {title[:40]}..."))

            def progress_cb(pct: int) -> None:
                self.events.put(("row_progress", {"id": item_id, "progress": pct}))
                overall = ((idx - 1) + (pct / 100.0)) / total
                self.events.put(("progress_value", overall))

            try:
                dest = download_media(
                    url=url,
                    download_dir=self.download_dir,
                    job_id=str(uuid.uuid4()),
                    media_format=media_format,
                    title=title,
                    format_id=fid_str,
                    progress_callback=progress_cb,
                    advanced=advanced,
                    cancel_event=self.download_cancel_event,
                )
                record_history(url, str(dest), title, media_format)
                self.events.put(("row_done", {"id": item_id, "path": str(dest), "detail": f"Lưu tại: {dest.name}"}))
                self.events.put(("history_refresh", None))
            except Exception as exc:
                if self.download_cancel_event.is_set():
                    cancelled = True
                    self.events.put(("row_status", {"id": item_id, "status": "Cancelled", "detail": "Đã hủy tải."}))
                    break
                err_text = friendly_error(str(exc))
                log_event(f"UI download error url={url} error={exc}")
                self.events.put(("row_status", {"id": item_id, "status": "Error", "detail": err_text}))

        if not cancelled:
            self.events.put(("progress_value", 1.0))
            self.events.put(("status", f"Hoàn tất tải {total} mục!"))
        self.events.put(("download_done", cancelled))

    def choose_folder(self) -> None:
        selected = filedialog.askdirectory(initialdir=str(self.download_dir))
        if selected:
            self.download_dir = Path(selected)
            self.status.set(f"Thư mục lưu mới: {self.download_dir}")

    def open_folder(self) -> None:
        self.download_dir.mkdir(parents=True, exist_ok=True)
        webbrowser.open(str(self.download_dir))

    def open_selected_file(self) -> None:
        selected = self.table.selection()
        if not selected:
            messagebox.showinfo("Chưa chọn", "Vui lòng chọn một dòng đã tải thành công.")
            return
        item = self.items.get(selected[0], {})
        file_path = str(item.get("file_path") or "")
        if file_path and Path(file_path).exists():
            webbrowser.open(file_path)
        else:
            messagebox.showinfo("Chưa có file", "Mục này chưa được tải về hoặc file đã bị di chuyển.")

    # =========================================================================
    # LOGIC: CHANNEL / BATCH EXTRACTOR
    # =========================================================================
    def fetch_channel_videos_ui(self) -> None:
        raw_url = self.channel_url_var.get().strip()
        if not raw_url:
            messagebox.showinfo("Cần link", "Vui lòng nhập đường link kênh Douyin/YouTube.")
            return
        url = normalize_url(raw_url)
        self.channel_url_var.set(url)

        limit_str = self.channel_limit_var.get().strip().lower()
        limit = 0 if limit_str in {"all", "tất cả", ""} else int(limit_str)
        keyword = self.channel_keyword_var.get().strip()

        self.channel_cancel_event.clear()
        self.is_channel_fetching = True
        self.channel_fetch_btn.configure(state="disabled")
        self.channel_stop_btn.configure(state="normal")

        self.status.set("⏳ Đang quét danh sách video của kênh...")
        self.details.set(f"Hệ thống đang trích xuất danh sách video từ kênh: {url}")
        self.progress_bar.set(0.2)

        threading.Thread(
            target=self._channel_fetch_worker,
            args=(url, limit, keyword, self.advanced_options()),
            daemon=True,
        ).start()

    def cancel_channel_fetch(self) -> None:
        self.channel_cancel_event.set()
        if self.is_channel_fetching:
            self.status.set("⛔ Đang dừng quét kênh...")
            self.details.set("Đang dừng trình duyệt và xuất các video đã quét được...")

    def _channel_fetch_worker(self, url: str, limit: int, keyword: str, advanced: AdvancedOptions) -> None:
        try:
            items = fetch_channel_videos(url, limit=limit, keyword=keyword, advanced=advanced, cancel_event=self.channel_cancel_event)
            self.events.put(("channel_fetch_done", items))
        except Exception as exc:
            log_event(f"UI channel fetch error url={url} error={exc}")
            self.events.put(("channel_fetch_error", friendly_error(str(exc))))

    def translate_channel_items(self) -> None:
        if not self.channel_items:
            messagebox.showinfo("Trống", "Vui lòng quét danh sách video của kênh trước.")
            return

        self.status.set(f"⏳ Đang dịch {len(self.channel_items)} video sang Tiếng Việt...")
        self.progress_bar.set(0.1)

        def _worker():
            try:
                titles = [it.get("original_title") or it.get("title", "") for it in self.channel_items]
                translations = batch_translate_texts(titles)
                for it in self.channel_items:
                    orig = it.get("original_title") or it.get("title", "")
                    if orig in translations:
                        it["translated_title"] = translations[orig]
                        it["title"] = translations[orig]
                self.events.put(("channel_titles_translated", None))
            except Exception as exc:
                self.events.put(("status", f"Lỗi dịch tiêu đề: {exc}"))

        threading.Thread(target=_worker, daemon=True).start()

    def _populate_channel_table(self, items: list[dict[str, Any]]) -> None:
        # Clear existing
        self.channel_table.delete(*self.channel_table.get_children())
        for widget in self.channel_card_widgets:
            try:
                widget.destroy()
            except Exception:
                pass
        self.channel_card_widgets.clear()
        self.channel_card_checkbox_vars.clear()
        self.channel_card_checkboxes.clear()
        self.channel_card_title_labels.clear()
        self.channel_selected_indices.clear()
        self.channel_selected_ids.clear()

        # Populate List View (Table)
        for idx, item in enumerate(items):
            raw_title = str(item.get("title") or "Douyin Video")
            if "original_title" not in item:
                item["original_title"] = raw_title
                item["clean_title"] = clean_title(raw_title)
            dur = item.get("duration")
            dur_text = format_duration(dur) if dur else ""
            self.channel_table.insert(
                "",
                END,
                iid=f"citem-{idx}",
                values=(
                    "[ ]",
                    item.get("title", ""),
                    item.get("uploader", ""),
                    dur_text,
                    item.get("url", ""),
                ),
            )

        # Populate Grid View (Visual Cards)
        for idx, item in enumerate(items):
            title = str(item.get("title") or "Douyin Video")
            uploader = str(item.get("uploader") or "Douyin Creator")
            dur = item.get("duration")
            dur_str = format_duration(dur) if dur else ""
            thumb_url = str(item.get("thumbnail") or "")
            vurl = str(item.get("url") or "")

            card = ctk.CTkFrame(self.channel_grid_scroll, corner_radius=10, fg_color=("gray85", "#242424"))
            card.grid(row=idx // 4, column=idx % 4, padx=8, pady=8, sticky="nsew")
            self.channel_card_widgets.append(card)

            # Thumbnail Image Label
            thumb_lbl = ctk.CTkLabel(card, text="", cursor="hand2")
            thumb_lbl.pack(padx=8, pady=(8, 4))
            placeholder = self.thumbnail_cache.load_thumbnail_async(
                thumb_url,
                callback=lambda img, lbl=thumb_lbl: lbl.configure(image=img),
                tk_root=self.root,
            )
            thumb_lbl.configure(image=placeholder)

            # Title & Meta
            display_title = title if len(title) <= 55 else title[:52] + "..."
            t_lbl = ctk.CTkLabel(
                card,
                text=display_title,
                font=ctk.CTkFont(size=11, weight="bold"),
                wraplength=180,
                justify="left",
                anchor="w",
                cursor="hand2",
            )
            t_lbl.pack(padx=8, pady=2, fill="x")
            self.channel_card_title_labels.append(t_lbl)

            meta_frame = ctk.CTkFrame(card, fg_color="transparent")
            meta_frame.pack(fill="x", padx=8, pady=(0, 6))

            u_lbl = ctk.CTkLabel(
                meta_frame,
                text=f"👤 {uploader[:14]}",
                font=ctk.CTkFont(size=10),
                text_color="gray",
                anchor="w",
            )
            u_lbl.pack(side="left")

            if dur_str:
                d_badge = ctk.CTkLabel(
                    meta_frame,
                    text=f"⏱️ {dur_str}",
                    font=ctk.CTkFont(size=10),
                    text_color="gray",
                )
                d_badge.pack(side="right")

            # Checkbox & Quick Download button
            action_frame = ctk.CTkFrame(card, fg_color="transparent")
            action_frame.pack(fill="x", padx=8, pady=(0, 8))

            chk_var = BooleanVar(value=False)
            self.channel_card_checkbox_vars.append(chk_var)

            def make_chk_cmd(i=idx, c_var=chk_var):
                def _cmd():
                    if c_var.get():
                        self.channel_selected_indices.add(i)
                    else:
                        self.channel_selected_indices.discard(i)
                    self._sync_channel_selection_ui(update_cards=False)
                return _cmd

            chk = ctk.CTkCheckBox(
                action_frame,
                text="Chọn",
                variable=chk_var,
                command=make_chk_cmd(idx, chk_var),
                width=60,
                font=ctk.CTkFont(size=11),
            )
            chk.pack(side="left")
            self.channel_card_checkboxes.append(chk)

            # Clicking thumbnail or title toggles checkbox
            def make_toggle_cmd(i=idx):
                def _toggle(event=None):
                    if i in self.channel_selected_indices:
                        self.channel_selected_indices.discard(i)
                    else:
                        self.channel_selected_indices.add(i)
                    self._sync_channel_selection_ui(update_cards=True)
                return _toggle

            toggle_fn = make_toggle_cmd(idx)
            thumb_lbl.bind("<Button-1>", toggle_fn)
            t_lbl.bind("<Button-1>", toggle_fn)

            quick_dl = ctk.CTkButton(
                action_frame,
                text="⬇️ Tải",
                width=65,
                height=26,
                font=ctk.CTkFont(size=11),
                command=lambda u=vurl, t=title: self._quick_download_video(u, t),
            )
            quick_dl.pack(side="right")

        self._sync_channel_selection_ui(update_cards=True)

    def _sync_channel_selection_ui(self, update_cards: bool = True) -> None:
        count = len(self.channel_selected_indices)
        total = len(self.channel_items)
        self.channel_selection_info_lbl.configure(text=f"Đã chọn: {count} / {total} video")

        # Sync Table rows
        for idx in range(total):
            row_id = f"citem-{idx}"
            if self.channel_table.exists(row_id):
                is_sel = idx in self.channel_selected_indices
                vals = list(self.channel_table.item(row_id, "values"))
                target_mark = "[x]" if is_sel else "[ ]"
                if vals and vals[0] != target_mark:
                    vals[0] = target_mark
                    self.channel_table.item(row_id, values=vals)

        # Sync Card checkboxes
        if update_cards:
            for idx, chk in enumerate(self.channel_card_checkboxes):
                is_sel = idx in self.channel_selected_indices
                if is_sel:
                    chk.select()
                else:
                    chk.deselect()

        # Keep channel_selected_ids in sync
        self.channel_selected_ids.clear()
        for idx in self.channel_selected_indices:
            if idx < len(self.channel_items):
                item = self.channel_items[idx]
                v_id = str(item.get("id") or item.get("url") or f"channel-{idx}")
                self.channel_selected_ids.add(v_id)

    def _update_channel_selection_info(self) -> None:
        self._sync_channel_selection_ui(update_cards=False)

    def _quick_download_video(self, url: str, title: str) -> None:
        if not url:
            return
        self.status.set(f"Đang tải video: {title[:35]}...")
        self.progress_bar.set(0.1)
        media_fmt = self.media_format.get()

        def _worker():
            try:
                dest = download_media(
                    url=url,
                    download_dir=self.download_dir,
                    job_id=str(uuid.uuid4()),
                    media_format=media_fmt,
                    title=title,
                    advanced=self.advanced_options(),
                )
                record_history(url, str(dest), title, media_fmt)
                self.events.put(("status", f"✅ Đã tải xong: {dest.name}"))
                self.events.put(("details", f"File lưu tại: {dest}"))
                self.events.put(("history_refresh", None))
                self.events.put(("progress_value", 1.0))
            except Exception as exc:
                self.events.put(("status", "Lỗi tải video."))
                self.events.put(("details", friendly_error(str(exc))))

        threading.Thread(target=_worker, daemon=True).start()

    def on_channel_table_click(self, event: object) -> None:
        region = self.channel_table.identify("region", event.x, event.y)
        if region == "cell":
            col = self.channel_table.identify_column(event.x)
            if col == "#1":
                row_id = self.channel_table.identify_row(event.y)
                if row_id and row_id.startswith("citem-"):
                    try:
                        idx = int(row_id.replace("citem-", ""))
                    except ValueError:
                        return
                    if idx in self.channel_selected_indices:
                        self.channel_selected_indices.discard(idx)
                    else:
                        self.channel_selected_indices.add(idx)
                    self._sync_channel_selection_ui(update_cards=True)

    def channel_select_all(self) -> None:
        self.channel_selected_indices = set(range(len(self.channel_items)))
        self._sync_channel_selection_ui(update_cards=True)

    def channel_deselect_all(self) -> None:
        self.channel_selected_indices.clear()
        self._sync_channel_selection_ui(update_cards=True)

    def add_channel_selected_to_queue(self) -> None:
        selected_indices = sorted(self.channel_selected_indices)
        selected_items = []
        for idx in selected_indices:
            if idx < len(self.channel_items):
                selected_items.append(self.channel_items[idx])

        if not selected_items:
            # Fallback to check table column
            for row_id in self.channel_table.get_children():
                vals = self.channel_table.item(row_id, "values")
                if vals and vals[0] == "[x]" and len(vals) > 4 and vals[4]:
                    matching = next((it for it in self.channel_items if str(it.get("url")) == str(vals[4])), None)
                    if matching:
                        selected_items.append(matching)
                    else:
                        selected_items.append({"url": str(vals[4]), "title": vals[1], "uploader": vals[2]})

        if not selected_items:
            messagebox.showinfo("Chưa chọn", "Vui lòng tích chọn ít nhất 1 video.")
            return

        existing_urls = {data.get("url") for data in self.items.values()}
        added_count = 0
        all_urls = []

        for item in selected_items:
            u = str(item.get("url") or "")
            if not u:
                continue
            all_urls.append(u)
            if u in existing_urls:
                continue
            existing_urls.add(u)

            item_id = str(uuid.uuid4())
            dur_val = item.get("duration")
            dur_text = format_duration(dur_val) if dur_val else ""
            uploader = str(item.get("uploader") or "Douyin Creator")

            orig_title = str(item.get("original_title") or item.get("title") or "Douyin Video")
            clean_t = str(item.get("clean_title") or clean_title(orig_title))
            trans_t = str(item.get("translated_title") or "")

            if trans_t:
                display_title = trans_t
            elif self.auto_translate.get():
                trans_t = translate_text(orig_title)
                display_title = trans_t or clean_t
            else:
                display_title = str(item.get("title") or clean_t)

            self.items[item_id] = {
                "id": item_id,
                "url": u,
                "status": "Ready",
                "detail": f"Đã sẵn sàng tải: {display_title}",
                "original_title": orig_title,
                "clean_title": clean_t,
                "translated_title": trans_t,
                "title": display_title,
                "uploader": uploader,
                "duration": dur_text,
                "provider": "Douyin",
                "formats": [],
                "quality": "Best",
                "progress": "",
                "file_name": "",
            }
            self.table.insert(
                "",
                END,
                iid=item_id,
                values=(display_title, uploader, dur_text, "Douyin", "Best", "", "Ready", ""),
            )
            added_count += 1

        self.switch_view("single")
        self.status.set(f"✅ Đã thêm {added_count} video vào hàng đợi tải (Tổng {len(self.items)} video).")
        self.details.set("Bạn có thể bấm '⚡ Tải Tất Cả' để bắt đầu tải ngay lập tức.")

    def download_channel_directly_ui(self) -> None:
        raw_url = self.channel_url_var.get().strip()
        if not raw_url:
            messagebox.showinfo("Cần link", "Vui lòng nhập đường link kênh Douyin.")
            return
        url = normalize_url(raw_url)
        self.channel_url_var.set(url)

        limit_str = self.channel_limit_var.get().strip().lower()
        limit = 0 if limit_str in {"all", "tất cả", ""} else int(limit_str)

        self.status.set(f"⏳ Bắt đầu tải toàn kênh 1-Click: {url}")
        self.details.set("Đang khởi tạo engine tải kênh...")
        self.progress_bar.set(0.05)

        threading.Thread(
            target=self._channel_download_worker,
            args=(url, limit, self.advanced_options()),
            daemon=True,
        ).start()

    def _channel_download_worker(self, url: str, limit: int, advanced: AdvancedOptions) -> None:
        def progress_cb(pct: int, msg: str) -> None:
            self.events.put(("channel_download_progress", (pct, msg)))

        try:
            summary = download_channel_with_jiji262(
                url=url,
                download_dir=self.download_dir,
                advanced=advanced,
                limit=limit,
                progress_callback=progress_cb,
            )
            self.events.put(("channel_download_done", summary))
        except Exception as exc:
            log_event(f"UI direct channel download error url={url} error={exc}")
            self.events.put(("channel_download_error", friendly_error(str(exc))))

    # =========================================================================
    # DIALOGS & SETTINGS ACTIONS
    # =========================================================================
    def open_douyin_cookie_dialog(self) -> None:
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Nhập Douyin Cookie Thủ Công")
        dialog.geometry("560x360")
        dialog.transient(self.root)
        dialog.grab_set()

        lbl = ctk.CTkLabel(
            dialog,
            text="Dán chuỗi Cookie từ trình duyệt của bạn vào đây:",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        lbl.pack(padx=16, pady=(16, 6), anchor="w")

        hint = ctk.CTkLabel(
            dialog,
            text="Hướng dẫn: Mở Douyin.com trên Chrome -> F12 -> Console -> gõ document.cookie rồi copy dán vào đây.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            wraplength=520,
            justify="left",
        )
        hint.pack(padx=16, pady=(0, 10), anchor="w")

        cookie_txt = ctk.CTkTextbox(dialog, height=140, font=ctk.CTkFont(family="Consolas", size=11))
        cookie_txt.pack(fill="x", padx=16, pady=(0, 12))

        btn_bar = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_bar.pack(fill="x", padx=16, pady=4)

        def save_action():
            val = cookie_txt.get("1.0", END).strip()
            if not val:
                messagebox.showwarning("Trống", "Vui lòng nhập chuỗi cookie.")
                return
            try:
                cfile = save_douyin_cookie_string(val)
                count = len(load_douyin_cookies(None))
                self.cookie_status_badge.configure(
                    text=f"🟢 Douyin Cookies ({count})",
                    text_color="#2ecc71",
                )
                messagebox.showinfo("Thành công", f"Đã lưu thành công {count} cookie vào:\n{cfile}")
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Lỗi", str(e))

        save_btn = ctk.CTkButton(btn_bar, text="💾 Lưu Cookie", width=120, height=32, command=save_action)
        save_btn.pack(side="right")

        cancel_btn = ctk.CTkButton(btn_bar, text="Hủy", width=90, height=32, fg_color="#7f8c8d", hover_color="#95a5a6", command=dialog.destroy)
        cancel_btn.pack(side="right", padx=(0, 8))

    def setup_douyin_cookies(self) -> None:
        try:
            self.status.set("Đang mở trình duyệt đăng nhập...")
            self.details.set("Một cửa sổ Chromium sẽ mở ra. Đăng nhập hoặc giải captcha nếu có, sau đó cookie sẽ tự lưu.")
            run_setup_cookies()
        except Exception as exc:
            self.status.set("Lỗi mở trình duyệt đăng nhập.")
            self.details.set(friendly_error(str(exc)))

    def update_ytdlp_ui(self, nightly: bool) -> None:
        label = "nightly" if nightly else "stable"
        self.status.set(f"Đang cập nhật yt-dlp ({label})...")
        threading.Thread(target=self._update_ytdlp_worker, args=(nightly,), daemon=True).start()

    def _update_ytdlp_worker(self, nightly: bool) -> None:
        try:
            res = update_ytdlp(nightly=nightly)
            self.events.put(("status", f"yt-dlp: {res.strip()[:60]}"))
            self.events.put(("details", res.strip()))
        except Exception as exc:
            self.events.put(("status", "Lỗi cập nhật yt-dlp."))
            self.events.put(("details", str(exc)))

    def refresh_history(self) -> None:
        self.history_table.delete(*self.history_table.get_children())
        entries = load_history()
        for idx, entry in enumerate(reversed(entries)):
            self.history_table.insert(
                "",
                END,
                iid=f"hist-{idx}",
                values=(
                    entry.get("title", ""),
                    entry.get("format", ""),
                    entry.get("timestamp", ""),
                    entry.get("path", ""),
                    entry.get("url", ""),
                ),
            )

    def open_history_file(self) -> None:
        from .core import HISTORY_FILE
        if HISTORY_FILE.exists():
            webbrowser.open(str(HISTORY_FILE))
        else:
            messagebox.showinfo("Lịch sử", "Chưa có file history.json.")

    def _check_tools(self) -> None:
        ffmpeg = find_ffmpeg_location()
        if not ffmpeg:
            self.details.set("Cảnh báo: Không tìm thấy ffmpeg. Một số định dạng có thể bị giới hạn.")

    def close(self) -> None:
        try:
            cleanup_temp_files(self.download_dir, max_age_seconds=0)
        except Exception:
            pass
        log_event("APP close")
        self.root.destroy()

    # =========================================================================
    # 1-CLICK AUTO UPDATER
    # =========================================================================
    def check_and_update_ui(self) -> None:
        self.status.set("🔍 Đang kiểm tra bản cập nhật từ GitHub...")
        self.details.set("Đang kết nối đến kho lưu trữ GitHub để kiểm tra phiên bản mới nhất...")
        self.progress_bar.set(0.2)

        def _worker() -> None:
            try:
                info = check_for_updates()
                self.events.put(("update_check_done", info))
            except Exception as exc:
                self.events.put(("update_check_error", str(exc)))

        threading.Thread(target=_worker, daemon=True).start()

    def _start_apply_update(self) -> None:
        self.status.set("⏳ Đang chuẩn bị cập nhật...")
        self.details.set("Vui lòng đợi giây lát trong khi ứng dụng tải phiên bản mới...")
        self.progress_bar.set(0.3)

        def _worker() -> None:
            def _cb(msg: str) -> None:
                self.events.put(("update_applying", msg))

            try:
                success, msg = perform_one_click_update(progress_callback=_cb)
                if success:
                    self.events.put(("update_ready_restart", msg))
                else:
                    self.events.put(("update_failed", msg))
            except Exception as exc:
                self.events.put(("update_failed", str(exc)))

        threading.Thread(target=_worker, daemon=True).start()

    # =========================================================================
    # EVENT LOOP & POLLING
    # =========================================================================
    def _poll_events(self) -> None:
        while True:
            try:
                event, payload = self.events.get_nowait()
            except queue.Empty:
                break
            self._handle_event(event, payload)
        self.root.after(100, self._poll_events)

    def _handle_event(self, event: str, payload: Any) -> None:
        if event == "add_row":
            data = dict(payload)
            item_id = str(data["id"])
            self.items[item_id] = {
                "id": item_id,
                "url": data["url"],
                "status": data.get("status", "Pending"),
                "detail": data.get("detail", ""),
                "title": "",
                "uploader": "",
                "duration": "",
                "provider": "",
                "quality": "Best",
                "progress": "",
                "file_name": "",
            }
            self.table.insert(
                "",
                END,
                iid=item_id,
                values=("", "", "", "", "Best", "", data.get("status", "Pending"), ""),
            )
        elif event == "info":
            data = dict(payload)
            item_id = str(data["id"])
            info = dict(data["info"])
            raw_title = str(info.get("title") or "Video")
            uploader = str(info.get("uploader") or "")
            dur_text = format_duration(info.get("duration"))
            provider = str(info.get("provider") or "Direct")
            formats = list(info.get("formats") or [])

            cleaned = clean_title(raw_title)
            translated = ""
            display_title = cleaned

            if self.auto_translate.get():
                try:
                    translated = translate_text(raw_title)
                    display_title = translated or cleaned
                except Exception:
                    display_title = cleaned

            self.items[item_id].update(
                {
                    "original_title": raw_title,
                    "clean_title": cleaned,
                    "translated_title": translated,
                    "title": display_title,
                    "uploader": uploader,
                    "duration": dur_text,
                    "provider": provider,
                    "formats": formats,
                    "status": "Ready",
                    "detail": f"Đã sẵn sàng tải: {display_title}",
                }
            )
            self._update_row(item_id)
        elif event == "error":
            data = dict(payload)
            item_id = str(data["id"])
            if item_id in self.items:
                self.items[item_id]["status"] = "Error"
                self.items[item_id]["detail"] = data["error"]
                self._update_row(item_id)
        elif event == "row_status":
            data = dict(payload)
            item_id = str(data["id"])
            if item_id in self.items:
                self.items[item_id]["status"] = data["status"]
                if data["status"] in ("Error", "Cancelled"):
                    if self.items[item_id].get("progress") == "100%":
                        self.items[item_id]["progress"] = "0%"
                if data.get("detail"):
                    self.items[item_id]["detail"] = data["detail"]
                self._update_row(item_id)
        elif event == "row_progress":
            data = dict(payload)
            item_id = str(data["id"])
            if item_id in self.items:
                pct_str = f"{int(data['progress'])}%"
                self.items[item_id]["progress"] = pct_str
                self.table.set(item_id, "progress", pct_str)
        elif event == "row_done":
            data = dict(payload)
            item_id = str(data["id"])
            if item_id in self.items:
                path = Path(str(data["path"]))
                self.items[item_id]["file_path"] = str(path)
                self.items[item_id]["file_name"] = path.name
                self.items[item_id]["progress"] = "100%"
                self.items[item_id]["status"] = "Done"
                self.items[item_id]["detail"] = data.get("detail") or "Download completed."
                self._update_row(item_id)
        elif event == "channel_fetch_done":
            self.is_channel_fetching = False
            self.channel_fetch_btn.configure(state="normal")
            self.channel_stop_btn.configure(state="disabled")
            items = list(payload) if isinstance(payload, list) else []
            self.channel_items = items
            self._populate_channel_table(items)
            if self.channel_cancel_event.is_set():
                self.status.set(f"⚠️ Đã dừng quét kênh: Thu thập được {len(items)} video.")
                self.details.set(f"Đã nạp {len(items)} video quét được trước khi dừng.")
            else:
                self.status.set(f"✅ Quét kênh hoàn tất: Tìm thấy {len(items)} video.")
                self.details.set(f"Đã nạp {len(items)} video. Bạn có thể chọn tải từng video hoặc bấm 'Tải Toàn Kênh (1-Click)'.")
            self.progress_bar.set(1.0)
        elif event == "channel_fetch_error":
            self.is_channel_fetching = False
            self.channel_fetch_btn.configure(state="normal")
            self.channel_stop_btn.configure(state="disabled")
            err_msg = str(payload)
            self.status.set("❌ Lỗi quét kênh.")
            self.details.set(err_msg)
            self.progress_bar.set(0.0)
            messagebox.showerror("Channel Fetch Error", err_msg)
        elif event == "channel_download_progress":
            pct, msg = payload
            self.progress_bar.set(max(0.01, min(1.0, pct / 100.0)))
            self.status.set(f"⏳ Đang tải toàn kênh ({pct}%)...")
            self.details.set(msg)
        elif event == "channel_download_done":
            summary = dict(payload)
            success = summary.get("success", 0)
            skipped = summary.get("skipped", 0)
            failed = summary.get("failed", 0)
            author = summary.get("author", "Douyin Creator")
            msg = f"Kênh '{author}' tải hoàn tất!\n- Thành công: {success}\n- Bỏ qua (đã có): {skipped}\n- Lỗi: {failed}"
            self.progress_bar.set(1.0)
            self.status.set(f"✅ Hoàn tất tải kênh! Đã lưu {success} video mới.")
            self.details.set(msg.replace("\n", " | "))
            messagebox.showinfo("Tải Kênh Hoàn Tất", msg)
            self.refresh_history()
        elif event == "channel_download_error":
            err_msg = str(payload)
            self.status.set("❌ Lỗi tải kênh.")
            self.details.set(err_msg)
            self.progress_bar.set(0.0)
            messagebox.showerror("Channel Download Error", err_msg)
        elif event == "download_done":
            is_cancelled = bool(payload)
            self.is_downloading = False
            self.stop_dl_btn.configure(state="disabled")
            self.dl_all_btn.configure(state="normal")
            self.dl_sel_btn.configure(state="normal")
            if is_cancelled:
                self.status.set("⛔ Đã dừng tải video theo yêu cầu.")
                self.details.set("Bạn có thể bấm '⚡ Tải Tất Cả' để tiếp tục tải các mục còn lại.")
        elif event == "status":
            self.status.set(str(payload))
        elif event == "details":
            self.details.set(str(payload))
        elif event == "progress_value":
            try:
                self.progress_bar.set(float(payload))
            except Exception:
                pass
        elif event == "history_refresh":
            self.refresh_history()
        elif event == "queue_titles_updated":
            for item_id in self.items:
                self._update_row(item_id)
            self.status.set(f"✅ Đã dịch xong {len(self.items)} tiêu đề sang Tiếng Việt!")
            self.details.set("Tất cả tiêu đề trong hàng đợi đã sẵn sàng để tải với tên Tiếng Việt.")
            self.progress_bar.set(1.0)
        elif event == "channel_titles_translated":
            for idx, lbl in enumerate(self.channel_card_title_labels):
                if idx < len(self.channel_items):
                    t = self.channel_items[idx].get("title", "")
                    display = t if len(t) <= 55 else t[:52] + "..."
                    lbl.configure(text=display)
            for idx in range(len(self.channel_items)):
                row_id = f"citem-{idx}"
                if self.channel_table.exists(row_id):
                    vals = list(self.channel_table.item(row_id, "values"))
                    vals[1] = self.channel_items[idx].get("title", "")
                    self.channel_table.item(row_id, values=vals)
            self.status.set(f"✅ Đã dịch thành công {len(self.channel_items)} video sang Tiếng Việt!")
            self.details.set("Tất cả thẻ video và danh sách đã được cập nhật sang Tiếng Việt.")
            self.progress_bar.set(1.0)
        elif event in ("fetch_done", "fetch_cancelled"):
            self.fetch_in_progress = False
            self.is_fetching = False
            self.fetch_btn.configure(
                text="🔍 Quét Link",
                fg_color="#4F46E5",
                hover_color="#4338CA",
                command=self.fetch_all,
            )
            if event == "fetch_cancelled":
                self.status.set("⛔ Đã dừng quét link.")
                self.details.set("Tiến trình quét liên kết đã dừng lại.")
        elif event == "update_check_done":
            info = dict(payload)
            if info.get("update_available"):
                ver = info.get("latest_version")
                title = info.get("release_title") or f"Phiên bản {ver}"
                notes = info.get("changelog", "Tối ưu hóa và nâng cấp tính năng mới.")
                self.status.set(f"🚀 Có bản cập nhật mới: {ver}")
                self.details.set(f"Phiên bản mới: {title} đã sẵn sàng.")
                if messagebox.askyesno(
                    "Có Bản Cập Nhật Mới! 🚀",
                    f"Phát hiện bản cập nhật mới: {title} (v{ver})\n\n"
                    f"Nội dung thay đổi:\n{notes}\n\n"
                    f"Bạn có muốn cập nhật ứng dụng tự động ngay bây giờ không?",
                ):
                    self._start_apply_update()
            else:
                self.status.set(f"✅ Ứng dụng đã ở phiên bản mới nhất (v{APP_VERSION}).")
                self.details.set("Bạn đang sử dụng bản phát hành mới nhất từ GitHub.")
                messagebox.showinfo(
                    "Kiểm Tra Cập Nhật",
                    f"Ứng dụng đang ở phiên bản mới nhất (v{APP_VERSION}).\nKhông có bản cập nhật nào mới hơn.",
                )
        elif event == "update_check_error":
            err = str(payload)
            self.status.set("⚠️ Không thể kiểm tra cập nhật.")
            self.details.set(err)
            messagebox.showwarning("Kiểm Tra Cập Nhật", f"Không thể kết nối đến máy chủ GitHub để kiểm tra cập nhật:\n{err}")
        elif event == "update_applying":
            msg = str(payload)
            self.status.set("⏳ Đang cập nhật ứng dụng...")
            self.details.set(msg)
            self.progress_bar.set(0.6)
        elif event == "update_ready_restart":
            self.progress_bar.set(1.0)
            self.status.set("✅ Cập nhật hoàn tất!")
            self.details.set("Ứng dụng đang khởi động lại...")
            messagebox.showinfo(
                "Cập Nhật Thành Công! 🎉",
                "Ứng dụng đã được cập nhật thành công lên bản mới nhất.\nChương trình sẽ tự động khởi động lại ngay bây giờ.",
            )
            restart_application()
        elif event == "update_failed":
            err = str(payload)
            self.progress_bar.set(0.0)
            self.status.set("❌ Cập nhật thất bại.")
            self.details.set(err)
            messagebox.showerror(
                "Cập Nhật Thất Bại",
                f"Đã xảy ra lỗi khi cập nhật ứng dụng:\n{err}\n\nVui lòng thử lại sau hoặc tải trực tiếp từ GitHub.",
            )

    def _update_row(self, item_id: str) -> None:
        if item_id not in self.items:
            return
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
    try:
        total = int(float(seconds))
        m, s = divmod(total, 60)
        return f"{m}:{s:02d}"
    except Exception:
        return ""


def is_format_compatible(fmt: object, media_format: str) -> bool:
    if not isinstance(fmt, dict):
        return False
    provider_media = fmt.get("media_format")
    if provider_media:
        return provider_media == ("audio" if media_format == "audio" else "video")
    return media_format == "video"


def format_option_label(fmt: dict[str, Any]) -> str:
    provider = str(fmt.get("provider") or "")
    label = str(fmt.get("label") or fmt.get("id") or "Best")
    return f"{provider} - {label}" if provider and not label.startswith(provider) else label


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

    root = ctk.CTk()
    ProDownloaderApp(root, lock_handle=lock_handle)
    root.mainloop()


if __name__ == "__main__":
    main()
