import os
import re
import html
import requests
from datetime import datetime, timezone
from engines.base import (
    DEFAULT_HEADERS, sanitize_filename, stream_download_file,
    fast_remux_mp4, extract_audio_from_video, normalize_image_to_jpeg,
    embed_thumbnail_to_media, probe_media_stream, postprocess_video
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
        tw_img = re.search(r'<meta\s+name=["\']twitter:image["\']\s+content=["\']([^"\']+)["\']', page_html)

        raw_title = html.unescape(og_title.group(1)).strip() if og_title else ''
        raw_desc = html.unescape(og_desc.group(1)).strip() if og_desc else ''

        candidates = []
        for im in (og_img, tw_img):
            if im:
                u = html.unescape(im.group(1)).strip()
                if u.startswith('http') and u not in candidates:
                    candidates.append(u)
        thumb = candidates[0] if candidates else ''

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

        # Parsing engagement metrics
        view_count = 0
        like_count = 0
        share_count = 0
        combined_text = f"{raw_title} {raw_desc}"
        vm = re.search(r'([\d.,]+)\s*(?:rb|k|m|jt|mil|bil)?\s*(?:tayangan|views)', combined_text, re.I)
        if vm:
            val_str = vm.group(1).replace('.', '').replace(',', '')
            if val_str.isdigit(): view_count = int(val_str)
        lm = re.search(r'([\d.,]+)\s*(?:rb|k|m|jt|mil|bil)?\s*(?:tanggapan|reactions|suka|likes)', combined_text, re.I)
        if lm:
            val_str = lm.group(1).replace('.', '').replace(',', '')
            if val_str.isdigit(): like_count = int(val_str)
        sm = re.search(r'([\d.,]+)\s*(?:rb|k|m|jt|mil|bil)?\s*(?:dibagikan|shares)', combined_text, re.I)
        if sm:
            val_str = sm.group(1).replace('.', '').replace(',', '')
            if val_str.isdigit(): share_count = int(val_str)

        # Parsing tanggal
        upload_date = ""
        date_string = ""
        date_cand_m = (
            re.search(r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)["\']', page_html, re.I) or
            re.search(r'"publish_time":\s*(\d+)', page_html, re.I) or
            re.search(r'data-utime="(\d+)"', page_html, re.I)
        )
        if date_cand_m:
            date_val = date_cand_m.group(1)
            if date_val.isdigit() and len(date_val) >= 9:
                try:
                    dt = datetime.fromtimestamp(int(date_val), tz=timezone.utc)
                    upload_date = dt.strftime('%Y%m%d')
                    date_string = dt.strftime('%d/%m/%Y')
                except Exception:
                    pass
            else:
                m_iso = re.search(r'(\d{4})-(\d{2})-(\d{2})', date_val)
                if m_iso:
                    upload_date = f"{m_iso.group(1)}{m_iso.group(2)}{m_iso.group(3)}"
                    date_string = f"{m_iso.group(3)}/{m_iso.group(2)}/{m_iso.group(1)}"

        # Probing video jika tersedia stream direct
        duration = 0
        dur_str = ""
        w = 0
        h = 0
        fps = 0
        codec = ""
        res_lbl = "HD Reel" if is_video else "HD Photo"
        video_url = None

        og_video = re.search(r'<meta\s+property=["\']og:video(?::secure_url)?["\']\s+content=["\']([^"\']+)["\']', page_html)
        if og_video:
            video_url = html.unescape(og_video.group(1))

        if is_video and video_url:
            p_res = probe_media_stream(video_url, timeout=4)
            if p_res:
                w = p_res.get('width') or 0
                h = p_res.get('height') or 0
                fps = p_res.get('fps') or 30
                codec = p_res.get('codec') or 'h264'
                dur_float = p_res.get('duration') or 0
                duration = int(dur_float)
                if duration:
                    dur_str = f"{duration // 60:02d}:{duration % 60:02d}"
                res_lbl = p_res.get('resolution_label') or "HD Reel"

        display_title = f"{author}: {clean_title}" if author else clean_title

        return {
            'title': display_title,
            'clean_title': clean_title,
            'author': author,
            'description': raw_desc or clean_title,
            'thumbnail': thumb,
            'thumbnails': candidates,
            'is_video': is_video,
            'video_url': video_url,
            'is_slide': not is_video,
            'slide_count': 1 if not is_video else 0,
            'duration': duration,
            'duration_string': dur_str if is_video else "1 Foto HD",
            'width': w or (1080 if is_video else 1200),
            'height': h or (1920 if is_video else 800),
            'fps': fps or (30 if is_video else 0),
            'codec': codec or ('h264' if is_video else ''),
            'resolution_label': res_lbl,
            'view_count': view_count,
            'like_count': like_count,
            'share_count': share_count,
            'upload_date': upload_date,
            'date_string': date_string,
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

            raw_container = options.get('container', 'auto') if options else 'auto'
            container = 'mp4' if raw_container in ('auto', 'best', '', None) else str(raw_container).lower()
            ext = f".{container}"

            raw_path = os.path.join(output_dir, f"{base_name}_raw.mp4")
            final_path = os.path.join(output_dir, f"{base_name}{ext}")

            success = stream_download_file(video_url, raw_path, ui_queue, abort_checker, label="Unduh Video Facebook")
            if not success:
                return False

            postprocess_video(raw_path, final_path, options, ui_queue, abort_checker)

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
