import os
import subprocess
import customtkinter as ctk
from PIL import Image
from ui.constants import THEME, PLATFORM_PATTERNS
from history import get_history_entries, delete_history_entry, clear_all_history, ensure_entry_thumbnail

def build_history_view(app, parent):
    """
    Membangun tampilan Riwayat Unduhan (Download History Library).
    """
    history_view = ctk.CTkFrame(parent, fg_color=THEME["card_bg"], corner_radius=14)

    # ══ TOP BAR: HEADER & PENCARIAN ══════════════════════════════════
    top_bar = ctk.CTkFrame(history_view, fg_color="transparent")
    top_bar.pack(fill="x", padx=16, pady=(16, 12))

    t_left = ctk.CTkFrame(top_bar, fg_color="transparent")
    t_left.pack(side="left", fill="y")

    ctk.CTkLabel(
        t_left, text="Riwayat Unduhan",
        font=ctk.CTkFont(family="Inter", size=16, weight="bold"), text_color=THEME["text_title"]
    ).pack(side="left")

    app.history_count_badge = ctk.CTkLabel(
        t_left, text="0 Media",
        font=ctk.CTkFont(size=10, weight="bold"),
        fg_color="#1E1B4B", text_color="#818CF8", corner_radius=6, padx=8, pady=3
    )
    app.history_count_badge.pack(side="left", padx=(10, 0))

    # Action Buttons di Kanan
    t_right = ctk.CTkFrame(top_bar, fg_color="transparent")
    t_right.pack(side="right")

    ctk.CTkButton(
        t_right, text="Bersihkan Riwayat",
        font=ctk.CTkFont(size=11, weight="bold"),
        fg_color="#31131E", hover_color="#4C1D24", text_color="#F87171",
        height=32, corner_radius=6,
        command=lambda: _on_clear_history(app)
    ).pack(side="right", padx=(8, 0))

    ctk.CTkButton(
        t_right, text="Buka Folder Unduhan",
        font=ctk.CTkFont(size=11),
        fg_color="#1E2032", hover_color="#2B2E45", text_color="#E5E7EB",
        height=32, corner_radius=6,
        command=app.open_folder
    ).pack(side="right")

    # ══ SEARCH BAR ═══════════════════════════════════════════════════
    search_bar = ctk.CTkFrame(history_view, fg_color="transparent")
    search_bar.pack(fill="x", padx=16, pady=(0, 10))

    app.history_search_entry = ctk.CTkEntry(
        search_bar, placeholder_text="Cari riwayat berdasarkan judul atau platform...",
        height=36, corner_radius=8,
        border_color=THEME["border_light"], fg_color="#0A0B12",
        text_color=THEME["text_title"], placeholder_text_color=THEME["text_dim"],
        font=ctk.CTkFont(size=12)
    )
    app.history_search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
    app.history_search_entry.bind("<KeyRelease>", lambda e: _on_search_keyrelease(app))

    ctk.CTkButton(
        search_bar, text="Reset", width=60, height=36, corner_radius=8,
        fg_color="#1E2032", hover_color="#2B2E45", font=ctk.CTkFont(size=11),
        command=lambda: _reset_search(app)
    ).pack(side="right")

    # ══ SCROLLABLE LIST AREA ═════════════════════════════════════════
    app.history_scroll = ctk.CTkScrollableFrame(history_view, fg_color="transparent")
    app.history_scroll.pack(fill="both", expand=True, padx=16, pady=(0, 16))

    # Inisialisasi daftar
    refresh_history_view(app)

    return history_view

def _on_search_keyrelease(app):
    query = app.history_search_entry.get().strip()
    refresh_history_view(app, search_query=query)

def _reset_search(app):
    app.history_search_entry.delete(0, "end")
    refresh_history_view(app, search_query="")

def _on_clear_history(app):
    clear_all_history()
    refresh_history_view(app)
    app.show_toast("Seluruh riwayat unduhan telah dibersihkan.", "info")

def _open_media_file(file_path: str):
    """Buka file media langsung dengan pemutar default OS."""
    if not file_path or not os.path.exists(file_path):
        return
    try:
        if os.name == 'nt':
            os.startfile(file_path)
        else:
            subprocess.Popen(["xdg-open", file_path])
    except Exception as e:
        print(f"Error opening file: {e}")

