import os
import re
import html as html_lib
import requests
from engines.base import (
    DEFAULT_HEADERS, sanitize_filename, stream_download_file,
    fast_remux_mp4, extract_audio_from_video, embed_thumbnail_to_media,
    probe_media_stream, postprocess_video
)

def extract_meta_content(html_text: str, prop: str) -> str:
    """
    Ekstrak nilai 'content' dari tag <meta> secara fleksibel
    baik attribute content berada di depan maupun di belakang property/name.
    Contoh:
    <meta content="..." property="og:title" />
    <meta property="og:title" content="..." />
    """
    m = re.search(r'<meta[^>]+(?:property|name)=["\']' + re.escape(prop) + r'["\'][^>]+content=["\']([^"\']+)["\']', html_text, re.IGNORECASE)
    if m:
        return html_lib.unescape(m.group(1).strip())
    m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']' + re.escape(prop) + r'["\']', html_text, re.IGNORECASE)
    if m:
        return html_lib.unescape(m.group(1).strip())
    return ''

def get_pinterest_info(url: str) -> dict:
    """
    Mengambil metadata postingan Pinterest via OpenGraph & HTML scraper.
    Mendukung shortlink (pin.it), link canonical pinterest.com, video, GIF, dan gambar HD.
    """
    clean_url = (url or '').strip()
    try:
        resp = requests.get(clean_url, headers=DEFAULT_HEADERS, timeout=12, allow_redirects=True)
        html_text = resp.text
        final_url = resp.url

        # Canonical pin URL
        pin_id_m = re.search(r'/pin/(\d+)', final_url)
        canonical_url = f"https://www.pinterest.com/pin/{pin_id_m.group(1)}/" if pin_id_m else final_url

        # Judul Pin
        raw_title = extract_meta_content(html_text, 'og:title') or extract_meta_content(html_text, 'twitter:title')
        if not raw_title:
            t_m = re.search(r'<title>([^<]+)</title>', html_text)
            raw_title = t_m.group(1) if t_m else 'Pinterest Media'
        clean_title = re.sub(r'\|\s*Pinterest.*$', '', raw_title, flags=re.IGNORECASE).strip()

        # Kreator / Pinner
        pinner_url = extract_meta_content(html_text, 'pinterestapp:pinner')
        pinner_uname = ''
        if pinner_url:
            pu_m = re.search(r'pinterest\.com\/([a-zA-Z0-9_\-]+)\/?', pinner_url)
            if pu_m:
                pinner_uname = pu_m.group(1)

        fn_m = re.search(r'"full_name":\s*"([^"]+)"', html_text)
        full_name = fn_m.group(1) if fn_m else ''

        if full_name and pinner_uname:
            author = f"{full_name} (@{pinner_uname})"
        elif full_name:
            author = full_name
        elif pinner_uname:
            author = f"@{pinner_uname}"
        else:
            author = 'Pinterest User'

        display_title = f"{author} - {clean_title}" if author and author != 'Pinterest User' else clean_title

        # Base Image / Thumbnail
        base_img = extract_meta_content(html_text, 'og:image') or extract_meta_content(html_text, 'twitter:image')
        preload_img = ''
        preload_m = re.search(r'<link[^>]+id=["\']pin-image-preload["\'][^>]+href=["\']([^"\']+)["\']', html_text)
        if preload_m:
            preload_img = preload_m.group(1).strip()
        if not base_img and preload_img:
            base_img = preload_img

        # Kumpulkan kandidat thumbnail cadangan (prioritaskan resolusi asli /originals/)
        candidates = []
        if base_img:
            orig_candidate = re.sub(r'\/(?:236x|474x|736x)\/', '/originals/', base_img)
            if orig_candidate and orig_candidate not in candidates:
                candidates.append(orig_candidate)
            if base_img not in candidates:
                candidates.append(base_img)
        if preload_img and preload_img not in candidates:
            candidates.append(preload_img)

        thumb = candidates[0] if candidates else (base_img or '')

        # Deteksi Video
        video_url = extract_meta_content(html_text, 'og:video') or extract_meta_content(html_text, 'og:video:secure_url')
        if not video_url:
            mp4_matches = re.findall(r'https:\/\/(?:v1|v\.pinimg|assets)\.pinimg\.com\/videos\/[^\s"\'<>\\]+?\.mp4', html_text)
            if not mp4_matches:
                mp4_matches = re.findall(r'https:\/\/[^\s"\'<>\\]+?\.mp4', html_text)
            if mp4_matches:
                video_url = next((m for m in mp4_matches if '720w' in m or 'expMp4' in m or '1080' in m), mp4_matches[0])

        is_video = bool(video_url)

        # Resolusi & Dimensi dasar
        w_str = extract_meta_content(html_text, 'og:image:width')
        h_str = extract_meta_content(html_text, 'og:image:height')
        width = int(w_str) if w_str and w_str.isdigit() else 0
        height = int(h_str) if h_str and h_str.isdigit() else 0

        duration = 0
        dur_str = ""
        fps = 0
        codec = ""
        res_lbl = ""

        # Jika konten berupa video, probe stream untuk mendapatkan durasi dan codec akurat
        if is_video and video_url:
            meta = probe_media_stream(video_url, timeout=5)
            if meta:
                width = meta.get('width') or width
                height = meta.get('height') or height
                fps = meta.get('fps') or 30
                codec = meta.get('codec') or 'h264'
                dur_float = meta.get('duration') or 0
                duration = int(dur_float)
                if duration:
                    dur_str = f"{duration // 60:02d}:{duration % 60:02d}"
                res_lbl = meta.get('resolution_label') or ''

        if not res_lbl:
            max_d = max(width, height) if (width and height) else 0
            min_d = min(width, height) if (width and height) else 0
            if max_d >= 1920 or min_d >= 1080:
                res_lbl = "1080p FHD"
            elif max_d >= 1280 or min_d >= 720:
                res_lbl = "720p HD"
            elif max_d >= 480 or min_d >= 480:
                res_lbl = "480p"
            else:
                res_lbl = "HD Video" if is_video else "HD Original"

        # Tanggal postingan
        upload_date = ""
        date_string = ""
        date_cand = (
            extract_meta_content(html_text, 'og:updated_time') or
            extract_meta_content(html_text, 'article:published_time')
        )
        if not date_cand:
            dp_m = re.search(r'"datePublished":\s*"([^"]+)"', html_text) or re.search(r'"created_at":\s*"([^"]+)"', html_text)
            if dp_m:
                date_cand = dp_m.group(1)

        if date_cand:
            try:
                m_iso = re.search(r'(\d{4})-(\d{2})-(\d{2})', date_cand)
                if m_iso:
                    upload_date = f"{m_iso.group(1)}{m_iso.group(2)}{m_iso.group(3)}"
                    date_string = f"{m_iso.group(3)}/{m_iso.group(2)}/{m_iso.group(1)}"
            except Exception:
                pass

        # Metrik engagement (Saves & Reactions)
        view_count = 0
        like_count = 0
        saves_m = re.search(r'"repin_count":\s*(\d+)', html_text) or re.search(r'"save_count":\s*(\d+)', html_text) or re.search(r'"saves":\s*(\d+)', html_text)
        if saves_m:
            view_count = int(saves_m.group(1))

        react_m = re.search(r'"reaction_counts":\s*\{[^}]*"1":\s*(\d+)', html_text) or re.search(r'"like_count":\s*(\d+)', html_text)
        if react_m:
            like_count = int(react_m.group(1))

        desc = extract_meta_content(html_text, 'og:description') or ''

        return {
            'title': display_title,
            'clean_title': clean_title,
            'author': author,
            'thumbnail': thumb,
            'thumbnails': candidates,
            'duration': duration,
            'duration_string': dur_str if is_video else "1 Foto HD",
            'is_slide': not is_video,
            'slide_count': 1 if not is_video else 0,
            'media_count': 1,
            'has_audio': is_video,
            'width': width or (736 if not is_video else 1080),
            'height': height or (981 if not is_video else 1920),
            'fps': fps if is_video else 0,
            'codec': codec if is_video else '',
            'resolution_label': res_lbl,
            'view_count': view_count,
            'like_count': like_count,
            'upload_date': upload_date,
            'date_string': date_string,
            'platform': 'Pinterest',
            'webpage_url': canonical_url,
            'description': desc or clean_title,
            'is_video': is_video
        }
    except Exception:
        return None

