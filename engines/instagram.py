import os
import re
import html
import json
import base64
import requests

from engines.base import (
    DEFAULT_HEADERS, sanitize_filename, stream_download_file,
    fast_remux_mp4, extract_audio_from_video, normalize_image_to_jpeg,
    probe_media_stream, embed_thumbnail_to_media
)

IG_CRAWLER_HEADERS = {
    'User-Agent': 'facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)',
    'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7'
}

def fetch_instagram_media(url: str) -> list:
    """
    Ekstraksi media Instagram per item (Foto Tunggal, Album Carousel/Slide, atau Video)
    menggunakan Fast Multi-Media Resolver.
    Mem-parse HTML respons per <li> elemen agar setiap slide atau video terdeteksi secara presisi.
    """
    clean_url = (url or '').split('?')[0].strip()
    payload = {
        'q': clean_url,
        'vt': 'reel',
        't': 'media',
        'lang': 'en',
        'v': 'v2'
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://indown.net",
        "Referer": "https://indown.net/",
    }

    try:
        resp = requests.post("https://indown.net/api/ajaxSearch", data=payload, headers=headers, timeout=12)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('status') == 'ok':
                html_data = data.get('data', '')

                # Cari elemen <li> (setiap <li> mewakili tepat 1 slide atau 1 media post)
                lis = re.findall(r'<li[^>]*>([\s\S]*?)</li>', html_data)
                if not lis:
                    lis = re.findall(r'<div class="download-items">([\s\S]*?)(?=<div class="download-items">|$)', html_data)

                media_items = []
                for li in lis:
                    # 1. Cek apakah di dalam <li> ini terdapat video
                    vid_match = re.search(r'<a[^>]+href="([^"]*token=[^"]*)"[^>]*title="Download Video"', li) or \
                                re.search(r'<a[^>]+title="Download Video"[^>]+href="([^"]*token=[^"]*)"', li)

                    if not vid_match:
                        for tok in re.findall(r'token=([a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+)', li):
                            try:
                                p = json.loads(base64.urlsafe_b64decode(tok.split('.')[1] + '=='))
                                fn = p.get('filename', '').lower()
                                u = p.get('url', '').lower()
                                if fn.endswith('.mp4') or '.mp4' in u:
                                    vid_match = tok
                                    break
                            except Exception:
                                pass

                    if vid_match:
                        tok = vid_match.group(1) if hasattr(vid_match, 'group') else vid_match
                        if 'token=' in tok:
                            tok_m = re.search(r'token=([^&"\']+)', tok)
                            if tok_m: tok = tok_m.group(1)
                        try:
                            p = json.loads(base64.urlsafe_b64decode(tok.split('.')[1] + '=='))
                            thumb_m = re.search(r'<img[^>]+src="([^"]+)"', li)
                            thumb_url = thumb_m.group(1) if thumb_m else ''
                            media_items.append({
                                'type': 'video',
                                'url': f"https://dl.snapcdn.app/get?token={tok}",
                                'direct_cdn': p.get('url'),
                                'filename': p.get('filename'),
                                'thumbnail': thumb_url,
                                'is_video': True
                            })
                            continue
                        except Exception:
                            pass

                    # 2. Jika bukan video, cari link download gambar (abaikan thumbnail preview)
                    img_match = re.search(r'<a[^>]+href="([^"]*token=[^"]*)"[^>]*title="Download (?:Image|Photo)"', li) or \
                                re.search(r'<a[^>]+title="Download (?:Image|Photo)"[^>]+href="([^"]*token=[^"]*)"', li) or \
                                re.search(r'<a[^>]+href="([^"]*token=[^"]*)"', li)

                    if img_match:
                        tok_str = img_match.group(1)
                        tok = tok_str
                        if 'token=' in tok:
                            tok_m = re.search(r'token=([^&"\']+)', tok)
                            if tok_m: tok = tok_m.group(1)
                        try:
                            p = json.loads(base64.urlsafe_b64decode(tok.split('.')[1] + '=='))
                            thumb_m = re.search(r'<img[^>]+src="([^"]+)"', li)
                            thumb_url = thumb_m.group(1) if thumb_m else f"https://dl.snapcdn.app/get?token={tok}"
                            media_items.append({
                                'type': 'image',
                                'url': f"https://dl.snapcdn.app/get?token={tok}",
                                'direct_cdn': p.get('url'),
                                'filename': p.get('filename'),
                                'thumbnail': thumb_url,
                                'is_video': False
                            })
                        except Exception:
                            pass

                if media_items:
                    return media_items

    except Exception:
        pass

    return []

