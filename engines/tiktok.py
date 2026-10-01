import os
import requests
from engines.base import (
    DEFAULT_HEADERS, sanitize_filename, stream_download_file,
    fast_remux_mp4, extract_audio_from_video, normalize_image_to_jpeg,
    postprocess_video, probe_media_stream, embed_thumbnail_to_media
)

TIKWM_API = "https://www.tikwm.com/api/"

def fetch_tikwm_data(url: str, timeout: int = 15) -> dict:
    """Mengambil data JSON dari TikWM API."""
    clean_url = (url or '').split('?')[0].strip()
    payload = {
        'url': clean_url,
        'hd': 1
    }
    resp = requests.post(TIKWM_API, data=payload, headers=DEFAULT_HEADERS, timeout=timeout)
    resp.raise_for_status()
    res_json = resp.json()
    if res_json.get('code') == 0 and res_json.get('data'):
        return res_json['data']
    return {}

def get_tiktok_info(url: str) -> dict:
    """
    Ekstraksi metadata TikTok secara instan (< 1s) untuk preview judul & thumbnail.
    """
    try:
        data = fetch_tikwm_data(url)
        if not data:
            return None

        title = data.get('title') or 'TikTok Media'
        author = data.get('author', {}).get('nickname') or 'TikTok User'
        thumb = data.get('cover') or data.get('origin_cover') or ''
        raw_duration = data.get('duration', 0)
        
        is_slide = bool(data.get('images'))
        images = data.get('images') or []

        dur_sec = int(raw_duration) if raw_duration else 0
        dur_str = f"{dur_sec // 60:02d}:{dur_sec % 60:02d}" if dur_sec else ""

        video_url = data.get('hdplay') or data.get('play') or ''
        audio_url = data.get('music') or ''

        view_count = data.get('play_count', 0)
        like_count = data.get('digg_count', 0)
        comment_count = data.get('comment_count', 0)
        share_count = data.get('share_count', 0)
        file_size = data.get('hd_size') or data.get('size', 0)
        formatted_size = f"{file_size / (1024*1024):.1f} MB" if file_size else None

        info_dict = {
            'title': f"{author} - {title}" if author else title,
            'clean_title': title,
            'author': author,
            'thumbnail': thumb,
            'duration': dur_sec,
            'duration_string': dur_str,
            'is_slide': is_slide,
            'slide_count': len(images) if is_slide else 0,
            'media_count': len(images) if is_slide else 1,
            'has_audio': bool(audio_url),
            'images': images,
            'video_url': video_url,
            'audio_url': audio_url,
            'view_count': view_count,
            'like_count': like_count,
            'comment_count': comment_count,
            'share_count': share_count,
            'formatted_size': formatted_size,
            'platform': 'TikTok'
        }

        if is_slide:
            info_dict.update({
                'width': 1080,
                'height': 1920,
                'resolution_label': 'HD Original',
                'duration_string': f"{len(images)} Foto Slide"
            })
        elif video_url:
            probe_info = probe_media_stream(video_url, timeout=4)
            w = probe_info.get('width')
            h = probe_info.get('height')
            fps = probe_info.get('fps')
            codec = probe_info.get('codec')
            res_lbl = probe_info.get('resolution_label')

            if not (w and h):
                if data.get('hdplay'):
                    w, h = 1080, 1920
                    res_lbl = "1080p FHD"
                else:
                    w, h = 720, 1280
                    res_lbl = "720p HD"

            info_dict.update({
                'width': w,
                'height': h,
                'fps': fps or 30,
                'codec': codec or 'h264',
                'resolution_label': res_lbl or ("1080p FHD" if (w and w >= 1080) or (h and h >= 1080) else "720p HD")
            })

        return info_dict
    except Exception:
        return None

