import os
import sys
import subprocess
import threading
import queue
from io import BytesIO
from PIL import Image
import customtkinter as ctk
from tkinter import filedialog

from config import BASE_DIR, DEFAULT_OUTPUT_DIR, load_config, save_config
from downloader import (
    ui_queue, get_video_info, download_video_logic,
    stop_current_process, update_ytdlp_logic
)

# Pemetaan Bahasa Subtitle / Lirik
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

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Maven Downloader")
        self.geometry("1400x860")
        self.minsize(1200, 780)
        
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        
        try:
            icon_path = os.path.join(BASE_DIR, "assets", "waifu_icon.ico")
            self.iconbitmap(icon_path)
        except Exception:
            pass
            
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

        self.setup_ui()
        self.after(100, self.process_ui_queue)

    def process_ui_queue(self):
        try:
            while True:
                msg = ui_queue.get_nowait()
                msg_type = msg.get("type")
                if msg_type == "log":
                    self.log_area.insert("end", msg["text"])
                    self.log_area.see("end")
                elif msg_type == "progress":
                    self.progress_bar.set(msg["value"])
                    self.progress_label.configure(text=msg["text"])
                elif msg_type == "info_title":
                    self.title_label.configure(text=msg["title"])
                elif msg_type == "info_thumb":
                    if msg.get("image"):
                        self.thumb_label.configure(image=msg["image"], text="")
                    else:
                        self.thumb_label.configure(text=msg.get("text", ""), image="")
                elif msg_type == "info_thumb_data":
                    try:
                        image = Image.open(BytesIO(msg["image_data"]))
                        ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=(360, 210))
                        self.thumb_label.configure(image=ctk_image, text="")
                    except Exception:
                        self.thumb_label.configure(text="Gagal memuat preview thumbnail.", image="")
                elif msg_type == "download_finish":
                    self.download_button.configure(text="MULAI UNDUH", fg_color="#10B981", hover_color="#059669", command=self.on_download, state="normal")
                    self.url_entry.configure(state="normal")
                    self.progress_bar.set(1.0)
                    self.progress_label.configure(text="Status: Unduhan Selesai ✨")
                elif msg_type == "update_finish":
                    self.update_button.configure(state="normal")
                    self.progress_bar.set(1.0)
                    self.progress_label.configure(text="Status: Update Selesai ✨")
        except queue.Empty:
            pass
        self.after(100, self.process_ui_queue)

    def setup_ui(self):
        self.configure(fg_color="#0F1017")
        
        main_container = ctk.CTkFrame(self, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=20, pady=20)

        # ----------------------------------------------------
        # 1. TOP HEADER & HERO URL BAR
        # ----------------------------------------------------
        header_card = ctk.CTkFrame(main_container, fg_color="#181A24", corner_radius=14)
        header_card.pack(fill="x", pady=(0, 16))
        
        header_inner = ctk.CTkFrame(header_card, fg_color="transparent")
        header_inner.pack(fill="x", padx=18, pady=14)

        # Brand Title Row
        brand_frame = ctk.CTkFrame(header_inner, fg_color="transparent")
        brand_frame.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(brand_frame, text="Maven Downloader", font=ctk.CTkFont(family="Inter", size=18, weight="bold"), text_color="#F3F4F6").pack(side="left")
        
        ver_badge = ctk.CTkFrame(brand_frame, fg_color="#26293B", corner_radius=6)
        ver_badge.pack(side="left", padx=10)
        ctk.CTkLabel(ver_badge, text="v1.5", font=ctk.CTkFont(size=11, weight="bold"), text_color="#818CF8").pack(padx=8, pady=2)

        # URL Input Row
        url_row = ctk.CTkFrame(header_inner, fg_color="transparent")
        url_row.pack(fill="x", pady=(0, 8))
        
        self.url_entry = ctk.CTkEntry(
            url_row, 
            placeholder_text="Tempelkan link YouTube di sini...", 
            height=44, 
            corner_radius=10,
            border_color="#2D3142",
            fg_color="#10111A",
            text_color="#F3F4F6",
            placeholder_text_color="#6B7280",
            font=ctk.CTkFont(size=13)
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        ctk.CTkButton(
            url_row, 
            text="Cek Info", 
            command=self.on_get_info, 
            width=110, 
            height=44, 
            corner_radius=10,
            font=ctk.CTkFont(weight="bold", size=13),
            fg_color="#4F46E5", 
            hover_color="#4338CA"
        ).pack(side="left", padx=(0, 8))
        
        self.download_button = ctk.CTkButton(
            url_row, 
            text="MULAI UNDUH", 
            command=self.on_download, 
            width=140, 
            height=44, 
            corner_radius=10,
            font=ctk.CTkFont(weight="bold", size=13),
            fg_color="#10B981", 
            hover_color="#059669"
        )
        self.download_button.pack(side="left")

        # Quick Tools Row
        tools_row = ctk.CTkFrame(header_inner, fg_color="transparent")
        tools_row.pack(fill="x")
        
        folder_label = ctk.CTkLabel(tools_row, text="Lokasi Simpan:", font=ctk.CTkFont(size=12), text_color="#9CA3AF")
        folder_label.pack(side="left", padx=(0, 6))
        
        self.output_disp = ctk.CTkLabel(
            tools_row, 
            textvariable=self.custom_output_path_var, 
            text_color="#38BDF8", 
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.output_disp.pack(side="left", padx=(0, 12))
        
        ctk.CTkButton(
            tools_row, text="Ubah Folder", command=self.select_folder, 
            width=90, height=28, corner_radius=6, font=ctk.CTkFont(size=11), 
            fg_color="#26293B", hover_color="#31354C", text_color="#E5E7EB"
        ).pack(side="left", padx=3)
        
        ctk.CTkButton(
            tools_row, text="Buka Folder", command=self.open_folder, 
            width=90, height=28, corner_radius=6, font=ctk.CTkFont(size=11), 
            fg_color="#26293B", hover_color="#31354C", text_color="#E5E7EB"
        ).pack(side="left", padx=3)
        
        self.update_button = ctk.CTkButton(
            tools_row, text="Update yt-dlp", command=self.on_update, 
            width=105, height=28, corner_radius=6, font=ctk.CTkFont(size=11, weight="bold"), 
            fg_color="#D97706", hover_color="#B45309", text_color="#FFFFFF"
        )
        self.update_button.pack(side="left", padx=3)

        # ----------------------------------------------------
        # 2. MAIN CONTENT SPLIT (Left: Media Card | Right: Options & Log)
        # ----------------------------------------------------
        content_split = ctk.CTkFrame(main_container, fg_color="transparent")
        content_split.pack(fill="both", expand=True)

        # ------------------ LEFT CARD: MEDIA PREVIEW ------------------
        preview_card = ctk.CTkFrame(content_split, width=380, fg_color="#181A24", corner_radius=14)
        preview_card.pack(side="left", fill="y", padx=(0, 16))
        preview_card.pack_propagate(False)
        
        p_inner = ctk.CTkFrame(preview_card, fg_color="transparent")
        p_inner.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(p_inner, text="Informasi Media", font=ctk.CTkFont(size=14, weight="bold"), text_color="#F3F4F6").pack(anchor="w", pady=(0, 10))
        
        self.thumb_label = ctk.CTkLabel(
            p_inner, 
            text="Pratinjau Thumbnail", 
            width=348, 
            height=210, 
            fg_color="#10111A", 
            corner_radius=10,
            text_color="#6B7280"
        )
        self.thumb_label.pack(fill="x", pady=(0, 12))
        
        self.title_label = ctk.CTkLabel(
            p_inner, 
            text="Judul Video akan muncul di sini setelah menekan tombol Cek Info.", 
            wraplength=340, 
            justify="left", 
            font=ctk.CTkFont(size=12), 
            text_color="#E5E7EB"
        )
        self.title_label.pack(fill="x", anchor="w", pady=(0, 16))

        # Progress Section
        prog_card = ctk.CTkFrame(p_inner, fg_color="#10111A", corner_radius=10)
        prog_card.pack(fill="x", side="bottom", pady=(10, 0))
        
        prog_inner = ctk.CTkFrame(prog_card, fg_color="transparent")
        prog_inner.pack(fill="x", padx=12, pady=12)
        
        self.progress_label = ctk.CTkLabel(prog_inner, text="Status: Siap", font=ctk.CTkFont(size=11, weight="bold"), text_color="#9CA3AF")
        self.progress_label.pack(anchor="w", pady=(0, 6))
        
        self.progress_bar = ctk.CTkProgressBar(prog_inner, height=8, corner_radius=4, progress_color="#10B981", fg_color="#1F2937")
        self.progress_bar.pack(fill="x")
        self.progress_bar.set(0)

        # ------------------ RIGHT PANEL: CONFIG & LOG ------------------
        right_panel = ctk.CTkFrame(content_split, fg_color="transparent")
        right_panel.pack(side="left", fill="both", expand=True)

        # Options Card
        options_card = ctk.CTkFrame(right_panel, fg_color="#181A24", corner_radius=14)
        options_card.pack(fill="x", pady=(0, 14))
        
        opts_inner = ctk.CTkFrame(options_card, fg_color="transparent")
        opts_inner.pack(fill="x", padx=16, pady=14)

        # ---------------- ROW 1: MODE & FORMAT ----------------
        row1 = ctk.CTkFrame(opts_inner, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 10))
        
        # Mode Switcher
        mode_box = ctk.CTkFrame(row1, fg_color="transparent")
        mode_box.pack(side="left", padx=(0, 20))
        ctk.CTkLabel(mode_box, text="Mode Unduhan:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#9CA3AF").pack(anchor="w", pady=(0, 3))
        
        self.mode_segmented = ctk.CTkSegmentedButton(
            mode_box,
            values=["Video + Audio", "Audio Only"],
            command=self.on_mode_segment_change,
            selected_color="#4F46E5",
            selected_hover_color="#4338CA",
            unselected_color="#10111A",
            unselected_hover_color="#26293B",
            text_color="#F3F4F6",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.mode_segmented.set("Video + Audio")
        self.mode_segmented.pack(side="left")

        # Container Frame for Dynamic Mode Content
        self.mode_content_frame = ctk.CTkFrame(opts_inner, fg_color="transparent")
        self.mode_content_frame.pack(fill="x", pady=(0, 10))

        # Audio Opts Container
        self.audio_opts = ctk.CTkFrame(self.mode_content_frame, fg_color="transparent")
        
        a_fmt_box = ctk.CTkFrame(self.audio_opts, fg_color="transparent")
        a_fmt_box.pack(side="left", padx=(0, 20))
        ctk.CTkLabel(a_fmt_box, text="Format Audio:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#9CA3AF").pack(anchor="w", pady=(0, 3))
        
        self.audio_fmt_segmented = ctk.CTkSegmentedButton(
            a_fmt_box,
            values=["MP3", "M4A", "FLAC", "WAV", "OPUS"],
            command=self.on_audio_fmt_change,
            selected_color="#4F46E5",
            selected_hover_color="#4338CA",
            unselected_color="#10111A",
            unselected_hover_color="#26293B",
            text_color="#F3F4F6",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.audio_fmt_segmented.set("MP3")
        self.audio_fmt_segmented.pack(side="left")

        # Video Opts Container
        self.video_opts = ctk.CTkFrame(self.mode_content_frame, fg_color="transparent")
        
        # Row 1 Video: Format & Codecs
        v_row1 = ctk.CTkFrame(self.video_opts, fg_color="transparent")
        v_row1.pack(fill="x", pady=(0, 8))

        v_fmt_box = ctk.CTkFrame(v_row1, fg_color="transparent")
        v_fmt_box.pack(side="left", padx=(0, 16))
        ctk.CTkLabel(v_fmt_box, text="Format Video:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#9CA3AF").pack(anchor="w", pady=(0, 3))
        
        self.video_fmt_segmented = ctk.CTkSegmentedButton(
            v_fmt_box,
            values=["MP4", "MKV", "WEBM", "MOV", "AVI"],
            command=self.on_video_fmt_change,
            selected_color="#4F46E5",
            selected_hover_color="#4338CA",
            unselected_color="#10111A",
            unselected_hover_color="#26293B",
            text_color="#F3F4F6",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.video_fmt_segmented.set("MP4")
        self.video_fmt_segmented.pack(side="left")

        v_codec_box = ctk.CTkFrame(v_row1, fg_color="transparent")
        v_codec_box.pack(side="left", padx=(0, 16))
        ctk.CTkLabel(v_codec_box, text="Video Codec:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#9CA3AF").pack(anchor="w", pady=(0, 3))
        
        self.v_codec_segmented = ctk.CTkSegmentedButton(
            v_codec_box,
            values=["Auto", "H.264", "VP9", "AV1"],
            command=self.on_vcodec_change,
            selected_color="#4F46E5",
            selected_hover_color="#4338CA",
            unselected_color="#10111A",
            unselected_hover_color="#26293B",
            text_color="#F3F4F6",
            font=ctk.CTkFont(size=11, weight="bold")
        )
        self.v_codec_segmented.set("Auto")
        self.v_codec_segmented.pack(side="left")

        a_codec_box = ctk.CTkFrame(v_row1, fg_color="transparent")
        a_codec_box.pack(side="left")
        ctk.CTkLabel(a_codec_box, text="Audio Codec:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#9CA3AF").pack(anchor="w", pady=(0, 3))
        
        self.a_codec_segmented = ctk.CTkSegmentedButton(
            a_codec_box,
            values=["Auto", "M4A", "Opus"],
            command=self.on_acodec_change,
            selected_color="#4F46E5",
            selected_hover_color="#4338CA",
            unselected_color="#10111A",
            unselected_hover_color="#26293B",
            text_color="#F3F4F6",
            font=ctk.CTkFont(size=11, weight="bold")
        )
        self.a_codec_segmented.set("Auto")
        self.a_codec_segmented.pack(side="left")

        # Row 2 Video: Resolution Segmented Control
        v_row2 = ctk.CTkFrame(self.video_opts, fg_color="transparent")
        v_row2.pack(fill="x")

        res_box = ctk.CTkFrame(v_row2, fg_color="transparent")
        res_box.pack(fill="x")
        ctk.CTkLabel(res_box, text="Kualitas Maksimal:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#9CA3AF").pack(anchor="w", pady=(0, 3))
        
        self.res_segmented = ctk.CTkSegmentedButton(
            res_box,
            values=["Best", "4K", "1440p", "1080p", "720p", "480p", "360p"],
            command=self.on_res_segmented_change,
            selected_color="#4F46E5",
            selected_hover_color="#4338CA",
            unselected_color="#10111A",
            unselected_hover_color="#26293B",
            text_color="#F3F4F6",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.res_segmented.set("1080p")
        self.res_segmented.pack(fill="x")

        # ---------------- ROW 2: LANGUAGE SELECTOR (PRESET + CODE ENTRY) ----------------
        row_lang = ctk.CTkFrame(opts_inner, fg_color="transparent")
        row_lang.pack(fill="x", pady=(4, 10))
        
        lang_box = ctk.CTkFrame(row_lang, fg_color="transparent")
        lang_box.pack(fill="x")
        
        self.lang_label = ctk.CTkLabel(lang_box, text="Bahasa Subtitle / Lirik:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#9CA3AF")
        self.lang_label.pack(anchor="w", pady=(0, 3))
        
        lang_controls = ctk.CTkFrame(lang_box, fg_color="transparent")
        lang_controls.pack(fill="x")

        # Preset Dropdown (Human readable labels only)
        self.lang_optionmenu = ctk.CTkOptionMenu(
            lang_controls,
            values=list(LANG_PRESETS.keys()),
            command=self.on_lang_preset_change,
            fg_color="#10111A",
            button_color="#26293B",
            button_hover_color="#31354C",
            text_color="#F3F4F6",
            dropdown_fg_color="#181A24",
            dropdown_hover_color="#26293B",
            font=ctk.CTkFont(size=12),
            height=32,
            width=260
        )
        self.lang_optionmenu.set("🇮🇩 Indonesia & 🇬🇧 English")
        self.lang_optionmenu.pack(side="left", padx=(0, 10))

        # Direct Code Input (Contains ONLY the clean code string e.g. "id,en", "ja", "zh")
        ctk.CTkLabel(lang_controls, text="Kode ISO:", font=ctk.CTkFont(size=11), text_color="#6B7280").pack(side="left", padx=(0, 4))
        self.lang_entry = ctk.CTkEntry(
            lang_controls,
            textvariable=self.subs_lang_var,
            width=100,
            height=32,
            corner_radius=6,
            border_color="#2D3142",
            fg_color="#10111A",
            text_color="#38BDF8",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.lang_entry.pack(side="left")

        # Divider Line
        div = ctk.CTkFrame(opts_inner, height=1, fg_color="#26293B")
        div.pack(fill="x", pady=(6, 10))

        # ---------------- ROW 3: EXTRAS CHECKBOX GRID ----------------
        extras_grid = ctk.CTkFrame(opts_inner, fg_color="transparent")
        extras_grid.pack(fill="x")
        
        self.embed_thumb_cb = ctk.CTkCheckBox(
            extras_grid, text="Embed Thumb", variable=self.embed_thumb_var, 
            font=ctk.CTkFont(size=12), fg_color="#4F46E5", hover_color="#4338CA"
        )
        self.embed_thumb_cb.grid(row=0, column=0, padx=(0, 14), pady=2, sticky="w")
        
        self.embed_subs_cb = ctk.CTkCheckBox(
            extras_grid, text="Embed Sub", variable=self.embed_subs_var, 
            font=ctk.CTkFont(size=12), fg_color="#4F46E5", hover_color="#4338CA"
        )
        self.embed_subs_cb.grid(row=0, column=1, padx=(0, 14), pady=2, sticky="w")
        
        self.download_subs_cb = ctk.CTkCheckBox(
            extras_grid, text="Download Sub Terpisah", variable=self.download_subs_var, 
            font=ctk.CTkFont(size=12), fg_color="#4F46E5", hover_color="#4338CA"
        )
        self.download_subs_cb.grid(row=0, column=2, padx=(0, 14), pady=2, sticky="w")
        
        self.use_aria2_cb = ctk.CTkCheckBox(
            extras_grid, text="Aria2c Downloader", variable=self.use_aria2_var, 
            font=ctk.CTkFont(size=12), fg_color="#4F46E5", hover_color="#4338CA"
        )
        self.use_aria2_cb.grid(row=0, column=3, padx=(0, 14), pady=2, sticky="w")
        
        self.download_playlist_cb = ctk.CTkCheckBox(
            extras_grid, text="Full Playlist", variable=self.download_playlist_var, 
            font=ctk.CTkFont(size=12), fg_color="#4F46E5", hover_color="#4338CA"
        )
        self.download_playlist_cb.grid(row=0, column=4, pady=2, sticky="w")

        # ------------------ LOG TERMINAL CARD ------------------
        log_card = ctk.CTkFrame(right_panel, fg_color="#181A24", corner_radius=14)
        log_card.pack(fill="both", expand=True)
        
        log_inner = ctk.CTkFrame(log_card, fg_color="transparent")
        log_inner.pack(fill="both", expand=True, padx=16, pady=14)
        
        log_header = ctk.CTkFrame(log_inner, fg_color="transparent")
        log_header.pack(fill="x", pady=(0, 8))
        
        ctk.CTkLabel(log_header, text="Log Eksekusi / Terminal", font=ctk.CTkFont(size=13, weight="bold"), text_color="#F3F4F6").pack(side="left")
        ctk.CTkButton(
            log_header, text="Bersihkan Log", command=self.clear_log, 
            width=85, height=24, corner_radius=6, font=ctk.CTkFont(size=10), 
            fg_color="#26293B", hover_color="#31354C", text_color="#9CA3AF"
        ).pack(side="right")

        self.log_area = ctk.CTkTextbox(
            log_inner, 
            font=ctk.CTkFont(family="Consolas", size=11), 
            fg_color="#0E0F17", 
            text_color="#D1D5DB",
            border_color="#1F2937",
            border_width=1,
            corner_radius=8
        )
        self.log_area.pack(fill="both", expand=True)

        # Initial Toggle View Setup
        self.toggle_opts()

    def on_mode_segment_change(self, value):
        if value == "Audio Only":
            self.mode_var.set("audio_only")
        else:
            self.mode_var.set("video_audio")
        self.toggle_opts()

    def on_video_fmt_change(self, value):
        self.container_var.set(value.lower())

    def on_audio_fmt_change(self, value):
        self.audio_only_format_var.set(value.lower())

    def on_vcodec_change(self, value):
        vmap = {"Auto": "best", "H.264": "h264", "VP9": "vp9", "AV1": "av1"}
        self.video_codec_var.set(vmap.get(value, "best"))

    def on_acodec_change(self, value):
        amap = {"Auto": "best", "M4A": "m4a", "Opus": "opus"}
        self.audio_codec_var.set(amap.get(value, "best"))

    def on_res_segmented_change(self, value):
        rmap = {
            "Best": "best", "4K": "2160", "1440p": "1440", 
            "1080p": "1080", "720p": "720", "480p": "480", "360p": "360"
        }
        self.resolution_var.set(rmap.get(value, "1080"))

    def on_lang_preset_change(self, value):
        code = LANG_PRESETS.get(value, "id,en")
        if code != "custom":
            self.subs_lang_var.set(code)
        else:
            self.lang_entry.focus()

    def toggle_opts(self):
        if hasattr(self, 'video_opts') and hasattr(self, 'audio_opts'):
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
                    self.embed_subs_cb.configure(text="Embed Sub")
                    self.lang_label.configure(text="Bahasa Subtitle Video:")

    def clear_log(self):
        self.log_area.delete("1.0", "end")

    def select_folder(self):
        path = filedialog.askdirectory(title="Pilih Folder Output")
        if path:
            self.custom_output_path_var.set(path)
            save_config(path)

    def open_folder(self):
        path = self.custom_output_path_var.get() or DEFAULT_OUTPUT_DIR
        if os.path.exists(path):
            if sys.platform == "win32":
                os.startfile(path)
            else:
                subprocess.Popen(["xdg-open", path])

    def on_get_info(self):
        url = self.url_entry.get().strip()
        if not url: return
        threading.Thread(target=get_video_info, args=(url,), daemon=True).start()

    def on_download(self):
        url = self.url_entry.get().strip()
        if not url: return

        self.download_button.configure(text="HENTIKAN UNDUH", fg_color="#EF4444", hover_color="#DC2626", command=self.on_stop)
        self.url_entry.configure(state="disabled")
        
        threading.Thread(target=download_video_logic, args=(
            url, self.mode_var.get(), self.audio_only_format_var.get(),
            self.resolution_var.get(), self.video_codec_var.get(), self.audio_codec_var.get(),
            self.container_var.get(), self.download_subs_var.get(), self.embed_subs_var.get(),
            self.subs_lang_var.get().strip(), self.embed_thumb_var.get(), self.use_aria2_var.get(),
            self.download_playlist_var.get(),
            self.custom_output_path_var.get(), self.custom_cmd_var.get().strip()
        ), daemon=True).start()

    def on_stop(self):
        stop_current_process()

    def on_update(self):
        self.update_button.configure(state="disabled")
        threading.Thread(target=update_ytdlp_logic, daemon=True).start()
