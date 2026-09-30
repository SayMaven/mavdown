import os
import customtkinter as ctk
from tkinter import filedialog
from config import BASE_DIR, DEFAULT_OUTPUT_DIR
from ui.constants import APP_VERSION

class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent, current_path: str = "", current_cookie: str = "", on_save=None):
        super().__init__(parent)
        self.title("Pengaturan Maven Downloader")
        self.geometry("500x440")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self._app = parent

        try:
            icon_path = os.path.join(BASE_DIR, "assets", "waifu_icon.ico")
            self.after(200, lambda: self.iconbitmap(icon_path))
        except Exception:
            pass

        self.on_save_callback = on_save
        self.configure(fg_color="#0D0E16")

        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=22, pady=20)

        # Header
        hdr = ctk.CTkFrame(container, fg_color="transparent")
        hdr.pack(fill="x", pady=(0, 16))
        ctk.CTkLabel(
            hdr, text="Pengaturan Aplikasi",
            font=ctk.CTkFont(family="Inter", size=16, weight="bold"),
            text_color="#F9FAFB"
        ).pack(side="left")
        
        badge = ctk.CTkFrame(hdr, fg_color="#1E1B4B", corner_radius=6)
        badge.pack(side="right")
        ctk.CTkLabel(
            badge, text=f"v{APP_VERSION}", font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#818CF8"
        ).pack(padx=8, pady=3)

        # ── 1. Output Folder ──────────────────────────────────────────────
        ctk.CTkLabel(
            container, text="Folder Penyimpanan Utama:",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#D1D5DB"
        ).pack(anchor="w", pady=(0, 4))

        path_row = ctk.CTkFrame(container, fg_color="transparent")
        path_row.pack(fill="x", pady=(0, 14))

        self.path_var = ctk.StringVar(value=current_path or DEFAULT_OUTPUT_DIR)
        self.path_entry = ctk.CTkEntry(
            path_row, textvariable=self.path_var, height=36, corner_radius=8,
            border_color="#26293B", fg_color="#131422", text_color="#E5E7EB",
            font=ctk.CTkFont(size=11)
        )
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            path_row, text="Pilih Folder", width=95, height=36, corner_radius=8,
            fg_color="#4F46E5", hover_color="#4338CA", font=ctk.CTkFont(size=11, weight="bold"),
            command=self._browse_folder
        ).pack(side="left")

        # ── 2. Browser Cookie ──────────────────────────────────────────────
        ctk.CTkLabel(
            container, text="Impor Cookie Browser (Bypass Login & Anti-Bot):",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#D1D5DB"
        ).pack(anchor="w", pady=(0, 4))

        cookie_opts = ["Tidak Ada", "Chrome", "Firefox", "Edge", "Brave", "Opera", "Vivaldi"]
        self.cookie_var = ctk.StringVar(value=current_cookie.capitalize() if current_cookie else "Tidak Ada")
        self.cookie_menu = ctk.CTkOptionMenu(
            container, variable=self.cookie_var, values=cookie_opts,
            height=36, corner_radius=8, fg_color="#131422", button_color="#26293B",
            button_hover_color="#31354C", text_color="#F3F4F6", font=ctk.CTkFont(size=12),
            dropdown_fg_color="#171828", dropdown_hover_color="#26293B"
        )
        self.cookie_menu.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            container,
            text="Berguna jika mengunduh konten privat / restricted yang membutuhkan sesi login.",
            font=ctk.CTkFont(size=10), text_color="#6B7280", wraplength=450, justify="left"
        ).pack(anchor="w", pady=(0, 14))

        # Reset Preferences Section
        ctk.CTkFrame(container, height=1, fg_color="#1E2032").pack(fill="x", pady=(0, 14))

        reset_row = ctk.CTkFrame(container, fg_color="transparent")
        reset_row.pack(fill="x", pady=(0, 18))
        ctk.CTkLabel(
            reset_row, text="Reset Preferensi Format:",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#D1D5DB"
        ).pack(side="left")
        ctk.CTkButton(
            reset_row, text="Reset ke Default", width=120, height=30, corner_radius=6,
            fg_color="#1E2030", hover_color="#2B2E45", text_color="#EF4444",
            font=ctk.CTkFont(size=11), command=self._reset_prefs
        ).pack(side="right")

        # Action Buttons
        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.pack(fill="x", side="bottom")

        ctk.CTkButton(
            btn_row, text="Batal", width=90, height=36, corner_radius=8,
            fg_color="#1E2030", hover_color="#2B2E45", text_color="#9CA3AF",
            command=self.destroy
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            btn_row, text="Simpan Pengaturan", width=140, height=36, corner_radius=8,
            fg_color="#10B981", hover_color="#059669", font=ctk.CTkFont(size=12, weight="bold"),
            command=self._save
        ).pack(side="right")

    def _browse_folder(self):
        chosen = filedialog.askdirectory(title="Pilih Folder Output", initialdir=self.path_var.get())
        if chosen:
            self.path_var.set(chosen)

    def _save(self):
        path = self.path_var.get().strip()
        cookie = self.cookie_var.get().strip()
        if self.on_save_callback:
            self.on_save_callback(path, cookie)
        try:
            self.grab_release()
        except Exception:
            pass
        self.after(20, self.destroy)

    def _reset_prefs(self):
        """Reset semua preferensi format ke default pabrik."""
        from config import save_preferences, is_aria2_available
        save_preferences({})
        app = self._app
        app._prefs_loading = True
        try:
            app.mode_var.set("video_audio")
            app.mode_segmented.set("Video + Audio")
            app.container_var.set("auto")
            app.video_fmt_segmented.set("Auto")
            app.audio_only_format_var.set("auto")
            app.audio_fmt_segmented.set("Auto")
            app.resolution_var.set("best")
            app.res_segmented.set("Auto")
            app.video_codec_var.set("best")
            app.v_codec_segmented.set("Auto")
            app.audio_codec_var.set("best")
            app.a_codec_segmented.set("Auto")
            app.embed_thumb_var.set(True)
            app.use_aria2_var.set(is_aria2_available())
            app.download_subs_var.set(False)
            app.embed_subs_var.set(False)
            app.download_playlist_var.set(False)
            app.subs_lang_var.set("id,en")
            app.toggle_opts()
        finally:
            app._prefs_loading = False
        if hasattr(app, 'show_toast'):
            app.show_toast("Preferensi direset ke default.", "info")
