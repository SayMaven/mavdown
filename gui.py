import flet as ft
import threading
import uuid
import webbrowser
import os
import re
import time

from config import load_config, save_config, get_full_config, save_full_config, DEFAULT_OUTPUT_DIR, is_android
from downloader import download_video_logic, download_state, ui_queue, get_video_info

# Global App State
app_state = {
    "tasks": {},
    "current_video_info": None
}

def main(page: ft.Page):
    # ===========================================================================
    # 1. CORE THEME & SETUP
    # ===========================================================================
    page.title = "Mavdown"
    
    # Modern Android Standard DPI Size
    page.window.width = 412
    page.window.height = 892
    
    # Material 3 Setup (Phase 4 requirement: strictly follow M3 guidelines)
    # Seed color requested by user: #99DD88 (Green)
    page.theme = ft.Theme(
        color_scheme_seed="#99DD88",
        use_material3=True
    )
    
    cfg_init = get_full_config()
    is_dark = (cfg_init.get("theme", "dark") == "dark")
    page.theme_mode = ft.ThemeMode.DARK if is_dark else ft.ThemeMode.LIGHT

    download_config = {
        "type": "video",
        "format_mode": "auto",
        "video_preset": "kualitas",
        "video_res": "best",
        "audio_format": "m4a",
        "convert_audio": "none",
        "download_subs": False,
        "subs_lang": "id,en",
        "embed_thumb": True,
        "download_playlist": False,
        "custom_cmd_template": ""
    }

    current_view = ["home"]
    main_container = ft.Container(expand=True)
    
    def show_toast(msg):
        page.overlay.append(ft.SnackBar(content=ft.Text(msg), open=True))
        page.update()

    # ===========================================================================
    # 2. APP BAR (NATIVE SEAL STYLE)
    # ===========================================================================
    app_bar = ft.Row([
        ft.IconButton(ft.Icons.SETTINGS_OUTLINED, icon_size=24, tooltip="Pengaturan", on_click=lambda e: switch_view("settings")),
        ft.Row([
            ft.IconButton(ft.Icons.TERMINAL_OUTLINED, icon_size=24, tooltip="Log Console", on_click=lambda e: switch_view("log")),
        ], spacing=4)
    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

    # ===========================================================================
    # 3. HOME VIEW (NATIVE M3 UI)
    # ===========================================================================
    header_title = ft.Text("Mavdown", size=36, weight="w900", color=ft.Colors.ON_SURFACE)
    
    platform_chip = ft.Container(
        content=ft.Text("", color=ft.Colors.ON_PRIMARY_CONTAINER, size=11, weight="bold"),
        bgcolor=ft.Colors.PRIMARY_CONTAINER,
        padding=ft.Padding(8, 4, 8, 4),
        border_radius=16,
        visible=False
    )

    def detect_platform(url):
        if "youtube.com" in url or "youtu.be" in url:
            return "YouTube"
        elif "twitter.com" in url or "x.com" in url:
            return "X (Twitter)"
        elif "tiktok.com" in url:
            return "TikTok"
        elif "instagram.com" in url:
            return "Instagram"
        return None

    def fetch_info_logic(url):
        try:
            info_title_text.value = "Menganalisa tautan..."
            meta_channel_text.value = "Mohon tunggu sebentar..."
            meta_duration_text.value = ""
            info_image_container.visible = False
            info_card.visible = True
            page.update()
            
            info = get_video_info(url)
            app_state["current_video_info"] = info
            title = info.get("title") or "Video"
            info_title_text.value = title
            
            thumb = info.get("thumbnail")
            if thumb:
                info_image.src = thumb
                info_image_container.visible = True
            else:
                info_image_container.visible = False
                
            uploader = info.get("uploader") or info.get("extractor") or ""
            meta_channel_text.value = uploader
            
            duration = info.get("duration")
            if duration:
                mins, secs = divmod(int(duration), 60)
                meta_duration_text.value = f"{mins:02d}:{secs:02d}"
            else:
                meta_duration_text.value = ""
                
            info_card.visible = True
            page.update()
        except Exception as ex:
            print(f"Error fetching info: {ex}")
            info_title_text.value = "Gagal mengambil info"
            meta_channel_text.value = str(ex)
            info_image_container.visible = False
            info_card.visible = True
            page.update()

    def on_url_change(e):
        name = detect_platform(url_input.value)
        if name:
            platform_chip.content.value = name
            platform_chip.visible = True
        else:
            platform_chip.visible = False
            
        url = url_input.value.strip()
        if url.startswith("http://") or url.startswith("https://"):
            if app_state["current_video_info"] is None or app_state["current_video_info"].get("webpage_url") != url:
                # Reset and show loading state if needed
                app_state["current_video_info"] = None
                threading.Thread(target=fetch_info_logic, args=(url,), daemon=True).start()
        else:
            info_card.visible = False
            app_state["current_video_info"] = None
        page.update()

    url_input = ft.TextField(
        label="Tautan video",
        hint_text="Tempelkan link video di sini...",
        border_radius=16,
        expand=True,
        on_change=on_url_change,
        content_padding=16,
        filled=True,
        border_color=ft.Colors.TRANSPARENT,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        prefix_icon=ft.Icons.LINK_ROUNDED
    )

    async def paste_url_action(e):
        try:
            clip = await page.clipboard.get()
            if clip and isinstance(clip, str):
                url_input.value = clip
                on_url_change(None)
                show_toast("Tautan berhasil ditempel! 📋")
                page.update()
        except Exception:
            pass

    # Media Info Preview Card (Seal Style M3)
    info_title_text = ft.Text("", size=16, weight="bold", selectable=True, color=ft.Colors.ON_SURFACE, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)
    info_image = ft.Image(src="", fit="cover", expand=True)
    info_image_container = ft.Container(
        content=info_image, 
        aspect_ratio=16/9,
        border_radius=ft.BorderRadius(16, 16, 0, 0),
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS, 
        visible=False
    )
    
    meta_channel_text = ft.Text("", size=13, color=ft.Colors.ON_SURFACE_VARIANT, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
    meta_duration_text = ft.Text("", size=13, color=ft.Colors.ON_SURFACE_VARIANT)

    info_card = ft.Container(
        content=ft.Column([
            info_image_container,
            ft.Container(
                content=ft.Column([
                    info_title_text,
                    ft.Row([meta_channel_text, ft.Container(expand=True), meta_duration_text], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
                ], spacing=4),
                padding=ft.Padding(16, 12, 16, 16)
            )
        ], spacing=0),
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
        border_radius=16,
        border=ft.Border.all(1, ft.Colors.SURFACE_CONTAINER_HIGHEST),
        visible=False
    )

    home_view = ft.ListView(
        expand=True,
        padding=ft.Padding(16, 0, 16, 16),
        spacing=16,
        controls=[
            app_bar,
            ft.Container(height=10),
            header_title,
            ft.Container(height=16),
            info_card,
            url_input
        ]
    )

    # ===========================================================================
    # 4. PREFERENCE DIALOGS (M3)
    # ===========================================================================
    def get_convert_label():
        c = download_config.get("convert_audio", "none")
        return "Tidak diubah" if c == "none" else f"Ubah ke {c}"

    def get_audio_fmt_label():
        return f"Format audio: {download_config.get('audio_format', 'm4a').upper()}"

    def get_video_fmt_label():
        p = download_config.get("video_preset", "kualitas")
        return "Lawas" if p == "lawas" else "Kualitas"

    def get_video_qual_label():
        res_map = {
            "best": "Kualitas terbaik", "2160": "2160p (4K)", "1440": "1440p", 
            "1080": "1080p", "720": "720p", "480": "480p", "360": "360p", "worst": "Kualitas rendah"
        }
        return res_map.get(download_config.get("video_res", "best"), "Kualitas terbaik")

    def sync_button_labels():
        btn_convert_audio.text = get_convert_label()
        btn_audio_fmt.text = get_audio_fmt_label()
        btn_video_fmt.text = get_video_fmt_label()
        btn_video_qual.text = get_video_qual_label()

    def open_video_format_dialog(e):
        def select_preset(val):
            download_config["video_preset"] = val
            sync_button_labels()
            dlg.open = False
            page.update()

        radio_group = ft.RadioGroup(
            value=download_config["video_preset"],
            content=ft.Column([
                ft.ListTile(leading=ft.Radio(value="lawas"), title=ft.Text("Lawas", weight="bold"), subtitle=ft.Text("Format MP4 (H.264) stabil untuk dibagikan", size=12)),
                ft.ListTile(leading=ft.Radio(value="kualitas"), title=ft.Text("Kualitas", weight="bold"), subtitle=ft.Text("Format modern AV1/VP9 untuk kualitas tinggi", size=12))
            ])
        )
        dlg = ft.AlertDialog(title=ft.Text("Format video pilihan"), content=radio_group, actions=[
            ft.TextButton("Batalkan", on_click=lambda e: setattr(dlg, 'open', False) or page.update()),
            ft.TextButton("Konfirmasi", on_click=lambda e: select_preset(radio_group.value))
        ])
        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    def open_video_quality_dialog(e):
        def confirm_res(val):
            download_config["video_res"] = val
            sync_button_labels()
            dlg.open = False
            page.update()
            
        radio_group = ft.RadioGroup(
            value=download_config["video_res"],
            content=ft.Column([
                ft.ListTile(leading=ft.Radio(value="best"), title=ft.Text("Kualitas terbaik")),
                ft.ListTile(leading=ft.Radio(value="1080"), title=ft.Text("1080p")),
                ft.ListTile(leading=ft.Radio(value="720"), title=ft.Text("720p"))
            ])
        )
        dlg = ft.AlertDialog(title=ft.Text("Kualitas video pilihan"), content=radio_group, actions=[
            ft.TextButton("Batalkan", on_click=lambda e: setattr(dlg, 'open', False) or page.update()),
            ft.TextButton("Konfirmasi", on_click=lambda e: confirm_res(radio_group.value))
        ])
        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    def open_audio_format_dialog(e):
        def confirm_aud(val):
            download_config["audio_format"] = val
            sync_button_labels()
            dlg.open = False
            page.update()
            
        radio_group = ft.RadioGroup(
            value=download_config["audio_format"],
            content=ft.Column([
                ft.ListTile(leading=ft.Radio(value="m4a"), title=ft.Text("m4a")),
                ft.ListTile(leading=ft.Radio(value="webm"), title=ft.Text("webm")),
                ft.ListTile(leading=ft.Radio(value="mp3"), title=ft.Text("mp3"))
            ])
        )
        dlg = ft.AlertDialog(title=ft.Text("Format audio pilihan"), content=radio_group, actions=[
            ft.TextButton("Batalkan", on_click=lambda e: setattr(dlg, 'open', False) or page.update()),
            ft.TextButton("Konfirmasi", on_click=lambda e: confirm_aud(radio_group.value))
        ])
        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    def open_audio_convert_dialog(e):
        def confirm_conv(val):
            download_config["convert_audio"] = val
            sync_button_labels()
            dlg.open = False
            page.update()
            
        radio_group = ft.RadioGroup(
            value=download_config["convert_audio"],
            content=ft.Column([
                ft.ListTile(leading=ft.Radio(value="none"), title=ft.Text("Tidak diubah")),
                ft.ListTile(leading=ft.Radio(value="mp3"), title=ft.Text("mp3"))
            ])
        )
        dlg = ft.AlertDialog(title=ft.Text("Konversi audio"), content=radio_group, actions=[
            ft.TextButton("Batalkan", on_click=lambda e: setattr(dlg, 'open', False) or page.update()),
            ft.TextButton("Konfirmasi", on_click=lambda e: confirm_conv(radio_group.value))
        ])
        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    # ===========================================================================
    # 5. BOTTOM SHEET & CUSTOM FORMAT MODAL (M3)
    # ===========================================================================
    btn_video_fmt = ft.OutlinedButton(get_video_fmt_label(), on_click=open_video_format_dialog, style=ft.ButtonStyle(color=ft.Colors.ON_SURFACE_VARIANT))
    btn_video_qual = ft.OutlinedButton(get_video_qual_label(), icon=ft.Icons.HIGH_QUALITY_OUTLINED, on_click=open_video_quality_dialog, style=ft.ButtonStyle(color=ft.Colors.ON_SURFACE_VARIANT))
    btn_audio_fmt = ft.OutlinedButton(get_audio_fmt_label(), icon=ft.Icons.AUDIO_FILE_OUTLINED, on_click=open_audio_format_dialog, style=ft.ButtonStyle(color=ft.Colors.ON_SURFACE_VARIANT))
    btn_convert_audio = ft.OutlinedButton(get_convert_label(), icon=ft.Icons.AUTORENEW_ROUNDED, on_click=open_audio_convert_dialog, style=ft.ButtonStyle(color=ft.Colors.ON_SURFACE_VARIANT))

    def create_toggle_button(label, key):
        def on_click(e):
            download_config[key] = not download_config[key]
            e.control.icon = ft.Icons.CHECK if download_config[key] else None
            e.control.style.bgcolor = ft.Colors.PRIMARY_CONTAINER if download_config[key] else ft.Colors.TRANSPARENT
            e.control.style.color = ft.Colors.ON_PRIMARY_CONTAINER if download_config[key] else ft.Colors.ON_SURFACE_VARIANT
            page.update()
        
        is_sel = download_config[key]
        return ft.OutlinedButton(
            label, 
            icon=ft.Icons.CHECK if is_sel else None,
            on_click=on_click,
            style=ft.ButtonStyle(
                color=ft.Colors.ON_PRIMARY_CONTAINER if is_sel else ft.Colors.ON_SURFACE_VARIANT,
                bgcolor=ft.Colors.PRIMARY_CONTAINER if is_sel else ft.Colors.TRANSPARENT,
            )
        )

    btn_playlist = create_toggle_button("Unduh daftar putar", "download_playlist")
    btn_subs = create_toggle_button("Unduh takarir", "download_subs")
    btn_thumb = create_toggle_button("Simpan thumbnail", "embed_thumb")

    pref_single_row = ft.Row([btn_audio_fmt, btn_convert_audio], scroll=ft.ScrollMode.HIDDEN, spacing=8)
    text_pref = ft.Text("Preferensi format", size=13, color=ft.Colors.PRIMARY)

    def update_pref_row():
        val = download_config["type"]
        text_pref.visible = True
        pref_single_row.visible = True
        if val == "video":
            pref_single_row.controls = [btn_video_fmt, btn_video_qual, btn_audio_fmt, btn_convert_audio]
        elif val == "audio":
            pref_single_row.controls = [btn_audio_fmt, btn_convert_audio]
        else:
            pref_single_row.controls = []
        page.update()

    # Custom M3 Segmented Button using a Row
    def on_type_change(idx):
        download_config["type"] = "audio" if idx == 0 else "video"
        update_type_ui()
        update_pref_row()
        
    def update_type_ui():
        is_aud = download_config["type"] == "audio"
        btn_type_aud.bgcolor = ft.Colors.ON_SURFACE_VARIANT if is_aud else ft.Colors.TRANSPARENT
        btn_type_aud.content.color = ft.Colors.SURFACE if is_aud else ft.Colors.ON_SURFACE_VARIANT
        btn_type_aud.content.value = "✓ Audio" if is_aud else "Audio"
        
        btn_type_vid.bgcolor = ft.Colors.ON_SURFACE_VARIANT if not is_aud else ft.Colors.TRANSPARENT
        btn_type_vid.content.color = ft.Colors.SURFACE if not is_aud else ft.Colors.ON_SURFACE_VARIANT
        btn_type_vid.content.value = "✓ Video" if not is_aud else "Video"
        page.update()

    btn_type_aud = ft.Container(content=ft.Text("Audio", size=13, text_align=ft.TextAlign.CENTER), expand=True, on_click=lambda e: on_type_change(0), border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT), border_radius=ft.BorderRadius(20, 0, 0, 20), padding=8)
    btn_type_vid = ft.Container(content=ft.Text("✓ Video", size=13, text_align=ft.TextAlign.CENTER, color=ft.Colors.SURFACE), expand=True, bgcolor=ft.Colors.ON_SURFACE_VARIANT, on_click=lambda e: on_type_change(1), border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT), border_radius=ft.BorderRadius(0, 20, 20, 0), padding=8)
    
    type_segmented = ft.Row([btn_type_aud, btn_type_vid], spacing=0)

    def on_format_mode_change(idx):
        download_config["format_mode"] = "auto" if idx == 0 else "custom"
        update_format_mode_ui()
        update_pref_row()
        
    def update_format_mode_ui():
        is_auto = download_config["format_mode"] == "auto"
        btn_fmt_auto.bgcolor = ft.Colors.ON_SURFACE_VARIANT if is_auto else ft.Colors.TRANSPARENT
        btn_fmt_auto.content.color = ft.Colors.SURFACE if is_auto else ft.Colors.ON_SURFACE_VARIANT
        btn_fmt_auto.content.value = "✓ Otomatis" if is_auto else "Otomatis"
        
        btn_fmt_cust.bgcolor = ft.Colors.ON_SURFACE_VARIANT if not is_auto else ft.Colors.TRANSPARENT
        btn_fmt_cust.content.color = ft.Colors.SURFACE if not is_auto else ft.Colors.ON_SURFACE_VARIANT
        btn_fmt_cust.content.value = "✓ Kustom" if not is_auto else "Kustom"
        page.update()

    btn_fmt_auto = ft.Container(content=ft.Text("✓ Otomatis", size=13, text_align=ft.TextAlign.CENTER, color=ft.Colors.SURFACE), width=120, bgcolor=ft.Colors.ON_SURFACE_VARIANT, on_click=lambda e: on_format_mode_change(0), border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT), border_radius=ft.BorderRadius(20, 0, 0, 20), padding=8)
    btn_fmt_cust = ft.Container(content=ft.Text("Kustom", size=13, text_align=ft.TextAlign.CENTER), width=120, on_click=lambda e: on_format_mode_change(1), border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT), border_radius=ft.BorderRadius(0, 20, 20, 0), padding=8)
    
    format_mode_segmented = ft.Row([btn_fmt_auto, btn_fmt_cust], spacing=0)

    def open_format_selection_dialog(info):
        formats = info.get("formats", [])
        suggested = []
        video_only = []
        audio_only = []
        
        def fmt_size(sz):
            if not sz: return "Unknown size"
            return f"{sz / 1024 / 1024:.2f} MB"
            
        for f in formats:
            vcodec = str(f.get("vcodec", "none"))
            acodec = str(f.get("acodec", "none"))
            ext = str(f.get("ext", ""))
            
            if ext in ["mhtml", "weba", "mha"] or f.get("format_note") == "storyboard":
                continue
                
            fid = str(f.get("format_id", ""))
            res = str(f.get("resolution", "")) or f"{f.get('width', '')}x{f.get('height', '')}"
            if res == "x" or res == "NonexNone": res = "audio only"
            if res == "audio only":
                res += f" ({f.get('format_note', 'medium')})"
            else:
                res += f" ({f.get('format_note', '')})"
                
            fs_str = fmt_size(f.get("filesize") or f.get("filesize_approx"))
            tbr = f.get("tbr", 0)
            tbr_str = f"{tbr} Kbps" if tbr else ""
            
            label = f"{fid} - {res}\n{fs_str} {tbr_str}\n{ext.upper()} ({vcodec} {acodec})".strip()
            item = ft.Radio(value=fid, label=label)
            
            if vcodec != "none" and acodec != "none":
                suggested.append(item)
            elif vcodec != "none":
                video_only.append(item)
            elif acodec != "none":
                audio_only.append(item)
                
        rg_sug = ft.RadioGroup(content=ft.Column(suggested))
        rg_vid = ft.RadioGroup(content=ft.Column(video_only))
        rg_aud = ft.RadioGroup(content=ft.Column(audio_only))
        
        def confirm_custom(e):
            try:
                dlg.open = False
                page.update()
                
                s_id = rg_sug.value
                v_id = rg_vid.value
                a_id = rg_aud.value
                
                if s_id:
                    fmt_str = s_id
                elif v_id and a_id:
                    fmt_str = f"{v_id}+{a_id}"
                elif v_id:
                    fmt_str = v_id
                elif a_id:
                    fmt_str = a_id
                else:
                    show_toast("Pilih format terlebih dahulu!")
                    return
                    
                task_id = str(uuid.uuid4())
                container = "mp4"
                args = (
                    task_id,
                    url_input.value.strip(),
                    "video_audio", 
                    download_config["audio_format"],
                    "best",
                    f"override:{fmt_str}", 
                    "best",
                    container,
                    chip_subs.selected,
                    chip_subs.selected,
                    download_config["subs_lang"],
                    chip_thumb.selected,
                    chip_playlist.selected,
                    get_full_config().get("output_path", DEFAULT_OUTPUT_DIR),
                    ""
                )
                
                title = "Video"
                thumb_url = ""
                if app_state.get("current_video_info"):
                    title = app_state["current_video_info"].get("title") or "Video"
                    thumb_url = app_state["current_video_info"].get("thumbnail") or ""
                    
                create_task_card(task_id, title, thumb_url)
                switch_view("tasks")
                
                threading.Thread(target=download_video_logic, args=args, daemon=True).start()
            except Exception as ex:
                show_toast(f"Error kustom: {ex}")

        dlg = ft.AlertDialog(
            title=ft.Row([ft.Text("Format selection", weight="bold", color=ft.Colors.ON_SURFACE), ft.TextButton("Unduh", on_click=confirm_custom)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            content=ft.Column([
                ft.Text("Suggested", weight="bold", color=ft.Colors.PRIMARY, visible=bool(suggested)),
                ft.Container(content=rg_sug, padding=10, border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT), border_radius=12, visible=bool(suggested)),
                ft.Text("Video", weight="bold", color=ft.Colors.PRIMARY, visible=bool(video_only)),
                ft.Container(content=rg_vid, padding=10, border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT), border_radius=12, visible=bool(video_only)),
                ft.Text("Audio", weight="bold", color=ft.Colors.PRIMARY, visible=bool(audio_only)),
                ft.Container(content=rg_aud, padding=10, border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT), border_radius=12, visible=bool(audio_only)),
            ], scroll=ft.ScrollMode.HIDDEN, height=450),
            actions=[
                ft.TextButton("Batalkan", on_click=lambda e: setattr(dlg, 'open', False) or page.update()),
            ]
        )
        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    def start_download_from_bs(e):
        try:
            bs.open = False
            page.update()
            
            if not url_input.value:
                show_toast("Harap isi tautan video terlebih dahulu!")
                return

            is_custom = (download_config["format_mode"] == "custom")
            
            if is_custom:
                if not app_state.get("current_video_info"):
                    show_toast("Harap tunggu info video selesai dimuat... ⏳")
                    return
                open_format_selection_dialog(app_state["current_video_info"])
                return

            task_id = str(uuid.uuid4())
            is_audio = (download_config["type"] == "audio")
            mode = "audio_only" if is_audio else "video_audio"
            audio_fmt = download_config["convert_audio"] if download_config["convert_audio"] != "none" else download_config["audio_format"]
            res = download_config["video_res"]
            vcodec = "h264" if download_config["video_preset"] == "lawas" else "best"
            container = "mp4"

            args = (
                task_id,
                url_input.value.strip(),
                mode,
                audio_fmt,
                res,
                vcodec,
                "best",
                container,
                download_config["download_subs"],
                download_config["download_subs"],
                download_config["subs_lang"],
                download_config["embed_thumb"],
                download_config["download_playlist"],
                get_full_config().get("output_path", DEFAULT_OUTPUT_DIR),
                ""
            )
            
            title = "Video"
            thumb_url = ""
            if app_state.get("current_video_info"):
                title = app_state["current_video_info"].get("title") or "Video"
                thumb_url = app_state["current_video_info"].get("thumbnail") or ""
                
            create_task_card(task_id, title, thumb_url)
            switch_view("tasks")
            
            threading.Thread(target=download_video_logic, args=args, daemon=True).start()
        except Exception as ex:
            show_toast(f"Error start: {ex}")

    bs = ft.BottomSheet(
        ft.Container(
            padding=ft.Padding(16, 12, 16, 24),
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            border_radius=ft.BorderRadius(top_left=24, top_right=24, bottom_left=0, bottom_right=0),
            content=ft.Column([
                ft.Container(
                    content=ft.Icon(ft.Icons.DONE_ALL, size=24, color=ft.Colors.ON_SURFACE_VARIANT),
                    alignment=ft.Alignment(0, 0)
                ),
                ft.Container(
                    content=ft.Text("Konfigurasikan sebelum unduh", size=20, color=ft.Colors.ON_SURFACE, text_align=ft.TextAlign.CENTER),
                    alignment=ft.Alignment(0, 0),
                    margin=ft.Margin(0, 8, 0, 4)
                ),
                ft.Container(
                    content=ft.Text("Sesuaikan unduhan ini", size=13, color=ft.Colors.ON_SURFACE_VARIANT, text_align=ft.TextAlign.CENTER),
                    alignment=ft.Alignment(0, 0),
                    margin=ft.Margin(0, 0, 0, 16)
                ),
                ft.Text("Jenis pengunduhan", size=13, color=ft.Colors.PRIMARY),
                type_segmented,
                ft.Container(height=4),
                ft.Text("Pilihan format", size=13, color=ft.Colors.PRIMARY),
                format_mode_segmented,
                ft.Container(height=4),
                text_pref,
                pref_single_row,
                ft.Container(height=4),
                ft.Text("Pengaturan tambahan", size=13, color=ft.Colors.PRIMARY),
                ft.Row([btn_playlist, btn_subs, btn_thumb], scroll=ft.ScrollMode.HIDDEN, spacing=8),
                ft.Container(height=16),
                ft.Row([
                    ft.OutlinedButton("Batalkan", icon=ft.Icons.CANCEL_OUTLINED, on_click=lambda e: setattr(bs, 'open', False) or page.update(), style=ft.ButtonStyle(color=ft.Colors.ON_SURFACE_VARIANT)),
                    ft.FilledButton("Unduh", icon=ft.Icons.DOWNLOAD_ROUNDED, on_click=start_download_from_bs, expand=True)
                ])
            ], tight=True)
        ),
        scrollable=True,
        show_drag_handle=True
    )
    page.overlay.append(bs)

    def open_download_modal(e):
        update_pref_row()
        bs.open = True
        page.update()

    fab_column = ft.Column([
        ft.FloatingActionButton(icon=ft.Icons.CONTENT_PASTE_ROUNDED, on_click=paste_url_action, bgcolor=ft.Colors.SECONDARY_CONTAINER, shape=ft.RoundedRectangleBorder(radius=16)),
        ft.FloatingActionButton(icon=ft.Icons.DOWNLOAD_ROUNDED, on_click=open_download_modal, bgcolor=ft.Colors.PRIMARY_CONTAINER, shape=ft.RoundedRectangleBorder(radius=16))
    ], alignment=ft.MainAxisAlignment.END, horizontal_alignment=ft.CrossAxisAlignment.END, spacing=16)

    # ===========================================================================
    # 6. TASKS TAB (M3 CARDS)
    # ===========================================================================
    tasks_empty_placeholder = ft.Container(
        content=ft.Column([
            ft.Icon(ft.Icons.DOWNLOAD_DONE_ROUNDED, size=72, color=ft.Colors.OUTLINE),
            ft.Text("Belum ada tugas", size=18, weight="bold", color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Text("Tugas unduhan akan muncul di sini.", size=13, color=ft.Colors.ON_SURFACE_VARIANT)
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        alignment=ft.Alignment(0, 0),
        padding=60
    )

    tasks_list_view = ft.ListView(expand=True, spacing=12, controls=[tasks_empty_placeholder])

    def stop_task(task_id):
        if task_id in download_state:
            download_state[task_id]["is_cancelled"] = True
            show_toast(f"Membatalkan tugas...")

    def create_task_card(task_id, title, thumb_url):
        pb = ft.ProgressBar(value=0, color=ft.Colors.PRIMARY, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, height=6)
        pt = ft.Text("Status: Memulai...", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        st = ft.Text("", size=11, color=ft.Colors.ON_SURFACE_VARIANT)
        cancel_btn = ft.IconButton(ft.Icons.CANCEL_OUTLINED, icon_color=ft.Colors.ERROR, on_click=lambda e: stop_task(task_id))
        
        thumb = ft.Image(src=thumb_url, width=72, height=72, fit="cover", border_radius=12) if thumb_url else ft.Icon(ft.Icons.VIDEO_FILE, size=40, color=ft.Colors.ON_SURFACE_VARIANT)
        
        card = ft.Container(
            content=ft.Row([
                ft.Container(content=thumb, width=72, height=72, border_radius=12, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, alignment=ft.Alignment(0, 0)),
                ft.Column([
                    ft.Text(title, weight="bold", size=14, color=ft.Colors.ON_SURFACE, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    pb,
                    ft.Row([pt, st], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
                ], expand=True, spacing=6),
                cancel_btn
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.START),
            padding=16,
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border_radius=20
        )
        
        app_state["tasks"][task_id] = {
            "card": card, "progress_bar": pb, "progress_text": pt, "stats_text": st, "cancel_btn": cancel_btn
        }
        
        if tasks_empty_placeholder in tasks_list_view.controls:
            tasks_list_view.controls.remove(tasks_empty_placeholder)
            
        tasks_list_view.controls.insert(0, card)
        page.update()

    active_task_filter = ["Semua"]
    def set_task_filter(filter_name):
        active_task_filter[0] = filter_name
        chip_all.selected = (filter_name == "Semua")
        chip_running.selected = (filter_name == "Berjalan")
        chip_canceled.selected = (filter_name == "Dibatalkan")
        chip_finished.selected = (filter_name == "Selesai")
        page.update()

    chip_all = ft.Chip(label=ft.Text("Semua"), selected=True, on_click=lambda e: set_task_filter("Semua"))
    chip_running = ft.Chip(label=ft.Text("Berjalan"), selected=False, on_click=lambda e: set_task_filter("Berjalan"))
    chip_canceled = ft.Chip(label=ft.Text("Dibatalkan"), selected=False, on_click=lambda e: set_task_filter("Dibatalkan"))
    chip_finished = ft.Chip(label=ft.Text("Selesai"), selected=False, on_click=lambda e: set_task_filter("Selesai"))

    tasks_view = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Text("Tugas", size=32, weight="w900", color=ft.Colors.ON_SURFACE),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Row([chip_all, chip_running, chip_canceled, chip_finished], scroll=ft.ScrollMode.HIDDEN, spacing=8),
            ft.Container(height=8),
            tasks_list_view
        ], expand=True),
        expand=True, padding=ft.Padding(16, 0, 16, 0)
    )

    # ===========================================================================
    # 7. LOG CONSOLE (M3)
    # ===========================================================================
    log_text = ft.Text(size=12, font_family="Consolas", selectable=True, color=ft.Colors.ON_SURFACE)
    log_view_container = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda e: switch_view("home")),
                ft.Text("Log Console", size=24, weight="w900", color=ft.Colors.ON_SURFACE)
            ], alignment=ft.MainAxisAlignment.START),
            ft.Container(
                content=ft.ListView(controls=[log_text], auto_scroll=True, expand=True),
                expand=True,
                bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
                border_radius=16,
                padding=16
            )
        ], expand=True),
        expand=True, padding=ft.Padding(16, 0, 16, 16)
    )

    # ===========================================================================
    # 8. SETTINGS VIEW (M3 FULL PAGE)
    # ===========================================================================
    lokasi_unduhan_subtitle = ft.Text(cfg_init.get("output_path", DEFAULT_OUTPUT_DIR), color=ft.Colors.ON_SURFACE_VARIANT)

    async def on_folder_click(e):
        if is_android():
            show_toast("Lokasi tidak dapat diubah di Android")
            return
            
        # Gunakan Tkinter khusus di Windows untuk menghindari bug FilePicker Flet
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.attributes('-topmost', True)
        root.withdraw()
        path = filedialog.askdirectory(parent=root, initialdir=cfg_init.get("output_path", ""))
        root.destroy()
        
        if path:
            save_full_config({"output_path": path})
            cfg_init["output_path"] = path
            lokasi_unduhan_subtitle.value = path
            lokasi_unduhan_subtitle.update()
            show_toast(f"Lokasi unduhan diubah:\n{path}")
            
    settings_view_container = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda e: switch_view("home")),
                ft.Text("Pengaturan", size=24, weight="w900", color=ft.Colors.ON_SURFACE)
            ]),
            ft.ListView([
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.DARK_MODE, color=ft.Colors.PRIMARY),
                    title=ft.Text("Tema Gelap", weight="bold"),
                    subtitle=ft.Text("Tampilan antarmuka", color=ft.Colors.ON_SURFACE_VARIANT),
                    trailing=ft.Switch(
                        value=(page.theme_mode == ft.ThemeMode.DARK),
                        on_change=lambda e: setattr(page, 'theme_mode', ft.ThemeMode.DARK if e.control.value else ft.ThemeMode.LIGHT) or page.update() or save_full_config({"theme": "dark" if e.control.value else "light"}),
                        active_color=ft.Colors.PRIMARY
                    )
                ),
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.FOLDER_ROUNDED, color=ft.Colors.PRIMARY),
                    title=ft.Text("Lokasi Unduhan", weight="bold"),
                    subtitle=lokasi_unduhan_subtitle,
                    on_click=on_folder_click
                ),
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.INFO_ROUNDED, color=ft.Colors.PRIMARY),
                    title=ft.Text("Tentang Mavdown", weight="bold"),
                    subtitle=ft.Text("Versi 1.0 (Material 3 Native)", color=ft.Colors.ON_SURFACE_VARIANT)
                )
            ], expand=True)
        ], expand=True),
        expand=True, padding=ft.Padding(16, 0, 16, 16)
    )

    # ===========================================================================
    # 9. QUEUE PROCESSING & VIEW SWITCHER
    # ===========================================================================
    def switch_view(target: str):
        current_view[0] = target
        if target == "home":
            main_container.content = home_view
            page.floating_action_button = fab_column
            if page.navigation_bar:
                page.navigation_bar.visible = True
                page.navigation_bar.selected_index = 0
        elif target == "tasks":
            main_container.content = tasks_view
            page.floating_action_button = None
            if page.navigation_bar:
                page.navigation_bar.visible = True
                page.navigation_bar.selected_index = 1
        elif target == "log":
            main_container.content = log_view_container
            page.floating_action_button = None
            if page.navigation_bar: page.navigation_bar.visible = False
        elif target == "settings":
            main_container.content = settings_view_container
            page.floating_action_button = None
            if page.navigation_bar: page.navigation_bar.visible = False
        page.update()

    def on_pubsub_message(payload):
        if payload.get("type") != "batch":
            return
            
        updated = False
        for m in payload.get("messages", []):
            msg_type = m.get("type")
            t_id = m.get("task_id")
            
            if msg_type == "log":
                log_text.value = (log_text.value or "") + m.get("text", "")
                if len(log_text.value) > 30000:
                    log_text.value = log_text.value[-20000:]
                updated = True
            
            elif msg_type == "progress" and t_id in app_state["tasks"]:
                c = app_state["tasks"][t_id]
                c["progress_bar"].value = m.get("value", 0)
                
                part = m.get("part", "")
                prefix = f"[{part}] " if part else ""
                c["progress_text"].value = f"{prefix}{m.get('text', '')}"
                
                speed = m.get("speed", "")
                eta = m.get("eta", "")
                if speed and eta:
                    c["stats_text"].value = f"{speed} | ETA: {eta}"
                updated = True
                
            elif msg_type == "download_error" and t_id in app_state["tasks"]:
                c = app_state["tasks"][t_id]
                c["progress_bar"].color = ft.Colors.RED
                c["progress_text"].value = "Gagal"
                c["stats_text"].value = "Terjadi kesalahan."
                c["cancel_btn"].visible = False
                updated = True

            elif msg_type == "download_finish" and t_id in app_state["tasks"]:
                c = app_state["tasks"][t_id]
                c["progress_bar"].value = 1.0
                c["progress_bar"].color = ft.Colors.GREEN
                c["progress_text"].value = "Selesai!"
                c["stats_text"].value = "Tugas rampung."
                c["cancel_btn"].visible = False
                updated = True
                
        if updated:
            page.update()

    page.pubsub.subscribe(on_pubsub_message)

    def process_queue():
        while True:
            try:
                # Blokir sebentar menunggu pesan
                msg = ui_queue.get(timeout=0.1)
                msgs = [msg]
                
                # Kuras pesan agar terkirim dalam 1 batch
                while not ui_queue.empty():
                    try:
                        msgs.append(ui_queue.get_nowait())
                    except:
                        break
                        
                # Kirim ke UI thread Flet lewat pubsub
                page.pubsub.send_all({"type": "batch", "messages": msgs})
                
                # Jeda tipis agar tak membanjiri pubsub
                time.sleep(0.05)
                
            except Exception:
                pass

    threading.Thread(target=process_queue, daemon=True).start()

    page.navigation_bar = ft.NavigationBar(
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.HOME_OUTLINED, selected_icon=ft.Icons.HOME_ROUNDED, label="Home"),
            ft.NavigationBarDestination(icon=ft.Icons.DOWNLOAD_OUTLINED, selected_icon=ft.Icons.DOWNLOAD_ROUNDED, label="Tugas"),
        ],
        on_change=lambda e: switch_view("home" if e.control.selected_index == 0 else "tasks"),
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW
    )
    
    page.add(main_container)
    switch_view("home")
    update_pref_row()
