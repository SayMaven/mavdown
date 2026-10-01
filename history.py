import os
import re
import json
import time
import uuid
import threading
import subprocess
import requests
from datetime import datetime
from PIL import Image
from config import HISTORY_FILE, FFMPEG_PATH, FFPROBE_PATH

_history_lock = threading.Lock()
THUMBNAILS_DIR = os.path.join(os.path.dirname(HISTORY_FILE), "thumbnails")
try:
    os.makedirs(THUMBNAILS_DIR, exist_ok=True)
except Exception:
    pass

def ensure_entry_thumbnail(entry: dict) -> str:
    """
    Memastikan thumbnail lokal tersedia untuk entri riwayat.
    Mendukung ekstraksi otomatis dari file gambar, slide album, frame video (FFmpeg),
    atau pengunduhan dari URL thumbnail asli.
    Mengembalikan path absolut file gambar thumbnail lokal (.jpg) jika sukses.
    """
    eid = entry.get("id")
    if not eid:
        return ""

    target_thumb = os.path.join(THUMBNAILS_DIR, f"{eid}.jpg")
    if os.path.isfile(target_thumb) and os.path.getsize(target_thumb) > 500:
        return target_thumb

    fpath = entry.get("file_path", "")
    thumb_url = entry.get("thumbnail", "")

    # 1. Sumber: File gambar lokal tunggal
    if fpath and os.path.isfile(fpath):
        ext = os.path.splitext(fpath)[1].lower()
        if ext in ('.jpg', '.jpeg', '.png', '.webp', '.bmp'):
            try:
                with Image.open(fpath) as im:
                    im = im.convert('RGB')
                    im.thumbnail((240, 144), Image.Resampling.LANCZOS)
                    im.save(target_thumb, "JPEG", quality=85)
                if os.path.isfile(target_thumb):
                    return target_thumb
            except Exception:
                pass

        # 2. Sumber: File video lokal (ekstrak frame detik ke-1 dengan FFmpeg)
        elif ext in ('.mp4', '.mkv', '.webm', '.mov', '.avi', '.flv'):
            if os.path.exists(FFMPEG_PATH):
                try:
                    cmd = [
                        FFMPEG_PATH, "-y",
                        "-ss", "00:00:01",
                        "-i", fpath,
                        "-vframes", "1",
                        "-vf", "scale=240:-2",
                        "-q:v", "2",
                        target_thumb
                    ]
                    startupinfo = None
                    if os.name == 'nt':
                        startupinfo = subprocess.STARTUPINFO()
                        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        startupinfo.wShowWindow = subprocess.SW_HIDE
                    subprocess.run(cmd, capture_output=True, timeout=8, startupinfo=startupinfo)
                    if os.path.isfile(target_thumb) and os.path.getsize(target_thumb) > 500:
                        return target_thumb
                except Exception:
                    pass

    # 3. Sumber: Folder album slide lokal (ambil foto pertama)
    if fpath and os.path.isdir(fpath):
        try:
            for item in sorted(os.listdir(fpath)):
                if item.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    first_img = os.path.join(fpath, item)
                    with Image.open(first_img) as im:
                        im = im.convert('RGB')
                        im.thumbnail((240, 144), Image.Resampling.LANCZOS)
                        im.save(target_thumb, "JPEG", quality=85)
                    if os.path.isfile(target_thumb):
                        return target_thumb
        except Exception:
            pass

    # 4. Sumber: Unduh dari URL thumbnail asli
    if thumb_url and thumb_url.startswith(('http://', 'https://')):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
            }
            r = requests.get(thumb_url, headers=headers, timeout=10)
            if r.status_code == 200 and len(r.content) > 500:
                with open(target_thumb, 'wb') as tf:
                    tf.write(r.content)
                # Normalisasi ke format JPEG standar
                try:
                    with Image.open(target_thumb) as im:
                        im = im.convert('RGB')
                        im.thumbnail((240, 144), Image.Resampling.LANCZOS)
                        im.save(target_thumb, "JPEG", quality=85)
                except Exception:
                    pass
                if os.path.isfile(target_thumb):
                    return target_thumb
        except Exception:
            pass

    return ""

