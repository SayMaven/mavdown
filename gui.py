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

from config import BASE_DIR, DEFAULT_OUTPUT_DIR, load_config, save_config, load_gemini_api_key
from downloader import (
    ui_queue, get_video_info, download_video_logic,
    stop_current_process, update_ytdlp_logic
)
from ai_helper import (
    analyze_download_error, clean_media_metadata,
    recommend_download_settings, test_api_connection
)

# ---------------------------------------------------------------------------
# Pemetaan Bahasa Subtitle / Lirik
# ---------------------------------------------------------------------------
LANG_PRESETS = {
    "🇮🇩 Indonesia & 🇬🇧 English": "id,en",
    "🇮🇩 Bahasa Indonesia": "id",
    "🇬🇧 English": "en",
    "🇯🇵 Jepang (Japanese)": "ja",
    "🇨🇳 Cina (Chinese)": "zh",
    "🇰🇷 Korea (Korean)": "ko",
    "🇪🇸 Spanyol (Spanish)": "es",
    "🌐 Semua Bahasa (All)": "all",
    "✏️ Custom / Manual": "custom"
}

# ---------------------------------------------------------------------------
# Deteksi Platform dari URL
# ---------------------------------------------------------------------------
PLATFORM_PATTERNS = [
    (r'youtu\.be|youtube\.com',       "🔴 YouTube",       "#FF4444"),
    (r'tiktok\.com',                   "🎵 TikTok",        "#69C9D0"),
    (r'instagram\.com',                "📸 Instagram",     "#E1306C"),
    (r'soundcloud\.com',               "☁️ SoundCloud",    "#FF7700"),
    (r'twitter\.com|x\.com',           "🐦 Twitter/X",     "#1D9BF0"),
    (r'facebook\.com|fb\.watch',       "👤 Facebook",      "#1877F2"),
    (r'vimeo\.com',                    "🎬 Vimeo",         "#1AB7EA"),
    (r'twitch\.tv',                    "💜 Twitch",        "#9146FF"),
    (r'nicovideo\.jp|nico\.ms',        "🇯🇵 NicoNico",    "#E6E6E6"),
    (r'dailymotion\.com',              "🎥 Dailymotion",   "#0066DC"),
    (r'reddit\.com',                   "🟠 Reddit",        "#FF4500"),
    (r'bilibili\.com',                 "📺 Bilibili",      "#00A1D6"),
    (r'pinterest\.com',                "📌 Pinterest",     "#E60023"),
]

# ---------------------------------------------------------------------------
# Tab Name Constants
# ---------------------------------------------------------------------------
TAB_UNDUH = "⚡ Unduh"
TAB_ANTEAN = "📋 Antrean"
TAB_LOG = "📜 Log"

# ---------------------------------------------------------------------------
# Quick Preset Profiles
# ---------------------------------------------------------------------------
QUICK_PRESETS = {
    "🎬 Super Quality": {
        "mode": "video_audio", "container": "mp4", "resolution": "best",
        "video_codec": "best", "audio_codec": "best",
        "audio_format": "mp3", "embed_thumb": True,
        "label_v": "MP4", "label_c": "Auto", "label_a": "Auto", "label_r": "Best"
    },
    "🎵 Musik MP3": {
        "mode": "audio_only", "container": "mp4", "resolution": "1080",
        "video_codec": "best", "audio_codec": "best",
        "audio_format": "mp3", "embed_thumb": True,
        "label_v": "MP4", "label_c": "Auto", "label_a": "Auto", "label_r": "1080p"
    },
    "📱 Hemat Data": {
        "mode": "video_audio", "container": "mp4", "resolution": "720",
        "video_codec": "h264", "audio_codec": "best",
        "audio_format": "mp3", "embed_thumb": True,
        "label_v": "MP4", "label_c": "H.264", "label_a": "Auto", "label_r": "720p"
    },
    "🎙️ Podcast": {
        "mode": "audio_only", "container": "mp4", "resolution": "1080",
        "video_codec": "best", "audio_codec": "best",
        "audio_format": "m4a", "embed_thumb": True,
        "label_v": "MP4", "label_c": "Auto", "label_a": "Auto", "label_r": "1080p"
    },
}


