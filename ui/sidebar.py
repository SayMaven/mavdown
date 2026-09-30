import os
from PIL import Image
import customtkinter as ctk
from config import BASE_DIR
from ui.constants import APP_VERSION, QUICK_PRESETS, THEME

def build_sidebar(app, parent):
    """
    Membangun komponen Left Sidebar Navigation untuk dashboard Mavdown.
    """
    sidebar = ctk.CTkFrame(parent, fg_color=THEME["sidebar_bg"], corner_radius=0, width=260)
    sidebar.grid(row=0, column=0, sticky="nsew")
    sidebar.grid_propagate(False)

    sb_inner = ctk.CTkFrame(sidebar, fg_color="transparent")
    sb_inner.pack(fill="both", expand=True, padx=16, pady=18)

    # ── App Brand & Logo ──────────────────────────────────────────────
    brand_box = ctk.CTkFrame(sb_inner, fg_color="transparent")
    brand_box.pack(fill="x", pady=(0, 16))

    try:
        logo_path = os.path.join(BASE_DIR, "assets", "waifu_icon.png")
        if os.path.exists(logo_path):
            img_raw = Image.open(logo_path)
            logo_ctk = ctk.CTkImage(light_image=img_raw, dark_image=img_raw, size=(34, 34))
            lbl_icon = ctk.CTkLabel(brand_box, image=logo_ctk, text="")
            lbl_icon.pack(side="left", padx=(0, 10))
    except Exception:
        pass

    brand_text_box = ctk.CTkFrame(brand_box, fg_color="transparent")
    brand_text_box.pack(side="left", fill="y", expand=True)

    b_top = ctk.CTkFrame(brand_text_box, fg_color="transparent")
    b_top.pack(fill="x", anchor="w")

    ctk.CTkLabel(
        b_top, text="MAVDOWN",
        font=ctk.CTkFont(family="Inter", size=18, weight="bold"),
        text_color=THEME["text_title"]
    ).pack(side="left")

    ver_badge = ctk.CTkFrame(b_top, fg_color="#1E1B4B", corner_radius=6)
    ver_badge.pack(side="left", padx=(6, 0))
    ctk.CTkLabel(
        ver_badge, text=f"v{APP_VERSION}", font=ctk.CTkFont(size=10, weight="bold"),
        text_color="#818CF8"
    ).pack(padx=6, pady=1)

    engine_chip = ctk.CTkFrame(brand_text_box, fg_color="#064E3B", corner_radius=6)
    engine_chip.pack(anchor="w", pady=(4, 0))
    ctk.CTkLabel(
        engine_chip, text="MULTI-TIER ENGINE",
        font=ctk.CTkFont(size=9, weight="bold"), text_color="#34D399"
    ).pack(padx=6, pady=1)

    # Divider
    ctk.CTkFrame(sb_inner, height=1, fg_color=THEME["border"]).pack(fill="x", pady=(0, 14))

    # ── Navigation Buttons ─────────────────────────────────────────────
    ctk.CTkLabel(
        sb_inner, text="NAVIGASI UTAMA", font=ctk.CTkFont(size=10, weight="bold"),
        text_color=THEME["text_dim"]
    ).pack(anchor="w", pady=(0, 6))

    app.nav_btns = {}
    nav_items = [
        ("studio",   "Studio Unduh",  app.show_studio_view),
        ("queue",    "Antrean Batch", app.show_queue_view),
        ("log",      "Konsol Log",    app.show_log_view),
        ("settings", "Pengaturan",    app.show_settings_view),
    ]
    for key, text, cmd in nav_items:
        btn = ctk.CTkButton(
            sb_inner, text=text, command=cmd, height=38, corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"), anchor="w",
            fg_color="#1E1B4B" if key == "studio" else "transparent",
            hover_color="#2A2D45",
            text_color="#818CF8" if key == "studio" else THEME["text_muted"]
        )
        btn.pack(fill="x", pady=2)
        app.nav_btns[key] = btn

    # Divider
    ctk.CTkFrame(sb_inner, height=1, fg_color=THEME["border"]).pack(fill="x", pady=(14, 14))

    # ── Quick Presets Card ─────────────────────────────────────────────
    ctk.CTkLabel(
        sb_inner, text="PRESET CEPAT", font=ctk.CTkFont(size=10, weight="bold"),
        text_color=THEME["text_dim"]
    ).pack(anchor="w", pady=(0, 6))

    preset_colors = {
        "Super Quality": ("#4338CA", "#3730A3"),
        "Musik MP3":     ("#6D28D9", "#5B21B6"),
        "Hemat Data":    ("#0E7490", "#155E75"),
        "Podcast":       ("#047857", "#065F46"),
    }
    for name in QUICK_PRESETS:
        fc, hc = preset_colors.get(name, ("#1E2235", "#2B2E45"))
        ctk.CTkButton(
            sb_inner, text=name,
            command=lambda n=name: app.apply_preset(n),
            height=32, corner_radius=6, font=ctk.CTkFont(size=11), anchor="w",
            fg_color=fc, hover_color=hc, text_color="#F3F4F6"
        ).pack(fill="x", pady=2)

    ctk.CTkLabel(
        sb_inner, text="Preset mengatur format, codec, dan resolusi secara otomatis.",
        font=ctk.CTkFont(size=9), text_color=THEME["text_dim"],
        wraplength=220, justify="left"
    ).pack(anchor="w", pady=(6, 0))

    # ── Bottom System Status Card ─────────────────────────────────────
    sys_box = ctk.CTkFrame(sb_inner, fg_color="#131522", corner_radius=10)
    sys_box.pack(side="bottom", fill="x")

    s_in = ctk.CTkFrame(sys_box, fg_color="transparent")
    s_in.pack(fill="x", padx=12, pady=12)

    ctk.CTkLabel(
        s_in, text="Lokasi Simpan:",
        font=ctk.CTkFont(size=10, weight="bold"), text_color=THEME["text_dim"]
    ).pack(anchor="w")

    app.lbl_outpath = ctk.CTkLabel(
        s_in, textvariable=app.custom_output_path_var,
        font=ctk.CTkFont(size=11, weight="bold"), text_color=THEME["text_accent"],
        wraplength=210, anchor="w", justify="left"
    )
    app.lbl_outpath.pack(fill="x", pady=(2, 8))

    f_btns = ctk.CTkFrame(s_in, fg_color="transparent")
    f_btns.pack(fill="x", pady=(0, 8))
    ctk.CTkButton(
        f_btns, text="Ubah", width=95, height=28, corner_radius=6,
        font=ctk.CTkFont(size=11), fg_color="#1E2235", hover_color="#2B2E45",
        command=app.select_folder
    ).pack(side="left", padx=(0, 4))
    ctk.CTkButton(
        f_btns, text="Buka", width=95, height=28, corner_radius=6,
        font=ctk.CTkFont(size=11), fg_color="#1E2235", hover_color="#2B2E45",
        command=app.open_folder
    ).pack(side="left")

    app.update_btn = ctk.CTkButton(
        s_in, text="Update yt-dlp", command=app.on_update,
        height=30, corner_radius=6, font=ctk.CTkFont(size=11, weight="bold"),
        fg_color=THEME["accent_amber"], hover_color=THEME["accent_amber_hover"], text_color="#FFFFFF"
    )
    app.update_btn.pack(fill="x")

    return sidebar
