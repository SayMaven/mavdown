"""
Mavdown Core Engine Daemon & CLI Interface (mav_core.py)
Menyediakan antarmuka JSON-RPC / IPC headless untuk C# WPF / WinUI 3 Frontend,
serta antarmuka baris perintah (CLI) untuk otomatisasi.
Sesuai panduan arsitektur AGENTS.md (Strict No-Emoji Policy).
"""

import os
import sys
import json
import time
import queue
import base64
import argparse
import threading
import tempfile
import traceback
import io
from PIL import Image

# Import modul internal Mavdown
import config
from config import (
    DEFAULT_OUTPUT_DIR, load_config, load_browser_cookie,
    load_proxy, save_proxy, load_organize_by_platform, save_organize_by_platform,
    load_clipboard_monitor, save_clipboard_monitor,
    load_pixiv_session, save_pixiv_session,
    load_ytdlp_channel, save_ytdlp_channel, is_aria2_available,
    save_config, _read_raw_config,
    YT_DLP_PATH, ARIA2_PATH, FFMPEG_PATH, FFPROBE_PATH, NODE_PATH
)
from engines.router import detect_platform, resolve_fast_info, resolve_service_output_dir
from engines.base import sanitize_filename, format_bytes, format_time
import history
from history import get_history_entries, delete_history_entry, clear_all_history, add_history_entry
import downloader
from downloader import (
    get_video_info, download_video_logic,
    stop_current_process, request_abort, reset_abort, is_abort_requested,
    update_ytdlp_logic, get_local_ytdlp_version
)

# Konfigurasi stdin/stdout agar selalu UTF-8 di Windows
if sys.platform == "win32":
    try:
        sys.stdin.reconfigure(encoding='utf-8', errors='replace')
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Output buffer lock untuk thread safety stdout
_stdout_lock = threading.Lock()
_daemon_running = True
_active_task_thread = None
_latest_inspected_meta = None
_latest_download_options = {}

def emit_json(payload: dict):
    """Mengirim pesan terstruktur JSON satu baris ke sys.stdout secara thread-safe."""
    try:
        data_str = json.dumps(payload, ensure_ascii=False)
        with _stdout_lock:
            sys.stdout.write(data_str + "\n")
            sys.stdout.flush()
    except Exception as e:
        sys.stderr.write(f"[mav_core error] Emit failed: {e}\n")
        sys.stderr.flush()

