import os
import webbrowser
import customtkinter as ctk
from tkinter import filedialog
from config import (
    BASE_DIR, DEFAULT_OUTPUT_DIR, save_config, save_preferences,
    is_aria2_available, save_ytdlp_channel, load_ytdlp_channel
)
from downloader import get_local_ytdlp_version
from ui.widgets import ThemedDropdown
from ui.constants import APP_VERSION, THEME


def build_settings_view(app, parent):
    """
    Membangun tampilan Pengaturan & Tentang Aplikasi (inline tab, bukan popup).
    """
    settings_view = ctk.CTkFrame(parent, fg_color=THEME["card_bg"], corner_radius=14)

    sv_scroll = ctk.CTkScrollableFrame(settings_view, fg_color="transparent")
    sv_scroll.pack(fill="both", expand=True, padx=16, pady=16)

    # ══ HEADER ════════════════════════════════════════════════════════
    hdr = ctk.CTkFrame(sv_scroll, fg_color="transparent")
    hdr.pack(fill="x", pady=(0, 14))

    ctk.CTkLabel(
        hdr, text="Pengaturan & Tentang",
        font=ctk.CTkFont(family="Inter", size=16, weight="bold"), text_color=THEME["text_title"]
    ).pack(side="left")

    ver_badge = ctk.CTkFrame(hdr, fg_color="#1E1B4B", corner_radius=6)
    ver_badge.pack(side="right")
    ctk.CTkLabel(
        ver_badge, text=f"v{APP_VERSION}", font=ctk.CTkFont(size=10, weight="bold"),
        text_color="#818CF8"
    ).pack(padx=8, pady=3)

    # ══ SECTION 1: FOLDER OUTPUT ══════════════════════════════════════
    sec1 = ctk.CTkFrame(sv_scroll, fg_color=THEME["card_inner"], corner_radius=10)
    sec1.pack(fill="x", pady=(0, 10))
    s1_in = ctk.CTkFrame(sec1, fg_color="transparent")
    s1_in.pack(fill="x", padx=14, pady=12)

    ctk.CTkLabel(
        s1_in, text="FOLDER PENYIMPANAN UTAMA",
        font=ctk.CTkFont(size=10, weight="bold"), text_color=THEME["text_dim"]
    ).pack(anchor="w", pady=(0, 6))

    path_row = ctk.CTkFrame(s1_in, fg_color="transparent")
    path_row.pack(fill="x")

    app.settings_path_entry = ctk.CTkEntry(
        path_row, textvariable=app.custom_output_path_var, height=36, corner_radius=8,
        border_color=THEME["border_light"], fg_color="#0A0B12", text_color=THEME["text_body"],
        font=ctk.CTkFont(size=11)
    )
    app.settings_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

    ctk.CTkButton(
        path_row, text="Pilih Folder", width=100, height=36, corner_radius=8,
        fg_color=THEME["accent_indigo"], hover_color=THEME["accent_indigo_hover"],
        font=ctk.CTkFont(size=11, weight="bold"),
        command=app.select_folder
    ).pack(side="left", padx=(0, 4))

    ctk.CTkButton(
        path_row, text="Buka", width=60, height=36, corner_radius=8,
        fg_color="#1E2032", hover_color="#2B2E45",
        font=ctk.CTkFont(size=11), command=app.open_folder
    ).pack(side="left")

    # ══ SECTION 2: BROWSER COOKIE ═════════════════════════════════════
    sec2 = ctk.CTkFrame(sv_scroll, fg_color=THEME["card_inner"], corner_radius=10)
    sec2.pack(fill="x", pady=(0, 10))
    s2_in = ctk.CTkFrame(sec2, fg_color="transparent")
    s2_in.pack(fill="x", padx=14, pady=12)

    ctk.CTkLabel(
        s2_in, text="IMPOR COOKIE BROWSER (BYPASS LOGIN & ANTI-BOT)",
        font=ctk.CTkFont(size=10, weight="bold"), text_color=THEME["text_dim"]
    ).pack(anchor="w", pady=(0, 6))

    cookie_row = ctk.CTkFrame(s2_in, fg_color="transparent")
    cookie_row.pack(fill="x", pady=(0, 4))

    cookie_opts = ["Tidak Ada", "Chrome", "Firefox", "Edge", "Brave", "Opera", "Vivaldi"]
    current_cookie = app.browser_cookie_var.get()
    display_cookie = current_cookie.capitalize() if current_cookie else "Tidak Ada"

    app.settings_cookie_menu = ThemedDropdown(
        cookie_row,
        values=cookie_opts,
        default_value=display_cookie,
        height=38,
        command=lambda val: _on_cookie_change(app, val)
    )
    app.settings_cookie_menu.pack(side="left", fill="x", expand=True)

    ctk.CTkLabel(
        s2_in,
        text="Berguna jika mengunduh konten privat / restricted yang membutuhkan sesi login aktif di browser.",
        font=ctk.CTkFont(size=10), text_color=THEME["text_dim"], wraplength=600, justify="left"
    ).pack(anchor="w", pady=(6, 0))

    # ══ SECTION 3: RESET PREFERENCES ══════════════════════════════════
    sec3 = ctk.CTkFrame(sv_scroll, fg_color=THEME["card_inner"], corner_radius=10)
    sec3.pack(fill="x", pady=(0, 10))
    s3_in = ctk.CTkFrame(sec3, fg_color="transparent")
    s3_in.pack(fill="x", padx=14, pady=12)

    ctk.CTkLabel(
        s3_in, text="MANAJEMEN PREFERENSI",
        font=ctk.CTkFont(size=10, weight="bold"), text_color=THEME["text_dim"]
    ).pack(anchor="w", pady=(0, 6))

    pref_row = ctk.CTkFrame(s3_in, fg_color="transparent")
    pref_row.pack(fill="x")

    ctk.CTkLabel(
        pref_row,
        text="Kembalikan semua pengaturan format, codec, resolusi, dan opsi unduhan ke nilai default.",
        font=ctk.CTkFont(size=11), text_color=THEME["text_muted"], anchor="w", justify="left",
        wraplength=500
    ).pack(side="left", fill="x", expand=True)

    ctk.CTkButton(
        pref_row, text="Reset ke Default", width=130, height=32, corner_radius=6,
        fg_color="#1E2030", hover_color="#2B2E45", text_color=THEME["accent_rose"],
        font=ctk.CTkFont(size=11, weight="bold"),
        command=lambda: _reset_prefs(app)
    ).pack(side="right")

    # ══ SECTION 4: UPDATE YT-DLP ══════════════════════════════════════
    sec4 = ctk.CTkFrame(sv_scroll, fg_color=THEME["card_inner"], corner_radius=10)
    sec4.pack(fill="x", pady=(0, 10))
    s4_in = ctk.CTkFrame(sec4, fg_color="transparent")
    s4_in.pack(fill="x", padx=14, pady=12)

    # Header with version badge
    s4_hdr = ctk.CTkFrame(s4_in, fg_color="transparent")
    s4_hdr.pack(fill="x", pady=(0, 8))

    ctk.CTkLabel(
        s4_hdr, text="PEMBARUAN ENGINE (YT-DLP)",
        font=ctk.CTkFont(size=10, weight="bold"), text_color=THEME["text_dim"]
    ).pack(side="left")

    local_ytdlp_ver = get_local_ytdlp_version() or "Belum Terpasang"
    ver_box = ctk.CTkFrame(s4_hdr, fg_color="#181B2E", corner_radius=6)
    ver_box.pack(side="right")
    ctk.CTkLabel(
        ver_box, text="Versi Terpasang:", font=ctk.CTkFont(size=10),
        text_color=THEME["text_dim"]
    ).pack(side="left", padx=(8, 4), pady=2)
    app.settings_ytdlp_ver_label = ctk.CTkLabel(
        ver_box, text=f"v{local_ytdlp_ver}",
        font=ctk.CTkFont(size=10, weight="bold"), text_color="#818CF8"
    )
    app.settings_ytdlp_ver_label.pack(side="left", padx=(0, 8), pady=2)

    # Description
    ctk.CTkLabel(
        s4_in,
        text="Pilih channel rilis engine yt-dlp yang ingin digunakan, lalu klik tombol update untuk memperbarui executable biner.",
        font=ctk.CTkFont(size=11), text_color=THEME["text_muted"], anchor="w", justify="left",
        wraplength=620
    ).pack(fill="x", pady=(0, 10))

    # Channel Selector Card
    ch_frame = ctk.CTkFrame(s4_in, fg_color="#0D0E1A", border_width=1, border_color=THEME["border_light"], corner_radius=8)
    ch_frame.pack(fill="x", pady=(0, 10))
    ch_inner = ctk.CTkFrame(ch_frame, fg_color="transparent")
    ch_inner.pack(fill="x", padx=12, pady=10)

    ctk.CTkLabel(
        ch_inner, text="PILIH CHANNEL RILIS",
        font=ctk.CTkFont(size=10, weight="bold"), text_color=THEME["text_dim"]
    ).pack(anchor="w", pady=(0, 6))

    current_ch = app.ytdlp_channel_var.get().lower()
    ch_display = "Versi Nightly" if current_ch == "nightly" else "Versi Stable"

    ch_hint_label = ctk.CTkLabel(
        ch_inner, text="", font=ctk.CTkFont(size=10),
        text_color=THEME["text_dim"], wraplength=620, justify="left", anchor="w"
    )

    def _update_channel_hint(val: str):
        if "nightly" in val.lower():
            ch_hint_label.configure(
                text="Channel Nightly: Build harian otomatis terbaru langsung dari commit developer yt-dlp. Sangat direkomendasikan jika situs video (YouTube, TikTok, dll.) baru saja memperbarui algoritma dan versi stable belum merilis patch.",
                text_color="#FBBF24"
            )
        else:
            ch_hint_label.configure(
                text="Channel Stable: Versi rilis berkala resmi yang telah melalui pengujian stabil, direkomendasikan untuk pemakaian harian.",
                text_color=THEME["text_dim"]
            )

    def _on_channel_select(selected_val: str):
        ch = "nightly" if "nightly" in selected_val.lower() else "stable"
        app.ytdlp_channel_var.set(ch)
        save_ytdlp_channel(ch)
        _update_channel_hint(selected_val)
        app.show_toast(f"Channel update diatur ke {ch.capitalize()}.", "info")

    app.ytdlp_channel_seg = ctk.CTkSegmentedButton(
        ch_inner,
        values=["Versi Stable", "Versi Nightly"],
        height=32,
        font=ctk.CTkFont(family="Inter", size=11, weight="bold"),
        fg_color="#090A12",
        selected_color=THEME["accent_indigo"],
        selected_hover_color=THEME["accent_indigo_hover"],
        unselected_color="#181A2A",
        unselected_hover_color="#25283C",
        text_color="#FFFFFF",
        command=_on_channel_select
    )
    app.ytdlp_channel_seg.set(ch_display)
    app.ytdlp_channel_seg.pack(fill="x", pady=(0, 6))

    ch_hint_label.pack(fill="x")
    _update_channel_hint(ch_display)

    # Action Row
    act_row = ctk.CTkFrame(s4_in, fg_color="transparent")
    act_row.pack(fill="x")

    ctk.CTkLabel(
        act_row,
        text="Proses unduhan dan verifikasi integritas biner akan dicatat langsung di tab Konsol Log.",
        font=ctk.CTkFont(size=10), text_color=THEME["text_dim"], anchor="w"
    ).pack(side="left", fill="x", expand=True)

    app.settings_update_btn = ctk.CTkButton(
        act_row, text="Update yt-dlp", width=140, height=34, corner_radius=6,
        fg_color=THEME["accent_amber"], hover_color=THEME["accent_amber_hover"],
        text_color="#FFFFFF", font=ctk.CTkFont(size=11, weight="bold"),
        command=app.on_update
    )
    app.settings_update_btn.pack(side="right")

    # ══ SECTION 5: TENTANG PROYEK ═════════════════════════════════════
    sec5 = ctk.CTkFrame(sv_scroll, fg_color=THEME["card_inner"], corner_radius=10)
    sec5.pack(fill="x", pady=(0, 10))
    s5_in = ctk.CTkFrame(sec5, fg_color="transparent")
    s5_in.pack(fill="x", padx=14, pady=14)

    ctk.CTkLabel(
        s5_in, text="TENTANG PROYEK",
        font=ctk.CTkFont(size=10, weight="bold"), text_color=THEME["text_dim"]
    ).pack(anchor="w", pady=(0, 10))

    # App Identity
    brand_row = ctk.CTkFrame(s5_in, fg_color="transparent")
    brand_row.pack(fill="x", pady=(0, 10))

    try:
        from PIL import Image
        logo_path = os.path.join(BASE_DIR, "assets", "waifu_icon.png")
        if os.path.exists(logo_path):
            img_raw = Image.open(logo_path)
            logo_ctk = ctk.CTkImage(light_image=img_raw, dark_image=img_raw, size=(48, 48))
            ctk.CTkLabel(brand_row, image=logo_ctk, text="").pack(side="left", padx=(0, 14))
    except Exception:
        pass

    brand_info = ctk.CTkFrame(brand_row, fg_color="transparent")
    brand_info.pack(side="left", fill="y")
    ctk.CTkLabel(
        brand_info, text="Maven Downloader (Mavdown)",
        font=ctk.CTkFont(family="Inter", size=15, weight="bold"), text_color=THEME["text_title"]
    ).pack(anchor="w")
    ctk.CTkLabel(
        brand_info, text=f"Versi {APP_VERSION}  --  Multi-Tier Engine Architecture",
        font=ctk.CTkFont(size=11), text_color=THEME["text_muted"]
    ).pack(anchor="w")
    ctk.CTkLabel(
        brand_info, text="Dikembangkan oleh SayMaven",
        font=ctk.CTkFont(size=11), text_color=THEME["text_dim"]
    ).pack(anchor="w", pady=(2, 0))

    # Divider
    ctk.CTkFrame(s5_in, height=1, fg_color=THEME["border"]).pack(fill="x", pady=(6, 10))

    # Info Grid
    info_data = [
        ("Repositori", "github.com/SayMaven/mavdown"),
        ("Lisensi", "MIT License -- Copyright (c) 2026 SayMaven"),
        ("Engine Tier 1", "REST Scraper (TikTok, Douyin, Instagram, Twitter/X, Pinterest, Facebook, Bilibili)"),
        ("Engine Tier 2", "yt-dlp + aria2c + ffmpeg + node.js anti-bot solver"),
        ("Framework UI", f"CustomTkinter (Python {os.sys.version.split()[0]})"),
        ("Akselerator", f"aria2c 16-thread {'(Tersedia)' if is_aria2_available() else '(Tidak ditemukan)'}"),
    ]

    for label, value in info_data:
        row = ctk.CTkFrame(s5_in, fg_color="transparent")
        row.pack(fill="x", pady=2)
        ctk.CTkLabel(
            row, text=f"{label}:", width=120,
            font=ctk.CTkFont(size=11, weight="bold"), text_color=THEME["text_muted"], anchor="w"
        ).pack(side="left")
        ctk.CTkLabel(
            row, text=value,
            font=ctk.CTkFont(size=11), text_color=THEME["text_body"], anchor="w",
            wraplength=550, justify="left"
        ).pack(side="left", fill="x", expand=True)

    # Divider
    ctk.CTkFrame(s5_in, height=1, fg_color=THEME["border"]).pack(fill="x", pady=(10, 10))

    # Action Buttons
    link_row = ctk.CTkFrame(s5_in, fg_color="transparent")
    link_row.pack(fill="x")

    ctk.CTkButton(
        link_row, text="Buka GitHub Repository", width=180, height=32, corner_radius=6,
        fg_color="#1E2032", hover_color="#2B2E45", text_color=THEME["text_accent"],
        font=ctk.CTkFont(size=11, weight="bold"),
        command=lambda: webbrowser.open("https://github.com/SayMaven/mavdown")
    ).pack(side="left", padx=(0, 8))

    ctk.CTkButton(
        link_row, text="Laporkan Bug", width=120, height=32, corner_radius=6,
        fg_color="#1E2032", hover_color="#2B2E45", text_color=THEME["text_muted"],
        font=ctk.CTkFont(size=11),
        command=lambda: webbrowser.open("https://github.com/SayMaven/mavdown/issues")
    ).pack(side="left")

    return settings_view


def _on_cookie_change(app, value: str):
    """Handler perubahan dropdown cookie browser."""
    cookie = "" if value == "Tidak Ada" else value.lower()
    app.browser_cookie_var.set(cookie)
    save_config(path=app.custom_output_path_var.get(), browser_cookie=cookie)
    app.show_toast("Cookie browser diperbarui.", "success")


def _reset_prefs(app):
    """Reset semua preferensi format ke default pabrik."""
    save_preferences({})
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
    app.show_toast("Preferensi direset ke default.", "info")
