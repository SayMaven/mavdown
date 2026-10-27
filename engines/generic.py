import os
import io
import re
import html
import urllib.parse
import requests
from PIL import Image

from engines.base import (
    DEFAULT_HEADERS, sanitize_filename, stream_download_file,
    probe_media_stream, postprocess_video, normalize_image_to_jpeg,
    embed_thumbnail_to_media
)

IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.avif', '.ico', '.tiff')
VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.webm', '.mov', '.avi', '.flv', '.m4v', '.ts', '.3gp')
AUDIO_EXTENSIONS = ('.mp3', '.m4a', '.flac', '.wav', '.aac', '.ogg', '.opus', '.wma')

def is_generic_direct_media_url(url: str) -> bool:
    """Mengecek apakah URL merupakan tautan langsung ke file gambar, video, atau audio."""
    if not url or not url.startswith(('http://', 'https://')):
        return False
    try:
        parsed = urllib.parse.urlparse(url)
        clean_path = parsed.path.lower()
        if any(clean_path.endswith(ext) for ext in IMAGE_EXTENSIONS + VIDEO_EXTENSIONS + AUDIO_EXTENSIONS):
            return True
    except Exception:
        pass
    return False

def get_generic_info(url: str) -> dict:
    """
    Ekstraksi instan metadata media direct URL (Gambar, Video, atau Audio)
    tanpa jeda yt-dlp.
    """
    clean_url = (url or '').strip()
    try:
        parsed = urllib.parse.urlparse(clean_url)
        raw_path = parsed.path
        raw_filename = os.path.basename(raw_path)
        decoded_filename = urllib.parse.unquote(raw_filename)
        base_name, file_ext = os.path.splitext(decoded_filename)
        file_ext = file_ext.lower()

        clean_title = sanitize_filename(base_name) or 'Direct Media'

        # ── 1. KASUS GAMBAR DIRECT ──
        if file_ext in IMAGE_EXTENSIONS:
            w, h = 0, 0
            fmt_name = file_ext.lstrip('.').upper()
            img_bytes = None
            try:
                resp = requests.get(clean_url, headers=DEFAULT_HEADERS, timeout=10)
                if resp.status_code == 200 and len(resp.content) > 100:
                    img_bytes = resp.content
                    with Image.open(io.BytesIO(img_bytes)) as pil_im:
                        w, h = pil_im.size
                        fmt_name = (pil_im.format or fmt_name).upper()
            except Exception:
                pass

            res_label = f"{w}x{h}" if (w and h) else "HD Asli"

            return {
                'title': clean_title,
                'author': '',
                'clean_title': clean_title,
                'thumbnail': clean_url,
                'preview_url': clean_url,
                'thumbnails': [clean_url],
                'is_slide': True,         # Mode Foto / Slide Aktif Otomatis!
                'is_video': False,
                'slide_count': 1,
                'has_audio': False,
                'width': w or 1080,
                'height': h or 1080,
                'duration': 0,
                'duration_string': '1 Foto HD',
                'codec': fmt_name,
                'resolution_label': res_label,
                'platform': 'Generic',
                'url': clean_url,
                'webpage_url': clean_url,
                '_direct_image_bytes': img_bytes
            }

        # ── 2. KASUS VIDEO DIRECT ──
        if file_ext in VIDEO_EXTENSIONS:
            p_res = probe_media_stream(clean_url, timeout=7, headers=DEFAULT_HEADERS)
            w = (p_res or {}).get('width') or 1280
            h = (p_res or {}).get('height') or 720
            dur_float = float((p_res or {}).get('duration') or 0)
            dur_sec = int(dur_float)
            dur_str = f"{dur_sec // 60:02d}:{dur_sec % 60:02d}" if dur_sec else "-"
            codec = (p_res or {}).get('codec') or 'H264'
            res_label = (p_res or {}).get('resolution_label') or f"{h}p"

            return {
                'title': clean_title,
                'author': '',
                'clean_title': clean_title,
                'video_url': clean_url,
                'thumbnail': '',
                'thumbnails': [],
                'is_slide': False,        # Mode Video Aktif!
                'is_video': True,
                'slide_count': 0,
                'has_audio': True,
                'width': w,
                'height': h,
                'duration': dur_float,
                'duration_string': dur_str,
                'fps': (p_res or {}).get('fps') or 30,
                'codec': codec,
                'resolution_label': res_label,
                'platform': 'Generic',
                'url': clean_url,
                'webpage_url': clean_url
            }

        # ── 3. KASUS AUDIO DIRECT ──
        if file_ext in AUDIO_EXTENSIONS:
            p_res = probe_media_stream(clean_url, timeout=7, headers=DEFAULT_HEADERS)
            dur_float = float((p_res or {}).get('duration') or 0)
            dur_sec = int(dur_float)
            dur_str = f"{dur_sec // 60:02d}:{dur_sec % 60:02d}" if dur_sec else "-"
            codec = (p_res or {}).get('codec') or file_ext.lstrip('.').upper()

            return {
                'title': clean_title,
                'author': '',
                'clean_title': clean_title,
                'thumbnail': '',
                'thumbnails': [],
                'is_slide': False,
                'is_video': False,
                'slide_count': 0,
                'has_audio': True,
                'width': 0,
                'height': 0,
                'duration': dur_float,
                'duration_string': dur_str,
                'codec': codec,
                'resolution_label': 'Audio',
                'platform': 'Generic',
                'url': clean_url,
                'webpage_url': clean_url
            }

    except Exception:
        pass

    return None