def _open_in_explorer(file_path: str):
    """Buka file di File Explorer dengan posisi terseleksi."""
    if not file_path or not os.path.exists(file_path):
        return
    try:
        if os.name == 'nt':
            if os.path.isfile(file_path):
                subprocess.Popen(f'explorer /select,"{os.path.abspath(file_path)}"')
            else:
                os.startfile(file_path)
        else:
            folder = file_path if os.path.isdir(file_path) else os.path.dirname(file_path)
            subprocess.Popen(["xdg-open", folder])
    except Exception as e:
        print(f"Error opening in explorer: {e}")

def _copy_source_link(app, url: str):
    """Salin tautan asli sumber media ke clipboard sistem."""
    if not url:
        return
    try:
        app.clipboard_clear()
        app.clipboard_append(url)
        app.show_toast("Tautan asli disalin ke clipboard!", "success")
    except Exception as e:
        print(f"Error copying link: {e}")

def _get_platform_badge_color(platform: str) -> tuple:
    """Mengembalikan warna (background, text) untuk tag platform."""
    plat_lower = (platform or '').lower()
    if 'youtube' in plat_lower:
        return "#FF0000", "#FFFFFF"
    elif 'tiktok' in plat_lower:
        return "#00F2FE", "#000000"
    elif 'douyin' in plat_lower:
        return "#FE2C55", "#FFFFFF"
    elif 'instagram' in plat_lower:
        return "#E1306C", "#FFFFFF"
    elif 'twitter' in plat_lower or 'x' in plat_lower:
        return "#1DA1F2", "#FFFFFF"
    elif 'bilibili' in plat_lower:
        return "#00A1D6", "#FFFFFF"
    elif 'pinterest' in plat_lower:
        return "#BD081C", "#FFFFFF"
    elif 'facebook' in plat_lower:
        return "#1877F2", "#FFFFFF"
    elif 'soundcloud' in plat_lower:
        return "#FF7700", "#FFFFFF"
    elif 'twitch' in plat_lower:
        return "#9146FF", "#FFFFFF"
    elif 'reddit' in plat_lower:
        return "#FF4500", "#FFFFFF"
    return "#4F46E5", "#FFFFFF"

