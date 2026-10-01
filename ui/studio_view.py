import customtkinter as ctk
from ui.constants import THEME, LANG_PRESETS

def build_studio_view(app, parent):
    """
    Membangun tampilan Studio Unduh (Media Inspector + Studio Configuration).
    """
    studio_view = ctk.CTkFrame(parent, fg_color="transparent")

    studio_view.grid_columnconfigure(0, weight=0, minsize=440)
    studio_view.grid_columnconfigure(1, weight=1)
    studio_view.grid_rowconfigure(0, weight=1)

    # ══ LEFT: MEDIA INSPECTOR ═════════════════════════════════════════
    left_inspector = ctk.CTkFrame(studio_view, fg_color=THEME["card_bg"], corner_radius=14, width=440)
    left_inspector.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
    left_inspector.grid_propagate(False)

    li_in = ctk.CTkFrame(left_inspector, fg_color="transparent")
    li_in.pack(fill="both", expand=True, padx=16, pady=16)

    ctk.CTkLabel(
        li_in, text="Pratinjau & Inspeksi Media",
        font=ctk.CTkFont(size=13, weight="bold"), text_color=THEME["text_title"]
    ).pack(anchor="w", pady=(0, 10))

    # Thumbnail
    app.thumb_label = ctk.CTkLabel(
        li_in, text="Pratinjau Thumbnail Video / Foto",
        width=408, height=230,
        fg_color=THEME["card_inner"], corner_radius=10, text_color=THEME["text_dim"]
    )
    app.thumb_label.pack(fill="x", pady=(0, 10))

    # Title
    app.title_label = ctk.CTkLabel(
        li_in,
        text="Judul video atau media akan muncul di sini setelah memasukkan URL.",
        wraplength=400, justify="left",
        font=ctk.CTkFont(size=12, weight="bold"), text_color=THEME["text_body"]
    )
    app.title_label.pack(fill="x", anchor="w", pady=(0, 8))

    # Dynamic Metadata Card
    app.meta_frame = ctk.CTkFrame(li_in, fg_color=THEME["card_inner"], corner_radius=10)
    app.meta_frame.pack(fill="x", pady=(0, 8))

    m_top = ctk.CTkFrame(app.meta_frame, fg_color="transparent")
    m_top.pack(fill="x", padx=10, pady=(8, 4))
    app.meta_platform = ctk.CTkLabel(
        m_top, text="", font=ctk.CTkFont(size=11, weight="bold"),
        text_color="#818CF8", anchor="w"
    )
    app.meta_platform.pack(side="left")
    app.meta_date = ctk.CTkLabel(
        m_top, text="", font=ctk.CTkFont(size=10), text_color=THEME["text_dim"], anchor="e"
    )
    app.meta_date.pack(side="right")

    ctk.CTkFrame(app.meta_frame, fg_color=THEME["border"], height=1).pack(fill="x", padx=10)

    m_grid = ctk.CTkFrame(app.meta_frame, fg_color="transparent")
    m_grid.pack(fill="x", padx=10, pady=(6, 4))
    m_grid.columnconfigure(0, weight=1)
    m_grid.columnconfigure(1, weight=1)

    app.meta_channel = ctk.CTkLabel(m_grid, text="", font=ctk.CTkFont(size=11), text_color="#D1D5DB", anchor="w")
    app.meta_channel.grid(row=0, column=0, sticky="w", padx=(0, 8), pady=2)

    app.meta_duration = ctk.CTkLabel(m_grid, text="", font=ctk.CTkFont(size=11), text_color="#D1D5DB", anchor="w")
    app.meta_duration.grid(row=0, column=1, sticky="w", padx=(8, 0), pady=2)

    app.meta_views = ctk.CTkLabel(m_grid, text="", font=ctk.CTkFont(size=11), text_color="#D1D5DB", anchor="w")
    app.meta_views.grid(row=1, column=0, sticky="w", padx=(0, 8), pady=2)

    app.meta_likes = ctk.CTkLabel(m_grid, text="", font=ctk.CTkFont(size=11), text_color="#D1D5DB", anchor="w")
    app.meta_likes.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=2)

    app.meta_desc = ctk.CTkLabel(
        app.meta_frame, text="", font=ctk.CTkFont(size=10), text_color=THEME["text_dim"],
        anchor="w", justify="left", wraplength=380
    )
    app.meta_desc.pack(fill="x", padx=10, pady=(2, 8))

    # Quality Badges
    ctk.CTkLabel(
        li_in, text="KUALITAS & TIPE FORMAT TERSEDIA",
        font=ctk.CTkFont(size=9, weight="bold"), text_color=THEME["text_dim"]
    ).pack(anchor="w", pady=(0, 4))

    app.badges_frame = ctk.CTkFrame(li_in, fg_color="transparent")
    app.badges_frame.pack(fill="x")

    # ══ RIGHT: CONFIGURATION STUDIO ═══════════════════════════════════
    right_studio = ctk.CTkScrollableFrame(studio_view, fg_color=THEME["card_bg"], corner_radius=14)
    right_studio.grid(row=0, column=1, sticky="nsew")

    rs_in = ctk.CTkFrame(right_studio, fg_color="transparent")
    rs_in.pack(fill="both", expand=True, padx=16, pady=16)

    # ── Section 1: Mode Switcher ──────────────────────────────────────
    sec_mode = ctk.CTkFrame(rs_in, fg_color=THEME["card_inner"], corner_radius=10)
    sec_mode.pack(fill="x", pady=(0, 10))
    sm_in = ctk.CTkFrame(sec_mode, fg_color="transparent")
    sm_in.pack(fill="x", padx=14, pady=10)

    ctk.CTkLabel(
        sm_in, text="PILIH MODE EKSTRAKSI",
        font=ctk.CTkFont(size=10, weight="bold"), text_color=THEME["text_dim"]
    ).pack(anchor="w", pady=(0, 4))

    app.mode_segmented = ctk.CTkSegmentedButton(
        sm_in, values=["Video + Audio", "Audio Saja (Musik)"],
        command=app.on_mode_segment_change,
        selected_color=THEME["accent_indigo"], selected_hover_color=THEME["accent_indigo_hover"],
        unselected_color="#131422", unselected_hover_color="#1E2032",
        text_color=THEME["text_title"], font=ctk.CTkFont(size=12, weight="bold"), height=36
    )
    app.mode_segmented.set("Video + Audio")
    app.mode_segmented.pack(fill="x")

    # ── Section 2: Format & Codec Options ─────────────────────────────
    app.format_card = ctk.CTkFrame(rs_in, fg_color=THEME["card_inner"], corner_radius=10)
    app.format_card.pack(fill="x", pady=(0, 10))
    fc_in = ctk.CTkFrame(app.format_card, fg_color="transparent")
    fc_in.pack(fill="x", padx=14, pady=12)

    app.format_title = ctk.CTkLabel(
        fc_in, text="PARAMETER FORMAT & KUALITAS",
        font=ctk.CTkFont(size=10, weight="bold"), text_color=THEME["text_dim"]
    )
    app.format_title.pack(anchor="w", pady=(0, 8))

    # Slide options frame (khusus album foto slide)
    app.slide_opts = ctk.CTkFrame(fc_in, fg_color="transparent")

    s_banner = ctk.CTkFrame(app.slide_opts, fg_color="#18192E", corner_radius=8, border_width=1, border_color="#2D3154")
    s_banner.pack(fill="x", pady=(0, 8))

    s_btop = ctk.CTkFrame(s_banner, fg_color="transparent")
    s_btop.pack(fill="x", padx=12, pady=(10, 4))
    app.slide_banner_title = ctk.CTkLabel(
        s_btop, text="MODE ALBUM SLIDE FOTO",
        font=ctk.CTkFont(size=11, weight="bold"), text_color="#A5B4FC"
    )
    app.slide_banner_title.pack(side="left")
    app.slide_badge_lbl = ctk.CTkLabel(
        s_btop, text="HD Original", font=ctk.CTkFont(size=10, weight="bold"),
        fg_color="#312E81", text_color="#E0E7FF", corner_radius=4, padx=8, pady=2
    )
    app.slide_badge_lbl.pack(side="right")

    app.slide_status_lbl = ctk.CTkLabel(
        s_banner,
        text="MavDown akan mengunduh semua file gambar asli HD tanpa watermark ke subfolder album khusus beserta file musik BGM.",
        font=ctk.CTkFont(size=10), text_color="#9CA3AF", justify="left", wraplength=420
    )
    app.slide_status_lbl.pack(anchor="w", padx=12, pady=(0, 10))

    s_grid = ctk.CTkFrame(app.slide_opts, fg_color="#131422", corner_radius=8)
    s_grid.pack(fill="x", pady=(0, 4))
    s_grid.columnconfigure(0, weight=1)
    s_grid.columnconfigure(1, weight=1)

    app.slide_p_count = ctk.CTkLabel(s_grid, text="Total: Album Slide", font=ctk.CTkFont(size=11), text_color="#D1D5DB", anchor="w")
    app.slide_p_count.grid(row=0, column=0, sticky="w", padx=12, pady=6)

    app.slide_p_format = ctk.CTkLabel(s_grid, text="Format: JPEG HD (Lossless)", font=ctk.CTkFont(size=11), text_color="#D1D5DB", anchor="w")
    app.slide_p_format.grid(row=0, column=1, sticky="w", padx=12, pady=6)

    app.slide_p_res = ctk.CTkLabel(s_grid, text="Dimensi: 1080x1511 (Asli)", font=ctk.CTkFont(size=11), text_color="#D1D5DB", anchor="w")
    app.slide_p_res.grid(row=1, column=0, sticky="w", padx=12, pady=6)

    app.slide_p_audio = ctk.CTkLabel(s_grid, text="Audio: Musik BGM (.mp3)", font=ctk.CTkFont(size=11), text_color="#D1D5DB", anchor="w")
    app.slide_p_audio.grid(row=1, column=1, sticky="w", padx=12, pady=6)

    # Format output Ugoira selector (dinamis jika media adalah animasi Ugoira)
    app.ugoira_fmt_container = ctk.CTkFrame(app.slide_opts, fg_color="transparent")
    ctk.CTkLabel(
        app.ugoira_fmt_container, text="PILIH FORMAT HASIL ANIMASI:",
        font=ctk.CTkFont(size=10, weight="bold"), text_color=THEME["text_muted"]
    ).pack(anchor="w", pady=(8, 4))

    app.ugoira_fmt_segmented = ctk.CTkSegmentedButton(
        app.ugoira_fmt_container, values=["Video (MP4)", "Animasi (GIF)"],
        command=app.on_ugoira_fmt_change,
        selected_color=THEME["accent_indigo"], selected_hover_color=THEME["accent_indigo_hover"],
        unselected_color="#131422", unselected_hover_color="#1E2032",
        text_color=THEME["text_title"], font=ctk.CTkFont(size=11, weight="bold"), height=34
    )
    app.ugoira_fmt_segmented.set("Video (MP4)")
    app.ugoira_fmt_segmented.pack(fill="x")

    # Audio options frame
    app.audio_opts = ctk.CTkFrame(fc_in, fg_color="transparent")
    ctk.CTkLabel(
        app.audio_opts, text="Format File Audio:",
        font=ctk.CTkFont(size=11, weight="bold"), text_color=THEME["text_muted"]
    ).pack(anchor="w", pady=(0, 4))
    app.audio_fmt_segmented = ctk.CTkSegmentedButton(
        app.audio_opts, values=["Auto", "MP3", "M4A", "FLAC", "WAV", "OPUS"],
        command=app.on_audio_fmt_change,
        selected_color=THEME["accent_indigo"], selected_hover_color=THEME["accent_indigo_hover"],
        unselected_color="#131422", unselected_hover_color="#1E2032",
        text_color=THEME["text_title"], font=ctk.CTkFont(size=11, weight="bold"), height=32
    )
    app.audio_fmt_segmented.set("Auto")
    app.audio_fmt_segmented.pack(fill="x")

    # Video options frame
    app.video_opts = ctk.CTkFrame(fc_in, fg_color="transparent")

    v_grid = ctk.CTkFrame(app.video_opts, fg_color="transparent")
    v_grid.pack(fill="x", pady=(0, 8))
    v_grid.columnconfigure(0, weight=1)
    v_grid.columnconfigure(1, weight=1)
    v_grid.columnconfigure(2, weight=1)

    def _make_seg(parent, col, label, values, cmd, default):
        b = ctk.CTkFrame(parent, fg_color="transparent")
        b.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 6, 0))
        ctk.CTkLabel(b, text=label, font=ctk.CTkFont(size=11, weight="bold"), text_color=THEME["text_muted"]).pack(anchor="w", pady=(0, 4))
        s = ctk.CTkSegmentedButton(
            b, values=values, command=cmd,
            selected_color=THEME["accent_indigo"], selected_hover_color=THEME["accent_indigo_hover"],
            unselected_color="#131422", unselected_hover_color="#1E2032",
            text_color=THEME["text_title"], font=ctk.CTkFont(size=11, weight="bold"), height=30
        )
        s.set(default)
        s.pack(fill="x")
        return s

    app.video_fmt_segmented = _make_seg(v_grid, 0, "Container Video:", ["Auto", "MP4", "MKV", "WEBM", "MOV"], app.on_video_fmt_change, "Auto")
    app.v_codec_segmented = _make_seg(v_grid, 1, "Video Codec:", ["Auto", "H.264", "VP9", "AV1"], app.on_vcodec_change, "Auto")
    app.a_codec_segmented = _make_seg(v_grid, 2, "Audio Codec:", ["Auto", "M4A", "Opus"], app.on_acodec_change, "Auto")

    ctk.CTkLabel(
        app.video_opts, text="Kualitas / Resolusi Maksimal:",
        font=ctk.CTkFont(size=11, weight="bold"), text_color=THEME["text_muted"]
    ).pack(anchor="w", pady=(4, 4))
    app.res_segmented = ctk.CTkSegmentedButton(
        app.video_opts,
        values=["Auto", "4K", "1440p", "1080p", "720p", "480p", "360p"],
        command=app.on_res_segmented_change,
        selected_color=THEME["accent_indigo"], selected_hover_color=THEME["accent_indigo_hover"],
        unselected_color="#131422", unselected_hover_color="#1E2032",
        text_color=THEME["text_title"], font=ctk.CTkFont(size=11, weight="bold"), height=32
    )
    app.res_segmented.set("Auto")
    app.res_segmented.pack(fill="x")

    # ── Section 3: Subtitle & Lyrics ──────────────────────────────────
    sec_sub = ctk.CTkFrame(rs_in, fg_color=THEME["card_inner"], corner_radius=10)
    sec_sub.pack(fill="x", pady=(0, 10))
    app.sec_sub = sec_sub
    ss_in = ctk.CTkFrame(sec_sub, fg_color="transparent")
    ss_in.pack(fill="x", padx=14, pady=12)

    app.lang_label = ctk.CTkLabel(
        ss_in, text="SUBTITLE & LIRIK OTOMATIS",
        font=ctk.CTkFont(size=10, weight="bold"), text_color=THEME["text_dim"]
    )
    app.lang_label.pack(anchor="w", pady=(0, 6))

    l_ctrl = ctk.CTkFrame(ss_in, fg_color="transparent")
    l_ctrl.pack(fill="x", pady=(0, 6))

    app.lang_optionmenu = ctk.CTkOptionMenu(
        l_ctrl, values=list(LANG_PRESETS.keys()), command=app.on_lang_preset_change,
        fg_color="#131422", button_color="#1E2032", button_hover_color="#2B2E45",
        text_color=THEME["text_title"], dropdown_fg_color="#171828", dropdown_hover_color="#26293B",
        font=ctk.CTkFont(size=11), height=32, width=240
    )
    app.lang_optionmenu.set("Indonesia & English")
    app.lang_optionmenu.pack(side="left", padx=(0, 8))

    ctk.CTkLabel(l_ctrl, text="ISO:", font=ctk.CTkFont(size=11), text_color=THEME["text_dim"]).pack(side="left", padx=(0, 4))
    app.lang_entry = ctk.CTkEntry(
        l_ctrl, textvariable=app.subs_lang_var, width=90, height=32, corner_radius=6,
        border_color=THEME["border"], fg_color="#131422", text_color=THEME["text_accent"],
        font=ctk.CTkFont(size=11, weight="bold")
    )
    app.lang_entry.pack(side="left")

    # ── Section 4: Advanced Checkbox Toggles ──────────────────────────
    sec_opts = ctk.CTkFrame(rs_in, fg_color=THEME["card_inner"], corner_radius=10)
    sec_opts.pack(fill="x", pady=(0, 10))
    app.sec_opts = sec_opts
    so_in = ctk.CTkFrame(sec_opts, fg_color="transparent")
    so_in.pack(fill="x", padx=14, pady=12)

    ctk.CTkLabel(
        so_in, text="AKSELERASI & FITUR TAMBAHAN",
        font=ctk.CTkFont(size=10, weight="bold"), text_color=THEME["text_dim"]
    ).pack(anchor="w", pady=(0, 8))

    cb_grid = ctk.CTkFrame(so_in, fg_color="transparent")
    cb_grid.pack(fill="x")
    cb_grid.columnconfigure(0, weight=1)
    cb_grid.columnconfigure(1, weight=1)

    cb_style = dict(font=ctk.CTkFont(size=11), fg_color=THEME["accent_indigo"], hover_color=THEME["accent_indigo_hover"])

    app.embed_thumb_cb = ctk.CTkCheckBox(cb_grid, text="Injeksi Thumbnail (Album Art)", variable=app.embed_thumb_var, **cb_style)
    app.embed_thumb_cb.grid(row=0, column=0, sticky="w", pady=3)

    app.use_aria2_cb = ctk.CTkCheckBox(cb_grid, text="Aria2c Multi-Thread (16x Speed)", variable=app.use_aria2_var, **cb_style)
    app.use_aria2_cb.grid(row=0, column=1, sticky="w", pady=3)

    app.embed_subs_cb = ctk.CTkCheckBox(cb_grid, text="Embed Softsub P0 (Default Aktif)", variable=app.embed_subs_var, **cb_style)
    app.embed_subs_cb.grid(row=1, column=0, sticky="w", pady=3)

    app.download_subs_cb = ctk.CTkCheckBox(cb_grid, text="Unduh Subtitle Terpisah (.srt)", variable=app.download_subs_var, **cb_style)
    app.download_subs_cb.grid(row=1, column=1, sticky="w", pady=3)

    app.download_playlist_cb = ctk.CTkCheckBox(cb_grid, text="Unduh Full Playlist", variable=app.download_playlist_var, **cb_style)
    app.download_playlist_cb.grid(row=2, column=0, sticky="w", pady=3)

    # ── Section 5: Custom Command ─────────────────────────────────────
    sec_custom = ctk.CTkFrame(rs_in, fg_color=THEME["card_inner"], corner_radius=10)
    sec_custom.pack(fill="x")
    sc_in = ctk.CTkFrame(sec_custom, fg_color="transparent")
    sc_in.pack(fill="x", padx=14, pady=10)

    ctk.CTkLabel(
        sc_in, text="ARGUMEN / PERINTAH CUSTOM (OPSIONAL):",
        font=ctk.CTkFont(size=10, weight="bold"), text_color=THEME["text_dim"]
    ).pack(anchor="w", pady=(0, 4))

    ctk.CTkEntry(
        sc_in, textvariable=app.custom_cmd_var,
        placeholder_text="Contoh: --sponsorblock-remove sponsor,selfpromo",
        height=34, corner_radius=8, border_color=THEME["border"], fg_color="#131422",
        text_color="#D1D5DB", placeholder_text_color="#4B5563", font=ctk.CTkFont(size=11)
    ).pack(fill="x")

    return studio_view