def download_tiktok(url: str, output_dir: str, ui_queue=None, options=None, abort_checker=None) -> bool:
    """
    Unduh video HD tanpa watermark atau album slide foto TikTok menggunakan TikWM API.
    """
    if options is None:
        options = {}

    mode = options.get('mode', 'video_audio')
    audio_format = options.get('audio_format', 'mp3')

    if ui_queue:
        ui_queue.put({"type": "log", "text": "[TIER 1] Menghubungi TikWM Engine...\n"})

    try:
        data = fetch_tikwm_data(url)
        if not data:
            if ui_queue:
                ui_queue.put({"type": "log", "text": "[TIER 1] TikWM tidak mengembalikan data media. Beralih ke Tier 2...\n"})
            return False

        author = data.get('author', {}).get('nickname') or 'TikTok User'
        raw_title = data.get('title') or 'TikTok Video'
        base_name = sanitize_filename(f"{author} - {raw_title}" if author else raw_title)

        # -------------------------------------------------------------
        # 1. KASUS A: Postingan berupa Album Slide Foto
        # -------------------------------------------------------------
        images = data.get('images')
        if images and isinstance(images, list) and len(images) > 0:
            if ui_queue:
                ui_queue.put({"type": "log", "text": f"[TIER 1] Terdeteksi Album Slide Foto ({len(images)} foto).\n"})

            folder_name = base_name if base_name else "TikTok_Slide"
            slide_folder = os.path.join(output_dir, folder_name)
            os.makedirs(slide_folder, exist_ok=True)

            # Unduh setiap foto satu per satu
            total_img = len(images)
            for i, img_url in enumerate(images, 1):
                if abort_checker and abort_checker():
                    return False
                img_path = os.path.join(slide_folder, f"foto_{i:02d}.jpg")
                label = f"Slide {i}/{total_img}"
                if ui_queue:
                    ui_queue.put({"type": "log", "text": f"Mengunduh {label}...\n"})
                if stream_download_file(img_url, img_path, ui_queue, abort_checker, label=label):
                    normalize_image_to_jpeg(img_path)

            # Unduh musik pengiring jika ada
            music_url = data.get('music')
            if music_url:
                if ui_queue:
                    ui_queue.put({"type": "log", "text": "Mengunduh file audio musik pengiring...\n"})
                music_path = os.path.join(slide_folder, "music.mp3")
                stream_download_file(music_url, music_path, ui_queue, abort_checker, label="Musik BGM")

            if ui_queue:
                ui_queue.put({"type": "log", "text": f"\n--- UNDUHAN SUKSES ---\nFolder: {slide_folder}\n"})
                ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
            return True

        # -------------------------------------------------------------
        # 2. KASUS B: Postingan berupa Video
        # -------------------------------------------------------------
        video_url = data.get('hdplay') or data.get('play')
        if not video_url:
            if ui_queue:
                ui_queue.put({"type": "log", "text": "[TIER 1] URL stream video tidak ditemukan.\n"})
            return False

        if ui_queue:
            hd_label = "HD (1080p)" if data.get('hdplay') else "SD"
            ui_queue.put({"type": "log", "text": f"[TIER 1] Menemukan stream video No Watermark {hd_label}.\n"})

        raw_container = options.get('container', 'auto') if options else 'auto'
        container = 'mp4' if raw_container in ('auto', 'best', '', None) else str(raw_container).lower()
        ext = f".{container}"
        raw_video_path = os.path.join(output_dir, f"{base_name}_raw.mp4")
        final_video_path = os.path.join(output_dir, f"{base_name}{ext}")

        success = stream_download_file(
            video_url, raw_video_path, ui_queue, abort_checker,
            label="Unduh TikTok Video"
        )
        if not success:
            return False

        # Jika pengguna memilih mode Audio Saja
        if mode == 'audio_only':
            final_audio_path = os.path.join(output_dir, f"{base_name}.{audio_format}")
            if ui_queue:
                ui_queue.put({"type": "log", "text": f"Mengekstrak audio ke format .{audio_format}...\n"})
            
            # Jika ada direct audio stream dari TikWM, coba unduh langsung atau ekstrak via ffmpeg
            music_url = data.get('music')
            if music_url and audio_format == 'mp3':
                stream_download_file(music_url, final_audio_path, ui_queue, abort_checker, label="Audio MP3")
            else:
                extract_audio_from_video(raw_video_path, final_audio_path, audio_format)
                
            if os.path.exists(raw_video_path):
                try: os.remove(raw_video_path)
                except Exception: pass
            saved_path = final_audio_path
        else:
            postprocess_video(raw_video_path, final_video_path, options, ui_queue, abort_checker)
            saved_path = final_video_path

        embed_thumb = options.get('embed_thumb', True) if options else True
        thumb_url = data.get('cover') or data.get('origin_cover')
        if embed_thumb and thumb_url and saved_path and os.path.exists(saved_path):
            embed_thumbnail_to_media(saved_path, thumb_url, ui_queue, abort_checker)

        if ui_queue:
            ui_queue.put({"type": "log", "text": f"\n--- UNDUHAN SUKSES (Tier 1 TikWM) ---\nFile tersimpan di: {saved_path}\n"})
            ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
        return True

    except Exception as e:
        if ui_queue:
            ui_queue.put({"type": "log", "text": f"[TIER 1 ERROR] {e}\n"})
        return False