def _pump_ui_queue():
    """Background consumer yang membaca downloader.ui_queue dan mengubahnya menjadi event JSON."""
    global _daemon_running, _latest_inspected_meta
    temp_dir = os.path.join(tempfile.gettempdir(), "mavdown_cache")
    try:
        os.makedirs(temp_dir, exist_ok=True)
    except Exception:
        pass

    while _daemon_running:
        try:
            msg = downloader.ui_queue.get(timeout=0.2)
        except queue.Empty:
            continue
        except Exception:
            break

        if not msg or not isinstance(msg, dict):
            continue

        msg_type = msg.get("type", "")

        if msg_type == "log":
            emit_json({
                "event": "log",
                "text": msg.get("text", "")
            })

        elif msg_type == "progress":
            emit_json({
                "event": "progress",
                "value": msg.get("value", 0.0),
                "text": msg.get("text", ""),
                "speed": msg.get("speed", ""),
                "eta": msg.get("eta", ""),
                "size_dl": msg.get("size_dl", ""),
                "size_total": msg.get("size_total", "")
            })

        elif msg_type == "info_title":
            emit_json({
                "event": "info_title",
                "title": msg.get("title", "")
            })

        elif msg_type == "info_data":
            meta = msg.get("data", {})
            if isinstance(meta, dict):
                url_target = meta.get("webpage_url") or meta.get("url") or ""
                if not meta.get("platform"):
                    p_detected = detect_platform(url_target) if url_target else ""
                    meta["platform"] = p_detected or meta.get("extractor") or "Web"

                if not meta.get("uploader"):
                    meta["uploader"] = meta.get("channel") or meta.get("author") or meta.get("uploader_id") or ""

                # Sinkronisasi tanggal postingan (upload_date <-> date_string)
                raw_up_date = str(meta.get("upload_date") or "").strip()
                raw_dt_str = str(meta.get("date_string") or "").strip()
                if raw_up_date and not raw_dt_str:
                    if len(raw_up_date) == 8 and raw_up_date.isdigit():
                        meta["date_string"] = f"{raw_up_date[6:8]}/{raw_up_date[4:6]}/{raw_up_date[0:4]}"
                elif raw_dt_str and not raw_up_date:
                    m_ds = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', raw_dt_str)
                    if m_ds:
                        meta["upload_date"] = f"{m_ds.group(3)}{int(m_ds.group(2)):02d}{int(m_ds.group(1)):02d}"

                if not meta.get("duration_string"):
                    dur = meta.get("duration", 0)
                    if isinstance(dur, (int, float)) and dur > 0:
                        m_total, s = divmod(int(dur), 60)
                        h, m = divmod(m_total, 60)
                        meta["duration_string"] = f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
                    elif isinstance(dur, str) and ":" in dur:
                        meta["duration_string"] = dur

                w = meta.get("width") or 0
                h = meta.get("height") or 0
                res_lbl = meta.get("resolution_label") or ""
                
                # Normalisasi label resolusi jika hanya berupa format dimensi mentah (misal: "720x1280")
                if not res_lbl or ('x' in str(res_lbl).lower() and not any(k in str(res_lbl).lower() for k in ('p', 'k', 'hd', 'fhd', 'qhd', 'uhd'))):
                    max_dim = max(w, h) if (w and h) else 0
                    min_dim = min(w, h) if (w and h) else 0
                    if max_dim >= 3840 or min_dim >= 2160:
                        meta["resolution_label"] = "4K UHD"
                    elif max_dim >= 2560 or min_dim >= 1440:
                        meta["resolution_label"] = "2K QHD"
                    elif max_dim >= 1920 or min_dim >= 1080:
                        meta["resolution_label"] = "1080p FHD"
                    elif max_dim >= 1280 or min_dim >= 720:
                        meta["resolution_label"] = "720p HD"
                    elif max_dim >= 480 or min_dim >= 480:
                        meta["resolution_label"] = "480p"
                    else:
                        meta["resolution_label"] = "HD"
                    res_lbl = meta["resolution_label"]

                is_slide = meta.get("is_slide", False)
                slide_count = meta.get("slide_count", 0)
                badges = []
                if is_slide:
                    if slide_count <= 1:
                        badges.append({"text": "Foto HD", "color": "#3B82F6"})
                        badges.append({"text": "HD Original", "color": "#10B981"})
                    else:
                        badges.append({"text": f"{slide_count} Foto", "color": "#3B82F6"})
                        badges.append({"text": "HD Slide", "color": "#10B981"})
                    if w and h:
                        badges.append({"text": f"{w}x{h}", "color": "#10B981"})
                    badges.append({"text": "JPEG HD", "color": "#8B5CF6"})
                    if meta.get("has_audio") or meta.get("audio_url"):
                        badges.append({"text": "Musik BGM", "color": "#EC4899"})
                else:
                    formats = meta.get("formats", [])
                    heights = set(f.get("height", 0) for f in formats if f.get("height"))
                    fps_vals = [f.get("fps", 0) for f in formats if f.get("fps")]
                    if h: heights.add(h)
                    if w: heights.add(w)
                    if meta.get("fps"): fps_vals.append(meta.get("fps"))

                    if res_lbl:
                        col = "#6366F1" if "720" in res_lbl else ("#3B82F6" if "1080" in res_lbl else ("#10B981" if "2K" in res_lbl else ("#EF4444" if "4K" in res_lbl else "#F59E0B")))
                        badges.append({"text": res_lbl, "color": col})
                    if w and h and res_lbl != f"{w}x{h}":
                        badges.append({"text": f"{w}x{h}", "color": "#10B981"})
                    max_fps = max(fps_vals, default=0)
                    if max_fps:
                        badges.append({"text": f"{max_fps} FPS", "color": "#3B82F6"})
                    codec = meta.get("codec") or meta.get("vcodec")
                    if codec and str(codec).lower() not in ("none", "unknown", ""):
                        badges.append({"text": str(codec).upper(), "color": "#8B5CF6"})
                    if not badges:
                        badges.append({"text": "Auto Stream", "color": "#4F46E5"})

                # Mencegah duplikasi badges dengan teks yang sama
                seen_badges = set()
                unique_badges = []
                for b in badges:
                    b_txt = b["text"].strip().lower()
                    if b_txt not in seen_badges:
                        seen_badges.add(b_txt)
                        unique_badges.append(b)

                meta["computed_badges"] = unique_badges

            _latest_inspected_meta = meta
            emit_json({
                "event": "info_data",
                "data": meta
            })

        elif msg_type == "info_thumb_data":
            # Selalu konversi raw bytes ke format standar JPEG menggunakan Pillow
            # agar WPF BitmapImage di Windows bisa memuat WebP, AVIF, HEIC tanpa error
            img_bytes = msg.get("image_data")
            thumb_path = ""
            b64_str = ""
            if img_bytes:
                try:
                    cache_file = os.path.join(temp_dir, f"thumb_{int(time.time() * 1000)}.jpg")
                    try:
                        with Image.open(io.BytesIO(img_bytes)) as pil_img:
                            pil_img.convert("RGB").save(cache_file, format="JPEG", quality=92)
                        with open(cache_file, "rb") as fc:
                            clean_bytes = fc.read()
                        thumb_path = cache_file
                        b64_str = base64.b64encode(clean_bytes).decode('ascii')
                    except Exception:
                        with open(cache_file, "wb") as f:
                            f.write(img_bytes)
                        thumb_path = cache_file
                        b64_str = base64.b64encode(img_bytes).decode('ascii')
                except Exception:
                    pass

            emit_json({
                "event": "info_thumb",
                "status": "ready",
                "path": thumb_path,
                "base64": b64_str
            })

        elif msg_type == "info_thumb":
            emit_json({
                "event": "info_thumb",
                "status": "placeholder",
                "text": msg.get("text", ""),
                "path": ""
            })

        elif msg_type == "download_finish":
            # Catat otomatis ke riwayat jika ada metadata
            try:
                _record_download_history()
            except Exception as e:
                emit_json({"event": "log", "text": f"[RIWAYAT ERROR] Gagal mencatat: {e}\n"})

            emit_json({
                "event": "download_finish",
                "status": "success"
            })

        elif msg_type == "download_error":
            emit_json({
                "event": "download_error",
                "message": msg.get("text", "Unduhan gagal.")
            })