def download_generic(url: str, output_dir: str, ui_queue=None, options=None, abort_checker=None) -> bool:
    """Unduh media langsung dari URL generic (Gambar, Video, atau Audio)."""
    clean_url = (url or '').strip()
    meta = get_generic_info(clean_url) or {}
    clean_title = meta.get('clean_title') or 'Direct Media'

    parsed = urllib.parse.urlparse(clean_url)
    _, file_ext = os.path.splitext(parsed.path)
    file_ext = file_ext.lower()

    # 1. KASUS GAMBAR
    if meta.get('is_slide') or file_ext in IMAGE_EXTENSIONS:
        ext = file_ext or '.jpg'
        final_img = os.path.join(output_dir, f"{clean_title}{ext}")
        if ui_queue:
            ui_queue.put({"type": "log", "text": f"[TIER 1] Mengunduh gambar generic ({ext})...\n"})

        ok = stream_download_file(clean_url, final_img, ui_queue, abort_checker, label="Unduh Foto HD")
        if not ok:
            return False

        if ext in ('.jpg', '.jpeg'):
            normalize_image_to_jpeg(final_img)

        if ui_queue:
            ui_queue.put({"type": "log", "text": f"\n--- UNDUHAN SUKSES (Foto Generic) ---\nTersimpan di: {final_img}\n"})
            ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
        return True

    # 2. KASUS VIDEO
    raw_container = options.get('container', 'auto') if options else 'auto'
    container = 'mp4' if raw_container in ('auto', 'best', '', None) else str(raw_container).lower()
    ext = f".{container}"

    raw_path = os.path.join(output_dir, f"{clean_title}_raw{file_ext or '.mp4'}")
    final_path = os.path.join(output_dir, f"{clean_title}{ext}")

    if ui_queue:
        ui_queue.put({"type": "log", "text": f"[TIER 1] Mengunduh stream video direct ({clean_title})...\n"})

    ok = stream_download_file(clean_url, raw_path, ui_queue, abort_checker, label="Unduh Video Direct")
    if not ok:
        return False

    postprocess_video(raw_path, final_path, options, ui_queue, abort_checker)

    if ui_queue:
        ui_queue.put({"type": "log", "text": f"\n--- UNDUHAN SUKSES (Video Generic) ---\nFile tersimpan di: {final_path}\n"})
        ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
    return True