# ===========================================================================
# Settings Window
# ===========================================================================
class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent, current_api_key: str = "", on_save=None):
        super().__init__(parent)
        self.title("⚙️ Pengaturan Maven Downloader")
        self.geometry("500x420")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.configure(fg_color="#0F1017")
        self.on_save_callback = on_save
        self._test_result_var = ctk.StringVar()

        # Center window relative to parent
        self.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width() - 500) // 2
        py = parent.winfo_y() + (parent.winfo_height() - 420) // 2
        self.geometry(f"500x420+{px}+{py}")

        self._build_ui(current_api_key)

    def _build_ui(self, current_api_key: str):
        # Header
        hdr = ctk.CTkFrame(self, fg_color="#181A24", corner_radius=0, height=60)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(
            hdr, text="⚙️  Pengaturan",
            font=ctk.CTkFont(family="Inter", size=16, weight="bold"),
            text_color="#F3F4F6"
        ).pack(side="left", padx=20, pady=0)

        # Body
        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=12)

        # ── Section: Gemini AI ──────────────────────────────────────────────
        sec_ai = ctk.CTkFrame(body, fg_color="#181A24", corner_radius=12)
        sec_ai.pack(fill="x", pady=(0, 12))
        inner_ai = ctk.CTkFrame(sec_ai, fg_color="transparent")
        inner_ai.pack(fill="x", padx=16, pady=14)

        # Title
        ai_title_row = ctk.CTkFrame(inner_ai, fg_color="transparent")
        ai_title_row.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(
            ai_title_row, text="🤖  Gemini AI API Key",
            font=ctk.CTkFont(size=13, weight="bold"), text_color="#F3F4F6"
        ).pack(side="left")

        badge = ctk.CTkFrame(ai_title_row, fg_color="#1E1B4B", corner_radius=6)
        badge.pack(side="left", padx=8)
        ctk.CTkLabel(
            badge, text="google-genai", font=ctk.CTkFont(size=10),
            text_color="#A5B4FC"
        ).pack(padx=6, pady=2)

        ctk.CTkLabel(
            inner_ai,
            text="Dapatkan API Key gratis di:  aistudio.google.com",
            font=ctk.CTkFont(size=11), text_color="#6B7280"
        ).pack(anchor="w", pady=(0, 10))

        # API Key entry row
        key_row = ctk.CTkFrame(inner_ai, fg_color="transparent")
        key_row.pack(fill="x", pady=(0, 8))

        self._show_key = False
        self.api_key_var = ctk.StringVar(value=current_api_key)
        self.api_entry = ctk.CTkEntry(
            key_row, textvariable=self.api_key_var,
            placeholder_text="AIzaSy...",
            show="•", height=38, corner_radius=8,
            border_color="#2D3142", fg_color="#10111A",
            text_color="#F3F4F6", placeholder_text_color="#6B7280",
            font=ctk.CTkFont(size=12)
        )
        self.api_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.toggle_eye_btn = ctk.CTkButton(
            key_row, text="👁", width=38, height=38,
            fg_color="#26293B", hover_color="#31354C",
            font=ctk.CTkFont(size=14),
            command=self._toggle_key_visibility
        )
        self.toggle_eye_btn.pack(side="left")

        # Test connection row
        test_row = ctk.CTkFrame(inner_ai, fg_color="transparent")
        test_row.pack(fill="x", pady=(0, 4))
        self.test_btn = ctk.CTkButton(
            test_row, text="🔌 Test Koneksi",
            command=self._test_connection,
            height=32, corner_radius=8,
            fg_color="#26293B", hover_color="#31354C",
            font=ctk.CTkFont(size=12)
        )
        self.test_btn.pack(side="left")
        self.test_result_lbl = ctk.CTkLabel(
            test_row, textvariable=self._test_result_var,
            font=ctk.CTkFont(size=11), text_color="#9CA3AF",
            wraplength=260
        )
        self.test_result_lbl.pack(side="left", padx=(10, 0))

        # Save button
        ctk.CTkFrame(body, height=1, fg_color="#26293B").pack(fill="x", pady=(4, 12))
        ctk.CTkButton(
            body, text="💾  Simpan Pengaturan",
            command=self._save,
            height=42, corner_radius=10,
            fg_color="#4F46E5", hover_color="#4338CA",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(fill="x")

    def _toggle_key_visibility(self):
        self._show_key = not self._show_key
        self.api_entry.configure(show="" if self._show_key else "•")

    def _test_connection(self):
        self.test_btn.configure(state="disabled", text="⏳ Menghubungi AI...")
        self._test_result_var.set("")
        key = self.api_key_var.get().strip()

        def cb(success, msg):
            if not self.winfo_exists():
                return
            self._test_result_var.set(msg)
            self.test_result_lbl.configure(
                text_color="#10B981" if success else "#EF4444"
            )
            self.test_btn.configure(state="normal", text="🔌 Test Koneksi")

        test_api_connection(key, lambda s, m: self.after(0, lambda: cb(s, m)))

    def _save(self):
        api_key = self.api_key_var.get().strip()
        if self.on_save_callback:
            self.on_save_callback(api_key)
        try:
            self.grab_release()
        except Exception:
            pass
        self.after(20, self.destroy)


# ===========================================================================
# Main Application
# ===========================================================================
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Maven Downloader")
        self.geometry("1440x880")
        self.minsize(1200, 780)

        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        try:
            icon_path = os.path.join(BASE_DIR, "assets", "waifu_icon.ico")
            self.iconbitmap(icon_path)
        except Exception:
            pass

        # ── Download option state vars ──────────────────────────────────────
        self.mode_var = ctk.StringVar(value="video_audio")
        self.custom_cmd_var = ctk.StringVar()
        self.custom_output_path_var = ctk.StringVar(value=load_config())
        self.audio_only_format_var = ctk.StringVar(value="mp3")
        self.resolution_var = ctk.StringVar(value="1080")
        self.video_codec_var = ctk.StringVar(value="best")
        self.audio_codec_var = ctk.StringVar(value="best")
        self.container_var = ctk.StringVar(value="mp4")
        self.download_subs_var = ctk.BooleanVar(value=False)
        self.embed_subs_var = ctk.BooleanVar(value=False)
        self.subs_lang_var = ctk.StringVar(value="id,en")
        self.embed_thumb_var = ctk.BooleanVar(value=True)
        self.use_aria2_var = ctk.BooleanVar(value=False)
        self.download_playlist_var = ctk.BooleanVar(value=False)

        # ── App state ────────────────────────────────────────────────────────
        self.gemini_api_key: str = load_gemini_api_key()
        self.last_video_info: dict = {}
        self._last_log_text: str = ""
        self._settings_window = None
        self._platform_badge_label = None
        # Track whether the dynamic info section has been shown yet
        self._info_container_shown: bool = False
        self._active_thumb_image = None

        self.setup_ui()
        self.after(100, self.process_ui_queue)

    # =========================================================================
    # UI Queue Processor
    # =========================================================================
    def process_ui_queue(self):
        try:
            while True:
                msg = ui_queue.get_nowait()
                msg_type = msg.get("type")

                if msg_type == "log":
                    self.log_area.insert("end", msg["text"])
                    self.log_area.see("end")
                    self._last_log_text += msg["text"]
                    # Jaga buffer log (maks 100KB)
                    if len(self._last_log_text) > 100_000:
                        self._last_log_text = self._last_log_text[-80_000:]

                elif msg_type == "progress":
                    if "value" in msg:
                        self.progress_bar.set(msg["value"])
                    if "text" in msg:
                        self.progress_label.configure(text=msg["text"])
                    # Update statistik unduhan
                    speed = msg.get("speed", "")
                    eta = msg.get("eta", "")
                    size_dl = msg.get("size_dl", "")
                    size_total = msg.get("size_total", "")
                    if speed or eta or size_dl:
                        parts = []
                        if speed:
                            parts.append(f"🚀 {speed}")
                        if eta:
                            parts.append(f"⏱️ ETA {eta}")
                        if size_dl and size_total:
                            parts.append(f"📦 {size_dl} / {size_total}")
                        elif size_dl:
                            parts.append(f"📦 {size_dl}")
                        self.stats_label.configure(text="   ".join(parts))

                elif msg_type == "info_title":
                    self.title_label.configure(text=msg["title"])

                elif msg_type == "info_thumb":
                    self._set_thumb_label(None, text=msg.get("text", "Thumbnail tidak ditemukan."))

                elif msg_type == "info_thumb_data":
                    try:
                        image = Image.open(BytesIO(msg["image_data"]))
                        ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=(348, 196))
                        self._set_thumb_label(ctk_image, text="")
                    except Exception:
                        self._set_thumb_label(None, text="Gagal memuat preview thumbnail.")

                elif msg_type == "info_data":
                    self._on_info_data(msg["data"])

                elif msg_type == "download_finish":
                    self.download_button.configure(
                        text="MULAI UNDUH", fg_color="#10B981", hover_color="#059669",
                        command=self.on_download, state="normal"
                    )
                    self.url_entry.configure(state="normal")
                    self.progress_bar.set(1.0)
                    self.progress_label.configure(text="Status: Unduhan Selesai ✨")
                    self.stats_label.configure(text="")
                    self.show_toast("Unduhan selesai! ✨", "success")
                    # Pindah ke tab Log
                    self.right_tabview.set(TAB_LOG)

                elif msg_type == "download_error":
                    # Tampilkan tombol AI Error Analyzer
                    self._show_ai_error_button()
                    self.show_toast("Unduhan gagal. Gunakan 🤖 Analisis Error untuk bantuan.", "error")

                elif msg_type == "update_finish":
                    self.update_button.configure(state="normal")
                    self.progress_bar.set(1.0)
                    self.progress_label.configure(text="Status: Update Selesai ✨")
                    self.show_toast("yt-dlp berhasil diperbarui!", "success")

                elif msg_type == "ai_result":
                    self._on_ai_result(msg)

        except queue.Empty:
            pass
        self.after(100, self.process_ui_queue)

    # =========================================================================
    # Setup UI
    # =========================================================================
    def setup_ui(self):
        self.configure(fg_color="#0A0B10")

        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=18, pady=18)

        # ─────────────────────────────────────────────────────────────────────
        # 1. HEADER CARD
        # ─────────────────────────────────────────────────────────────────────
        header_card = ctk.CTkFrame(main, fg_color="#13141F", corner_radius=16)
        header_card.pack(fill="x", pady=(0, 14))

        hi = ctk.CTkFrame(header_card, fg_color="transparent")
        hi.pack(fill="x", padx=18, pady=14)

        # ── Brand Row ──────────────────────────────────────────────────────
        brand_row = ctk.CTkFrame(hi, fg_color="transparent")
        brand_row.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            brand_row, text="Maven Downloader",
            font=ctk.CTkFont(family="Inter", size=19, weight="bold"),
            text_color="#F3F4F6"
        ).pack(side="left")

        ver_badge = ctk.CTkFrame(brand_row, fg_color="#1E1B4B", corner_radius=6)
        ver_badge.pack(side="left", padx=10)
        ctk.CTkLabel(
            ver_badge, text="v1.7", font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#818CF8"
        ).pack(padx=8, pady=2)

        # Settings button — far right
        ctk.CTkButton(
            brand_row, text="⚙️  Pengaturan",
            command=self.open_settings,
            width=110, height=28, corner_radius=7,
            fg_color="#26293B", hover_color="#31354C",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#D1D5DB"
        ).pack(side="right")

        # ── URL Row ───────────────────────────────────────────────────────
        url_row = ctk.CTkFrame(hi, fg_color="transparent")
        url_row.pack(fill="x", pady=(0, 8))

        # Platform badge (hidden initially)
        self.platform_badge = ctk.CTkFrame(url_row, fg_color="#26293B", corner_radius=8, width=0)
        self.platform_badge.pack(side="left")
        self.platform_badge.pack_forget()  # start hidden
        self._platform_label = ctk.CTkLabel(
            self.platform_badge, text="",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#F3F4F6"
        )
        self._platform_label.pack(padx=8, pady=5)

        self.url_entry = ctk.CTkEntry(
            url_row,
            placeholder_text="Tempelkan link YouTube, TikTok, Instagram, atau URL lainnya...",
            height=44, corner_radius=10,
            border_color="#2D3142", fg_color="#0E0F17",
            text_color="#F3F4F6", placeholder_text_color="#6B7280",
            font=ctk.CTkFont(size=13)
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(6, 8))
        self.url_entry.bind("<KeyRelease>", self._on_url_keyrelease)
        self.url_entry.bind("<FocusIn>", self._on_url_focus)

        # Paste button
        ctk.CTkButton(
            url_row, text="📋", width=44, height=44,
            corner_radius=10, fg_color="#26293B", hover_color="#31354C",
            font=ctk.CTkFont(size=16),
            command=self._auto_paste
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            url_row, text="Cek Info",
            command=self.on_get_info,
            width=110, height=44, corner_radius=10,
            font=ctk.CTkFont(weight="bold", size=13),
            fg_color="#4F46E5", hover_color="#4338CA"
        ).pack(side="left", padx=(0, 8))

        self.download_button = ctk.CTkButton(
            url_row, text="MULAI UNDUH",
            command=self.on_download,
            width=150, height=44, corner_radius=10,
            font=ctk.CTkFont(weight="bold", size=13),
            fg_color="#10B981", hover_color="#059669"
        )
        self.download_button.pack(side="left")

        # ── Tools Row ─────────────────────────────────────────────────────
        tools_row = ctk.CTkFrame(hi, fg_color="transparent")
        tools_row.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            tools_row, text="Lokasi Simpan:",
            font=ctk.CTkFont(size=12), text_color="#9CA3AF"
        ).pack(side="left", padx=(0, 6))

        ctk.CTkLabel(
            tools_row, textvariable=self.custom_output_path_var,
            text_color="#38BDF8", font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left", padx=(0, 12))

        for (label, cmd, w) in [
            ("Ubah Folder", self.select_folder, 90),
            ("Buka Folder", self.open_folder, 90),
        ]:
            ctk.CTkButton(
                tools_row, text=label, command=cmd,
                width=w, height=28, corner_radius=6, font=ctk.CTkFont(size=11),
                fg_color="#26293B", hover_color="#31354C", text_color="#E5E7EB"
            ).pack(side="left", padx=3)

        self.update_button = ctk.CTkButton(
            tools_row, text="Update yt-dlp", command=self.on_update,
            width=105, height=28, corner_radius=6,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#D97706", hover_color="#B45309", text_color="#FFFFFF"
        )
        self.update_button.pack(side="left", padx=3)

        # ── Quick Preset Row ───────────────────────────────────────────────
        preset_row = ctk.CTkFrame(hi, fg_color="transparent")
        preset_row.pack(fill="x")

        ctk.CTkLabel(
            preset_row, text="⚡ Preset Cepat:",
            font=ctk.CTkFont(size=11), text_color="#6B7280"
        ).pack(side="left", padx=(0, 8))

        preset_colors = {
            "🎬 Super Quality": ("#4F46E5", "#4338CA"),
            "🎵 Musik MP3":     ("#7C3AED", "#6D28D9"),
            "📱 Hemat Data":    ("#0891B2", "#0E7490"),
            "🎙️ Podcast":       ("#059669", "#047857"),
        }
        for name in QUICK_PRESETS:
            fc, hc = preset_colors.get(name, ("#26293B", "#31354C"))
            ctk.CTkButton(
                preset_row, text=name,
                command=lambda n=name: self.apply_preset(n),
                height=26, corner_radius=6, font=ctk.CTkFont(size=11),
                fg_color=fc, hover_color=hc, text_color="#F3F4F6"
            ).pack(side="left", padx=3)

        # ─────────────────────────────────────────────────────────────────────
        # 2. CONTENT SPLIT
        # ─────────────────────────────────────────────────────────────────────
        content_split = ctk.CTkFrame(main, fg_color="transparent")
        content_split.pack(fill="both", expand=True)

        # ══ LEFT CARD: MEDIA PREVIEW ══════════════════════════════════════
        preview_card = ctk.CTkFrame(content_split, width=390, fg_color="#13141F", corner_radius=16)
        preview_card.pack(side="left", fill="y", padx=(0, 14))
        preview_card.pack_propagate(False)

        pi = ctk.CTkFrame(preview_card, fg_color="transparent")
        pi.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            pi, text="Informasi Media",
            font=ctk.CTkFont(size=14, weight="bold"), text_color="#F3F4F6"
        ).pack(anchor="w", pady=(0, 10))

        # Thumbnail
        self.thumb_label = ctk.CTkLabel(
            pi, text="Pratinjau Thumbnail",
            width=358, height=200,
            fg_color="#0E0F17", corner_radius=10, text_color="#6B7280"
        )
        self.thumb_label.pack(fill="x", pady=(0, 10))

        # Video Title
        self.title_label = ctk.CTkLabel(
            pi,
            text="Judul video akan muncul di sini setelah menekan tombol Cek Info.",
            wraplength=354, justify="left",
            font=ctk.CTkFont(size=12), text_color="#E5E7EB"
        )
        self.title_label.pack(fill="x", anchor="w", pady=(0, 8))

        # ── Dynamic Info Container ────────────────────────────────────────
        # Single container wrapping meta + badges + AI panel.
        # Packed ONCE on first _on_info_data(); never pack_forgot again.
        # This prevents pack-ordering bugs when switching between URLs.
        self._info_container = ctk.CTkFrame(pi, fg_color="transparent")
        # (NOT packed yet — packed on first successful Cek Info)

        # Metadata grid (channel, duration, views)
        self.meta_frame = ctk.CTkFrame(self._info_container, fg_color="#0E0F17", corner_radius=8)
        self.meta_frame.pack(fill="x", pady=(0, 8))

        meta_inner = ctk.CTkFrame(self.meta_frame, fg_color="transparent")
        meta_inner.pack(fill="x", padx=10, pady=8)

        self.meta_channel = ctk.CTkLabel(
            meta_inner, text="", font=ctk.CTkFont(size=11), text_color="#9CA3AF", anchor="w"
        )
        self.meta_channel.pack(fill="x")
        self.meta_duration = ctk.CTkLabel(
            meta_inner, text="", font=ctk.CTkFont(size=11), text_color="#9CA3AF", anchor="w"
        )
        self.meta_duration.pack(fill="x")
        self.meta_views = ctk.CTkLabel(
            meta_inner, text="", font=ctk.CTkFont(size=11), text_color="#9CA3AF", anchor="w"
        )
        self.meta_views.pack(fill="x")

        # Quality badges row (always packed inside container; children rebuilt each time)
        self.badges_frame = ctk.CTkFrame(self._info_container, fg_color="transparent")
        self.badges_frame.pack(fill="x", pady=(0, 4))

        # ── Contextual AI Panel ────────────────────────────────────────────
        self.ai_panel = ctk.CTkFrame(self._info_container, fg_color="#0D0F1C", corner_radius=10)
        self.ai_panel.pack(fill="x", pady=(0, 8))

        ai_hdr = ctk.CTkFrame(self.ai_panel, fg_color="transparent")
        ai_hdr.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkLabel(
            ai_hdr, text="🤖 Maven AI",
            font=ctk.CTkFont(size=11, weight="bold"), text_color="#818CF8"
        ).pack(side="left")

        ai_btn_row = ctk.CTkFrame(self.ai_panel, fg_color="transparent")
        ai_btn_row.pack(fill="x", padx=10, pady=(0, 6))

        self.ai_metadata_btn = ctk.CTkButton(
            ai_btn_row, text="🏷️ AI Metadata",
            command=self.on_ai_metadata,
            height=28, corner_radius=6,
            fg_color="#1E1B4B", hover_color="#2D2A6E",
            text_color="#A5B4FC", font=ctk.CTkFont(size=11),
            state="disabled"  # enabled after first successful Cek Info
        )
        self.ai_metadata_btn.pack(side="left", padx=(0, 6))

        self.ai_settings_btn = ctk.CTkButton(
            ai_btn_row, text="⚙️ AI Settings",
            command=self.on_ai_recommend_settings,
            height=28, corner_radius=6,
            fg_color="#1E1B4B", hover_color="#2D2A6E",
            text_color="#A5B4FC", font=ctk.CTkFont(size=11),
            state="disabled"  # enabled after first successful Cek Info
        )
        self.ai_settings_btn.pack(side="left", padx=(0, 6))

        self.ai_error_btn = ctk.CTkButton(
            ai_btn_row, text="🔍 Analisis Error",
            command=self.on_analyze_error,
            height=28, corner_radius=6,
            fg_color="#3B1515", hover_color="#5B2525",
            text_color="#FCA5A5", font=ctk.CTkFont(size=11)
        )
        # ai_error_btn: never packed until download_error event fires

        # AI result text area — packed only when showing a result
        self.ai_result_text = ctk.CTkTextbox(
            self.ai_panel,
            height=110, font=ctk.CTkFont(family="Consolas", size=10),
            fg_color="#080910", text_color="#C4B5FD",
            border_color="#1E1B4B", border_width=1, corner_radius=6,
            wrap="word"
        )
        # ai_result_text starts hidden; shown via _show_ai_result()

        # ── Progress Section ─────────────────────────────────────────────
        prog_card = ctk.CTkFrame(pi, fg_color="#0E0F17", corner_radius=10)
        prog_card.pack(fill="x", side="bottom", pady=(8, 0))

        prog_inner = ctk.CTkFrame(prog_card, fg_color="transparent")
        prog_inner.pack(fill="x", padx=12, pady=10)

        self.progress_label = ctk.CTkLabel(
            prog_inner, text="Status: Siap",
            font=ctk.CTkFont(size=11, weight="bold"), text_color="#9CA3AF"
        )
        self.progress_label.pack(anchor="w", pady=(0, 5))

        self.progress_bar = ctk.CTkProgressBar(
            prog_inner, height=8, corner_radius=4,
            progress_color="#10B981", fg_color="#1F2937"
        )
        self.progress_bar.pack(fill="x")
        self.progress_bar.set(0)

        self.stats_label = ctk.CTkLabel(
            prog_inner, text="",
            font=ctk.CTkFont(size=10), text_color="#6B7280"
        )
        self.stats_label.pack(anchor="w", pady=(4, 0))

        # ══ RIGHT PANEL: TABVIEW ══════════════════════════════════════════
        right_panel = ctk.CTkFrame(content_split, fg_color="transparent")
        right_panel.pack(side="left", fill="both", expand=True)

        self.right_tabview = ctk.CTkTabview(
            right_panel,
            fg_color="#13141F",
            segmented_button_fg_color="#0A0B10",
            segmented_button_selected_color="#4F46E5",
            segmented_button_selected_hover_color="#4338CA",
            segmented_button_unselected_color="#0A0B10",
            segmented_button_unselected_hover_color="#1E2030",
            text_color="#D1D5DB",
            corner_radius=16
        )
        self.right_tabview.pack(fill="both", expand=True)

        tab_dl = self.right_tabview.add(TAB_UNDUH)
        tab_queue = self.right_tabview.add(TAB_ANTEAN)
        tab_log = self.right_tabview.add(TAB_LOG)

        # ── Tab: ⚡ Unduh ─────────────────────────────────────────────────
        self._build_download_tab(tab_dl)

        # ── Tab: 📋 Antrean ───────────────────────────────────────────────
        self._build_queue_tab(tab_queue)

        # ── Tab: 📜 Log ───────────────────────────────────────────────────
        self._build_log_tab(tab_log)

        # Init toggle
        self.toggle_opts()

    # =========================================================================
    # Tab Builders
    # =========================================================================
    def _build_download_tab(self, parent):
        """Bangun tab ⚡ Unduh dengan semua opsi download."""
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        oi = ctk.CTkFrame(scroll, fg_color="transparent")
        oi.pack(fill="x", padx=4, pady=8)

        # ── Mode Switcher ────────────────────────────────────────────────
        mode_row = ctk.CTkFrame(oi, fg_color="transparent")
        mode_row.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            mode_row, text="Mode Unduhan:",
            font=ctk.CTkFont(size=11, weight="bold"), text_color="#9CA3AF"
        ).pack(anchor="w", pady=(0, 4))
        self.mode_segmented = ctk.CTkSegmentedButton(
            mode_row,
            values=["Video + Audio", "Audio Only"],
            command=self.on_mode_segment_change,
            selected_color="#4F46E5", selected_hover_color="#4338CA",
            unselected_color="#10111A", unselected_hover_color="#26293B",
            text_color="#F3F4F6", font=ctk.CTkFont(size=12, weight="bold")
        )
        self.mode_segmented.set("Video + Audio")
        self.mode_segmented.pack(anchor="w")

        # ── Dynamic Mode Content ─────────────────────────────────────────
        self.mode_content_frame = ctk.CTkFrame(oi, fg_color="transparent")
        self.mode_content_frame.pack(fill="x", pady=(0, 12))

        # Audio-only opts
        self.audio_opts = ctk.CTkFrame(self.mode_content_frame, fg_color="transparent")
        a_fmt_box = ctk.CTkFrame(self.audio_opts, fg_color="transparent")
        a_fmt_box.pack(side="left")
        ctk.CTkLabel(
            a_fmt_box, text="Format Audio:",
            font=ctk.CTkFont(size=11, weight="bold"), text_color="#9CA3AF"
        ).pack(anchor="w", pady=(0, 4))
        self.audio_fmt_segmented = ctk.CTkSegmentedButton(
            a_fmt_box, values=["MP3", "M4A", "FLAC", "WAV", "OPUS"],
            command=self.on_audio_fmt_change,
            selected_color="#4F46E5", selected_hover_color="#4338CA",
            unselected_color="#10111A", unselected_hover_color="#26293B",
            text_color="#F3F4F6", font=ctk.CTkFont(size=12, weight="bold")
        )
        self.audio_fmt_segmented.set("MP3")
        self.audio_fmt_segmented.pack(anchor="w")

        # Video opts
        self.video_opts = ctk.CTkFrame(self.mode_content_frame, fg_color="transparent")

        v_row1 = ctk.CTkFrame(self.video_opts, fg_color="transparent")
        v_row1.pack(fill="x", pady=(0, 10))

        def _seg_box(parent, label, values, cmd, default):
            box = ctk.CTkFrame(parent, fg_color="transparent")
            box.pack(side="left", padx=(0, 16))
            ctk.CTkLabel(
                box, text=label,
                font=ctk.CTkFont(size=11, weight="bold"), text_color="#9CA3AF"
            ).pack(anchor="w", pady=(0, 4))
            seg = ctk.CTkSegmentedButton(
                box, values=values, command=cmd,
                selected_color="#4F46E5", selected_hover_color="#4338CA",
                unselected_color="#10111A", unselected_hover_color="#26293B",
                text_color="#F3F4F6", font=ctk.CTkFont(size=11, weight="bold")
            )
            seg.set(default)
            seg.pack(anchor="w")
            return seg

        self.video_fmt_segmented = _seg_box(
            v_row1, "Format Video:", ["MP4", "MKV", "WEBM", "MOV", "AVI"],
            self.on_video_fmt_change, "MP4"
        )
        self.v_codec_segmented = _seg_box(
            v_row1, "Video Codec:", ["Auto", "H.264", "VP9", "AV1"],
            self.on_vcodec_change, "Auto"
        )
        self.a_codec_segmented = _seg_box(
            v_row1, "Audio Codec:", ["Auto", "M4A", "Opus"],
            self.on_acodec_change, "Auto"
        )

        v_row2 = ctk.CTkFrame(self.video_opts, fg_color="transparent")
        v_row2.pack(fill="x")
        ctk.CTkLabel(
            v_row2, text="Kualitas Maksimal:",
            font=ctk.CTkFont(size=11, weight="bold"), text_color="#9CA3AF"
        ).pack(anchor="w", pady=(0, 4))
        self.res_segmented = ctk.CTkSegmentedButton(
            v_row2,
            values=["Best", "4K", "1440p", "1080p", "720p", "480p", "360p"],
            command=self.on_res_segmented_change,
            selected_color="#4F46E5", selected_hover_color="#4338CA",
            unselected_color="#10111A", unselected_hover_color="#26293B",
            text_color="#F3F4F6", font=ctk.CTkFont(size=12, weight="bold")
        )
        self.res_segmented.set("1080p")
        self.res_segmented.pack(fill="x")

        # Divider
        ctk.CTkFrame(oi, height=1, fg_color="#26293B").pack(fill="x", pady=(4, 12))

        # ── Language selector ────────────────────────────────────────────
        lang_box = ctk.CTkFrame(oi, fg_color="transparent")
        lang_box.pack(fill="x", pady=(0, 10))

        self.lang_label = ctk.CTkLabel(
            lang_box, text="Bahasa Subtitle / Lirik:",
            font=ctk.CTkFont(size=11, weight="bold"), text_color="#9CA3AF"
        )
        self.lang_label.pack(anchor="w", pady=(0, 4))

        lang_ctrl = ctk.CTkFrame(lang_box, fg_color="transparent")
        lang_ctrl.pack(fill="x")

        self.lang_optionmenu = ctk.CTkOptionMenu(
            lang_ctrl, values=list(LANG_PRESETS.keys()),
            command=self.on_lang_preset_change,
            fg_color="#10111A", button_color="#26293B",
            button_hover_color="#31354C", text_color="#F3F4F6",
            dropdown_fg_color="#13141F", dropdown_hover_color="#26293B",
            font=ctk.CTkFont(size=12), height=32, width=260
        )
        self.lang_optionmenu.set("🇮🇩 Indonesia & 🇬🇧 English")
        self.lang_optionmenu.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(
            lang_ctrl, text="Kode ISO:", font=ctk.CTkFont(size=11), text_color="#6B7280"
        ).pack(side="left", padx=(0, 4))
        self.lang_entry = ctk.CTkEntry(
            lang_ctrl, textvariable=self.subs_lang_var,
            width=100, height=32, corner_radius=6,
            border_color="#2D3142", fg_color="#10111A",
            text_color="#38BDF8", font=ctk.CTkFont(size=12, weight="bold")
        )
        self.lang_entry.pack(side="left")

        # Divider
        ctk.CTkFrame(oi, height=1, fg_color="#26293B").pack(fill="x", pady=(6, 12))

        # ── Checkboxes ───────────────────────────────────────────────────
        extras = ctk.CTkFrame(oi, fg_color="transparent")
        extras.pack(fill="x")

        cb_style = dict(font=ctk.CTkFont(size=12), fg_color="#4F46E5", hover_color="#4338CA")
        self.embed_thumb_cb = ctk.CTkCheckBox(
            extras, text="Embed Thumb", variable=self.embed_thumb_var, **cb_style
        )
        self.embed_thumb_cb.grid(row=0, column=0, padx=(0, 14), pady=3, sticky="w")

        self.embed_subs_cb = ctk.CTkCheckBox(
            extras, text="Embed Sub (Otomatis Aktif)", variable=self.embed_subs_var, **cb_style
        )
        self.embed_subs_cb.grid(row=0, column=1, padx=(0, 14), pady=3, sticky="w")

        self.download_subs_cb = ctk.CTkCheckBox(
            extras, text="Download Sub Terpisah", variable=self.download_subs_var, **cb_style
        )
        self.download_subs_cb.grid(row=0, column=2, padx=(0, 14), pady=3, sticky="w")

        self.use_aria2_cb = ctk.CTkCheckBox(
            extras, text="Aria2c Downloader", variable=self.use_aria2_var, **cb_style
        )
        self.use_aria2_cb.grid(row=0, column=3, padx=(0, 14), pady=3, sticky="w")

        self.download_playlist_cb = ctk.CTkCheckBox(
            extras, text="Full Playlist", variable=self.download_playlist_var, **cb_style
        )
        self.download_playlist_cb.grid(row=0, column=4, pady=3, sticky="w")

        # ── Custom Command ───────────────────────────────────────────────
        ctk.CTkFrame(oi, height=1, fg_color="#26293B").pack(fill="x", pady=(12, 8))

        ctk.CTkLabel(
            oi, text="Perintah Custom (Opsional):",
            font=ctk.CTkFont(size=11, weight="bold"), text_color="#6B7280"
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkEntry(
            oi, textvariable=self.custom_cmd_var,
            placeholder_text="Contoh: --sponsorblock-remove sponsor",
            height=32, corner_radius=8,
            border_color="#2D3142", fg_color="#0E0F17",
            text_color="#D1D5DB", placeholder_text_color="#4B5563",
            font=ctk.CTkFont(size=11)
        ).pack(fill="x")

    def _build_queue_tab(self, parent):
        """Bangun tab 📋 Antrean — batch download queue sederhana."""
        qi = ctk.CTkFrame(parent, fg_color="transparent")
        qi.pack(fill="both", expand=True, padx=4, pady=8)

        hdr = ctk.CTkFrame(qi, fg_color="transparent")
        hdr.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(
            hdr, text="Antrean Unduhan (Batch)",
            font=ctk.CTkFont(size=13, weight="bold"), text_color="#F3F4F6"
        ).pack(side="left")
        ctk.CTkButton(
            hdr, text="🗑️ Kosongkan",
            command=self._clear_queue_input,
            width=90, height=26, corner_radius=6, font=ctk.CTkFont(size=10),
            fg_color="#26293B", hover_color="#31354C", text_color="#9CA3AF"
        ).pack(side="right")

        ctk.CTkLabel(
            qi,
            text="Masukkan satu URL per baris. Gunakan tombol ➕ Tambahkan ke Antrean lalu tekan Mulai Semua.",
            font=ctk.CTkFont(size=11), text_color="#6B7280", wraplength=700, justify="left"
        ).pack(anchor="w", pady=(0, 6))

        self.queue_textbox = ctk.CTkTextbox(
            qi, height=140, font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="#0E0F17", text_color="#D1D5DB",
            border_color="#26293B", border_width=1, corner_radius=8
        )
        self.queue_textbox.pack(fill="x", pady=(0, 8))

        btn_row = ctk.CTkFrame(qi, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 10))
        ctk.CTkButton(
            btn_row, text="➕  Tambahkan ke Antrean",
            command=self._add_to_queue,
            height=34, corner_radius=8,
            fg_color="#4F46E5", hover_color="#4338CA",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_row, text="▶  Mulai Semua",
            command=self._start_queue,
            height=34, corner_radius=8,
            fg_color="#10B981", hover_color="#059669",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left")
        ctk.CTkButton(
            btn_row, text="📂  Import dari .txt",
            command=self._import_queue_txt,
            height=34, corner_radius=8,
            fg_color="#26293B", hover_color="#31354C",
            font=ctk.CTkFont(size=12)
        ).pack(side="right")

        # Queue list display
        self.queue_list_frame = ctk.CTkScrollableFrame(
            qi, fg_color="#0E0F17", corner_radius=8
        )
        self.queue_list_frame.pack(fill="both", expand=True)

        self._queue_items = []  # List of (url, status_label)

    def _build_log_tab(self, parent):
        """Bangun tab 📜 Log — terminal output yt-dlp."""
        li = ctk.CTkFrame(parent, fg_color="transparent")
        li.pack(fill="both", expand=True, padx=4, pady=8)

        log_hdr = ctk.CTkFrame(li, fg_color="transparent")
        log_hdr.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(
            log_hdr, text="Log Eksekusi / Terminal",
            font=ctk.CTkFont(size=13, weight="bold"), text_color="#F3F4F6"
        ).pack(side="left")
        ctk.CTkButton(
            log_hdr, text="Bersihkan Log", command=self.clear_log,
            width=90, height=26, corner_radius=6, font=ctk.CTkFont(size=10),
            fg_color="#26293B", hover_color="#31354C", text_color="#9CA3AF"
        ).pack(side="right")

        self.log_area = ctk.CTkTextbox(
            li,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="#080910", text_color="#D1D5DB",
            border_color="#1F2937", border_width=1, corner_radius=8
        )
        self.log_area.pack(fill="both", expand=True)

    # =========================================================================
    # Info Data Handler (after Cek Info)
    # =========================================================================
    def _on_info_data(self, info: dict):
        self.last_video_info = info

        # ── Update metadata labels ───────────────────────────────────────
        channel = info.get('uploader') or info.get('channel') or info.get('uploader_id', '')
        self.meta_channel.configure(text=f"👤 {channel}" if channel else "")

        dur_str = info.get('duration_string', '')
        if not dur_str:
            dur_sec = info.get('duration', 0)
            if dur_sec:
                m, s = divmod(int(dur_sec), 60)
                h, m = divmod(m, 60)
                dur_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
        self.meta_duration.configure(text=f"⏱️  {dur_str}" if dur_str else "")

        vc = info.get('view_count', 0)
        if vc:
            vc_str = f"{vc:,}".replace(",", ".")
            self.meta_views.configure(text=f"👁️  {vc_str} penonton")
        else:
            self.meta_views.configure(text="")

        # ── Rebuild quality badges (always destroy & recreate) ────────────
        for widget in self.badges_frame.winfo_children():
            widget.destroy()

        formats = info.get('formats', [])
        heights = set(f.get('height', 0) for f in formats if f.get('height'))
        fps_vals = [f.get('fps', 0) for f in formats if f.get('fps')]
        has_hdr = any(
            str(f.get('dynamic_range', '')).upper() in ('HDR', 'HDR10', 'HDR10+', 'DOVI', 'HLG')
            for f in formats
        )
        badges = []
        max_h = max(heights, default=0)
        if max_h >= 2160: badges.append(("4K", "#F59E0B"))
        if max_h >= 1440: badges.append(("1440p", "#10B981"))
        if max_h >= 1080: badges.append(("1080p", "#3B82F6"))
        if any(f >= 59 for f in fps_vals): badges.append(("60FPS", "#8B5CF6"))
        if has_hdr: badges.append(("HDR", "#F97316"))

        if badges:
            ctk.CTkLabel(
                self.badges_frame, text="🏷️",
                font=ctk.CTkFont(size=10), text_color="#6B7280"
            ).pack(side="left", padx=(0, 4))
            for (badge_text, fg) in badges:
                b = ctk.CTkFrame(self.badges_frame, fg_color=fg, corner_radius=5)
                b.pack(side="left", padx=2)
                ctk.CTkLabel(
                    b, text=badge_text, font=ctk.CTkFont(size=9, weight="bold"),
                    text_color="white"
                ).pack(padx=5, pady=2)

        # ── Show info container (only packed once, stays in place after) ──
        if not self._info_container_shown:
            self._info_container.pack(fill="x", pady=(0, 4))
            self._info_container_shown = True

        # Enable AI buttons
        self.ai_metadata_btn.configure(state="normal")
        self.ai_settings_btn.configure(state="normal")

        # Show API key hint if not configured
        if not self.gemini_api_key:
            self._show_ai_result(
                "ℹ️ API Key belum diatur.\nBuka ⚙️ Pengaturan untuk memasukkan Gemini API Key\nagar fitur AI dapat digunakan.",
                color="#6B7280"
            )

    # =========================================================================
    # AI Feature Handlers
    # =========================================================================
    def on_ai_metadata(self):
        if not self._check_api_key():
            return
        title = self.last_video_info.get('title', '')
        if not title:
            self.show_toast("Lakukan Cek Info terlebih dahulu.", "warning")
            return
        uploader = (self.last_video_info.get('uploader')
                    or self.last_video_info.get('channel', ''))
        self.ai_metadata_btn.configure(text="⏳ Memproses...", state="disabled")
        self.ai_settings_btn.configure(state="disabled")
        self._show_ai_result("🤖 Maven AI sedang menganalisis metadata lagu...", color="#818CF8")

        def cb(result):
            ui_queue.put({"type": "ai_result", "result_type": "metadata", "data": result})

        clean_media_metadata(title, uploader, self.gemini_api_key, cb)

    def on_ai_recommend_settings(self):
        if not self._check_api_key():
            return
        if not self.last_video_info:
            self.show_toast("Lakukan Cek Info terlebih dahulu.", "warning")
            return
        self.ai_settings_btn.configure(text="⏳ Memproses...", state="disabled")
        self.ai_metadata_btn.configure(state="disabled")
        self._show_ai_result("🤖 Maven AI sedang menganalisis video dan menyiapkan rekomendasi...", color="#818CF8")

        def cb(result):
            ui_queue.put({"type": "ai_result", "result_type": "settings", "data": result})

        recommend_download_settings(self.last_video_info, self.gemini_api_key, cb)

    def on_analyze_error(self):
        if not self._check_api_key():
            return
        log_text = self._last_log_text
        if not log_text.strip():
            self.show_toast("Tidak ada log error untuk dianalisis.", "warning")
            return
        self.ai_error_btn.configure(text="⏳ Menganalisis...", state="disabled")
        self._show_ai_result("🤖 Maven AI sedang membaca log dan menganalisis error...", color="#818CF8")
        # Switch to Log tab so user can see context
        self.right_tabview.set(TAB_LOG)

        def cb(result):
            ui_queue.put({"type": "ai_result", "result_type": "error_analysis", "data": result})

        analyze_download_error(log_text, self.gemini_api_key, cb)

    def _on_ai_result(self, msg: dict):
        """Handle AI result messages dari ui_queue."""
        result_type = msg.get("result_type")
        data = msg.get("data")

        # Re-enable buttons
        self.ai_metadata_btn.configure(text="🏷️ AI Metadata", state="normal")
        self.ai_settings_btn.configure(text="⚙️ AI Settings", state="normal")
        self.ai_error_btn.configure(text="🔍 Analisis Error", state="normal")

        if result_type == "metadata":
            if isinstance(data, dict) and "error" in data:
                self._show_ai_result(f"❌ {data['error']}", color="#EF4444")
            elif isinstance(data, dict) and data.get("not_music"):
                self._show_ai_result(
                    f"ℹ️ Bukan video musik.\n{data.get('reason', '')}",
                    color="#6B7280"
                )
            else:
                confidence_color = {
                    "high": "✅", "medium": "⚠️", "low": "❓"
                }.get(str(data.get('confidence', '')).lower(), "🔍")
                text = (
                    f"🎵 AI Metadata Result:\n"
                    f"━━━━━━━━━━━━━━━━━\n"
                    f"🎵 Judul  : {data.get('song_title', '-')}\n"
                    f"👤 Artis  : {data.get('artist', '-')}\n"
                    f"📀 Album  : {data.get('album', '-') or '—'}\n"
                    f"🏷️ Genre  : {data.get('genre', '-')}\n"
                    f"📅 Tahun  : {data.get('year', '-') or '—'}\n"
                    f"🎯 Akurasi: {confidence_color} {str(data.get('confidence', '-')).upper()}"
                )
                self._show_ai_result(text, color="#C4B5FD")
                self.show_toast("✅ Metadata AI berhasil dianalisis!", "success")

        elif result_type == "settings":
            if isinstance(data, dict) and "error" in data:
                self._show_ai_result(f"❌ {data['error']}", color="#EF4444")
            else:
                reasoning = data.get('reasoning', 'Pengaturan optimal telah dipilih.')
                text = f"⚙️ AI Rekomendasi Setting:\n━━━━━━━━━━━━━━━━━\n{reasoning}"
                self._show_ai_result(text, color="#A5F3FC")
                # Apply recommended settings to UI widgets
                self.apply_ai_settings(data)
                self.show_toast("⚙️ Setting otomatis diterapkan!", "info")

        elif result_type == "error_analysis":
            self._show_ai_result(
                data if isinstance(data, str) else str(data),
                color="#FCA5A5"
            )

    def apply_ai_settings(self, data: dict):
        """Terapkan rekomendasi setting dari AI ke widget UI."""
        mode = data.get("mode", "")
        if mode == "audio_only":
            self.mode_var.set("audio_only")
            self.mode_segmented.set("Audio Only")
            af = data.get("audio_format", "mp3").upper()
            if af in ["MP3", "M4A", "FLAC", "WAV", "OPUS"]:
                self.audio_fmt_segmented.set(af)
                self.audio_only_format_var.set(af.lower())
        elif mode == "video_audio":
            self.mode_var.set("video_audio")
            self.mode_segmented.set("Video + Audio")
            container = data.get("container", "mp4").upper()
            if container in ["MP4", "MKV", "WEBM", "MOV", "AVI"]:
                self.video_fmt_segmented.set(container)
                self.container_var.set(container.lower())
            # Resolution
            res = str(data.get("resolution", "1080"))
            res_map_rev = {
                "best": "Best", "2160": "4K", "1440": "1440p",
                "1080": "1080p", "720": "720p", "480": "480p", "360": "360p"
            }
            r_label = res_map_rev.get(res, "1080p")
            self.res_segmented.set(r_label)
            self.resolution_var.set(res)
            # Video codec
            vc = data.get("video_codec", "best")
            vc_label_map = {"best": "Auto", "h264": "H.264", "vp9": "VP9", "av1": "AV1"}
            self.v_codec_segmented.set(vc_label_map.get(vc, "Auto"))
            self.video_codec_var.set(vc)
            # Audio codec
            ac = data.get("audio_codec", "best")
            ac_label_map = {"best": "Auto", "m4a": "M4A", "opus": "Opus"}
            self.a_codec_segmented.set(ac_label_map.get(ac, "Auto"))
            self.audio_codec_var.set(ac)
        # Embed thumb
        if "embed_thumb" in data:
            self.embed_thumb_var.set(bool(data["embed_thumb"]))
        self.toggle_opts()

    def _show_ai_result(self, text: str, color: str = "#C4B5FD"):
        """Tampilkan teks hasil AI di area bawah panel AI."""
        self.ai_result_text.configure(text_color=color)
        self.ai_result_text.delete("1.0", "end")
        self.ai_result_text.insert("end", text)
        # Only pack if not already in layout
        if not self.ai_result_text.winfo_ismapped():
            self.ai_result_text.pack(fill="x", padx=10, pady=(0, 8))

    def _show_ai_error_button(self):
        """Tampilkan tombol 🔍 Analisis Error di panel AI (setelah download gagal)."""
        # Make sure info container is visible (even if Cek Info was never pressed)
        if not self._info_container_shown:
            self._info_container.pack(fill="x", pady=(0, 4))
            self._info_container_shown = True
        # Pack the error button if not already shown
        if not self.ai_error_btn.winfo_ismapped():
            self.ai_error_btn.pack(side="left", padx=(0, 6))

    def _check_api_key(self) -> bool:
        if not self.gemini_api_key:
            self.show_toast("Atur Gemini API Key di ⚙️ Pengaturan terlebih dahulu.", "warning")
            self.open_settings()
            return False
        return True

    # =========================================================================
    # Batch Queue Tab Actions
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
        self.show_toast(f"✅ {len(urls)} URL ditambahkan ke antrean.", "success")

    def _add_queue_item(self, url: str):
        item_frame = ctk.CTkFrame(self.queue_list_frame, fg_color="#13141F", corner_radius=8)
        item_frame.pack(fill="x", pady=3)
        inner = ctk.CTkFrame(item_frame, fg_color="transparent")
        inner.pack(fill="x", padx=10, pady=6)
        url_lbl = ctk.CTkLabel(
            inner, text=url[:80] + ("..." if len(url) > 80 else ""),
            font=ctk.CTkFont(size=11), text_color="#9CA3AF", anchor="w"
        )
        url_lbl.pack(side="left", fill="x", expand=True)
        status_var = ctk.StringVar(value="⏳ Menunggu")
        status_lbl = ctk.CTkLabel(
            inner, textvariable=status_var, font=ctk.CTkFont(size=11),
            text_color="#6B7280", width=100
        )
        status_lbl.pack(side="right")
        self._queue_items.append((url, status_var))

    def _start_queue(self):
        if not self._queue_items:
            self.show_toast("Antrean kosong.", "warning")
            return
        self.show_toast(f"Memulai {len(self._queue_items)} unduhan dalam antrean...", "info")

        def _run_queue():
            for (url, status_var) in self._queue_items:
                self.after(0, lambda sv=status_var: sv.set("🔄 Mengunduh"))
                # Set URL and trigger download
                self.after(0, lambda u=url: self.url_entry.delete(0, "end"))
                self.after(0, lambda u=url: self.url_entry.insert(0, u))
                # Use an event to wait for download completion
                import time
                # Simple sequential approach: trigger and wait
                done_event = threading.Event()
                original_finish = None

                def _patched_finish(sv=status_var, ev=done_event):
                    sv.set("✅ Selesai")
                    ev.set()

                self.after(0, self.on_download)
                # Wait up to 30 minutes per item
                done_event.wait(timeout=1800)
                import time; time.sleep(1)

        threading.Thread(target=_run_queue, daemon=True).start()

    def _clear_queue_input(self):
        self.queue_textbox.delete("1.0", "end")
        for widget in self.queue_list_frame.winfo_children():
            widget.destroy()
        self._queue_items.clear()

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
            self.show_toast(f"✅ File berhasil dimuat.", "success")
        except Exception as e:
            self.show_toast(f"Gagal membaca file: {e}", "error")

    # =========================================================================
    # Platform Detection & URL Interactions
    # =========================================================================
    def _on_url_keyrelease(self, event=None):
        url = self.url_entry.get().strip()
        self._update_platform_badge(url)

    def _on_url_focus(self, event=None):
        """Deteksi URL dari clipboard saat entry difokuskan."""
        try:
            clipboard = self.clipboard_get()
            if clipboard and (
                clipboard.startswith("http://") or clipboard.startswith("https://")
            ):
                current = self.url_entry.get().strip()
                if not current:
                    self.url_entry.insert(0, clipboard)
                    self._update_platform_badge(clipboard)
        except Exception:
            pass

    def _auto_paste(self):
        try:
            clipboard = self.clipboard_get()
            if clipboard:
                self.url_entry.delete(0, "end")
                self.url_entry.insert(0, clipboard)
                self._update_platform_badge(clipboard)
        except Exception:
            pass

    def _update_platform_badge(self, url: str):
        if not url:
            self.platform_badge.pack_forget()
            return
        for pattern, name, color in PLATFORM_PATTERNS:
            if re.search(pattern, url, re.I):
                self._platform_label.configure(text=name, text_color=color)
                self.platform_badge.pack(side="left", padx=(0, 6))
                return
        # Generic URL
        if url.startswith("http"):
            self._platform_label.configure(text="🌐 Web", text_color="#6B7280")
            self.platform_badge.pack(side="left", padx=(0, 6))
        else:
            self.platform_badge.pack_forget()

    # =========================================================================
    # Quick Presets
    # =========================================================================
    def apply_preset(self, preset_name: str):
        p = QUICK_PRESETS.get(preset_name)
        if not p:
            return
        mode = p["mode"]
        self.mode_var.set(mode)
        self.mode_segmented.set("Audio Only" if mode == "audio_only" else "Video + Audio")
        self.container_var.set(p["container"])
        self.resolution_var.set(p["resolution"])
        self.video_codec_var.set(p["video_codec"])
        self.audio_codec_var.set(p["audio_codec"])
        self.audio_only_format_var.set(p["audio_format"])
        self.embed_thumb_var.set(p["embed_thumb"])
        # Update segmented buttons
        self.video_fmt_segmented.set(p["label_v"])
        self.v_codec_segmented.set(p["label_c"])
        self.a_codec_segmented.set(p["label_a"])
        self.res_segmented.set(p["label_r"])
        af_map = {"mp3": "MP3", "m4a": "M4A", "flac": "FLAC", "wav": "WAV", "opus": "OPUS"}
        self.audio_fmt_segmented.set(af_map.get(p["audio_format"], "MP3"))
        self.toggle_opts()
        self.show_toast(f"Preset '{preset_name}' diterapkan.", "info")

    # =========================================================================
    # Toast Notification
    # =========================================================================
    def show_toast(self, message: str, toast_type: str = "info"):
        icons = {"success": "✅", "error": "❌", "info": "ℹ️", "warning": "⚠️"}
        colors = {
            "success": "#10B981",
            "error":   "#EF4444",
            "info":    "#3B82F6",
            "warning": "#F59E0B",
        }
        icon = icons.get(toast_type, "ℹ️")
        bg = colors.get(toast_type, "#3B82F6")

        try:
            toast = ctk.CTkToplevel(self)
            toast.overrideredirect(True)
            toast.attributes("-topmost", True)
            toast.configure(fg_color=bg)

            w, h = 360, 56
            self.update_idletasks()
            x = self.winfo_x() + self.winfo_width() - w - 24
            y = self.winfo_y() + self.winfo_height() - h - 60
            toast.geometry(f"{w}x{h}+{x}+{y}")

            ctk.CTkLabel(
                toast,
                text=f"{icon}  {message}",
                text_color="white",
                font=ctk.CTkFont(size=12, weight="bold"),
                wraplength=330, anchor="w", justify="left"
            ).pack(fill="both", expand=True, padx=14, pady=8)

            toast.after(3200, lambda: toast.destroy() if toast.winfo_exists() else None)
        except Exception:
            pass

    # =========================================================================
    # Settings Window
    # =========================================================================
    def open_settings(self):
        if self._settings_window and self._settings_window.winfo_exists():
            self._settings_window.focus()
            return
        self._settings_window = SettingsWindow(
            self,
            current_api_key=self.gemini_api_key,
            on_save=self._on_settings_save
        )

    def _on_settings_save(self, api_key: str):
        self.gemini_api_key = api_key
        save_config(api_key=api_key)
        status = "✅ API Key tersimpan!" if api_key else "⚠️ API Key dikosongkan."
        self.show_toast(status, "success" if api_key else "warning")

    # =========================================================================
    # Segmented Button Handlers
    # =========================================================================
    def on_mode_segment_change(self, value):
        self.mode_var.set("audio_only" if value == "Audio Only" else "video_audio")
        self.toggle_opts()

    def on_video_fmt_change(self, value):
        self.container_var.set(value.lower())

    def on_audio_fmt_change(self, value):
        self.audio_only_format_var.set(value.lower())

    def on_vcodec_change(self, value):
        self.video_codec_var.set({"Auto": "best", "H.264": "h264", "VP9": "vp9", "AV1": "av1"}.get(value, "best"))

    def on_acodec_change(self, value):
        self.audio_codec_var.set({"Auto": "best", "M4A": "m4a", "Opus": "opus"}.get(value, "best"))

    def on_res_segmented_change(self, value):
        self.resolution_var.set(
            {"Best": "best", "4K": "2160", "1440p": "1440",
             "1080p": "1080", "720p": "720", "480p": "480", "360p": "360"}.get(value, "1080")
        )

    def on_lang_preset_change(self, value):
        code = LANG_PRESETS.get(value, "id,en")
        if code != "custom":
            self.subs_lang_var.set(code)
        else:
            self.lang_entry.focus()

    def toggle_opts(self):
        if not (hasattr(self, 'video_opts') and hasattr(self, 'audio_opts')):
            return
        if self.mode_var.get() == "audio_only":
            self.video_opts.pack_forget()
            self.audio_opts.pack(fill="x")
            if hasattr(self, 'download_subs_cb'):
                self.download_subs_cb.configure(text="Download Lirik Terpisah")
                self.embed_subs_cb.configure(text="Embed Lirik")
                self.lang_label.configure(text="Bahasa Lirik Lagu:")
        else:
            self.audio_opts.pack_forget()
            self.video_opts.pack(fill="x")
            if hasattr(self, 'download_subs_cb'):
                self.download_subs_cb.configure(text="Download Sub Terpisah")
                self.embed_subs_cb.configure(text="Embed Sub (Otomatis Aktif)")
                self.lang_label.configure(text="Bahasa Subtitle Video:")

    # =========================================================================
    # Core Actions
    # =========================================================================
    def clear_log(self):
        self.log_area.delete("1.0", "end")
        self._last_log_text = ""

    def select_folder(self):
        path = filedialog.askdirectory(title="Pilih Folder Output")
        if path:
            self.custom_output_path_var.set(path)
            save_config(path=path)

    def open_folder(self):
        path = self.custom_output_path_var.get() or DEFAULT_OUTPUT_DIR
        if os.path.exists(path):
            if sys.platform == "win32":
                os.startfile(path)
            else:
                subprocess.Popen(["xdg-open", path])

    def _set_thumb_label(self, ctk_image=None, text=""):
        """Helper aman untuk update thumbnail tanpa error Tcl pyimage dangling."""
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
        url = self.url_entry.get().strip()
        if not url:
            return
        self.last_video_info = {}

        # ── Visually reset for new URL ─────────────────────────────────────
        self._set_thumb_label(None, text="🔄 Mengambil Thumbnail...")
        self.title_label.configure(
            text="Judul video akan muncul di sini setelah menekan tombol Cek Info."
        )

        if self._info_container_shown:
            # Container is already visible — just reset content in-place
            self.meta_channel.configure(text="")
            self.meta_duration.configure(text="")
            self.meta_views.configure(text="")
            for widget in self.badges_frame.winfo_children():
                widget.destroy()
            # Collapse AI result area and disable buttons while loading
            self.ai_result_text.delete("1.0", "end")
            if self.ai_result_text.winfo_ismapped():
                self.ai_result_text.pack_forget()
            self.ai_metadata_btn.configure(state="disabled", text="🏷️ AI Metadata")
            self.ai_settings_btn.configure(state="disabled", text="⚙️ AI Settings")
            # Hide error button until next download failure
            if self.ai_error_btn.winfo_ismapped():
                self.ai_error_btn.pack_forget()

        threading.Thread(target=get_video_info, args=(url,), daemon=True).start()

    def on_download(self):
        url = self.url_entry.get().strip()
        if not url:
            return
        self.stats_label.configure(text="")
        self.download_button.configure(
            text="HENTIKAN UNDUH", fg_color="#EF4444", hover_color="#DC2626",
            command=self.on_stop
        )
        self.url_entry.configure(state="disabled")
        # Switch to log tab
        self.right_tabview.set(TAB_LOG)

        threading.Thread(target=download_video_logic, args=(
            url, self.mode_var.get(), self.audio_only_format_var.get(),
            self.resolution_var.get(), self.video_codec_var.get(), self.audio_codec_var.get(),
            self.container_var.get(), self.download_subs_var.get(), self.embed_subs_var.get(),
            self.subs_lang_var.get().strip(), self.embed_thumb_var.get(),
            self.use_aria2_var.get(), self.download_playlist_var.get(),
            self.custom_output_path_var.get(), self.custom_cmd_var.get().strip()
        ), daemon=True).start()

    def on_stop(self):
        stop_current_process()

    def on_update(self):
        self.update_button.configure(state="disabled")
        threading.Thread(target=update_ytdlp_logic, daemon=True).start()