def _record_download_history():
    """Mendeteksi file yang baru diunduh dan mencatatnya ke history.json."""
    global _latest_inspected_meta, _latest_download_options
    if not _latest_inspected_meta:
        return

    meta = _latest_inspected_meta
    custom_path = _latest_download_options.get("custom_path", "")
    base_dir = custom_path if custom_path else DEFAULT_OUTPUT_DIR
    organize = load_organize_by_platform()
    url = meta.get("url") or meta.get("webpage_url") or _latest_download_options.get("url", "")
    platform = meta.get("platform") or detect_platform(url)
    out_dir = resolve_service_output_dir(base_dir, url, organize_by_platform=organize)

    if not os.path.exists(out_dir):
        return

    # Cari file/folder terbaru di direktori output
    candidates = []
    for item in os.listdir(out_dir):
        fp = os.path.join(out_dir, item)
        if item.startswith('.') or item.endswith(('.temp', '.part', '.ytdl', '.aria2')):
            continue
        try:
            mtime = os.path.getmtime(fp)
            candidates.append((mtime, fp))
        except Exception:
            pass

    if not candidates:
        return

    candidates.sort(key=lambda x: x[0], reverse=True)
    newest_path = candidates[0][1]

    is_slide = meta.get("is_slide", False)
    media_fmt = "SLIDE" if (is_slide or os.path.isdir(newest_path)) else os.path.splitext(newest_path)[1].lstrip('.').upper()

    add_history_entry(
        title=meta.get("title", os.path.basename(newest_path)),
        platform=platform,
        file_path=newest_path,
        thumbnail=meta.get("thumbnail", ""),
        is_slide=is_slide,
        duration=str(meta.get("duration", "")),
        source_url=url,
        author=meta.get("uploader", ""),
        resolution=meta.get("resolution_label", ""),
        media_format=media_fmt,
        slide_count=meta.get("slide_count", 0)
    )

def handle_inspect(req: dict):
    """Menangani inspeksi metadata URL."""
    url = req.get("url", "").strip()
    share_text = req.get("share_text")
    cookie = req.get("cookie")
    if not cookie or cookie.lower() == "tidak ada":
        cookie = load_browser_cookie() or "Tidak Ada"
    req_id = req.get("id", "")

    if not url:
        emit_json({"event": "error", "id": req_id, "message": "URL tidak boleh kosong."})
        return

    def _worker():
        try:
            get_video_info(url, browser_cookie=cookie, share_text=share_text)
            emit_json({"event": "inspect_complete", "id": req_id, "url": url})
        except Exception as e:
            emit_json({"event": "inspect_error", "id": req_id, "error": str(e), "trace": traceback.format_exc()})

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