def get_instagram_info(url: str) -> dict:
    """
    Mengambil info Reels, Album Slide Carousel, atau Foto Instagram.
    Mendukung deteksi otomatis Album Slide untuk mengaktifkan UI Photo/Slide Mode,
    serta deteksi presisi Video Reels dengan probe resolusi & durasi.
    """
    clean_url = (url or '').split('?')[0].strip()

    author = "Instagram User"
    clean_title = "Instagram Media"
    og_thumb = ""

    # 1. Ekstraksi OpenGraph Metadata untuk Title & Creator yang akurat
    try:
        resp = requests.get(clean_url, headers=IG_CRAWLER_HEADERS, timeout=8)
        if resp.status_code == 200:
            page_html = resp.text
            og_title_m = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']', page_html)
            og_img_m = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', page_html)
            og_desc_m = re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']', page_html)

            raw_title = html.unescape(og_title_m.group(1)) if og_title_m else ''
            raw_desc = html.unescape(og_desc_m.group(1)) if og_desc_m else ''
            og_thumb = html.unescape(og_img_m.group(1)) if og_img_m else ''

            auth_match = re.search(r'^(?:Instagram post by\s+)?([^:•|]+?)(?:\s+di\s+Instagram|\s+on\s+Instagram|\s+shared a post|\s+•|:)', raw_title, re.IGNORECASE) or \
                         re.search(r'^(.+?)(?:\s+di\s+Instagram|\s+on\s+Instagram)', raw_title, re.IGNORECASE)
            if auth_match:
                author = auth_match.group(1).strip()

            cap_match = re.search(r':\s*“([\s\S]+?)”', raw_title) or re.search(r':\s*"([\s\S]+?)"', raw_title) or re.search(r':\s*([\s\S]+)$', raw_title)
            if cap_match:
                clean_title = cap_match.group(1).strip()
            elif raw_desc and not any(k in raw_desc.lower() for k in ['likes', 'comments', 'suka', 'komentar']):
                clean_title = raw_desc.strip()
            elif raw_title:
                clean_title = raw_title.strip()
    except Exception:
        pass

    # 2. Ambil media items via Multi-Media Resolver
    media_items = fetch_instagram_media(clean_url)

    # 3. Klasifikasi Media
    display_title = f"{author}: {clean_title[:80]}" if author != "Instagram User" else clean_title[:80]

    if media_items:
        # Kasus A: Album Carousel / Slide (> 1 media item unik)
        if len(media_items) > 1:
            slide_count = len(media_items)
            images = [m['url'] for m in media_items]
            thumb = media_items[0].get('thumbnail') or media_items[0]['url'] or og_thumb
            return {
                'title': display_title,
                'clean_title': clean_title[:100],
                'author': author,
                'thumbnail': thumb,
                'is_slide': True,
                'slide_count': slide_count,
                'media_count': slide_count,
                'width': 1440,
                'height': 1920,
                'resolution_label': "HD Original",
                'duration_string': f"{slide_count} Foto Slide",
                'images': images,
                'platform': 'Instagram'
            }

        # Kasus B: 1 Video Tunggal (Reels / Post Video)
        item = media_items[0]
        if item.get('is_video'):
            video_url = item.get('url')
            thumb = item.get('thumbnail') or og_thumb

            # Probe resolusi, durasi, codec video secara cepat
            probe_info = {}
            if video_url:
                probe_info = probe_media_stream(video_url, timeout=5)

            w = probe_info.get('width')
            h = probe_info.get('height')
            fps = probe_info.get('fps')
            dur = probe_info.get('duration', 0)
            codec = probe_info.get('codec') or 'h264'
            res_lbl = probe_info.get('resolution_label') or (f"{h}p" if h else "HD Video")

            dur_str = ""
            if dur:
                m_total, s = divmod(int(dur), 60)
                dur_h, dur_m = divmod(m_total, 60)
                dur_str = f"{dur_h}:{dur_m:02d}:{s:02d}" if dur_h else f"{dur_m:02d}:{s:02d}"

            return {
                'title': display_title,
                'clean_title': clean_title[:100],
                'author': author,
                'thumbnail': thumb,
                'is_slide': False,
                'is_video': True,
                'video_url': video_url,
                'width': w,
                'height': h,
                'fps': fps,
                'duration': dur,
                'duration_string': dur_str,
                'codec': codec,
                'resolution_label': res_lbl,
                'platform': 'Instagram'
            }

        # Kasus C: 1 Foto Tunggal
        thumb = item.get('thumbnail') or item.get('url') or og_thumb
        return {
            'title': display_title,
            'clean_title': clean_title[:100],
            'author': author,
            'thumbnail': thumb,
            'is_slide': True,
            'slide_count': 1,
            'is_photo': True,
            'width': 1440,
            'height': 1920,
            'resolution_label': "HD Photo",
            'duration_string': "1 Foto HD",
            'images': [item['url']],
            'platform': 'Instagram'
        }

    # Fallback OpenGraph
    return {
        'title': display_title,
        'clean_title': clean_title[:100],
        'author': author,
        'thumbnail': og_thumb,
        'is_slide': False,
        'platform': 'Instagram'
    }

