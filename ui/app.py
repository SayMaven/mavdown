import os
import sys
import re
import subprocess
import threading
import queue
from io import BytesIO
from PIL import Image
import customtkinter as ctk
from tkinter import filedialog

from config import (
    BASE_DIR, DEFAULT_OUTPUT_DIR, load_config, save_config,
    load_browser_cookie, load_preferences, save_preferences, is_aria2_available,
    load_ytdlp_channel, save_ytdlp_channel, load_proxy, save_proxy,
    load_clipboard_monitor, save_clipboard_monitor,
    load_organize_by_platform, save_organize_by_platform
)
from downloader import (
    ui_queue, get_video_info, download_video_logic,
    stop_current_process, update_ytdlp_logic
)
from ui.constants import (
    APP_VERSION, APP_TITLE, THEME, PLATFORM_PATTERNS,
    QUICK_PRESETS, LANG_PRESETS
)
from ui.sidebar import build_sidebar
from ui.studio_view import build_studio_view
from ui.queue_view import build_queue_view
from ui.history_view import build_history_view, refresh_history_view
from ui.log_view import build_log_view
from ui.settings_view import build_settings_view
from history import add_history_entry

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1420x860")
        self.minsize(1180, 750)

        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        try:
            icon_path = os.path.join(BASE_DIR, "assets", "waifu_icon.ico")
            self.iconbitmap(icon_path)
        except Exception:
            pass

        # ── State Variables ──────────────────────────────────────────────────
        self.mode_var = ctk.StringVar(value="video_audio")
        self.custom_cmd_var = ctk.StringVar()
        self.custom_output_path_var = ctk.StringVar(value=load_config())
        self.browser_cookie_var = ctk.StringVar(value=load_browser_cookie())
        self.ytdlp_channel_var = ctk.StringVar(value=load_ytdlp_channel())
        self.audio_only_format_var = ctk.StringVar(value="auto")
        self.resolution_var = ctk.StringVar(value="best")
        self.video_codec_var = ctk.StringVar(value="best")
        self.audio_codec_var = ctk.StringVar(value="best")
        self.container_var = ctk.StringVar(value="auto")
        self.download_subs_var = ctk.BooleanVar(value=False)
        self.embed_subs_var = ctk.BooleanVar(value=False)
        self.subs_lang_var = ctk.StringVar(value="id,en")
        self.embed_thumb_var = ctk.BooleanVar(value=True)
        self.use_aria2_var = ctk.BooleanVar(value=is_aria2_available())
        self.download_playlist_var = ctk.BooleanVar(value=False)
        self.proxy_var = ctk.StringVar(value=load_proxy())
        self.clipboard_monitor_var = ctk.BooleanVar(value=load_clipboard_monitor())
        self.organize_by_platform_var = ctk.BooleanVar(value=load_organize_by_platform())

        # ── Runtime State ────────────────────────────────────────────────────
        self.last_video_info: dict = {}
        self._last_log_text: str = ""
        self._settings_window = None
        self._active_thumb_image = None
        self._history_thumb_refs: dict = {}
        self._active_toast = None
        self._current_active_view: str = "studio"
        self._queue_done_event = threading.Event()
        self._queue_running: bool = False
        self._queue_items = []
        self._prefs_loading: bool = False
        self._last_clipboard_seen: str = ""

        self.setup_ui()
        self._load_and_apply_preferences()
        self._setup_pref_traces()
        self.after(100, self.process_ui_queue)
        self.after(1500, self._check_clipboard_daemon)

    # =========================================================================
    # UI Setup
    # =========================================================================
    def setup_ui(self):
        self.configure(fg_color=THEME["bg_master"])

        # Master Grid Layout
        self.grid_columnconfigure(0, weight=0, minsize=260)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # 1. Left Sidebar Navigation
        self.sidebar = build_sidebar(self, self)

        # 2. Main Workspace
        main_workspace = ctk.CTkFrame(self, fg_color="transparent")
        main_workspace.grid(row=0, column=1, sticky="nsew", padx=16, pady=16)

        # ── Top Universal Command Bar ─────────────────────────────────────
        top_bar = ctk.CTkFrame(main_workspace, fg_color=THEME["card_bg"], corner_radius=12)
        top_bar.pack(fill="x", pady=(0, 14))

        tb_in = ctk.CTkFrame(top_bar, fg_color="transparent")
        tb_in.pack(fill="x", padx=12, pady=10)

        # Platform Pill
        self.platform_badge = ctk.CTkFrame(tb_in, fg_color="#1E2032", corner_radius=8)
        self.platform_badge.pack(side="left")
        self.platform_badge.pack_forget()
        self._platform_label = ctk.CTkLabel(
            self.platform_badge, text="", font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#F3F4F6"
        )
        self._platform_label.pack(padx=8, pady=4)

        # URL Input
        self.url_entry = ctk.CTkEntry(
            tb_in,
            placeholder_text="Tempelkan link YouTube, TikTok, Instagram, Twitter/X, Douyin, Pinterest...",
            height=44, corner_radius=10, border_color=THEME["border_light"], fg_color="#0A0B12",
            text_color=THEME["text_title"], placeholder_text_color=THEME["text_dim"],
            font=ctk.CTkFont(size=13)
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(4, 6))
        self.url_entry.bind("<KeyRelease>", self._on_url_keyrelease)
        self.url_entry.bind("<Return>", lambda e: self.on_get_info())
        self.url_entry.bind("<Control-v>", self._on_entry_paste)
        self.url_entry.bind("<Control-V>", self._on_entry_paste)
        self.url_entry.bind("<<Paste>>", self._on_entry_paste)
        if hasattr(self.url_entry, '_entry'):
            self.url_entry._entry.bind("<Control-v>", self._on_entry_paste)
            self.url_entry._entry.bind("<Control-V>", self._on_entry_paste)
            self.url_entry._entry.bind("<<Paste>>", self._on_entry_paste)

        # Paste Button
        ctk.CTkButton(
            tb_in, text="Tempel", width=55, height=42, corner_radius=8,
            fg_color="#1E2032", hover_color="#2B2E45", font=ctk.CTkFont(size=12, weight="bold"),
            command=self._auto_paste
        ).pack(side="left", padx=(0, 4))

        # Clear URL Button
        ctk.CTkButton(
            tb_in, text="X", width=36, height=42, corner_radius=8,
            fg_color="#1E2032", hover_color="#2B2E45", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=THEME["text_muted"], command=self._clear_url
        ).pack(side="left", padx=(0, 8))

        # Cek Info Button
        ctk.CTkButton(
            tb_in, text="Cek Info", command=self.on_get_info,
            width=100, height=44, corner_radius=10,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=THEME["accent_indigo"], hover_color=THEME["accent_indigo_hover"]
        ).pack(side="left", padx=(0, 8))

        # Primary Download Button
        self.download_button = ctk.CTkButton(
            tb_in, text="MULAI UNDUH", command=self.on_download,
            width=140, height=44, corner_radius=10,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=THEME["accent_emerald"], hover_color=THEME["accent_emerald_hover"]
        )
        self.download_button.pack(side="left")

        # ── Views Container (Studio, Queue, Log) ───────────────────────────
        self.views_container = ctk.CTkFrame(main_workspace, fg_color="transparent")
        self.views_container.pack(fill="both", expand=True)

        # ── Bottom Live Progress & Telemetry Dock (Persistent) ───────────
        self.telemetry_dock = ctk.CTkFrame(main_workspace, fg_color=THEME["card_bg"], corner_radius=12)
        self.telemetry_dock.pack(fill="x", pady=(12, 0))

        td_in = ctk.CTkFrame(self.telemetry_dock, fg_color="transparent")
        td_in.pack(fill="x", padx=16, pady=10)

        t_row = ctk.CTkFrame(td_in, fg_color="transparent")
        t_row.pack(fill="x", pady=(0, 6))

        self.progress_label = ctk.CTkLabel(
            t_row, text="Status: Siap Mengunduh",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=THEME["text_body"]
        )
        self.progress_label.pack(side="left")

        self.stats_label = ctk.CTkLabel(
            t_row, text="",
            font=ctk.CTkFont(family="Consolas", size=11), text_color=THEME["text_accent"]
        )
        self.stats_label.pack(side="right")

        self.progress_bar = ctk.CTkProgressBar(
            td_in, height=8, corner_radius=4,
            progress_color=THEME["accent_emerald"], fg_color="#1E2032"
        )
        self.progress_bar.pack(fill="x")
        self.progress_bar.set(0)

        # Build subviews
        self.studio_view = build_studio_view(self, self.views_container)
        self.queue_view = build_queue_view(self, self.views_container)
        self.history_view = build_history_view(self, self.views_container)
        self.log_view = build_log_view(self, self.views_container)
        self.settings_view_frame = build_settings_view(self, self.views_container)

        self.show_studio_view()
        self.toggle_opts()

    # =========================================================================
    # Navigation View Switcher
    # =========================================================================
    def show_studio_view(self):
        self._switch_nav_active("studio")
        self.queue_view.pack_forget()
        self.history_view.pack_forget()
        self.log_view.pack_forget()
        self.settings_view_frame.pack_forget()
        self.studio_view.pack(fill="both", expand=True)

    def show_queue_view(self):
        self._switch_nav_active("queue")
        self.studio_view.pack_forget()
        self.history_view.pack_forget()
        self.log_view.pack_forget()
        self.settings_view_frame.pack_forget()
        self.queue_view.pack(fill="both", expand=True)

    def show_history_view(self):
        self._switch_nav_active("history")
        self.studio_view.pack_forget()
        self.queue_view.pack_forget()
        self.log_view.pack_forget()
        self.settings_view_frame.pack_forget()
        self.history_view.pack(fill="both", expand=True)
        refresh_history_view(self)

    def show_log_view(self):
        self._switch_nav_active("log")
        self.studio_view.pack_forget()
        self.queue_view.pack_forget()
        self.history_view.pack_forget()
        self.settings_view_frame.pack_forget()
        self.log_view.pack(fill="both", expand=True)

    def show_settings_view(self):
        self._switch_nav_active("settings")
        self.studio_view.pack_forget()
        self.queue_view.pack_forget()
        self.history_view.pack_forget()
        self.log_view.pack_forget()
        self.settings_view_frame.pack(fill="both", expand=True)

    def _switch_nav_active(self, active_key: str):
        self._current_active_view = active_key
        if hasattr(self, 'nav_btns'):
            for key, btn in self.nav_btns.items():
                if key == active_key:
                    btn.configure(fg_color="#1E1B4B", text_color="#818CF8")
                else:
                    btn.configure(fg_color="transparent", text_color=THEME["text_muted"])

    # =========================================================================
    # UI Queue Processor
    # =========================================================================
    def process_ui_queue(self):
        try:
            while True:
                try:
                    msg = ui_queue.get_nowait()
                except queue.Empty:
                    break

                try:
                    msg_type = msg.get("type")

                    if msg_type == "log":
                        self.log_area.insert("end", msg["text"])
                        self.log_area.see("end")
                        self._last_log_text += msg["text"]
                        if len(self._last_log_text) > 100_000:
                            self._last_log_text = self._last_log_text[-80_000:]

                    elif msg_type == "progress":
                        if "value" in msg:
                            self.progress_bar.set(msg["value"])
                        if "text" in msg:
                            self.progress_label.configure(text=msg["text"])
                        
                        speed = msg.get("speed", "")
                        eta = msg.get("eta", "")
                        size_dl = msg.get("size_dl", "")
                        size_total = msg.get("size_total", "")
                        parts = []
                        if speed: parts.append(speed)
                        if eta: parts.append(f"ETA {eta}")
                        if size_dl and size_total: parts.append(f"{size_dl} / {size_total}")
                        elif size_dl: parts.append(size_dl)
                        self.stats_label.configure(text="   •   ".join(parts))

                    elif msg_type == "info_title":
                        self.title_label.configure(text=msg["title"])

                    elif msg_type == "info_thumb":
                        self._set_thumb_label(None, text=msg.get("text", "Thumbnail tidak ditemukan."))

                    elif msg_type == "info_thumb_data":
                        try:
                            image = Image.open(BytesIO(msg["image_data"]))
                            max_w, max_h = 420, 240
                            ratio = min(max_w / image.width, max_h / image.height)
                            new_w = max(1, int(image.width * ratio))
                            new_h = max(1, int(image.height * ratio))
                            ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=(new_w, new_h))
                            self._set_thumb_label(ctk_image, text="")
                        except Exception:
                            self._set_thumb_label(None, text="Gagal memuat preview thumbnail.")

                    elif msg_type == "info_data":
                        self._on_info_data(msg["data"])

                    elif msg_type == "download_success_meta":
                        try:
                            meta = getattr(self, 'last_video_info', {}) or {}
                            url = msg.get("url") or meta.get("url", "") or self.url_entry.get().strip()
                            out_dir = msg.get("output_dir") or self.custom_output_path_var.get() or DEFAULT_OUTPUT_DIR

                            newest_path = ""
                            newest_mtime = 0
                            if os.path.exists(out_dir):
                                for item in os.listdir(out_dir):
                                    item_path = os.path.join(out_dir, item)
                                    if not item.endswith(('.tmp', '.part', '.ytdl', '.old', '.new')):
                                        try:
                                            mt = os.path.getmtime(item_path)
                                            if mt > newest_mtime:
                                                newest_mtime = mt
                                                newest_path = item_path
                                        except Exception:
                                            pass

                            title = meta.get("title") or (os.path.splitext(os.path.basename(newest_path))[0] if newest_path else "Media Unduhan")

                            # Deteksi Platform secara akurat dari URL atau metadata
                            platform = meta.get("platform") or ""
                            if not platform or platform.lower() in ("web", "generic", "fast engine"):
                                for pattern, label, _ in PLATFORM_PATTERNS:
                                    if re.search(pattern, url, re.IGNORECASE):
                                        platform = label
                                        break
                            if not platform:
                                platform = "Web"

                            is_slide = meta.get("is_slide", False) or (os.path.isdir(newest_path) if newest_path else False)

                            # Ekstraksi kreator / uploader
                            author = meta.get("uploader") or meta.get("channel") or meta.get("author") or meta.get("uploader_id", "")
                            if author.lower() in ('douyin user', 'douyinuser', 'user', 'none', 'douyin video', 'kreator douyin', 'akun douyin', 'tiktok user', 'instagram user', 'facebook user'):
                                author = ""

                            # Ekstraksi resolusi
                            resolution = meta.get("resolution_label") or meta.get("resolution") or ""
                            if not resolution and meta.get("width") and meta.get("height"):
                                resolution = f"{meta.get('width')}x{meta.get('height')}"

                            # Ekstraksi durasi
                            duration = meta.get("duration_string") or ""
                            if not duration and meta.get("duration"):
                                d_val = meta.get("duration")
                                if isinstance(d_val, (int, float)):
                                    m, s = divmod(int(d_val), 60)
                                    h, m = divmod(m, 60)
                                    duration = f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
                                else:
                                    duration = str(d_val)

                            # Ekstraksi format media
                            media_fmt = ""
                            if newest_path:
                                if is_slide or os.path.isdir(newest_path):
                                    media_fmt = "SLIDE"
                                else:
                                    media_fmt = os.path.splitext(newest_path)[1].lstrip('.').upper()

                            add_history_entry(
                                title=title,
                                platform=platform,
                                file_path=newest_path,
                                thumbnail=meta.get("thumbnail", ""),
                                is_slide=is_slide,
                                duration=duration,
                                source_url=url,
                                author=author,
                                resolution=resolution,
                                media_format=media_fmt,
                                slide_count=meta.get("slide_count", 0)
                            )
                            if hasattr(self, 'history_scroll') and self.history_scroll.winfo_exists():
                                refresh_history_view(self)
                        except Exception as e:
                            print(f"Error recording download history: {e}")

                    elif msg_type == "download_finish":
                        self.download_button.configure(
                            text="MULAI UNDUH", fg_color=THEME["accent_emerald"], hover_color=THEME["accent_emerald_hover"],
                            command=self.on_download, state="normal"
                        )
                        self.url_entry.configure(state="normal")
                        self.progress_bar.set(1.0)
                        self.progress_label.configure(text="Status: Unduhan Selesai")
                        self.stats_label.configure(text="")
                        self._queue_done_event.set()
                        if not self._queue_running:
                            self.show_toast("Unduhan selesai!", "success")

                    elif msg_type == "download_error":
                        self.download_button.configure(
                            text="MULAI UNDUH", fg_color=THEME["accent_emerald"], hover_color=THEME["accent_emerald_hover"],
                            command=self.on_download, state="normal"
                        )
                        self.url_entry.configure(state="normal")
                        self._queue_done_event.set()
                        self.show_toast("Unduhan gagal. Buka tab Log untuk detail.", "error")

                    elif msg_type == "update_finish":
                        self.update_btn.configure(state="normal", text="Update yt-dlp")
                        if hasattr(self, "settings_update_btn") and self.settings_update_btn.winfo_exists():
                            self.settings_update_btn.configure(state="normal", text="Update yt-dlp")
                        if hasattr(self, "settings_ytdlp_ver_label") and self.settings_ytdlp_ver_label.winfo_exists():
                            try:
                                from downloader import get_local_ytdlp_version
                                cur_ver = get_local_ytdlp_version() or "Terpasang"
                                self.settings_ytdlp_ver_label.configure(text=f"v{cur_ver}")
                            except Exception:
                                pass
                        self.progress_bar.set(1.0)
                        self.progress_label.configure(text="Status: Update Selesai")
                        self.show_toast("yt-dlp berhasil diperbarui!", "success")
                except Exception as ex:
                    print(f"Error handling UI message {msg.get('type')}: {ex}")
        finally:
            self.after(100, self.process_ui_queue)

    # =========================================================================
    # Info Data Handler
    # =========================================================================
    def _on_info_data(self, info: dict):
        self.last_video_info = info

        webpage_url = info.get('webpage_url', '') or info.get('url', '')
        platform_name = info.get('platform', '')
        platform_text = ""
        for (pattern, label, _color) in PLATFORM_PATTERNS:
            if re.search(pattern, webpage_url, re.IGNORECASE) or (platform_name and platform_name.lower() in label.lower()):
                platform_text = label
                break
        self.meta_platform.configure(text=platform_text or "Web Media")

        raw_date = info.get('upload_date', '')
        if raw_date and len(raw_date) == 8:
            date_str = f"{raw_date[6:8]}/{raw_date[4:6]}/{raw_date[:4]}"
        else:
            date_str = ""
        self.meta_date.configure(text=date_str)

        channel = info.get('uploader') or info.get('channel') or info.get('uploader_id', '') or info.get('author', '')
        if channel.lower() in ('douyin user', 'douyinuser', 'user', 'none', 'douyin video', 'kreator douyin', 'akun douyin', 'tiktok user', 'instagram user', 'facebook user'):
            channel = ""
        if not channel:
            title_text = info.get('title', '') or ''
            at_m = re.search(r'@([a-zA-Z0-9_.\u4e00-\u9fa5]+)', title_text)
            if at_m:
                channel = f"@{at_m.group(1)}"

        is_slide = info.get('is_slide', False)
        slide_count = info.get('slide_count', 0)
        w = info.get('width')
        h = info.get('height')
        res_lbl = info.get('resolution_label') or ''

        display_channel = channel
        if len(display_channel) > 26:
            display_channel = display_channel[:24] + ".."

        if display_channel:
            self.meta_channel.configure(text=f"Kreator: {display_channel}")
        elif is_slide:
            self.meta_channel.configure(text="Album Slide")
        else:
            self.meta_channel.configure(text=f"Media {platform_name or 'Web'}")

        if is_slide:
            if slide_count == 1:
                self.meta_duration.configure(text="1 Foto HD")
                if w and h:
                    self.meta_views.configure(text=f"HD Photo ({w}x{h})")
                else:
                    self.meta_views.configure(text="Foto HD")
                self.meta_likes.configure(text="Foto HD Asli")
            else:
                self.meta_duration.configure(text=f"{slide_count} Foto Slide" if slide_count else "Album Slide")
                if w and h:
                    self.meta_views.configure(text=f"HD Slide ({w}x{h})")
                else:
                    self.meta_views.configure(text="Album Slide HD")
                self.meta_likes.configure(text=f"{slide_count} Foto HD" if slide_count else "Foto Slide HD")
        else:
            dur_str = info.get('duration_string', '')
            if not dur_str:
                dur_val = info.get('duration', 0)
                if isinstance(dur_val, str):
                    if ":" in dur_val:
                        dur_str = dur_val
                    else:
                        try:
                            dur_num = float(dur_val)
                            m_total, s = divmod(int(dur_num), 60)
                            dur_h, dur_m = divmod(m_total, 60)
                            dur_str = f"{dur_h}:{dur_m:02d}:{s:02d}" if dur_h else f"{dur_m:02d}:{s:02d}"
                        except Exception:
                            dur_str = dur_val
                elif isinstance(dur_val, (int, float)) and dur_val > 0:
                    m_total, s = divmod(int(dur_val), 60)
                    dur_h, dur_m = divmod(m_total, 60)
                    dur_str = f"{dur_h}:{dur_m:02d}:{s:02d}" if dur_h else f"{dur_m:02d}:{s:02d}"
            self.meta_duration.configure(text=f"Durasi: {dur_str}" if dur_str else "")

            vc = info.get('view_count', 0)
            if vc:
                self.meta_views.configure(text=f"{vc:,} Views".replace(",", "."))
            elif w and h:
                res_text = f"{res_lbl} ({w}x{h})" if res_lbl else f"{w}x{h}"
                self.meta_views.configure(text=res_text)
            elif res_lbl:
                self.meta_views.configure(text=res_lbl)
            else:
                self.meta_views.configure(text="")

            lc = info.get('like_count', 0)
            fps = info.get('fps', 0)
            codec = info.get('codec') or ''
            if lc:
                lc_str = f"{lc/1_000_000:.1f}Jt" if lc >= 1_000_000 else (f"{lc/1_000:.1f}Rb" if lc >= 1_000 else str(lc))
                self.meta_likes.configure(text=f"{lc_str} Likes")
            elif fps and codec:
                self.meta_likes.configure(text=f"{fps} FPS · {codec.upper()}")
            elif fps:
                self.meta_likes.configure(text=f"{fps} FPS")
            elif codec:
                self.meta_likes.configure(text=f"Codec: {codec.upper()}")
            else:
                self.meta_likes.configure(text="")

        desc_raw = info.get('description', '') or ''
        author_display = channel

        if not desc_raw:
            parts = []
            if author_display:
                parts.append(f"Kreator: {author_display}")
            if is_slide:
                dim_str = f"({w}x{h})" if w and h else "HD"
                if slide_count == 1:
                    parts.append(f"Foto HD {dim_str}")
                else:
                    parts.append(f"Album Slide: {slide_count} Foto {dim_str}" if slide_count else f"Album Slide {dim_str}")
                if info.get('has_audio') or info.get('audio_url'):
                    parts.append("Musik BGM")
                parts.append(f"Diunduh via {platform_name or 'Web'}")
            elif w and h:
                res_str = f"{res_lbl} ({w}x{h})" if res_lbl else f"{w}x{h}"
                fps_str = f"{fps} FPS" if fps else ""
                parts.append(f"Resolusi: {res_str}")
                if fps_str:
                    parts.append(fps_str)
                parts.append(f"Diunduh via {platform_name or 'Web'}")
            desc_raw = " · ".join(parts)
        else:
            if author_display and not desc_raw.startswith("Kreator:"):
                desc_raw = f"Kreator: {author_display} · {desc_raw}"

        if desc_raw:
            lines = [l.strip() for l in desc_raw.splitlines() if l.strip()]
            preview = " · ".join(lines[:2])
            if len(preview) > 160:
                preview = preview[:157] + "..."
            self.meta_desc.configure(text=preview)
        else:
            self.meta_desc.configure(text="")

        for widget in self.badges_frame.winfo_children():
            widget.destroy()

        formats = info.get('formats', [])
        heights = set(f.get('height', 0) for f in formats if f.get('height'))
        fps_vals = [f.get('fps', 0) for f in formats if f.get('fps')]
        
        # Sertakan metadata root (dari Tier 1 fast engine)
        if info.get('height'): heights.add(info.get('height'))
        if info.get('width'): heights.add(info.get('width'))
        if info.get('fps'): fps_vals.append(info.get('fps'))

        has_hdr = any(str(f.get('dynamic_range', '')).upper() in ('HDR', 'HDR10', 'HDR10+', 'DOVI', 'HLG') for f in formats)

        badges = []
        if is_slide:
            if slide_count == 1:
                badges.append(("Foto HD", "#3B82F6"))
                badges.append(("HD Photo", "#10B981"))
            else:
                if slide_count:
                    badges.append((f"{slide_count} Foto Slide", "#3B82F6"))
                badges.append(("HD Slide", "#10B981"))
            if w and h:
                badges.append((f"{w}x{h}", "#10B981"))
            badges.append(("JPEG HD", "#8B5CF6"))
            if info.get('has_audio') or info.get('audio_url'):
                badges.append(("Musik BGM", "#EC4899"))
        else:
            max_dim = max(heights, default=0)
            min_dim = min(info.get('width') or 99999, info.get('height') or 99999)
            if min_dim == 99999: min_dim = 0
            
            # Badge Kategori Resolusi (4K, 2K, 1080p, dsb)
            if res_lbl:
                badges.append((res_lbl, "#F59E0B"))
            elif max_dim >= 3840 or min_dim >= 2160:
                badges.append(("4K UHD", "#F59E0B"))
            elif max_dim >= 2560 or min_dim >= 1440:
                badges.append(("2K QHD", "#10B981"))
            elif max_dim >= 1920 or min_dim >= 1080:
                badges.append(("1080p FHD", "#3B82F6"))
            elif max_dim >= 1280 or min_dim >= 720:
                badges.append(("720p HD", "#6366F1"))
            elif max_dim >= 480 or min_dim >= 480:
                badges.append(("480p", "#8B5CF6"))

            # Badge Dimensi Pixel Eksak (misal 2160x3840)
            if w and h:
                badges.append((f"{w}x{h}", "#10B981"))

            # Badge FPS
            max_fps = max(fps_vals, default=0)
            if max_fps:
                badges.append((f"{max_fps} FPS", "#3B82F6"))

            # Badge Codec Video
            codec = info.get('codec') or info.get('vcodec')
            if codec and str(codec).lower() not in ('none', 'unknown', ''):
                badges.append((str(codec).upper(), "#8B5CF6"))

            # Badge Ukuran File
            size_str = info.get('formatted_size')
            if size_str:
                badges.append((size_str, "#EC4899"))

            if has_hdr:
                badges.append(("HDR", "#F97316"))

            if not badges:
                badges.append(("Auto Stream", THEME["accent_indigo"]))

        for (badge_text, fg) in badges:
            b = ctk.CTkFrame(self.badges_frame, fg_color=fg, corner_radius=6)
            b.pack(side="left", padx=(0, 5), pady=2)
            ctk.CTkLabel(
                b, text=badge_text, font=ctk.CTkFont(size=9, weight="bold"),
                text_color="white"
            ).pack(padx=8, pady=3)

        # Update Studio Mode & Parameters dynamically
        if is_slide:
            if hasattr(self, 'slide_p_count'):
                self.slide_p_count.configure(text="Total: 1 Foto HD" if slide_count == 1 else (f"Total: {slide_count} Foto Slide" if slide_count else "Total: Album Slide"))
            if hasattr(self, 'slide_p_res'):
                self.slide_p_res.configure(text=f"Dimensi: {w}x{h} (Asli)" if w and h else "Dimensi: HD Original")
            if hasattr(self, 'slide_p_audio'):
                has_bgm = info.get('has_audio') or info.get('audio_url')
                self.slide_p_audio.configure(text="Audio: Musik BGM (.mp3)" if has_bgm else "Audio: Tanpa Musik")

            if hasattr(self, 'mode_segmented'):
                label_dl = "Unduh Foto HD" if slide_count == 1 else "Unduh Semua Slide (+ Audio)"
                self.mode_segmented.configure(values=[label_dl, "Audio Saja (Musik)"])
                if self.mode_var.get() == "audio_only":
                    self.mode_segmented.set("Audio Saja (Musik)")
                else:
                    self.mode_segmented.set(label_dl)
        else:
            if hasattr(self, 'mode_segmented'):
                self.mode_segmented.configure(values=["Video + Audio", "Audio Saja (Musik)"])
                if self.mode_var.get() == "audio_only":
                    self.mode_segmented.set("Audio Saja (Musik)")
                else:
                    self.mode_segmented.set("Video + Audio")

        self.toggle_opts()

    # =========================================================================
    # Batch Queue Actions
    # =========================================================================
    def _add_to_queue(self):
        raw = self.queue_textbox.get("1.0", "end").strip()
        urls = [line.strip() for line in raw.splitlines() if line.strip()]
        if not urls:
            self.show_toast("Tidak ada URL yang valid.", "warning")
            return
        for url in urls:
            self._add_queue_item(url)
        self.queue_textbox.delete("1.0", "end")
        self.show_toast(f"{len(urls)} URL ditambahkan ke antrean.", "success")

    def _add_queue_item(self, url: str):
        item_frame = ctk.CTkFrame(self.queue_list_frame, fg_color="#131522", corner_radius=8)
        item_frame.pack(fill="x", pady=3)
        inner = ctk.CTkFrame(item_frame, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=8)

        url_lbl = ctk.CTkLabel(
            inner, text=url[:85] + ("..." if len(url) > 85 else ""),
            font=ctk.CTkFont(size=11), text_color="#D1D5DB", anchor="w"
        )
        url_lbl.pack(side="left", fill="x", expand=True)

        status_var = ctk.StringVar(value="Menunggu")
        status_lbl = ctk.CTkLabel(
            inner, textvariable=status_var, font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#818CF8", width=110
        )
        status_lbl.pack(side="right")
        self._queue_items.append((url, status_var))

    def _start_queue(self):
        if not self._queue_items:
            self.show_toast("Antrean kosong.", "warning")
            return
        if self._queue_running:
            self.show_toast("Antrean sedang berjalan.", "warning")
            return

        total = len(self._queue_items)
        self.show_toast(f"Memulai {total} unduhan dalam antrean...", "info")

        def _run_queue():
            self._queue_running = True
            completed = 0

            for (url, status_var) in list(self._queue_items):
                self.after(0, lambda sv=status_var: sv.set("Mengunduh"))
                self.after(0, lambda: self.progress_label.configure(
                    text=f"Antrean Berjalan: {completed+1}/{total}"
                ))

                self._queue_done_event.clear()

                download_video_logic(
                    url,
                    self.mode_var.get(),
                    self.audio_only_format_var.get(),
                    self.resolution_var.get(),
                    self.video_codec_var.get(),
                    self.audio_codec_var.get(),
                    self.container_var.get(),
                    self.download_subs_var.get(),
                    self.embed_subs_var.get(),
                    self.subs_lang_var.get().strip(),
                    self.embed_thumb_var.get(),
                    self.use_aria2_var.get(),
                    self.download_playlist_var.get(),
                    self.custom_output_path_var.get(),
                    self.custom_cmd_var.get().strip(),
                    self.browser_cookie_var.get()
                )

                self._queue_done_event.wait(timeout=3600)
                completed += 1
                self.after(0, lambda sv=status_var: sv.set("Selesai"))

            self._queue_running = False
            self.after(0, lambda: self.show_toast(
                f"Antrean selesai! {completed} media berhasil diunduh.", "success"
            ))
            self.after(0, lambda: self.progress_label.configure(text="Status: Semua Antrean Selesai"))

        threading.Thread(target=_run_queue, daemon=True).start()

    def _clear_queue_input(self):
        self.queue_textbox.delete("1.0", "end")
        for widget in self.queue_list_frame.winfo_children():
            widget.destroy()
        self._queue_items.clear()
        self.show_toast("Antrean dikosongkan.", "info")

    def _import_queue_txt(self):
        path = filedialog.askopenfilename(
            title="Pilih file .txt berisi daftar URL",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.queue_textbox.delete("1.0", "end")
            self.queue_textbox.insert("1.0", content)
            self.show_toast("File berhasil dimuat.", "success")
        except Exception as e:
            self.show_toast(f"Gagal membaca file: {e}", "error")

    # =========================================================================
    # URL & Platform Detection & Clipboard Daemon
    # =========================================================================
    def _check_clipboard_daemon(self):
        try:
            if hasattr(self, 'clipboard_monitor_var') and self.clipboard_monitor_var.get():
                raw = self.clipboard_get()
                if raw and raw != self._last_clipboard_seen:
                    self._last_clipboard_seen = raw
                    m = re.search(r'https?://[^\s"\'<>]+', raw)
                    if m:
                        detected_url = m.group(0).rstrip('，。！？!?,;)"\'\r\n')
                        current_entry_val = self.url_entry.get().strip()
                        if detected_url != current_entry_val:
                            # Cek apakah cocok dengan salah satu platform
                            is_media_url = False
                            plat_name = "Media"
                            for pattern, label, _ in PLATFORM_PATTERNS:
                                if re.search(pattern, detected_url, re.I):
                                    is_media_url = True
                                    plat_name = label
                                    break

                            if is_media_url:
                                self.url_entry.delete(0, "end")
                                self.url_entry.insert(0, detected_url)
                                self._update_platform_badge(detected_url)
                                self.last_pasted_share_text = raw
                                self.show_toast(f"Link {plat_name} terdeteksi dari Clipboard!", "info")
                                self.on_get_info()
        except Exception:
            pass
        finally:
            self.after(1500, self._check_clipboard_daemon)

    def _on_entry_paste(self, event=None):
        try:
            clipboard = self.clipboard_get()
            if clipboard:
                raw_text = clipboard.strip()
                m = re.search(r'https?://[^\s"\'<>]+', raw_text)
                if m:
                    clean_url = m.group(0).rstrip('，。！？!?,;)"\'\r\n')
                else:
                    clean_url = raw_text

                self.last_pasted_share_text = raw_text
                self.url_entry.delete(0, "end")
                self.url_entry.insert(0, clean_url)
                self._update_platform_badge(clean_url)
                self.on_get_info()
                return "break"
        except Exception:
            pass
        return None

    def _on_url_keyrelease(self, event=None):
        url = self.url_entry.get().strip()
        m = re.search(r'https?://[^\s"\'<>]+', url)
        if m and (len(url) > len(m.group(0)) or any(c in m.group(0) for c in '，。！？!?,;)"\'\r\n')):
            clean_url = m.group(0).rstrip('，。！？!?,;)"\'\r\n')
            self.last_pasted_share_text = url
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, clean_url)
            url = clean_url
            self._update_platform_badge(url)
            self.on_get_info()
            return
        self._update_platform_badge(url)

    def _auto_paste(self):
        self._on_entry_paste()

    def _clear_url(self):
        self.url_entry.delete(0, "end")
        self._update_platform_badge("")
        self._set_thumb_label(None, text="Pratinjau Thumbnail Video / Foto")
        self.title_label.configure(text="Judul video atau media akan muncul di sini setelah memasukkan URL.")

    def _update_platform_badge(self, url: str):
        if not url:
            self.platform_badge.pack_forget()
            return
        for pattern, name, color in PLATFORM_PATTERNS:
            if re.search(pattern, url, re.I):
                self._platform_label.configure(text=name, text_color=color)
                self.platform_badge.pack(side="left", padx=(0, 6))
                return
        if url.startswith("http"):
            self._platform_label.configure(text="Web", text_color="#6B7280")
            self.platform_badge.pack(side="left", padx=(0, 6))
        else:
            self.platform_badge.pack_forget()

    # =========================================================================
    # Presets & Segment Handlers
    # =========================================================================
    def apply_preset(self, preset_name: str):
        p = QUICK_PRESETS.get(preset_name)
        if not p:
            return
        mode = p["mode"]
        self.mode_var.set(mode)
        self.mode_segmented.set("Audio Saja (Musik)" if mode == "audio_only" else "Video + Audio")
        self.container_var.set(p["container"])
        self.resolution_var.set(p["resolution"])
        self.video_codec_var.set(p["video_codec"])
        self.audio_codec_var.set(p["audio_codec"])
        self.audio_only_format_var.set(p["audio_format"])
        self.embed_thumb_var.set(p["embed_thumb"])

        self.video_fmt_segmented.set(p["label_v"])
        self.v_codec_segmented.set(p["label_c"])
        self.a_codec_segmented.set(p["label_a"])
        self.res_segmented.set(p["label_r"])
        af_map = {"auto": "Auto", "mp3": "MP3", "m4a": "M4A", "flac": "FLAC", "wav": "WAV", "opus": "OPUS"}
        self.audio_fmt_segmented.set(af_map.get(p["audio_format"], "Auto"))
        self.toggle_opts()
        self._save_current_preferences()
        self.show_toast(f"Preset '{preset_name}' diterapkan.", "info")

    def on_mode_segment_change(self, value):
        self.mode_var.set("audio_only" if "Audio" in value and "Video" not in value and "Slide" not in value else "video_audio")
        self.toggle_opts()
        self._save_current_preferences()

    def on_video_fmt_change(self, value):
        self.container_var.set("auto" if value == "Auto" else value.lower())
        self._save_current_preferences()

    def on_audio_fmt_change(self, value):
        self.audio_only_format_var.set("auto" if value == "Auto" else value.lower())
        self._save_current_preferences()

    def on_vcodec_change(self, value):
        self.video_codec_var.set({"Auto": "best", "H.264": "h264", "VP9": "vp9", "AV1": "av1"}.get(value, "best"))
        self._save_current_preferences()

    def on_acodec_change(self, value):
        self.audio_codec_var.set({"Auto": "best", "M4A": "m4a", "Opus": "opus"}.get(value, "best"))
        self._save_current_preferences()

    def on_res_segmented_change(self, value):
        self.resolution_var.set(
            {"Auto": "best", "Best": "best", "4K": "2160", "1440p": "1440",
             "1080p": "1080", "720p": "720", "480p": "480", "360p": "360"}.get(value, "best")
        )
        self._save_current_preferences()

    def on_lang_preset_change(self, value):
        code = LANG_PRESETS.get(value, "id,en")
        if code != "custom":
            self.subs_lang_var.set(code)
        else:
            self.lang_entry.focus()
        self._save_current_preferences()

    def toggle_opts(self):
        if not (hasattr(self, 'video_opts') and hasattr(self, 'audio_opts')):
            return

        is_slide = getattr(self, 'last_video_info', {}).get('is_slide', False) if hasattr(self, 'last_video_info') and self.last_video_info else False

        if is_slide:
            slide_count = getattr(self, 'last_video_info', {}).get('slide_count', 0) if hasattr(self, 'last_video_info') and self.last_video_info else 0
            if hasattr(self, 'format_title'):
                title_fmt = "PARAMETER FOTO HD" if slide_count == 1 else "PARAMETER ALBUM SLIDE FOTO"
                self.format_title.configure(text=title_fmt if self.mode_var.get() != "audio_only" else "PARAMETER FORMAT AUDIO (BGM)")
            if self.mode_var.get() == "audio_only":
                if hasattr(self, 'slide_opts'): self.slide_opts.pack_forget()
                self.video_opts.pack_forget()
                self.audio_opts.pack(fill="x")
            else:
                self.video_opts.pack_forget()
                self.audio_opts.pack_forget()
                if hasattr(self, 'slide_opts'): self.slide_opts.pack(fill="x")
            if hasattr(self, 'sec_sub'):
                self.sec_sub.pack_forget()
            if hasattr(self, 'embed_subs_cb'):
                self.embed_subs_cb.configure(state="disabled")
                self.download_subs_cb.configure(state="disabled")
            return

        # Mode reguler non-slide (Video atau Audio)
        if hasattr(self, 'format_title'):
            self.format_title.configure(text="PARAMETER FORMAT & KUALITAS")
        if hasattr(self, 'slide_opts'):
            self.slide_opts.pack_forget()
        if hasattr(self, 'sec_sub') and hasattr(self, 'sec_opts'):
            self.sec_sub.pack(fill="x", pady=(0, 10), before=self.sec_opts)
        if hasattr(self, 'embed_subs_cb'):
            self.embed_subs_cb.configure(state="normal")
            self.download_subs_cb.configure(state="normal")

        if self.mode_var.get() == "audio_only":
            self.video_opts.pack_forget()
            self.audio_opts.pack(fill="x")
            if hasattr(self, 'download_subs_cb'):
                self.download_subs_cb.configure(text="Unduh Lirik Terpisah (.lrc)")
                self.embed_subs_cb.configure(text="Embed Lirik Lagu")
                self.lang_label.configure(text="LIRIK LAGU & BAHASA AUDIO")
        else:
            self.audio_opts.pack_forget()
            self.video_opts.pack(fill="x")
            if hasattr(self, 'download_subs_cb'):
                self.download_subs_cb.configure(text="Unduh Subtitle Terpisah (.srt)")
                self.embed_subs_cb.configure(text="Embed Softsub P0 (Default Aktif)")
                self.lang_label.configure(text="SUBTITLE & LIRIK OTOMATIS")

    # =========================================================================
    # Preferences Persistence
    # =========================================================================
    def _load_and_apply_preferences(self):
        """Muat preferensi tersimpan dan terapkan ke seluruh widget UI."""
        prefs = load_preferences()
        if not prefs:
            return

        self._prefs_loading = True
        try:
            mode = prefs.get("mode", "video_audio")
            self.mode_var.set(mode)
            if hasattr(self, 'mode_segmented'):
                self.mode_segmented.set(
                    "Audio Saja (Musik)" if mode == "audio_only" else "Video + Audio"
                )

            container = prefs.get("container", "auto")
            self.container_var.set(container)
            if hasattr(self, 'video_fmt_segmented'):
                c_map = {"auto": "Auto", "mp4": "MP4", "mkv": "MKV", "webm": "WEBM", "mov": "MOV"}
                self.video_fmt_segmented.set(c_map.get(container, "Auto"))

            af = prefs.get("audio_format", "auto")
            self.audio_only_format_var.set(af)
            if hasattr(self, 'audio_fmt_segmented'):
                af_map = {"auto": "Auto", "mp3": "MP3", "m4a": "M4A",
                          "flac": "FLAC", "wav": "WAV", "opus": "OPUS"}
                self.audio_fmt_segmented.set(af_map.get(af, "Auto"))

            res = prefs.get("resolution", "best")
            self.resolution_var.set(res)
            if hasattr(self, 'res_segmented'):
                r_map = {"best": "Auto", "2160": "4K", "1440": "1440p",
                         "1080": "1080p", "720": "720p", "480": "480p", "360": "360p"}
                self.res_segmented.set(r_map.get(res, "Auto"))

            vc = prefs.get("video_codec", "best")
            self.video_codec_var.set(vc)
            if hasattr(self, 'v_codec_segmented'):
                vc_map = {"best": "Auto", "h264": "H.264", "vp9": "VP9", "av1": "AV1"}
                self.v_codec_segmented.set(vc_map.get(vc, "Auto"))

            ac = prefs.get("audio_codec", "best")
            self.audio_codec_var.set(ac)
            if hasattr(self, 'a_codec_segmented'):
                ac_map = {"best": "Auto", "m4a": "M4A", "opus": "Opus"}
                self.a_codec_segmented.set(ac_map.get(ac, "Auto"))

            self.embed_thumb_var.set(prefs.get("embed_thumbnail", True))
            self.use_aria2_var.set(prefs.get("use_aria2", is_aria2_available()))
            self.download_subs_var.set(prefs.get("download_subs", False))
            self.embed_subs_var.set(prefs.get("embed_subs", False))
            self.download_playlist_var.set(prefs.get("download_playlist", False))
            self.subs_lang_var.set(prefs.get("subs_lang", "id,en"))

            self.toggle_opts()
        finally:
            self._prefs_loading = False

    def _save_current_preferences(self):
        """Simpan seluruh state preferensi terkini ke config file."""
        if getattr(self, '_prefs_loading', False):
            return
        prefs = {
            "mode": self.mode_var.get(),
            "audio_format": self.audio_only_format_var.get(),
            "resolution": self.resolution_var.get(),
            "video_codec": self.video_codec_var.get(),
            "audio_codec": self.audio_codec_var.get(),
            "container": self.container_var.get(),
            "embed_thumbnail": self.embed_thumb_var.get(),
            "use_aria2": self.use_aria2_var.get(),
            "download_subs": self.download_subs_var.get(),
            "embed_subs": self.embed_subs_var.get(),
            "subs_lang": self.subs_lang_var.get(),
            "download_playlist": self.download_playlist_var.get(),
        }
        save_preferences(prefs)

    def _setup_pref_traces(self):
        """Pasang trace pada BooleanVar agar preferensi tersimpan otomatis."""
        for var in [self.embed_thumb_var, self.use_aria2_var, self.download_subs_var,
                    self.embed_subs_var, self.download_playlist_var]:
            var.trace_add("write", lambda *_: self._save_current_preferences())

    # =========================================================================
    # Toast Notification
    # =========================================================================
    def show_toast(self, message: str, toast_type: str = "info"):
        if self._active_toast:
            try:
                if self._active_toast.winfo_exists():
                    self._active_toast.destroy()
            except Exception:
                pass
            self._active_toast = None

        colors = {
            "success": THEME["accent_emerald"],
            "error":   THEME["accent_rose"],
            "info":    THEME["accent_indigo"],
            "warning": THEME["accent_amber"],
        }
        bg = colors.get(toast_type, THEME["accent_indigo"])

        try:
            toast = ctk.CTkToplevel(self)
            toast.overrideredirect(True)
            toast.attributes("-topmost", True)
            toast.configure(fg_color=bg)

            w, h = 380, 52
            self.update_idletasks()
            x = self.winfo_x() + self.winfo_width() - w - 24
            y = self.winfo_y() + self.winfo_height() - h - 50
            toast.geometry(f"{w}x{h}+{x}+{y}")

            ctk.CTkLabel(
                toast, text=message, text_color="white",
                font=ctk.CTkFont(size=12, weight="bold"),
                wraplength=350, anchor="w", justify="left"
            ).pack(fill="both", expand=True, padx=14, pady=8)

            self._active_toast = toast
            toast.after(3500, lambda: self._dismiss_toast(toast))
        except Exception:
            pass

    def _dismiss_toast(self, toast):
        """Hapus toast notification secara aman."""
        try:
            if toast.winfo_exists():
                toast.destroy()
            if self._active_toast == toast:
                self._active_toast = None
        except Exception:
            pass

    # =========================================================================
    # Core Actions
    # =========================================================================
    def clear_log(self):
        self.log_area.delete("1.0", "end")
        self._last_log_text = ""

    def copy_log(self):
        try:
            content = self.log_area.get("1.0", "end")
            self.clipboard_clear()
            self.clipboard_append(content)
            self.show_toast("Log disalin ke clipboard!", "success")
        except Exception:
            pass

    def select_folder(self):
        path = filedialog.askdirectory(title="Pilih Folder Output", initialdir=self.custom_output_path_var.get())
        if path:
            self.custom_output_path_var.set(path)
            save_config(path=path)
            self.show_toast("Lokasi output berhasil diperbarui!", "success")

    def open_folder(self):
        path = self.custom_output_path_var.get() or DEFAULT_OUTPUT_DIR
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])

    def open_settings(self):
        self.show_settings_view()

    def _on_settings_save(self, path: str, cookie: str):
        if path:
            self.custom_output_path_var.set(path)
            self.browser_cookie_var.set(cookie)
            save_config(path=path, browser_cookie=cookie)
            self.show_toast("Pengaturan berhasil disimpan!", "success")

    def _set_thumb_label(self, ctk_image=None, text=""):
        try:
            self.thumb_label._label.configure(image="")
        except Exception:
            pass
        self._active_thumb_image = ctk_image
        if ctk_image:
            self.thumb_label.configure(image=ctk_image, text="")
        else:
            self.thumb_label.configure(image=None, text=text)

    def on_get_info(self):
        url_input = self.url_entry.get().strip()
        if not url_input:
            self.show_toast("Masukkan URL terlebih dahulu!", "warning")
            return

        m = re.search(r'https?://[^\s"\'<>]+', url_input)
        if m:
            clean_url = m.group(0).rstrip('，。！？!?,;)"\'\r\n')
            if clean_url != url_input:
                self.last_pasted_share_text = url_input
                self.url_entry.delete(0, "end")
                self.url_entry.insert(0, clean_url)
                self._update_platform_badge(clean_url)
                url_input = clean_url
        url = url_input

        self.last_video_info = {}

        self._set_thumb_label(None, text="Mengambil Informasi Media...")
        self.title_label.configure(text="Sedang mengambil data & thumbnail dari server...")

        self.meta_platform.configure(text="")
        self.meta_date.configure(text="")
        self.meta_channel.configure(text="")
        self.meta_duration.configure(text="")
        self.meta_views.configure(text="")
        self.meta_likes.configure(text="")
        self.meta_desc.configure(text="")
        for widget in self.badges_frame.winfo_children():
            widget.destroy()

        share_ctx = getattr(self, 'last_pasted_share_text', None)
        if share_ctx and url not in share_ctx:
            share_ctx = None

        threading.Thread(target=get_video_info, args=(url, self.browser_cookie_var.get(), share_ctx), daemon=True).start()

    def on_download(self):
        url_input = self.url_entry.get().strip()
        if not url_input:
            self.show_toast("Masukkan URL sebelum memulai unduhan!", "warning")
            return

        m = re.search(r'https?://[^\s"\'<>]+', url_input)
        if m:
            clean_url = m.group(0).rstrip('，。！？!?,;)"\'\r\n')
            if clean_url != url_input:
                self.last_pasted_share_text = url_input
                self.url_entry.delete(0, "end")
                self.url_entry.insert(0, clean_url)
                self._update_platform_badge(clean_url)
                url_input = clean_url
        url = url_input

        self.stats_label.configure(text="")
        self.download_button.configure(
            text="HENTIKAN UNDUH", fg_color=THEME["accent_rose"], hover_color=THEME["accent_rose_hover"],
            command=self.on_stop
        )
        self.url_entry.configure(state="disabled")

        share_ctx = getattr(self, 'last_pasted_share_text', None)
        if share_ctx and url not in share_ctx:
            share_ctx = None

        threading.Thread(target=download_video_logic, args=(
            url, self.mode_var.get(), self.audio_only_format_var.get(),
            self.resolution_var.get(), self.video_codec_var.get(), self.audio_codec_var.get(),
            self.container_var.get(), self.download_subs_var.get(), self.embed_subs_var.get(),
            self.subs_lang_var.get().strip(), self.embed_thumb_var.get(),
            self.use_aria2_var.get(), self.download_playlist_var.get(),
            self.custom_output_path_var.get(), self.custom_cmd_var.get().strip(),
            self.browser_cookie_var.get(), share_ctx
        ), daemon=True).start()

    def on_stop(self):
        stop_current_process()

    def on_update(self, channel: str = None):
        target_channel = channel or self.ytdlp_channel_var.get() or "stable"
        self.update_btn.configure(state="disabled", text="Memeriksa...")
        if hasattr(self, "settings_update_btn") and self.settings_update_btn.winfo_exists():
            self.settings_update_btn.configure(state="disabled", text="Memeriksa...")
        threading.Thread(target=update_ytdlp_logic, args=(target_channel,), daemon=True).start()