def handle_download(req: dict):
    """Menangani eksekusi unduhan media."""
    global _active_task_thread, _latest_download_options
    _latest_download_options = req
    req_id = req.get("id", "")
    url = req.get("url", "").strip()

    if not url:
        emit_json({"event": "error", "id": req_id, "message": "URL unduhan tidak boleh kosong."})
        return

    mode = req.get("mode", "video")
    audio_format = req.get("audio_format", "mp3")
    res = req.get("res", "best")
    vcodec = req.get("vcodec", "auto")
    acodec = req.get("acodec", "auto")
    container = req.get("container", "mp4")
    download_subs = req.get("download_subs", False)
    embed_subs = req.get("embed_subs", True)
    subs_lang = req.get("subs_lang", "id,en")
    embed_thumb = req.get("embed_thumb", True)
    use_aria2 = req.get("use_aria2", True)
    download_playlist = req.get("download_playlist", False)
    custom_path = req.get("custom_path", "")
    custom_cmd = req.get("custom_cmd", "")
    cookie = req.get("cookie")
    if not cookie or cookie.lower() == "tidak ada":
        cookie = load_browser_cookie() or "Tidak Ada"
    share_text = req.get("share_text", "")
    ugoira_format = req.get("ugoira_format", "mp4")

    def _worker():
        try:
            download_video_logic(
                url=url,
                mode=mode,
                audio_format=audio_format,
                res=res,
                vcodec=vcodec,
                acodec=acodec,
                container=container,
                download_subs=download_subs,
                embed_subs=embed_subs,
                subs_lang=subs_lang,
                embed_thumb=embed_thumb,
                use_aria2=use_aria2,
                download_playlist=download_playlist,
                custom_path=custom_path,
                custom_cmd=custom_cmd,
                browser_cookie=cookie,
                share_text=share_text,
                ugoira_format=ugoira_format
            )
        except Exception as e:
            emit_json({"event": "download_error", "id": req_id, "message": f"Terjadi kesalahan: {e}"})

    _active_task_thread = threading.Thread(target=_worker, daemon=True)
    _active_task_thread.start()
    emit_json({"event": "download_started", "id": req_id, "url": url})

def handle_cancel(req: dict):
    """Membatalkan proses unduhan yang sedang berjalan."""
    stop_current_process()
    emit_json({"event": "cancelled", "id": req.get("id", "")})

def handle_get_history(req: dict):
    """Mengambil daftar riwayat unduhan."""
    query = req.get("query") or req.get("search", "")
    limit = req.get("limit", 150)
    entries = get_history_entries(search=query, limit=limit)
    emit_json({"event": "history_list", "id": req.get("id", ""), "entries": entries})

def handle_delete_history(req: dict):
    """Menghapus entri riwayat tertentu."""
    entry_id = req.get("entry_id", "")
    delete_file = req.get("delete_file", False)
    success = delete_history_entry(entry_id, delete_file=delete_file)
    emit_json({"event": "history_deleted", "id": req.get("id", ""), "entry_id": entry_id, "success": success})

def handle_clear_history(req: dict):
    """Menghapus seluruh riwayat unduhan."""
    success = clear_all_history()
    emit_json({"event": "history_cleared", "id": req.get("id", ""), "success": success})

_cached_ytdlp_version = None
_cached_aria2_available = None

def get_cached_ytdlp_version():
    global _cached_ytdlp_version
    if _cached_ytdlp_version is None:
        _cached_ytdlp_version = get_local_ytdlp_version() or ""
    return _cached_ytdlp_version

def get_cached_aria2_available():
    global _cached_aria2_available
    if _cached_aria2_available is None:
        _cached_aria2_available = is_aria2_available()
    return _cached_aria2_available

def handle_get_config(req: dict):
    """Mengembalikan preferensi konfigurasi saat ini."""
    data = {
        "output_dir": load_config(),
        "browser_cookie": load_browser_cookie(),
        "proxy": load_proxy(),
        "clipboard_monitor": load_clipboard_monitor(),
        "organize_by_platform": load_organize_by_platform(),
        "pixiv_session": load_pixiv_session(),
        "has_pixiv_session": bool(load_pixiv_session()),
        "ytdlp_channel": load_ytdlp_channel(),
        "ytdlp_version": get_cached_ytdlp_version(),
        "is_aria2_available": get_cached_aria2_available(),
        "bin_ytdlp": YT_DLP_PATH,
        "bin_aria2": ARIA2_PATH,
        "bin_ffmpeg": FFMPEG_PATH,
        "bin_ffprobe": FFPROBE_PATH,
        "bin_node": NODE_PATH
    }
    emit_json({"event": "config_data", "id": req.get("id", ""), "config": data})