def download_instagram(url: str, output_dir: str, ui_queue=None, options=None, abort_checker=None) -> bool:
    """
    Unduh media Instagram (Reels Video, Slide Foto Carousel, atau Single Photo).
    - Jika multi-slide, seluruh foto HD disimpan ke dalam subfolder [Instagram Slide].
    - Jika video reels, diunduh langsung via stream HD dan di-remux ke MP4.
    - Jika stream Tier 1 tidak ditemukan, otomatis fallback ke Tier 2 (yt-dlp).
    """
    if options is None:
        options = {}
    mode = options.get('mode', 'video_audio')
    audio_format = options.get('audio_format', 'mp3')

    clean_url = (url or '').split('?')[0].strip()
    if ui_queue:
        ui_queue.put({"type": "log", "text": "[TIER 1] Mencoba ekstraksi media Instagram...\n"})

    try:
        author = ""
        clean_title = "Instagram Media"
        og_thumb = ""
        try:
            resp_og = requests.get(clean_url, headers=IG_CRAWLER_HEADERS, timeout=8)
            if resp_og.status_code == 200:
                raw_html = resp_og.text
                og_i = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', raw_html)
                if og_i:
                    og_thumb = html.unescape(og_i.group(1))
                og_t = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']', raw_html)
                if og_t:
                    t_str = html.unescape(og_t.group(1))
                    auth_m = re.search(r'^(?:Instagram post by\s+)?([^:•|]+?)(?:\s+di\s+Instagram|\s+on\s+Instagram|\s+shared a post|\s+•|:)', t_str, re.IGNORECASE) or \
                             re.search(r'^(.+?)(?:\s+di\s+Instagram|\s+on\s+Instagram)', t_str, re.IGNORECASE)
                    if auth_m:
                        author = auth_m.group(1).strip()
                    cap_m = re.search(r':\s*“([\s\S]+?)”', t_str) or re.search(r':\s*"([\s\S]+?)"', t_str) or re.search(r':\s*([\s\S]+)$', t_str)
                    if cap_m:
                        clean_title = cap_m.group(1).strip()
                    else:
                        clean_title = t_str
        except Exception:
            pass

        base_name = sanitize_filename(f"{author} - {clean_title[:60]}" if author else clean_title[:60])
        if not base_name:
            base_name = "Instagram_Media"

        media_items = fetch_instagram_media(clean_url)

        # -------------------------------------------------------------
        # KASUS A: Multi-Slide Carousel (Foto / Video)
        # -------------------------------------------------------------
        if media_items and len(media_items) > 1:
            folder_name = base_name if base_name else "Instagram_Slide"
            slide_folder = os.path.join(output_dir, folder_name)
            os.makedirs(slide_folder, exist_ok=True)

            total_items = len(media_items)
            if ui_queue:
                ui_queue.put({"type": "log", "text": f"[TIER 1] Terdeteksi Album Slide Instagram ({total_items} item HD).\n"})
                ui_queue.put({"type": "log", "text": f"[TIER 1] Menyimpan ke folder: {slide_folder}\n"})

            downloaded_count = 0
            for i, item in enumerate(media_items, 1):
                if abort_checker and abort_checker():
                    return False

                is_vid = item.get('is_video', False)
                prefix = "video" if is_vid else "foto"
                ext = ".mp4" if is_vid else ".jpg"
                dest_path = os.path.join(slide_folder, f"{prefix}_{i:02d}{ext}")
                label = f"Slide {i}/{total_items}"

                download_url = item.get('url') or item.get('direct_cdn')
                dl_ok = stream_download_file(download_url, dest_path, ui_queue, abort_checker, label=label)
                if not dl_ok and item.get('direct_cdn') and item.get('direct_cdn') != download_url:
                    dl_ok = stream_download_file(item.get('direct_cdn'), dest_path, ui_queue, abort_checker, label=f"{label} (Mirror)")

                if dl_ok and os.path.exists(dest_path) and os.path.getsize(dest_path) > 100:
                    if not is_vid:
                        normalize_image_to_jpeg(dest_path)
                    downloaded_count += 1
                else:
                    if ui_queue:
                        ui_queue.put({"type": "log", "text": f"[PERINGATAN] Gagal mengunduh {label}.\n"})

            if downloaded_count > 0:
                if ui_queue:
                    ui_queue.put({"type": "log", "text": f"\n--- UNDUHAN SUKSES (Instagram Slide) ---\nFolder: {slide_folder}\nBerhasil mengunduh {downloaded_count} item HD!\n"})
                    ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
                return True
            return False

        # -------------------------------------------------------------
        # KASUS B: 1 Video (Reels)
        # -------------------------------------------------------------
        video_url = None
        if media_items and len(media_items) == 1 and media_items[0].get('is_video'):
            video_url = media_items[0].get('url') or media_items[0].get('direct_cdn')

        # Fallback ke OpenGraph og:video jika ada
        if not video_url:
            resp_vid = requests.get(clean_url, headers=IG_CRAWLER_HEADERS, timeout=8)
            og_video = re.search(r'<meta\s+property=["\']og:video(?::secure_url)?["\']\s+content=["\']([^"\']+)["\']', resp_vid.text)
            if og_video:
                video_url = html.unescape(og_video.group(1))
            if not og_thumb:
                og_i = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', resp_vid.text)
                if og_i:
                    og_thumb = html.unescape(og_i.group(1))

        if video_url:
            if ui_queue:
                ui_queue.put({"type": "log", "text": "[TIER 1] Menemukan video Instagram Reels/Post!\n"})

            raw_path = os.path.join(output_dir, f"{base_name}_raw.mp4")
            final_path = os.path.join(output_dir, f"{base_name}.mp4")

            success = stream_download_file(video_url, raw_path, ui_queue, abort_checker, label="Unduh Instagram Reels")
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
            thumb_url = ""
            if media_items:
                thumb_url = media_items[0].get('thumbnail') or ""
            if not thumb_url:
                thumb_url = og_thumb

            if embed_thumb and thumb_url and saved_path and os.path.exists(saved_path):
                embed_thumbnail_to_media(saved_path, thumb_url, ui_queue, abort_checker)

            if ui_queue:
                ui_queue.put({"type": "log", "text": f"\n--- UNDUHAN SUKSES (Instagram Reels HD) ---\nFile: {saved_path}\n"})
                ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
            return True

        # -------------------------------------------------------------
        # KASUS C: 1 Foto Saja
        # -------------------------------------------------------------
        if media_items and len(media_items) == 1 and not media_items[0].get('is_video'):
            item = media_items[0]
            final_img = os.path.join(output_dir, f"{base_name}.jpg")
            dl_url = item.get('url') or item.get('direct_cdn')
            success = stream_download_file(dl_url, final_img, ui_queue, abort_checker, label="Unduh Foto Instagram")
            if not success and item.get('direct_cdn'):
                success = stream_download_file(item.get('direct_cdn'), final_img, ui_queue, abort_checker, label="Unduh Foto Instagram (Mirror)")

            if success and os.path.exists(final_img) and os.path.getsize(final_img) > 100:
                normalize_image_to_jpeg(final_img)
                if ui_queue:
                    ui_queue.put({"type": "log", "text": f"\n--- UNDUHAN SUKSES (Instagram Photo HD) ---\nFile: {final_img}\n"})
                    ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
                return True
            return False

    except Exception as e:
        if ui_queue:
            ui_queue.put({"type": "log", "text": f"[TIER 1 ERROR] {e}\n"})

    if ui_queue:
        ui_queue.put({"type": "log", "text": "[TIER 1] Beralih ke Engine Fallback Tier 2 (yt-dlp)...\n"})
    return False