def refresh_history_view(app, search_query: str = ""):
    """
    Segarkan daftar riwayat unduhan di UI dengan thumbnail visual dan metadata kaya.
    """
    if not hasattr(app, 'history_scroll') or not app.history_scroll.winfo_exists():
        return

    # Bersihkan item lama
    for child in app.history_scroll.winfo_children():
        child.destroy()

    if not hasattr(app, '_history_thumb_refs'):
        app._history_thumb_refs = {}
    app._history_thumb_refs.clear()

    entries = get_history_entries(search=search_query)

    # Perbarui badge count
    if hasattr(app, 'history_count_badge') and app.history_count_badge.winfo_exists():
        total_text = f"{len(entries)} Media" if not search_query else f"{len(entries)} Ditemukan"
        app.history_count_badge.configure(text=total_text)

    if not entries:
        empty_box = ctk.CTkFrame(app.history_scroll, fg_color=THEME["card_inner"], corner_radius=10)
        empty_box.pack(fill="x", pady=40, padx=20)
        empty_in = ctk.CTkFrame(empty_box, fg_color="transparent")
        empty_in.pack(padx=20, pady=30)
        
        msg = "Belum ada riwayat unduhan." if not search_query else f"Tidak ada hasil untuk '{search_query}'."
        ctk.CTkLabel(
            empty_in, text=msg,
            font=ctk.CTkFont(size=13, weight="bold"), text_color=THEME["text_muted"]
        ).pack(pady=(0, 4))
        ctk.CTkLabel(
            empty_in, text="Media yang berhasil diunduh dari YouTube, TikTok, Douyin, IG, dll. akan muncul di sini lengkap dengan preview & metadata.",
            font=ctk.CTkFont(size=11), text_color=THEME["text_dim"]
        ).pack()
        return

    for entry in entries:
        eid = entry.get("id")
        title = entry.get("title", "Unduhan Media")
        platform = entry.get("platform", "Web")
        fpath = entry.get("file_path", "")
        fsize = entry.get("file_size", "")
        ts = entry.get("timestamp", "")
        is_slide = entry.get("is_slide", False)
        author = entry.get("author", "")
        resolution = entry.get("resolution", "")
        duration = entry.get("duration", "")
        media_format = entry.get("media_format", "")
        source_url = entry.get("source_url", "")
        slide_count = entry.get("slide_count", 0)

        item_card = ctk.CTkFrame(app.history_scroll, fg_color=THEME["card_inner"], corner_radius=10)
        item_card.pack(fill="x", pady=5)

        card_in = ctk.CTkFrame(item_card, fg_color="transparent")
        card_in.pack(fill="x", padx=12, pady=10)

        # ── 1. LEFT: Visual Thumbnail Preview ──
        thumb_path = entry.get("local_thumbnail")
        if not thumb_path or not os.path.isfile(thumb_path):
            thumb_path = ensure_entry_thumbnail(entry)

        ctk_thumb = None
        if thumb_path and os.path.isfile(thumb_path):
            try:
                with Image.open(thumb_path) as pil_im:
                    im_copy = pil_im.copy().convert('RGB')
                    target_w, target_h = 116, 68
                    im_copy.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
                    ctk_thumb = ctk.CTkImage(
                        light_image=im_copy,
                        dark_image=im_copy,
                        size=(im_copy.width, im_copy.height)
                    )
                    app._history_thumb_refs[eid] = ctk_thumb
            except Exception:
                ctk_thumb = None

        thumb_box = ctk.CTkFrame(
            card_in, width=118, height=70, corner_radius=8,
            fg_color="#0D0E18", border_width=1, border_color="#26293D"
        )
        thumb_box.pack(side="left", padx=(0, 14))
        thumb_box.pack_propagate(False)

        file_exists = bool(fpath and os.path.exists(fpath))

        if ctk_thumb:
            t_lbl = ctk.CTkLabel(thumb_box, image=ctk_thumb, text="", corner_radius=8)
            t_lbl.pack(expand=True)
            if file_exists:
                t_lbl.bind("<Button-1>", lambda e, p=fpath: _open_media_file(p))
                t_lbl.configure(cursor="hand2")
        else:
            media_type = media_format or ("SLIDE" if is_slide else ("AUDIO" if fpath.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.opus')) else "VIDEO"))
            t_fallback = ctk.CTkLabel(
                thumb_box,
                text=media_type,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#818CF8" if not is_slide else "#34D399"
            )
            t_fallback.pack(expand=True)
            if file_exists:
                t_fallback.bind("<Button-1>", lambda e, p=fpath: _open_media_file(p))
                t_fallback.configure(cursor="hand2")

        # ── 2. CENTER: Rich Info & Metadata ──
        info_col = ctk.CTkFrame(card_in, fg_color="transparent")
        info_col.pack(side="left", fill="both", expand=True)

        # Baris 1: Judul
        display_title = title if len(title) <= 85 else title[:82] + "..."
        ctk.CTkLabel(
            info_col, text=display_title,
            font=ctk.CTkFont(size=12, weight="bold"), text_color=THEME["text_title"],
            anchor="w", justify="left"
        ).pack(fill="x", pady=(0, 4))

        # Baris 2: Badges & Metadata Chips
        pill_row = ctk.CTkFrame(info_col, fg_color="transparent")
        pill_row.pack(fill="x", pady=(0, 4))

        # Badge Platform
        bg_col, txt_col = _get_platform_badge_color(platform)
        p_badge = ctk.CTkFrame(pill_row, fg_color=bg_col, corner_radius=4)
        p_badge.pack(side="left", padx=(0, 6))
        ctk.CTkLabel(
            p_badge, text=platform, font=ctk.CTkFont(size=9, weight="bold"),
            text_color=txt_col
        ).pack(padx=6, pady=1)

        # Badge Format Media (e.g. MP4, SLIDE, JPG, MP3)
        fmt_display = media_format or ("SLIDE" if is_slide else "MEDIA")
        fmt_badge = ctk.CTkFrame(pill_row, fg_color="#1E2035", corner_radius=4)
        fmt_badge.pack(side="left", padx=(0, 6))
        ctk.CTkLabel(
            fmt_badge, text=fmt_display, font=ctk.CTkFont(size=9, weight="bold"),
            text_color="#818CF8" if fmt_display != "SLIDE" else "#34D399"
        ).pack(padx=6, pady=1)

        # Nama Kreator / Artis (jika terdeteksi)
        if author:
            disp_author = author if len(author) <= 22 else author[:20] + ".."
            auth_badge = ctk.CTkFrame(pill_row, fg_color="#181B2C", corner_radius=4)
            auth_badge.pack(side="left", padx=(0, 6))
            ctk.CTkLabel(
                auth_badge, text=f"Kreator: {disp_author}", font=ctk.CTkFont(size=9),
                text_color="#C7D2FE"
            ).pack(padx=6, pady=1)

        # Resolusi (e.g. 1080p FHD)
        if resolution:
            res_badge = ctk.CTkFrame(pill_row, fg_color="#181B2C", corner_radius=4)
            res_badge.pack(side="left", padx=(0, 6))
            ctk.CTkLabel(
                res_badge, text=resolution, font=ctk.CTkFont(size=9),
                text_color="#93C5FD"
            ).pack(padx=6, pady=1)

        # Durasi Video atau Jumlah Slide
        if is_slide and slide_count > 1:
            dur_chip = f"{slide_count} Foto"
        elif duration:
            dur_chip = duration
        else:
            dur_chip = ""

        if dur_chip:
            dur_badge = ctk.CTkFrame(pill_row, fg_color="#181B2C", corner_radius=4)
            dur_badge.pack(side="left", padx=(0, 6))
            ctk.CTkLabel(
                dur_badge, text=dur_chip, font=ctk.CTkFont(size=9),
                text_color="#CBD5E1"
            ).pack(padx=6, pady=1)

        # Ukuran File
        if fsize:
            ctk.CTkLabel(
                pill_row, text=fsize,
                font=ctk.CTkFont(size=10, weight="bold"), text_color=THEME["text_accent"]
            ).pack(side="left", padx=(2, 8))

        # Waktu / Tanggal Unduh
        if ts:
            ctk.CTkLabel(
                pill_row, text=ts,
                font=ctk.CTkFont(size=9), text_color=THEME["text_dim"]
            ).pack(side="left")

        # Baris 3: Lokasi File & Status
        row3 = ctk.CTkFrame(info_col, fg_color="transparent")
        row3.pack(fill="x")

        if fpath:
            path_display = fpath if len(fpath) <= 90 else "..." + fpath[-87:]
            path_color = THEME["text_dim"] if file_exists else "#EF4444"
            status_text = path_display if file_exists else f"{path_display} (File telah dipindah atau dihapus)"
            ctk.CTkLabel(
                row3, text=status_text,
                font=ctk.CTkFont(size=9), text_color=path_color,
                anchor="w", justify="left"
            ).pack(side="left", fill="x", expand=True)

        # ── 3. RIGHT: Action Buttons ──
        act_col = ctk.CTkFrame(card_in, fg_color="transparent")
        act_col.pack(side="right", padx=(8, 0))

        if file_exists:
            is_image_or_slide = is_slide or (media_format and media_format.upper() in ("SLIDE", "JPG", "JPEG", "PNG", "WEBP", "BMP")) or fpath.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp')) or os.path.isdir(fpath)
            action_btn_text = "Buka" if is_image_or_slide else "Putar"

            ctk.CTkButton(
                act_col, text=action_btn_text, width=64, height=32, corner_radius=6,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=THEME["accent_emerald"], hover_color=THEME["accent_emerald_hover"],
                command=lambda p=fpath: _open_media_file(p)
            ).pack(side="left", padx=(0, 4))

            ctk.CTkButton(
                act_col, text="Folder", width=64, height=32, corner_radius=6,
                font=ctk.CTkFont(size=11),
                fg_color="#1E2032", hover_color="#2B2E45", text_color="#E5E7EB",
                command=lambda p=fpath: _open_in_explorer(p)
            ).pack(side="left", padx=(0, 4))

        if source_url:
            ctk.CTkButton(
                act_col, text="Salin Link", width=74, height=32, corner_radius=6,
                font=ctk.CTkFont(size=11),
                fg_color="#1E2032", hover_color="#2B2E45", text_color="#818CF8",
                command=lambda u=source_url: _copy_source_link(app, u)
            ).pack(side="left", padx=(0, 6))

        # Delete Entry Button
        ctk.CTkButton(
            act_col, text="Hapus", width=54, height=32, corner_radius=6,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#27131B", hover_color="#451824", text_color="#F87171",
            command=lambda i=eid: _delete_entry(app, i)
        ).pack(side="left")

def _delete_entry(app, entry_id: str):
    delete_history_entry(entry_id)
    refresh_history_view(app, search_query=app.history_search_entry.get().strip())