def handle_set_config(req: dict):
    """Menyimpan konfigurasi baru."""
    key = req.get("key")
    val = req.get("value")
    if key == "output_path" or key == "output_dir":
        save_config(path=str(val))
    elif key == "browser_cookie":
        save_config(browser_cookie=str(val))
    elif key == "proxy":
        save_proxy(str(val))
    elif key == "organize_by_platform":
        save_organize_by_platform(bool(val))
    elif key == "clipboard_monitor":
        save_clipboard_monitor(bool(val))
    elif key == "ytdlp_channel":
        save_ytdlp_channel(str(val))
    elif key == "pixiv_session":
        save_pixiv_session(str(val))
    elif key:
        # Generic config save
        raw = _read_raw_config()
        raw[key] = val
        from config import _write_raw_config
        _write_raw_config(raw)
    else:
        emit_json({"event": "error", "id": req.get("id", ""), "message": "Kunci konfigurasi tidak boleh kosong."})
        return

    emit_json({"event": "config_saved", "id": req.get("id", ""), "key": key, "value": val})

def handle_update_ytdlp(req: dict):
    """Menjalankan pembaruan biner yt-dlp secara background."""
    channel = req.get("channel", "stable")
    req_id = req.get("id", "")
    def _worker():
        try:
            update_ytdlp_logic(channel=channel)
            emit_json({"event": "update_complete", "id": req_id})
        except Exception as e:
            emit_json({"event": "update_error", "id": req_id, "error": str(e)})
    threading.Thread(target=_worker, daemon=True).start()

def handle_pixiv_login_browser(req: dict):
    """Membuka browser login Pixiv secara interaktif untuk menangkap cookie PHPSESSID."""
    from engines.pixiv import login_pixiv_via_browser, verify_pixiv_session
    req_id = req.get("id", "")

    def _status_cb(msg: str):
        emit_json({"event": "pixiv_login_status", "id": req_id, "status": msg})

    def _worker():
        try:
            ok, res = login_pixiv_via_browser(status_callback=_status_cb)
            if ok:
                save_pixiv_session(res)
                v_ok, v_res = verify_pixiv_session(res)
                user_name = v_res.get('name', 'User') if (v_ok and isinstance(v_res, dict)) else ''
                emit_json({
                    "event": "pixiv_login_complete",
                    "id": req_id,
                    "success": True,
                    "session": res,
                    "user_name": user_name
                })
            else:
                emit_json({
                    "event": "pixiv_login_complete",
                    "id": req_id,
                    "success": False,
                    "error": str(res)
                })
        except Exception as e:
            emit_json({
                "event": "pixiv_login_complete",
                "id": req_id,
                "success": False,
                "error": str(e)
            })

    threading.Thread(target=_worker, daemon=True).start()

def handle_verify_pixiv_session(req: dict):
    """Memverifikasi sesi Pixiv yang diberikan atau tersimpan."""
    from engines.pixiv import verify_pixiv_session
    req_id = req.get("id", "")
    session = req.get("session")
    if session is None:
        session = load_pixiv_session()
    def _worker():
        try:
            ok, res = verify_pixiv_session(session)
            user_name = res.get('name', 'User') if (ok and isinstance(res, dict)) else ''
            emit_json({
                "event": "pixiv_verify_result",
                "id": req_id,
                "valid": ok,
                "session": session,
                "user_name": user_name,
                "message": f"Terhubung sebagai {user_name}" if user_name else (res if isinstance(res, str) else "Sesi aktif")
            })
        except Exception as e:
            emit_json({
                "event": "pixiv_verify_result",
                "id": req_id,
                "valid": False,
                "session": session,
                "message": f"Gagal verifikasi: {e}"
            })
    threading.Thread(target=_worker, daemon=True).start()

