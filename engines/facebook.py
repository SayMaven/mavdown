import os
import re
import html
import requests
from engines.base import (
    DEFAULT_HEADERS, sanitize_filename, stream_download_file,
    fast_remux_mp4, extract_audio_from_video, normalize_image_to_jpeg,
    embed_thumbnail_to_media
)

FB_CRAWLER_HEADERS = {
    'User-Agent': 'facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)',
    'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7'
}

FB_IMAGE_HEADERS = {
    'User-Agent': 'facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)',
    'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'
}

def is_metric_string(s: str) -> bool:
    """Mengecek apakah string hanya berupa metrik tayangan/tanggapan."""
    if not s:
        return False
    return bool(re.search(r'^(?:\d+[\d.,]*\s*(?:rb|jt|k|m|mil|bil)?\s*(?:tayangan|views|tanggapan|reactions|suka|likes|dibagikan|shares))(?:\s*·.*)?$', s.strip(), re.IGNORECASE))

def get_facebook_info(url: str) -> dict:
    """Mengambil metadata postingan Facebook via OpenGraph crawler."""
    clean_url = (url or '').strip()
    is_url_video = bool(re.search(r'/(?:reel|reels|watch|videos?)/|fb\.watch|/share/(?:r|v)/', clean_url, re.IGNORECASE))
    try:
        resp = requests.get(clean_url, headers=FB_CRAWLER_HEADERS, timeout=8)
        page_html = resp.text

        og_type_m = re.search(r'<meta\s+property=["\']og:type["\']\s+content=["\']([^"\']+)["\']', page_html)
        og_type = og_type_m.group(1).lower() if og_type_m else ''
        is_video = is_url_video or ('video' in og_type and '/share/p/' not in clean_url)

        og_title = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']', page_html)
        og_desc = re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']', page_html) or \
                  re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']', page_html)
        og_img = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', page_html)

        raw_title = html.unescape(og_title.group(1)).strip() if og_title else ''
        raw_desc = html.unescape(og_desc.group(1)).strip() if og_desc else ''
        thumb = html.unescape(og_img.group(1)).strip() if og_img else ''

        title = ''
        author = ''

        # Parsing format "Metric | Title | Author" atau "Author | Title"
        if '|' in raw_title:
            parts = [p.strip() for p in raw_title.split('|') if p.strip() and 'facebook' not in p.lower()]
            if len(parts) >= 3 and is_metric_string(parts[0]):
                title = parts[1]
                author = " | ".join(parts[2:])
            elif len(parts) == 2 and is_metric_string(parts[0]):
                title = parts[1]
            elif len(parts) >= 2:
                author = parts[0]
                title = " | ".join(parts[1:])
            elif len(parts) == 1 and not is_metric_string(parts[0]):
                author = parts[0]

        if not title:
            if raw_desc and not any(k in raw_desc.lower() for k in ('log in', 'facebook', 'watch video')):
                title = raw_desc
            elif raw_title and not any(k in raw_title.lower() for k in ('log in', 'facebook')):
                title = re.sub(r'\|.*$', '', raw_title).strip()

        if not author and ' - ' in raw_title:
            sub_parts = raw_title.split(' - ')
            if len(sub_parts) >= 2:
                author = sub_parts[-1].strip()
                if not title:
                    title = sub_parts[0].strip()

        if is_metric_string(author) or author.lower() in ('facebook user', 'user', 'facebook', 'none', ''):
            author = ''

        if not title:
            title = 'Facebook Video' if is_video else 'Facebook Post'

        clean_title = title.splitlines()[0] if title else 'Facebook Media'

        return {
            'title': clean_title,
            'clean_title': clean_title,
            'author': author,
            'description': raw_desc or clean_title,
            'thumbnail': thumb,
            'is_video': is_video,
            'resolution_label': 'HD Reel' if is_video else 'HD Photo',
            'platform': 'Facebook'
        }
    except Exception:
        return None