def download_pinterest(url: str, output_dir: str, ui_queue=None, options=None, abort_checker=None) -> bool:
    """
    Unduh media Pinterest (Video MP4, GIF animasi, atau Foto High-Res Original).
    Otomatis menghindari icon/border statis UI dan memastikan foto uncompressed HD asli terunduh.
    """
    if options is None:
        options = {}
    mode = options.get('mode', 'video_audio')
    audio_format = options.get('audio_format', 'mp3')

    clean_url = (url or '').strip()
    if ui_queue:
        ui_queue.put({"type": "log", "text": "[TIER 1] Menghubungkan ke Pinterest Scraper Engine...\n"})

    try:
        resp = requests.get(clean_url, headers=DEFAULT_HEADERS, timeout=12, allow_redirects=True)
        html_text = resp.text

        raw_title = extract_meta_content(html_text, 'og:title') or extract_meta_content(html_text, 'twitter:title')
        if not raw_title:
            t_m = re.search(r'<title>([^<]+)</title>', html_text)
            raw_title = t_m.group(1) if t_m else 'Pinterest Media'
        raw_title = re.sub(r'\|\s*Pinterest.*$', '', raw_title, flags=re.IGNORECASE).strip()
        base_name = sanitize_filename(raw_title)

        # -------------------------------------------------------------
        # 1. Cari Video MP4
        # -------------------------------------------------------------
        video_url = extract_meta_content(html_text, 'og:video') or extract_meta_content(html_text, 'og:video:secure_url')
        if not video_url:
            mp4_matches = re.findall(r'https:\/\/(?:v1|v\.pinimg|assets)\.pinimg\.com\/videos\/[^\s"\'<>\\]+?\.mp4', html_text)
            if not mp4_matches:
                mp4_matches = re.findall(r'https:\/\/[^\s"\'<>\\]+?\.mp4', html_text)
            if mp4_matches:
                video_url = next((m for m in mp4_matches if '720w' in m or 'expMp4' in m or '1080' in m), mp4_matches[0])

        if video_url:
            if ui_queue:
                ui_queue.put({"type": "log", "text": "[TIER 1] Menemukan stream video Pinterest MP4.\n"})

            raw_container = options.get('container', 'auto') if options else 'auto'
            container = 'mp4' if raw_container in ('auto', 'best', '', None) else str(raw_container).lower()
            ext = f".{container}"

            raw_path = os.path.join(output_dir, f"{base_name}_raw.mp4")
            final_path = os.path.join(output_dir, f"{base_name}{ext}")

            success = stream_download_file(video_url, raw_path, ui_queue, abort_checker, label="Unduh Video Pinterest")
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
            thumb_url = extract_meta_content(html_text, 'og:image') or extract_meta_content(html_text, 'twitter:image')
            if embed_thumb and thumb_url and saved_path and os.path.exists(saved_path):
                embed_thumbnail_to_media(saved_path, thumb_url, ui_queue, abort_checker)

            if ui_queue:
                ui_queue.put({"type": "log", "text": f"\n--- UNDUHAN SUKSES (Pinterest Video) ---\nFile: {saved_path}\n"})
                ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
            return True

        # -------------------------------------------------------------
        # 2. Cari Animasi GIF
        # -------------------------------------------------------------
        gif_matches = re.findall(r'https:\/\/i\.pinimg\.com\/originals\/[^\s"\'<>\\]+?\.gif', html_text)
        if gif_matches:
            gif_url = gif_matches[0]
            if ui_queue:
                ui_queue.put({"type": "log", "text": "[TIER 1] Menemukan animasi Pinterest GIF.\n"})
            final_gif_path = os.path.join(output_dir, f"{base_name}.gif")
            success = stream_download_file(gif_url, final_gif_path, ui_queue, abort_checker, label="Unduh GIF Pinterest")
            if success and ui_queue:
                ui_queue.put({"type": "log", "text": f"\n--- UNDUHAN SUKSES (Pinterest GIF) ---\nFile: {final_gif_path}\n"})
                ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
            return success

        # -------------------------------------------------------------
        # 3. Cari Foto High-Res Original (Kebal Icon/Border Statis UI)
        # -------------------------------------------------------------
        base_img = extract_meta_content(html_text, 'og:image') or extract_meta_content(html_text, 'twitter:image')
        if not base_img:
            preload_m = re.search(r'<link[^>]+id=["\']pin-image-preload["\'][^>]+href=["\']([^"\']+)["\']', html_text)
            if preload_m:
                base_img = preload_m.group(1)

        img_url = None
        if base_img:
            # Transformasikan URL CDN ke path /originals/ untuk kualitas resolusi tinggi tanpa kompresi
            orig_candidate = re.sub(r'\/[0-9]+x(?:_RS)?\/', '/originals/', base_img)
            try:
                head_res = requests.head(orig_candidate, headers=DEFAULT_HEADERS, timeout=5)
                if head_res.status_code == 200:
                    img_url = orig_candidate
                else:
                    img_url = base_img
            except Exception:
                img_url = base_img

        # Fallback jika base_img tidak terdeteksi via meta
        if not img_url:
            orig_matches = re.findall(r'https:\/\/i\.pinimg\.com\/originals\/[^\s"\'<>\\]+?\.(?:jpg|png|webp)', html_text)
            # Filter keluar aset statis / logo / icon border UI Pinterest
            filtered_orig = [
                m for m in orig_matches 
                if not any(x in m.lower() for x in ['logo', 'favicon', 'd53b014d86a6b6761bf649a0ed813c2b', 'icon', 'badge', 'app_icon'])
            ]
            if filtered_orig:
                img_url = filtered_orig[0]
            elif orig_matches:
                img_url = orig_matches[0]

        if img_url:
            if ui_queue:
                ui_queue.put({"type": "log", "text": "[TIER 1] Menemukan gambar Pinterest HD.\n"})
            
            ext = ".jpg"
            if ".png" in img_url.lower():
                ext = ".png"
            elif ".webp" in img_url.lower():
                ext = ".webp"

            final_img_path = os.path.join(output_dir, f"{base_name}{ext}")
            success = stream_download_file(img_url, final_img_path, ui_queue, abort_checker, label="Unduh Foto Pinterest")
            if success and ui_queue:
                ui_queue.put({"type": "log", "text": f"\n--- UNDUHAN SUKSES (Pinterest Image) ---\nFile: {final_img_path}\n"})
                ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
            return success

    except Exception as e:
        if ui_queue:
            ui_queue.put({"type": "log", "text": f"[TIER 1 ERROR] {e}\n"})
        return False

    return False