def run_daemon():
    """Mode Daemon IPC: Mendengarkan perintah JSON-lines dari sys.stdin."""
    global _daemon_running

    # Mulai pump queue di background thread
    pump_thread = threading.Thread(target=_pump_ui_queue, daemon=True)
    pump_thread.start()

    # Beri tahu frontend bahwa engine telah aktif
    emit_json({
        "event": "ready",
        "version": "1.0.0",
        "platform": sys.platform,
        "pid": os.getpid()
    })

    while _daemon_running:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue

            try:
                req = json.loads(line)
            except json.JSONDecodeError as err:
                emit_json({"event": "error", "message": f"Format JSON tidak valid: {err}"})
                continue

            action = req.get("action", "").lower()
            if action == "inspect":
                handle_inspect(req)
            elif action == "download":
                handle_download(req)
            elif action == "cancel":
                handle_cancel(req)
            elif action == "get_history":
                handle_get_history(req)
            elif action == "delete_history":
                handle_delete_history(req)
            elif action == "clear_history":
                handle_clear_history(req)
            elif action == "get_config":
                handle_get_config(req)
            elif action == "set_config":
                handle_set_config(req)
            elif action == "update_ytdlp":
                handle_update_ytdlp(req)
            elif action == "pixiv_login_browser":
                handle_pixiv_login_browser(req)
            elif action == "verify_pixiv_session":
                handle_verify_pixiv_session(req)
            elif action == "detect_platform":
                url = req.get("url", "")
                emit_json({"event": "platform_detected", "id": req.get("id", ""), "platform": detect_platform(url)})
            elif action == "ping":
                emit_json({"event": "pong", "id": req.get("id", ""), "time": time.time()})
            elif action in ("exit", "quit"):
                emit_json({"event": "shutting_down"})
                _daemon_running = False
                break
            else:
                emit_json({"event": "error", "id": req.get("id", ""), "message": f"Aksi '{action}' tidak dikenal."})

        except KeyboardInterrupt:
            break
        except Exception as e:
            emit_json({"event": "fatal_error", "message": str(e)})

    _daemon_running = False

def run_cli(args):
    """Mode CLI sekali jalan (one-shot command)."""
    if args.inspect:
        url = args.inspect.strip()
        print(f"Menginspeksi URL: {url}...")
        platform = detect_platform(url)
        fast_info = resolve_fast_info(url)
        if fast_info:
            print(json.dumps(fast_info, indent=2, ensure_ascii=False))
        else:
            print("Fast engine tidak menghasilkan data, mencoba yt-dlp...")
            # Tangkap dari ui_queue
            def _drain():
                while True:
                    try:
                        m = downloader.ui_queue.get(timeout=3)
                        if m.get("type") == "info_data":
                            print(json.dumps(m.get("data", {}), indent=2, ensure_ascii=False))
                            break
                    except Exception:
                        break
            t = threading.Thread(target=_drain, daemon=True)
            t.start()
            get_video_info(url)
            t.join(timeout=15)

    elif args.history:
        entries = get_history_entries()
        print(f"Total Riwayat: {len(entries)} item.")
        for item in entries[:args.limit]:
            print(f"- [{item.get('platform', 'web').upper()}] {item.get('title')} ({item.get('timestamp')})")

    elif args.download:
        url = args.download.strip()
        print(f"Mengunduh URL: {url}...")
        pump_thread = threading.Thread(target=_pump_ui_queue, daemon=True)
        pump_thread.start()
        handle_download({"url": url, "mode": args.mode or "video", "container": args.container or "mp4"})
        if _active_task_thread:
            _active_task_thread.join()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mavdown Headless Core Daemon & CLI")
    parser.add_argument("--daemon", action="store_true", help="Jalankan sebagai IPC background daemon (JSON-lines)")
    parser.add_argument("--inspect", type=str, help="Inspeksi metadata dari URL")
    parser.add_argument("--download", type=str, help="Unduh media langsung dari URL")
    parser.add_argument("--mode", type=str, default="video", choices=["video", "audio"], help="Mode unduh")
    parser.add_argument("--container", type=str, default="mp4", help="Format container video/audio")
    parser.add_argument("--history", action="store_true", help="Tampilkan daftar riwayat unduhan")
    parser.add_argument("--limit", type=int, default=10, help="Batas jumlah riwayat yang ditampilkan")

    parsed_args = parser.parse_args()

    # Jika dipanggil tanpa argumen atau dengan flag --daemon, masuk ke mode daemon IPC
    if parsed_args.daemon or len(sys.argv) == 1:
        run_daemon()
    else:
        run_cli(parsed_args)