def _extract_media_info_from_disk(fpath: str) -> dict:
    """
    Ekstrak metadata teknis (resolusi, kreator/artis, durasi, format)
    langsung dari file lokal menggunakan ffprobe atau PIL.
    """
    meta = {}
    if not fpath or not os.path.exists(fpath):
        return meta

    try:
        if os.path.isfile(fpath):
            ext = os.path.splitext(fpath)[1].lower()
            if ext in ('.jpg', '.jpeg', '.png', '.webp', '.bmp'):
                meta["media_format"] = ext.lstrip('.').upper()
                try:
                    with Image.open(fpath) as im:
                        meta["resolution"] = f"{im.width}x{im.height}"
                except Exception:
                    pass
            elif ext in ('.mp4', '.mkv', '.webm', '.mov', '.avi', '.flv', '.mp3', '.m4a', '.flac', '.opus', '.wav'):
                meta["media_format"] = ext.lstrip('.').upper()
                if os.path.isfile(FFPROBE_PATH):
                    cmd = [
                        FFPROBE_PATH, "-v", "error",
                        "-show_entries", "stream=width,height:format=duration:format_tags=artist,uploader,channel",
                        "-of", "json", fpath
                    ]
                    startupinfo = None
                    if os.name == 'nt':
                        startupinfo = subprocess.STARTUPINFO()
                        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        startupinfo.wShowWindow = subprocess.SW_HIDE
                    res = subprocess.run(cmd, capture_output=True, text=True, startupinfo=startupinfo, timeout=6, encoding='utf-8', errors='ignore')
                    if res.returncode == 0 and res.stdout.strip():
                        info = json.loads(res.stdout)
                        streams = info.get("streams", [])
                        for s in streams:
                            w = s.get("width")
                            h = s.get("height")
                            if w and h:
                                if h >= 2160 or w >= 3840:
                                    meta["resolution"] = f"4K UHD ({w}x{h})"
                                elif h >= 1440 or w >= 2560:
                                    meta["resolution"] = f"2K QHD ({w}x{h})"
                                elif h >= 1080 or w >= 1920:
                                    meta["resolution"] = f"1080p FHD ({w}x{h})"
                                elif h >= 720 or w >= 1280:
                                    meta["resolution"] = f"720p HD ({w}x{h})"
                                else:
                                    meta["resolution"] = f"{w}x{h}"
                                break
                        dur_sec = info.get("format", {}).get("duration")
                        if dur_sec:
                            try:
                                d_val = float(dur_sec)
                                m, s = divmod(int(d_val), 60)
                                h, m = divmod(m, 60)
                                meta["duration"] = f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
                            except Exception:
                                pass
                        tags = info.get("format", {}).get("tags", {})
                        cand_artist = tags.get("artist") or tags.get("uploader") or tags.get("channel") or ""
                        if cand_artist and len(cand_artist) < 50:
                            meta["author"] = cand_artist
        elif os.path.isdir(fpath):
            meta["media_format"] = "SLIDE"
            imgs = [f for f in os.listdir(fpath) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
            if imgs:
                meta["slide_count"] = len(imgs)
                try:
                    with Image.open(os.path.join(fpath, imgs[0])) as im:
                        meta["resolution"] = f"{im.width}x{im.height}"
                except Exception:
                    pass
    except Exception:
        pass

    return meta

def _normalize_entry(entry: dict) -> bool:
    """Normalisasi metadata entri riwayat (memperbaiki platform YouTube/Bilibili dll yang tertulis Web)."""
    modified = False
    url = (entry.get("source_url") or "").lower()
    plat = entry.get("platform", "")

    # Perbaiki platform yang sebelumnya salah tercatat sebagai 'Web' atau kosong
    if not plat or plat.lower() in ("web", "generic", "fast engine"):
        if "youtube.com" in url or "youtu.be" in url:
            entry["platform"] = "YouTube"
            modified = True
        elif "bilibili.com" in url or "b23.tv" in url:
            entry["platform"] = "Bilibili"
            modified = True
        elif "tiktok.com" in url:
            entry["platform"] = "TikTok"
            modified = True
        elif "douyin.com" in url:
            entry["platform"] = "Douyin"
            modified = True
        elif "instagram.com" in url:
            entry["platform"] = "Instagram"
            modified = True
        elif "pinterest.com" in url or "pin.it" in url:
            entry["platform"] = "Pinterest"
            modified = True
        elif "twitter.com" in url or "x.com" in url:
            entry["platform"] = "Twitter / X"
            modified = True
        elif "facebook.com" in url or "fb.watch" in url:
            entry["platform"] = "Facebook"
            modified = True

    fpath = entry.get("file_path", "")

    # Ekstraksi format media jika belum ada
    if not entry.get("media_format"):
        if fpath:
            if os.path.isdir(fpath) or entry.get("is_slide"):
                entry["media_format"] = "SLIDE"
            else:
                ext = os.path.splitext(fpath)[1].lstrip('.').upper()
                entry["media_format"] = ext or "MEDIA"
            modified = True

    # Jika metadata teknis belum lengkap, gali dari file disk
    if fpath and (not entry.get("resolution") or not entry.get("author") or not entry.get("duration")):
        disk_meta = _extract_media_info_from_disk(fpath)
        for k, v in disk_meta.items():
            if v and not entry.get(k):
                entry[k] = v
                modified = True

    # Ekstraksi nama kreator cadangan dari nama file jika masih kosong
    if not entry.get("author"):
        bname = os.path.basename(fpath) if fpath else ""
        if " - " in bname:
            cand = bname.split(" - ")[0].strip()
            if cand and len(cand) < 40:
                entry["author"] = cand
                modified = True
        elif " - " in entry.get("title", ""):
            cand = entry["title"].split(" - ")[0].strip()
            if cand and len(cand) < 40:
                entry["author"] = cand
                modified = True

    # Pastikan thumbnail lokal dibuat
    local_thumb = ensure_entry_thumbnail(entry)
    if local_thumb and entry.get("local_thumbnail") != local_thumb:
        entry["local_thumbnail"] = local_thumb
        modified = True

    return modified

def _load_raw_history() -> list:
    """Muat daftar riwayat dari file JSON secara thread-safe dengan auto-healing metadata."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    needs_save = False
                    for item in data:
                        if isinstance(item, dict):
                            if _normalize_entry(item):
                                needs_save = True
                    if needs_save:
                        _save_raw_history(data)
                    return data
        except Exception:
            pass
    return []

def _save_raw_history(entries: list):
    """Simpan daftar riwayat ke file JSON secara atomik."""
    temp_file = HISTORY_FILE + ".tmp"
    try:
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
        try:
            os.replace(temp_file, HISTORY_FILE)
        except Exception:
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(entries, f, indent=2, ensure_ascii=False)
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
    except Exception as e:
        print(f"Error saving download history: {e}")
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass

def add_history_entry(
    title: str,
    platform: str,
    file_path: str,
    file_size: str = "",
    thumbnail: str = "",
    is_slide: bool = False,
    duration: str = "",
    source_url: str = "",
    author: str = "",
    resolution: str = "",
    media_format: str = "",
    slide_count: int = 0
) -> dict:
    """
    Menambahkan catatan riwayat unduhan baru lengkap dengan metadata terperinci.
    """
    with _history_lock:
        entries = _load_raw_history()

        # Dapatkan ukuran file dari disk jika tidak disuplai
        if not file_size and file_path and os.path.exists(file_path):
            try:
                if os.path.isfile(file_path):
                    bytes_val = os.path.getsize(file_path)
                    for unit in ['B', 'KB', 'MB', 'GB']:
                        if bytes_val < 1024.0:
                            file_size = f"{bytes_val:.1f} {unit}"
                            break
                        bytes_val /= 1024.0
                elif os.path.isdir(file_path):
                    total_bytes = sum(
                        os.path.getsize(os.path.join(root, f))
                        for root, _, files in os.walk(file_path) for f in files
                    )
                    file_size = f"{total_bytes / (1024*1024):.1f} MB"
            except Exception:
                file_size = ""

        # Deteksi format file jika belum ada
        if not media_format and file_path:
            if is_slide or os.path.isdir(file_path):
                media_format = "SLIDE"
            else:
                ext = os.path.splitext(file_path)[1].lstrip('.').upper()
                media_format = ext or "MEDIA"

        # Validasi platform dari URL jika masih default 'Web'
        url_low = (source_url or '').lower()
        if not platform or platform.lower() in ("web", "generic", "fast engine"):
            if "youtube.com" in url_low or "youtu.be" in url_low:
                platform = "YouTube"
            elif "bilibili.com" in url_low or "b23.tv" in url_low:
                platform = "Bilibili"
            elif "tiktok.com" in url_low:
                platform = "TikTok"
            elif "douyin.com" in url_low:
                platform = "Douyin"
            elif "pinterest.com" in url_low or "pin.it" in url_low:
                platform = "Pinterest"
            elif "instagram.com" in url_low:
                platform = "Instagram"
            elif "twitter.com" in url_low or "x.com" in url_low:
                platform = "Twitter / X"
            elif "facebook.com" in url_low or "fb.watch" in url_low:
                platform = "Facebook"

        if file_path and (not author or not resolution or not duration or not media_format):
            disk_meta = _extract_media_info_from_disk(file_path)
            if not author and disk_meta.get("author"):
                author = disk_meta["author"]
            if not resolution and disk_meta.get("resolution"):
                resolution = disk_meta["resolution"]
            if not duration and disk_meta.get("duration"):
                duration = disk_meta["duration"]
            if not media_format and disk_meta.get("media_format"):
                media_format = disk_meta["media_format"]
            if not slide_count and disk_meta.get("slide_count"):
                slide_count = disk_meta["slide_count"]

        now = datetime.now()
        eid = str(uuid.uuid4())[:8]

        entry = {
            "id": eid,
            "title": title or "Media Unduhan",
            "platform": platform or "Web",
            "author": author or "",
            "resolution": resolution or "",
            "media_format": media_format or "",
            "file_path": file_path or "",
            "file_size": file_size,
            "thumbnail": thumbnail or "",
            "is_slide": bool(is_slide),
            "slide_count": slide_count if slide_count else (1 if is_slide else 0),
            "duration": duration,
            "source_url": source_url or "",
            "timestamp": now.strftime("%d/%m/%Y %H:%M"),
            "unix_time": time.time(),
            "local_thumbnail": ""
        }

        # Buat thumbnail lokal seketika
        local_thumb = ensure_entry_thumbnail(entry)
        entry["local_thumbnail"] = local_thumb

        # Masukkan ke urutan paling atas
        entries.insert(0, entry)

        # Batasi riwayat maksimal 500 entri agar file tetap ringan
        if len(entries) > 500:
            entries = entries[:500]

        _save_raw_history(entries)
        return entry

def get_history_entries(search: str = "", limit: int = 150) -> list:
    """
    Mengambil daftar entri riwayat unduhan, opsional difilter dengan kata kunci pencarian.
    """
    with _history_lock:
        entries = _load_raw_history()

    if search:
        q = search.lower().strip()
        entries = [
            e for e in entries
            if q in e.get("title", "").lower()
            or q in e.get("platform", "").lower()
            or q in e.get("author", "").lower()
            or q in e.get("media_format", "").lower()
        ]

    return entries[:limit]

def delete_history_entry(entry_id: str) -> bool:
    """
    Menghapus satu entri riwayat beserta file thumbnail lokalnya.
    """
    with _history_lock:
        entries = _load_raw_history()
        new_entries = [e for e in entries if e.get("id") != entry_id]
        if len(new_entries) != len(entries):
            _save_raw_history(new_entries)
            thumb_path = os.path.join(THUMBNAILS_DIR, f"{entry_id}.jpg")
            if os.path.exists(thumb_path):
                try:
                    os.remove(thumb_path)
                except Exception:
                    pass
            return True
    return False

def clear_all_history() -> bool:
    """
    Mengosongkan seluruh riwayat unduhan beserta cache thumbnail.
    """
    with _history_lock:
        _save_raw_history([])
        try:
            if os.path.exists(THUMBNAILS_DIR):
                for f in os.listdir(THUMBNAILS_DIR):
                    try:
                        os.remove(os.path.join(THUMBNAILS_DIR, f))
                    except Exception:
                        pass
        except Exception:
            pass
        return True
