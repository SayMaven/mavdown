import os
import re
import time
import json
import hmac
import hashlib
import requests
import subprocess
from engines.base import (
    DEFAULT_HEADERS, FFMPEG_PATH, sanitize_filename, stream_download_file,
    fast_remux_mp4, extract_audio_from_video, postprocess_video,
    probe_media_stream, embed_thumbnail_to_media
)

SNAPANY_SECRET = 'a5wU-SVyy5gXIyMbPQIfIz7UP7rCBp76U8Z8i-FtDMU'

def expand_bilibili_url(raw_url: str) -> str:
    """
    Ekspansi shortlink b23.tv ke URL kanonikal bilibili.com.
    """
    clean_url = (raw_url or '').strip()
    if 'b23.tv' not in clean_url:
        return clean_url

    try:
        resp = requests.get(clean_url, allow_redirects=True, headers=DEFAULT_HEADERS, timeout=8)
        resolved = resp.url.split('?')[0] if resp.url else clean_url
        return resolved or clean_url
    except Exception:
        return clean_url

def get_snapany_headers(link: str, locale: str = 'en') -> dict:
    """
    Membuat HMAC-SHA256 signature untuk SnapAny API.
    """
    timestamp = str(int(time.time() * 1000))
    signature = hmac.new(
        SNAPANY_SECRET.encode('utf-8'),
        (link + locale + timestamp).encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    return {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Origin': 'https://snapany.com',
        'Referer': 'https://snapany.com/',
        'Accept-Language': locale,
        'G-Timestamp': timestamp,
        'G-Footer': signature,
        'G-Timezone': 'Asia/Jakarta'
    }

def get_bilibili_page_meta(url: str) -> dict:
    """
    Ekstraksi metadata asli web Bilibili (HTML scraper) untuk judul, uploader, dan durasi akurat.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
        }
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code == 200:
            resp.encoding = 'utf-8'
            m = re.search(r'window\.__INITIAL_STATE__\s*=\s*({[\s\S]*?});(?:\(function|var|const|\n|<)', resp.text)
            if not m:
                m = re.search(r'window\.__INITIAL_STATE__\s*=\s*({[\s\S]*?});', resp.text)
            if m:
                data = json.loads(m.group(1))
                vdata = data.get('videoData') or {}
                uploader = vdata.get('owner', {}).get('name') or data.get('upData', {}).get('name') or ''
                title = vdata.get('title', '')
                thumbnail = vdata.get('pic', '')
                duration_sec = vdata.get('duration', 0)
                dur_str = f"{duration_sec // 60}:{duration_sec % 60:02d}" if duration_sec else ""
                stat = vdata.get('stat', {})
                return {
                    'uploader': uploader,
                    'title': title,
                    'thumbnail': thumbnail,
                    'duration': duration_sec,
                    'duration_string': dur_str,
                    'view_count': stat.get('view', 0),
                    'like_count': stat.get('like', 0)
                }
    except Exception:
        pass
    return None

def fetch_bilibili_snapany(target_url: str) -> dict:
    """
    Mengambil data stream video dan audio Bilibili via SnapAny Cloud Engine.
    """
    headers = get_snapany_headers(target_url)
    resp = requests.post(
        'https://api.snapany.com/v1/extract/post',
        json={'link': target_url},
        headers=headers,
        timeout=15
    )
    if resp.status_code == 200:
        data = resp.json()
        if data and data.get('medias'):
            return data
    return None

def get_bilibili_info(url: str) -> dict:
    """
    Ekstraksi info Bilibili secara instan (< 1-2s) untuk pratinjau judul, thumbnail, dan statistik.
    """
    clean_url = (url or '').strip()
    target_url = expand_bilibili_url(clean_url)

    page_meta = get_bilibili_page_meta(target_url) or {}
    snap_data = fetch_bilibili_snapany(target_url) or {}

    if not snap_data and not page_meta:
        return None

    clean_title = page_meta.get('title') or snap_data.get('title') or snap_data.get('text') or 'Bilibili Video'
    author = page_meta.get('uploader') or (snap_data.get('author') or {}).get('name') or 'Bilibili Creator'
    display_title = f"{author} - {clean_title}" if author and author != 'Bilibili Creator' else clean_title

    medias = snap_data.get('medias', [])
    m0 = medias[0] if medias else {}
    thumbnail = page_meta.get('thumbnail') or m0.get('preview_url') or snap_data.get('thumbnail') or ''

    # Durasi
    duration = page_meta.get('duration', 0)
    dur_str = page_meta.get('duration_string', '')
    if not dur_str and duration:
        dur_str = f"{duration // 60}:{duration % 60:02d}"

    # Metrik engagement
    stats = snap_data.get('stats') or {}
    view_count = page_meta.get('view_count') or stats.get('view_count', 0)
    like_count = page_meta.get('like_count') or stats.get('like_count', 0)
    comment_count = stats.get('comment_count', 0)
    share_count = stats.get('share_count', 0)

    # Resolusi & codec dari varian tertinggi
    variants = m0.get('variants', [])
    best_variant = None
    if variants:
        best_variant = next((v for v in variants if (v.get('video_codec') or '').lower().startswith(('hevc', 'h265'))), None)
        if not best_variant:
            best_variant = variants[0]

    res_label = best_variant.get('quality_label') if best_variant else "1080p FHD"
    codec = (best_variant.get('video_codec') or 'h264') if best_variant else 'h264'

    w = 1920
    h = 1080
    if best_variant:
        ql = (best_variant.get('quality_label') or '').lower()
        if '4k' in ql or '2160' in ql:
            w, h = 3840, 2160
            res_label = "4K UHD"
        elif '2k' in ql or '1440' in ql:
            w, h = 2560, 1440
            res_label = "2K QHD"
        elif '720' in ql:
            w, h = 1280, 720
            res_label = "720p HD"
        elif '480' in ql:
            w, h = 854, 480
            res_label = "480p"
        elif '360' in ql:
            w, h = 640, 360
            res_label = "360p"

    return {
        'title': display_title,
        'clean_title': clean_title,
        'author': author,
        'thumbnail': thumbnail,
        'duration': duration,
        'duration_string': dur_str,
        'is_slide': False,
        'width': w,
        'height': h,
        'fps': 30,
        'codec': codec,
        'resolution_label': res_label,
        'view_count': view_count,
        'like_count': like_count,
        'comment_count': comment_count,
        'share_count': share_count,
        'platform': 'Bilibili',
        'webpage_url': target_url
    }

def download_bilibili(url: str, output_dir: str, ui_queue=None, options=None, abort_checker=None) -> bool:
    """
    Unduh media Bilibili (Video 1080p/720p atau Audio HQ) via SnapAny Cloud Engine (Tier 1).
    Otomatis menggabungkan stream video + audio DASH dan menginjeksi cover thumbnail asli.
    """
    if options is None:
        options = {}
    mode = options.get('mode', 'video_audio')
    audio_format = options.get('audio_format', 'mp3')
    embed_thumb = options.get('embed_thumb', True)

    clean_url = (url or '').strip()
    target_url = expand_bilibili_url(clean_url)

    if ui_queue:
        ui_queue.put({"type": "log", "text": "[TIER 1] Menghubungi Bilibili Cloud Engine (SnapAny)...\n"})

    try:
        snap_data = fetch_bilibili_snapany(target_url)
        if not snap_data or not snap_data.get('medias'):
            if ui_queue:
                ui_queue.put({"type": "log", "text": "[TIER 1] SnapAny tidak mengembalikan media Bilibili. Beralih ke Tier 2...\n"})
            return False

        page_meta = get_bilibili_page_meta(target_url) or {}
        clean_title = page_meta.get('title') or snap_data.get('title') or snap_data.get('text') or 'Bilibili Video'
        author = page_meta.get('uploader') or (snap_data.get('author') or {}).get('name') or ''
        base_name = sanitize_filename(f"{author} - {clean_title}" if author and author != 'Bilibili Creator' else clean_title)

        m0 = snap_data['medias'][0]
        thumbnail = page_meta.get('thumbnail') or m0.get('preview_url') or snap_data.get('thumbnail') or ''

        req_headers = {
            'User-Agent': m0.get('headers', {}).get('User-Agent', DEFAULT_HEADERS['User-Agent']),
            'Referer': m0.get('headers', {}).get('Referer', 'https://www.bilibili.com/')
        }

        variants = m0.get('variants', [])

        # -------------------------------------------------------------
        # 1. MODE AUDIO SAJA
        # -------------------------------------------------------------
        if mode == 'audio_only':
            audio_url = None
            if variants:
                audio_v = next((v for v in variants if v.get('audio_url')), None)
                if audio_v:
                    audio_url = audio_v['audio_url']
            if not audio_url:
                audio_url = m0.get('resource_url')

            if not audio_url:
                if ui_queue:
                    ui_queue.put({"type": "log", "text": "[TIER 1] Stream audio tidak ditemukan.\n"})
                return False

            raw_audio_path = os.path.join(output_dir, f"{base_name}_raw_audio.mp4")
            final_audio_path = os.path.join(output_dir, f"{base_name}.{audio_format}")

            if ui_queue:
                ui_queue.put({"type": "log", "text": "[TIER 1] Mengunduh stream audio Bilibili...\n"})

            dl_ok = stream_download_file(audio_url, raw_audio_path, ui_queue, abort_checker, headers=req_headers, label="Unduh Audio Bilibili")
            if not dl_ok:
                return False

            extract_audio_from_video(raw_audio_path, final_audio_path, audio_format)
            if os.path.exists(raw_audio_path):
                try: os.remove(raw_audio_path)
                except Exception: pass

            saved_path = final_audio_path
            if embed_thumb and thumbnail and os.path.exists(saved_path):
                embed_thumbnail_to_media(saved_path, thumbnail, ui_queue, abort_checker)

            if ui_queue:
                ui_queue.put({"type": "log", "text": f"\n--- UNDUHAN SUKSES (Bilibili Audio) ---\nFile: {saved_path}\n"})
                ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
            return True

        # -------------------------------------------------------------
        # 2. MODE VIDEO (+ AUDIO)
        # -------------------------------------------------------------
        chosen_video_url = None
        chosen_audio_url = None

        if variants:
            # Cari varian yang cocok dengan preferensi codec (H.265/HEVC atau H.264/AVC)
            pref_codec = (options.get('video_codec', 'best') or 'best').lower()
            if pref_codec == 'av1':
                best_v = next((v for v in variants if 'av1' in (v.get('video_codec') or '').lower()), None)
            elif pref_codec in ('vp9', 'hevc', 'h265'):
                best_v = next((v for v in variants if any(c in (v.get('video_codec') or '').lower() for c in ('hevc', 'h265', 'hev1', 'hvc1'))), None)
            else:
                best_v = next((v for v in variants if any(c in (v.get('video_codec') or '').lower() for c in ('h264', 'avc', 'avc1'))), None)

            if not best_v:
                best_v = variants[0]

            chosen_video_url = best_v.get('video_url') or best_v.get('resource_url')
            chosen_audio_url = best_v.get('audio_url')

        if not chosen_audio_url and variants:
            audio_v = next((v for v in variants if v.get('audio_url')), None)
            if audio_v:
                chosen_audio_url = audio_v['audio_url']

        if not chosen_video_url:
            chosen_video_url = m0.get('resource_url')

        if not chosen_video_url:
            if ui_queue:
                ui_queue.put({"type": "log", "text": "[TIER 1] Video stream URL tidak ditemukan.\n"})
            return False

        raw_video_path = os.path.join(output_dir, f"{base_name}_raw_video.mp4")
        raw_audio_path = os.path.join(output_dir, f"{base_name}_raw_audio.m4a")
        muxed_video_path = os.path.join(output_dir, f"{base_name}_muxed.mp4")
        final_video_path = os.path.join(output_dir, f"{base_name}.mp4")

        if ui_queue:
            ui_queue.put({"type": "log", "text": "[TIER 1] Mengunduh stream video Bilibili...\n"})

        dl_v_ok = stream_download_file(chosen_video_url, raw_video_path, ui_queue, abort_checker, headers=req_headers, label="Unduh Video Bilibili")
        if not dl_v_ok:
            return False

        # Jika Bilibili menggunakan DASH terpisah (audio stream mandiri), unduh dan muxing
        if chosen_audio_url:
            if ui_queue:
                ui_queue.put({"type": "log", "text": "[TIER 1] Mengunduh stream audio Bilibili...\n"})

            dl_a_ok = stream_download_file(chosen_audio_url, raw_audio_path, ui_queue, abort_checker, headers=req_headers, label="Unduh Audio Bilibili")
            if dl_a_ok and os.path.exists(raw_audio_path) and os.path.getsize(raw_audio_path) > 100:
                # Satukan video + audio via FFmpeg copy muxing (0% CPU)
                if ui_queue:
                    ui_queue.put({"type": "log", "text": "[FFMPEG] Menggabungkan stream video & audio DASH (Copy Mux)...\n"})

                cmd = [
                    FFMPEG_PATH, "-y",
                    "-i", raw_video_path,
                    "-i", raw_audio_path,
                    "-c", "copy",
                    "-movflags", "+faststart",
                    muxed_video_path
                ]
                startupinfo = None
                if os.name == 'nt':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE

                res = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=60,
                    startupinfo=startupinfo, encoding='utf-8', errors='ignore'
                )
                if res.returncode == 0 and os.path.exists(muxed_video_path):
                    source_for_postprocess = muxed_video_path
                else:
                    source_for_postprocess = raw_video_path
            else:
                source_for_postprocess = raw_video_path
        else:
            source_for_postprocess = raw_video_path

        # Postprocessing (Transcoding / Downscaling jika diminta pengguna, atau Fast Remux)
        postprocess_video(source_for_postprocess, final_video_path, options, ui_queue, abort_checker)

        # Bersihkan file sementara
        for temp_f in (raw_video_path, raw_audio_path, muxed_video_path):
            if os.path.exists(temp_f):
                try: os.remove(temp_f)
                except Exception: pass

        saved_path = final_video_path
        if embed_thumb and thumbnail and os.path.exists(saved_path):
            embed_thumbnail_to_media(saved_path, thumbnail, ui_queue, abort_checker)

        if ui_queue:
            ui_queue.put({"type": "log", "text": f"\n--- UNDUHAN SUKSES (Bilibili HD) ---\nFile tersimpan di: {saved_path}\n"})
            ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
        return True

    except Exception as e:
        if ui_queue:
            ui_queue.put({"type": "log", "text": f"[TIER 1 ERROR] {e}\n"})

    if ui_queue:
        ui_queue.put({"type": "log", "text": "[TIER 1] Beralih ke Engine Fallback Tier 2 (yt-dlp)...\n"})
    return False