def download_facebook(url: str, output_dir: str, ui_queue=None, options=None, abort_checker=None) -> bool:
    """
    Unduh media Facebook:
    - Jika video reels/watch: coba cek direct MP4, jika tidak ada alihkan ke Tier 2 (yt-dlp).
    - Jika foto: unduh dengan crawler headers dan normalisasi ke format JPEG standar.
    """
    if options is None:
        options = {}
    mode = options.get('mode', 'video_audio')
    audio_format = options.get('audio_format', 'mp3')

    clean_url = (url or '').strip()
    is_url_video = bool(re.search(r'/(?:reel|reels|watch|videos?)/|fb\.watch|/share/(?:r|v)/', clean_url, re.IGNORECASE))

    if ui_queue:
        ui_queue.put({"type": "log", "text": "[TIER 1] Menghubungi Facebook Scraper Engine...\n"})

    try:
        resp = requests.get(clean_url, headers=FB_CRAWLER_HEADERS, timeout=10)
        page_html = resp.text

        og_type_m = re.search(r'<meta\s+property=["\']og:type["\']\s+content=["\']([^"\']+)["\']', page_html)
        og_type = og_type_m.group(1).lower() if og_type_m else ''
        is_video = is_url_video or ('video' in og_type and '/share/p/' not in clean_url)

        meta_info = get_facebook_info(clean_url) or {}
        title_str = meta_info.get('clean_title') or 'Facebook Media'
        author_str = meta_info.get('author') or ''
        base_name = sanitize_filename(f"{author_str} - {title_str}" if author_str else title_str)

        # 1. KASUS A: Video Reels / Watch MP4 Direct
        og_video = re.search(r'<meta\s+property=["\']og:video(?::secure_url)?["\']\s+content=["\']([^"\']+)["\']', page_html)
        if og_video:
            video_url = html.unescape(og_video.group(1))
            if ui_queue:
                ui_queue.put({"type": "log", "text": "[TIER 1] Menemukan stream video direct Facebook!\n"})

            raw_path = os.path.join(output_dir, f"{base_name}_raw.mp4")
            final_path = os.path.join(output_dir, f"{base_name}.mp4")

            success = stream_download_file(video_url, raw_path, ui_queue, abort_checker, label="Unduh Video Facebook")
            if not success:
                return False

            fast_remux_mp4(raw_path, final_path)

            saved_path = final_path
            if mode == 'audio_only':
                final_audio = os.path.join(output_dir, f"{base_name}.{audio_format}")
                extract_audio_from_video(final_path, final_audio, audio_format)
                if os.path.exists(final_path):
                    try: os.remove(final_path)
                    except Exception: pass
                saved_path = final_audio

            embed_thumb = options.get('embed_thumb', True) if options else True
            thumb_url = meta_info.get('thumbnail')
            if not thumb_url:
                og_img = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', page_html)
                thumb_url = html.unescape(og_img.group(1)) if og_img else ''

            if embed_thumb and thumb_url and saved_path and os.path.exists(saved_path):
                embed_thumbnail_to_media(saved_path, thumb_url, ui_queue, abort_checker)

            if ui_queue:
                ui_queue.put({"type": "log", "text": f"\n--- UNDUHAN SUKSES (Facebook) ---\nFile: {saved_path}\n"})
                ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
            return True

        # Jika konten adalah video/reels dan tidak ada direct MP4 di OpenGraph,
        # JANGAN PERNAH mengunduh og:image karena itu hanya poster thumbnail!
        if is_video:
            if ui_queue:
                ui_queue.put({"type": "log", "text": "[TIER 1] Video/Reels Facebook memerlukan Tier 2 (yt-dlp) untuk audio & video HD...\n"})
            return False

        # 2. KASUS B: Postingan Foto Facebook
        og_img = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', page_html)
        if og_img:
            img_url = html.unescape(og_img.group(1))
            final_img = os.path.join(output_dir, f"{base_name}.jpg")

            # Unduh gambar dengan crawler header agar tidak terblokir / redirect ke HTML
            success = stream_download_file(
                img_url, final_img, ui_queue, abort_checker,
                headers=FB_IMAGE_HEADERS, label="Unduh Foto Facebook"
            )
            if success and os.path.exists(final_img):
                # Validasi apakah file bukan HTML redirect
                if os.path.getsize(final_img) < 500:
                    try: os.remove(final_img)
                    except Exception: pass
                    return False

                # Normalisasi format gambar (WEBP -> JPEG murni) agar kompatibel dengan semua viewer
                normalize_image_to_jpeg(final_img)

                if ui_queue:
                    ui_queue.put({"type": "log", "text": f"\n--- UNDUHAN SUKSES (Facebook Photo HD) ---\nFile: {final_img}\n"})
                    ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
                return True

    except Exception as e:
        if ui_queue:
            ui_queue.put({"type": "log", "text": f"[TIER 1 ERROR] {e}\n"})

    return False
