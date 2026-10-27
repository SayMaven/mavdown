import os
import sys
import subprocess
import shlex
import requests
from PIL import Image
from io import BytesIO
import re
import json
import queue
import html
import urllib.parse

from config import (
    YT_DLP_PATH, ARIA2_PATH, FFMPEG_PATH, NODE_PATH,
    DEFAULT_OUTPUT_DIR, load_proxy, load_organize_by_platform,
    get_ytdlp_update_dest, refresh_binary_paths, load_pixiv_session,
    get_sanitized_env
)
from engines import (
    resolve_fast_info, dispatch_fast_download, detect_platform,
    resolve_service_output_dir
)
from engines.base import cleanup_orphaned_temp_files

# Antrean pesan untuk thread safety
ui_queue = queue.Queue()

current_process = None
_abort_requested = False

def request_abort():
    global _abort_requested
    _abort_requested = True

def reset_abort():
    global _abort_requested
    _abort_requested = False

def is_abort_requested():
    global _abort_requested
    return _abort_requested

def stop_current_process():
    global current_process, _abort_requested
    _abort_requested = True
    if current_process:
        try:
            pid = current_process.pid
            if os.name == 'nt':
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, creationflags=0x08000000)
            else:
                current_process.kill()
            ui_queue.put({"type": "log", "text": "\n\n[DIBATALKAN] Proses unduhan dihentikan oleh pengguna.\n"})
        except Exception as e:
            ui_queue.put({"type": "log", "text": f"\n[ERROR] Gagal menghentikan: {e}\n"})
        finally:
            current_process = None

def create_yt_dlp_command(url, options=[]):
    command = [YT_DLP_PATH]
    command.extend(options)
    command.append(url)
    return command

# State progress download — reset setiap kali download baru dimulai
_dl_segment_count = 0   # jumlah segmen [download] Destination yang sudah terdeteksi

def reset_download_phase():
    global _dl_segment_count
    _dl_segment_count = 0

def update_progress_bar(line):
    global _dl_segment_count
    progress_data = {"type": "progress"}

    # Deteksi awal segmen baru (yt-dlp log: "[download] Destination: ...")
    if re.search(r'\[download\]\s+Destination:', line):
        _dl_segment_count += 1

    # Persen unduhan (yt-dlp native atau aria2c)
    match_yt = re.search(r'\[download\]\s+([\d.]+)%', line)
    match_aria = re.search(r'\(([\d.]+)%\)', line)

    if match_yt or match_aria:
        raw = match_yt or match_aria
        percent = float(raw.group(1))

        # 2-fase: segmen 1 = video (0–70%), segmen 2 = audio (70–100%)
        if _dl_segment_count >= 2:
            unified = 0.70 + (percent / 100.0) * 0.30
            phase_label = f"Mengunduh Audio ({percent:.1f}%)"
        elif _dl_segment_count == 1:
            unified = (percent / 100.0) * 0.70
            phase_label = f"Mengunduh Video ({percent:.1f}%)"
        else:
            unified = percent / 100.0
            phase_label = f"Mengunduh ({percent:.1f}%)"

        progress_data["value"] = min(unified, 1.0)
        progress_data["text"] = f"Status: {phase_label}"

    # Kecepatan unduhan (yt-dlp: 'at 8.50MiB/s', aria2c: 'DL:1.9MiB')
    match_speed_yt = re.search(r'at\s+([\d.]+\s*[KMGTk]i?B/s)', line)
    match_speed_aria = re.search(r'DL:([\d.]+\s*[KMGTk]i?B)', line)
    if match_speed_yt:
        progress_data["speed"] = match_speed_yt.group(1).strip()
    elif match_speed_aria:
        progress_data["speed"] = f"{match_speed_aria.group(1).strip()}/s"

    # ETA (yt-dlp: 'ETA 00:35', aria2c: 'ETA:1m10s')
    match_eta_yt = re.search(r'ETA\s+([\d:]+)', line)
    match_eta_aria = re.search(r'ETA:([0-9a-zA-Z:]+)', line)
    if match_eta_yt:
        progress_data["eta"] = match_eta_yt.group(1).strip()
    elif match_eta_aria:
        progress_data["eta"] = match_eta_aria.group(1).strip()

    # Ukuran terunduh / total (yt-dlp: '45.20MiB of 120.50MiB', aria2c: '1.7MiB/142MiB')
    match_size_yt = re.search(r'([\d.]+\s*[KMGTk]i?B)\s+of\s+~?\s*([\d.]+\s*[KMGTk]i?B)', line)
    match_size_aria = re.search(r'([\d.]+\s*[KMGTk]i?B)/([\d.]+\s*[KMGTk]i?B)', line)
    if match_size_yt:
        progress_data["size_dl"] = match_size_yt.group(1).strip()
        progress_data["size_total"] = match_size_yt.group(2).strip()
    elif match_size_aria:
        progress_data["size_dl"] = match_size_aria.group(1).strip()
        progress_data["size_total"] = match_size_aria.group(2).strip()

    # Deteksi fase penggabungan & penanaman thumbnail FFmpeg
    if "[Merger]" in line or "Merging formats into" in line:
        progress_data["value"] = 0.94
        progress_data["text"] = "Status: Menggabungkan video & audio (FFmpeg)..."
        progress_data["speed"] = "-"
        progress_data["eta"] = "-"
    elif "[Metadata]" in line or "[EmbedThumbnail]" in line or "Adding thumbnail" in line:
        progress_data["value"] = 0.98
        progress_data["text"] = "Status: Menanamkan metadata & album art..."
        progress_data["speed"] = "-"
        progress_data["eta"] = "-"

    # Kirim jika ada data progress yang relevan
    if len(progress_data) > 1:
        ui_queue.put(progress_data)

    clean_line = line.strip('\r\n')
    if clean_line:
        ui_queue.put({"type": "log", "text": f"{clean_line}\n"})


def get_video_info(url, browser_cookie="Tidak Ada", share_text=None):
    # ── Tier 1 Fast Engine Info Check (< 1s) ──
    try:
        fast_info = resolve_fast_info(url, share_text=share_text)
        if fast_info:
            title = fast_info.get('title', 'Judul Tidak Ditemukan')
            ui_queue.put({"type": "info_title", "title": f"Judul: {title}"})
            
            desc_parts = []
            author_val = fast_info.get('author') or ''
            if author_val.lower() in ('douyin user', 'douyinuser', 'user', 'none', 'douyin video', 'kreator douyin', 'akun douyin', 'facebook user', 'facebook', 'facebook media', 'instagram user', 'instagram', 'tiktok user', 'tiktok', 'bilibili creator', 'bilibili user', 'bilibili', 'pinterest user', 'pinterest'):
                author_val = ''
            
            if author_val:
                desc_parts.append(f"Kreator: {author_val}")

            if fast_info.get('is_slide'):
                sc = fast_info.get('slide_count', 0)
                w = fast_info.get('width')
                h = fast_info.get('height')
                dim_str = f"({w}x{h})" if w and h else "HD"
                if sc == 1:
                    desc_parts.append(f"Foto HD {dim_str}")
                else:
                    desc_parts.append(f"Album Slide: {sc} Foto {dim_str}" if sc else f"Album Slide {dim_str}")
                if fast_info.get('has_audio'):
                    desc_parts.append("Musik BGM")
            else:
                w = fast_info.get('width')
                h = fast_info.get('height')
                res_lbl = fast_info.get('resolution_label') or ''
                fps = fast_info.get('fps')
                codec = fast_info.get('codec') or ''
                if res_lbl or (w and h):
                    res_str = f"{res_lbl} ({w}x{h})" if res_lbl and w and h else (res_lbl or f"{w}x{h}")
                    desc_parts.append(f"Resolusi: {res_str}")
                if fps:
                    desc_parts.append(f"{fps} FPS")
                if codec:
                    desc_parts.append(f"Codec: {codec.upper()}")
            desc_parts.append(f"Diunduh via {fast_info.get('platform', 'Fast Engine')}")
            desc_text = " · ".join(desc_parts)

            raw_desc = fast_info.get('description') or ''
            if raw_desc and raw_desc.strip() != title.strip():
                final_desc = f"{raw_desc.strip()}\n\n{desc_text}"
            else:
                final_desc = desc_text

            clean_meta = {
                'title': fast_info.get('clean_title', title),
                'uploader': author_val,
                'thumbnail': fast_info.get('thumbnail', ''),
                'thumbnails': fast_info.get('thumbnails', []),
                'duration': fast_info.get('duration', 0),
                'duration_string': fast_info.get('duration_string', ''),
                'width': fast_info.get('width'),
                'height': fast_info.get('height'),
                'fps': fast_info.get('fps'),
                'codec': fast_info.get('codec'),
                'resolution_label': fast_info.get('resolution_label'),
                'formatted_size': fast_info.get('formatted_size'),
                'view_count': fast_info.get('view_count', 0),
                'like_count': fast_info.get('like_count', 0),
                'comment_count': fast_info.get('comment_count', 0),
                'share_count': fast_info.get('share_count', 0),
                'upload_date': fast_info.get('upload_date', ''),
                'date_string': fast_info.get('date_string', ''),
                'is_slide': fast_info.get('is_slide', False),
                'is_ugoira': fast_info.get('is_ugoira', False),
                'slide_count': fast_info.get('slide_count', 0),
                'has_audio': fast_info.get('has_audio', False),
                'platform': fast_info.get('platform', 'Fast Engine'),
                'webpage_url': fast_info.get('webpage_url') or url,
                'url': fast_info.get('url') or url,
                'description': final_desc
            }
            ui_queue.put({"type": "info_data", "data": clean_meta})
            
            # Kumpulkan seluruh kandidat thumbnail cadangan dari server platform
            raw_candidates = []
            if isinstance(fast_info.get('thumbnails'), list):
                raw_candidates.extend(fast_info['thumbnails'])
            for k in ('thumbnail', 'cover', 'dynamic_cover', 'origin_cover', 'preview_url'):
                v = fast_info.get(k)
                if v and isinstance(v, str):
                    raw_candidates.append(v)
            if fast_info.get('is_slide') and isinstance(fast_info.get('images'), list):
                raw_candidates.extend(fast_info['images'][:3])

            clean_candidates = []
            for u in raw_candidates:
                if u and isinstance(u, str):
                    c = html.unescape(u.strip())
                    if c.startswith('//'):
                        c = 'https:' + c
                    if c.startswith('http') and c not in clean_candidates:
                        clean_candidates.append(c)

            platform_name = str(fast_info.get('platform', '')).lower()
            thumb_loaded = False

            for cand_url in clean_candidates:
                try:
                    is_fb = ('facebook' in cand_url or 'fbcdn' in cand_url or 'fbsbx' in cand_url or platform_name == 'facebook')
                    is_pixiv = ('pixiv' in cand_url or 'pximg' in cand_url or platform_name == 'pixiv')
                    is_douyin = ('douyin' in cand_url or 'snapsave' in cand_url or 'snapdouyin' in cand_url or platform_name == 'douyin')
                    is_bilibili = ('bilibili' in cand_url or 'hdslb' in cand_url or platform_name == 'bilibili')
                    is_tiktok = ('tiktok' in cand_url or 'tikwm' in cand_url or platform_name == 'tiktok')
                    is_instagram = ('instagram' in cand_url or 'cdninstagram' in cand_url or 'snapcdn' in cand_url or platform_name == 'instagram')
                    is_pinterest = ('pinterest' in cand_url or 'pinimg' in cand_url or platform_name == 'pinterest')

                    headers = {
                        'User-Agent': 'facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)' if is_fb else 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
                        'Referer': ''
                    }

                    if is_pixiv:
                        headers['Referer'] = 'https://www.pixiv.net/'
                        px_sess = load_pixiv_session()
                        if px_sess:
                            headers['Cookie'] = f"PHPSESSID={px_sess.strip()}"
                    elif is_douyin:
                        headers['Referer'] = 'https://www.douyin.com/'
                    elif is_bilibili:
                        headers['Referer'] = 'https://www.bilibili.com/'
                    elif is_tiktok:
                        headers['Referer'] = 'https://www.tiktok.com/'
                    elif is_instagram:
                        headers['Referer'] = 'https://www.instagram.com/'
                    elif is_pinterest:
                        headers['Referer'] = 'https://www.pinterest.com/'

                    r_thumb = requests.get(cand_url, headers=headers, timeout=6)
                    if r_thumb.status_code == 200 and len(r_thumb.content) > 100:
                        # Validasi integritas gambar dengan Pillow
                        Image.open(BytesIO(r_thumb.content)).verify()
                        ui_queue.put({"type": "info_thumb_data", "image_data": r_thumb.content})
                        thumb_loaded = True
                        break
                except Exception:
                    continue

            # Direct Image Bytes jika sudah diunduh oleh generic engine
            if not thumb_loaded and fast_info.get('_direct_image_bytes'):
                ui_queue.put({"type": "info_thumb_data", "image_data": fast_info['_direct_image_bytes']})
                thumb_loaded = True

            # Fallback pamungkas: Ekstraksi 1 frame video via ffmpeg jika semua CDN thumbnail server gagal
            if not thumb_loaded and fast_info.get('video_url'):
                try:
                    v_url = fast_info['video_url']
                    cmd = [
                        FFMPEG_PATH,
                        '-headers', 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\r\n',
                        '-ss', '00:00:01',
                        '-i', v_url,
                        '-vframes', '1',
                        '-f', 'image2pipe',
                        '-vcodec', 'mjpeg',
                        'pipe:1'
                    ]
                    startupinfo = None
                    if sys.platform == "win32":
                        startupinfo = subprocess.STARTUPINFO()
                        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        startupinfo.wShowWindow = subprocess.SW_HIDE
                    ff_res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=6, startupinfo=startupinfo)
                    if ff_res.returncode == 0 and len(ff_res.stdout) > 500:
                        Image.open(BytesIO(ff_res.stdout)).verify()
                        ui_queue.put({"type": "info_thumb_data", "image_data": ff_res.stdout})
                        thumb_loaded = True
                except Exception:
                    pass

            if not thumb_loaded:
                ui_queue.put({"type": "info_thumb", "text": "Pratinjau media tidak tersedia.", "image": None})
            return
    except Exception:
        pass

    detected_plat = detect_platform(url)
    info_options = [
        "--skip-download", "--print-json", "--no-playlist", 
        "--js-runtimes", f"node:{NODE_PATH}",
        "--ffmpeg-location", os.path.dirname(FFMPEG_PATH),
        "--no-config-locations",
    ]
    if detected_plat == 'youtube':
        info_options.extend([
            "--impersonate", "chrome",
            "--extractor-args", "youtube:player_client=web_embedded,android,web"
        ])
    else:
        info_options.extend([
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ])
    proxy_val = load_proxy()
    if proxy_val:
        info_options.extend(["--proxy", proxy_val])
    active_cookie = browser_cookie
    if not active_cookie or active_cookie.lower() == "tidak ada":
        from config import load_browser_cookie
        active_cookie = load_browser_cookie()
    if active_cookie and active_cookie.lower() != "tidak ada":
        info_options.extend(["--cookies-from-browser", active_cookie.lower()])

    info_command = create_yt_dlp_command(url, options=info_options)
    startupinfo = None
    if os.name == 'nt': 
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
    try:
        ui_queue.put({"type": "info_title", "title": "Mengambil Info..."})
        ui_queue.put({"type": "info_thumb", "text": "Mengambil Thumbnail...", "image": None})
        
        try:
            result = subprocess.run(
                info_command, capture_output=True, text=True, check=True,
                timeout=45, stdin=subprocess.DEVNULL, startupinfo=startupinfo,
                env=get_sanitized_env(), encoding='utf-8', errors='ignore'
            )
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as run_err:
            retry_success = False
            # Fallback 1: Jika impersonate chrome bermasalah di IP tertentu, coba tanpa impersonate
            if "--impersonate" in info_options:
                try:
                    fallback_options = [opt for opt in info_options if opt not in ("--impersonate", "chrome")]
                    fallback_cmd = create_yt_dlp_command(url, options=fallback_options)
                    result = subprocess.run(
                        fallback_cmd, capture_output=True, text=True, check=True,
                        timeout=45, stdin=subprocess.DEVNULL, startupinfo=startupinfo,
                        env=get_sanitized_env(), encoding='utf-8', errors='ignore'
                    )
                    retry_success = True
                except Exception:
                    pass
            
            # Fallback 2: Jika terdeteksi tantangan bot atau rate-limit 429, fallback ke Android client
            if not retry_success and detected_plat == 'youtube':
                try:
                    emergency_options = [
                        opt for opt in info_options
                        if opt not in ("--impersonate", "chrome", "--extractor-args", "youtube:player_client=web_embedded,android,web")
                    ]
                    emergency_options.extend(["--extractor-args", "youtube:player_client=android"])
                    emergency_cmd = create_yt_dlp_command(url, options=emergency_options)
                    result = subprocess.run(
                        emergency_cmd, capture_output=True, text=True, check=True,
                        timeout=45, stdin=subprocess.DEVNULL, startupinfo=startupinfo,
                        env=get_sanitized_env(), encoding='utf-8', errors='ignore'
                    )
                    retry_success = True
                except Exception:
                    pass

            if not retry_success:
                raise run_err

        stdout_text = result.stdout.strip()
        if not stdout_text:
            raise Exception("Respons info video kosong.")
            
        first_line = stdout_text.splitlines()[0]
        info = json.loads(first_line)
        title = info.get('title', 'Judul Tidak Ditemukan')

        # Lengkapi metadata video generic via probe_media_stream (FFprobe) jika durasi atau resolusi belum ada
        if detected_plat == 'generic' or not info.get('duration') or not info.get('width'):
            try:
                from engines.base import probe_media_stream
                target_probe_url = info.get('url') or url
                probe_res = probe_media_stream(target_probe_url, timeout=6)
                if probe_res:
                    if not info.get('width') and probe_res.get('width'):
                        info['width'] = probe_res['width']
                    if not info.get('height') and probe_res.get('height'):
                        info['height'] = probe_res['height']
                    if not info.get('duration') and probe_res.get('duration'):
                        info['duration'] = probe_res['duration']
                    if not info.get('fps') and probe_res.get('fps'):
                        info['fps'] = probe_res['fps']
                    if not info.get('codec') and probe_res.get('codec'):
                        info['codec'] = probe_res['codec']
                    if probe_res.get('resolution_label'):
                        info['resolution_label'] = probe_res['resolution_label']
            except Exception:
                pass

        # Deteksi otomatis jika media generic adalah gambar langsung
        ext_check = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
        is_direct_img = (
            ext_check in ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.avif') or
            str(info.get('vcodec') or '').lower() in ('png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif') or
            str(info.get('ext') or '').lower() in ('png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif')
        )
        if is_direct_img:
            info['is_slide'] = True
            info['slide_count'] = 1
            info['duration'] = 0
            info['duration_string'] = '1 Foto HD'
            info['fps'] = None
            if not info.get('thumbnail'):
                info['thumbnail'] = info.get('url') or url

        # Format string durasi yang rapi
        if not info.get('duration_string') and info.get('duration'):
            try:
                dur_sec = float(info['duration'])
                if dur_sec > 0:
                    m, s = divmod(int(dur_sec), 60)
                    h, m = divmod(m, 60)
                    info['duration_string'] = f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
            except Exception:
                pass

        ui_queue.put({"type": "info_title", "title": f"Judul: {title}"})
        ui_queue.put({"type": "info_data", "data": info})

        # Kumpulkan kandidat thumbnail dari yt-dlp metadata
        raw_thumbs = info.get('thumbnails') or []
        candidate_thumbs = []
        if isinstance(raw_thumbs, list) and raw_thumbs:
            sorted_thumbs = sorted(
                [t for t in raw_thumbs if isinstance(t, dict) and t.get('url')],
                key=lambda x: (x.get('preference', 0), (x.get('width', 0) or 0) * (x.get('height', 0) or 0)),
                reverse=True
            )
            for t in sorted_thumbs:
                u = t.get('url')
                if u and u.startswith('http') and u not in candidate_thumbs:
                    candidate_thumbs.append(u)

        main_thumb = info.get('thumbnail') or (info.get('url') if is_direct_img else None)
        if main_thumb and main_thumb.startswith('http') and main_thumb not in candidate_thumbs:
            candidate_thumbs.insert(0, main_thumb)

        thumb_loaded = False
        for c_url in candidate_thumbs:
            try:
                r_t = requests.get(c_url, timeout=6)
                if r_t.status_code == 200 and len(r_t.content) > 100:
                    Image.open(BytesIO(r_t.content)).verify()
                    ui_queue.put({"type": "info_thumb_data", "image_data": r_t.content})
                    thumb_loaded = True
                    break
            except Exception:
                continue

        # Fallback ekstraksi thumbnail frame via FFmpeg untuk video generic / direct stream
        if not thumb_loaded and not is_direct_img and os.path.exists(FFMPEG_PATH):
            try:
                target_stream = info.get('url') or url
                dur_val = float(info.get('duration') or 0)
                ss_time = "00:00:03" if (dur_val == 0 or dur_val > 10) else "00:00:01"
                cmd = [
                    FFMPEG_PATH,
                    '-headers', 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\r\n',
                    '-ss', ss_time,
                    '-i', target_stream,
                    '-vframes', '1',
                    '-f', 'image2pipe',
                    '-vcodec', 'mjpeg',
                    'pipe:1'
                ]
                startupinfo_ff = None
                if sys.platform == "win32":
                    startupinfo_ff = subprocess.STARTUPINFO()
                    startupinfo_ff.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo_ff.wShowWindow = subprocess.SW_HIDE
                ff_res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=7, startupinfo=startupinfo_ff)
                if ff_res.returncode == 0 and len(ff_res.stdout) > 500:
                    Image.open(BytesIO(ff_res.stdout)).verify()
                    ui_queue.put({"type": "info_thumb_data", "image_data": ff_res.stdout})
                    thumb_loaded = True
            except Exception:
                pass

        if not thumb_loaded:
            ui_queue.put({"type": "info_thumb", "text": "Thumbnail tidak ditemukan.", "image": None})
    except subprocess.CalledProcessError as e:
        # Fallback khusus video generic/direct stream yang tidak dikenali extractor bawaan yt-dlp
        if detected_plat == 'generic':
            try:
                from engines.base import probe_media_stream
                probe_res = probe_media_stream(url, timeout=6)
                if probe_res and (probe_res.get('width') or probe_res.get('duration')):
                    parsed_path = urllib.parse.urlparse(url).path
                    base_name = os.path.basename(parsed_path) or 'Direct Video'
                    title_cand = os.path.splitext(base_name)[0] or 'Direct Video'
                    dur_sec = float(probe_res.get('duration', 0) or 0)
                    m, s = divmod(int(dur_sec), 60)
                    h, m = divmod(m, 60)
                    dur_str = f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
                    synthetic_info = {
                        'title': title_cand,
                        'uploader': 'Media Generic',
                        'width': probe_res.get('width'),
                        'height': probe_res.get('height'),
                        'duration': dur_sec,
                        'duration_string': dur_str,
                        'fps': probe_res.get('fps'),
                        'codec': probe_res.get('codec'),
                        'resolution_label': probe_res.get('resolution_label', 'HD'),
                        'platform': 'generic',
                        'webpage_url': url,
                        'url': url
                    }
                    ui_queue.put({"type": "info_title", "title": f"Judul: {title_cand}"})
                    ui_queue.put({"type": "info_data", "data": synthetic_info})

                    if os.path.exists(FFMPEG_PATH):
                        ss_time = '00:00:03' if dur_sec > 5 else '00:00:01'
                        cmd = [
                            FFMPEG_PATH,
                            '-ss', ss_time,
                            '-i', url,
                            '-vframes', '1',
                            '-f', 'image2pipe',
                            '-vcodec', 'mjpeg',
                            'pipe:1'
                        ]
                        startupinfo_ff = None
                        if sys.platform == "win32":
                            startupinfo_ff = subprocess.STARTUPINFO()
                            startupinfo_ff.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                            startupinfo_ff.wShowWindow = subprocess.SW_HIDE
                        ff_res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=7, startupinfo=startupinfo_ff)
                        if ff_res.returncode == 0 and len(ff_res.stdout) > 500:
                            Image.open(BytesIO(ff_res.stdout)).verify()
                            ui_queue.put({"type": "info_thumb_data", "image_data": ff_res.stdout})
                            return
            except Exception:
                pass

        err_msg = e.stderr or ""
        reason = "Gagal mendapatkan info video (url error)."
        if "This video is unavailable" in err_msg:
            reason = "Video tidak tersedia di YouTube (mungkin dihapus, privat, atau dibatasi wilayah)."
        elif "Private video" in err_msg:
            reason = "Video bersifat privat. Diperlukan cookie login akun di Pengaturan."
        elif "Sign in to confirm your age" in err_msg:
            reason = "Video dibatasi usia (+18). Gunakan Cookie Browser di Pengaturan."
        
        ui_queue.put({"type": "info_title", "title": reason})
        ui_queue.put({"type": "info_thumb", "text": reason, "image": None})
        ui_queue.put({"type": "log", "text": f"\n[YT-DLP ERROR] {err_msg.strip()}\n"})
    except FileNotFoundError:
        ui_queue.put({"type": "info_title", "title": "ERROR: yt-dlp.exe tidak ditemukan di bin/"})
    except Exception as e:
        ui_queue.put({"type": "info_title", "title": f"Error Info: {e}"})
        ui_queue.put({"type": "info_thumb", "text": "Gagal mengambil thumbnail.", "image": None})

def convert_srt_file_to_lrc(srt_path, lrc_path):
    try:
        with open(srt_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        lrc_lines = []
        blocks = content.strip().split('\n\n')
        for block in blocks:
            lines = [l.strip() for l in block.strip().split('\n') if l.strip()]
            if len(lines) >= 3 and '-->' in lines[1]:
                time_line = lines[1]
                text = " ".join(lines[2:]).strip()
                # Clean ASS tags like {\b1}, HTML tags like <c>, and \h escape codes (hard space)
                text = re.sub(r'\{[^}]*\}', '', text)
                text = re.sub(r'<[^>]*>', '', text)
                text = text.replace('\\h', ' ').replace('\\N', ' ')
                text = re.sub(r'\s+', ' ', text).strip()
                if text:
                    start_time = time_line.split('-->')[0].strip().replace(',', '.')
                    parts = start_time.split(':')
                    if len(parts) == 3:
                        h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
                        total_min = h * 60 + m
                        sec = int(s)
                        cs = int(round((s - sec) * 100))
                        lrc_lines.append(f"[{total_min:02d}:{sec:02d}.{cs:02d}]{text}")
        if lrc_lines:
            with open(lrc_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(lrc_lines) + "\n")
            return True
    except Exception:
        pass
    return False

def expand_sub_langs(subs_lang_str: str) -> str:
    """
    Ekspansi bahasa subtitle agar mencakup varian bahasa resmi & auto-caption
    (seperti en, en-US, en-GB, en-orig, en-nP7...) tanpa mencocokkan terjemahan ke bahasa lain (seperti en-zh, en-de, id-zh).
    """
    if not subs_lang_str:
        return "id,id-ID,id-orig,id-id,id-nP7.*,en,en-US,en-GB,en-orig,en-en,en-nP7.*"
    raw = subs_lang_str.strip().lower()
    if raw in ("all", ".*"):
        return "all"
    
    tokens = [t.strip() for t in subs_lang_str.split(",") if t.strip()]
    expanded = []
    for t in tokens:
        expanded.append(t)
        t_clean = t.split('-')[0].lower()
        if t_clean == "en":
            expanded.extend(["en-US", "en-GB", "en-orig", "en-en", "en-nP7.*"])
        elif t_clean == "id":
            expanded.extend(["id-ID", "id-orig", "id-id", "id-nP7.*"])
        elif t_clean == "ja":
            expanded.extend(["ja-JP", "ja-orig", "ja-ja", "ja-nP7.*"])
        elif t_clean == "zh":
            expanded.extend(["zh-Hans", "zh-Hant", "zh-CN", "zh-TW", "zh-HK", "zh-orig", "zh-nP7.*"])
        elif t_clean == "ko":
            expanded.extend(["ko-KR", "ko-orig", "ko-ko", "ko-nP7.*"])
        elif t_clean == "es":
            expanded.extend(["es-ES", "es-419", "es-orig", "es-nP7.*"])
        else:
            expanded.extend([f"{t_clean}-{t_clean}", f"{t_clean}-orig", f"{t_clean}-nP7.*"])
            
    seen = set()
    res = []
    for item in expanded:
        if item not in seen:
            seen.add(item)
            res.append(item)
    return ",".join(res)

def process_downloaded_subtitles(output_dir: str, download_start_time: float, is_audio_only: bool, embed_subs: bool, download_subs: bool):
    """
    Deduplikasi & pembersihan subtitle setelah unduhan selesai:
    1. Mengumpulkan semua file subtitle (.srt, .vtt, .ass, .lrc, .ttml) yang baru diunduh.
    2. Membedakan antara subtitle manual buatan pembuat video vs subtitle otomatis YouTube.
    3. Jika subtitle manual ada, prioritaskan subtitle manual & hapus subtitle otomatis yang duplikat.
    4. Jika hanya ada subtitle otomatis, ubah namanya jadi bersih (contoh: Video.id.srt).
    5. Jika mode audio_only, konversi subtitle terbaik ke .lrc dan hapus sisanya.
    6. Jika embed_subs aktif di mode video: Embed Softsub ke track P0 (Default Active) via FFmpeg.
       Subtitle akan LANGSUNG TAMPIL saat video dijalankan, namun TETAP BISA DIMATIKAN/ON-OFF di player!
       Jika download_subs tidak dicentang, hapus file subtitle luar setelah embed selesai.
    """
    try:
        sub_files = []
        video_files = []

        for item in os.listdir(output_dir):
            file_path = os.path.join(output_dir, item)
            if not os.path.isfile(file_path):
                continue
            try:
                if os.path.getmtime(file_path) < download_start_time:
                    continue
            except Exception:
                pass
            
            item_lower = item.lower()
            if item_lower.endswith(('.srt', '.vtt', '.ass', '.lrc', '.ttml')):
                sub_files.append(item)
            elif item_lower.endswith(('.mp4', '.mkv', '.webm', '.mov', '.avi')):
                video_files.append(item)

        if not sub_files:
            return

        groups = {}

        for item in sub_files:
            parts = item.rsplit('.', 2)
            if len(parts) == 3:
                title, lang_tag, ext = parts[0], parts[1], parts[2]
            else:
                title, ext = os.path.splitext(item)
                title = title.lstrip('.')
                lang_tag = ""
                ext = ext.lstrip('.')
            
            lang_lower = lang_tag.lower()
            is_auto = False
            if 'np7' in lang_lower or 'srv' in lang_lower or len(lang_lower.split('-')) > 2:
                is_auto = True
            elif '-' in lang_lower:
                subparts = lang_lower.split('-')
                if len(subparts) == 2 and subparts[0] == subparts[1]:
                    is_auto = True
            
            if '-' in lang_tag and not is_auto and len(lang_tag) <= 6:
                base_lang = lang_tag
            else:
                base_lang = lang_tag.split('-')[0] if lang_tag else "default"

            key = (title, base_lang)
            if key not in groups:
                groups[key] = []
            groups[key].append((item, is_auto, lang_tag, ext))

        selected_sub_paths = []

        for (title, base_lang), items in groups.items():
            manual_subs = [x for x in items if not x[1]]
            auto_subs = [x for x in items if x[1]]

            if is_audio_only:
                best_sub = manual_subs[0] if manual_subs else auto_subs[0]
                best_file = best_sub[0]
                best_path = os.path.join(output_dir, best_file)
                target_lrc_path = os.path.join(output_dir, f"{title}.lrc")

                if best_file.lower().endswith('.lrc'):
                    if best_path != target_lrc_path and os.path.exists(best_path):
                        try:
                            if os.path.exists(target_lrc_path):
                                os.remove(target_lrc_path)
                            os.rename(best_path, target_lrc_path)
                        except Exception:
                            pass
                else:
                    convert_srt_file_to_lrc(best_path, target_lrc_path)

                for x in items:
                    fp = os.path.join(output_dir, x[0])
                    if fp != target_lrc_path and os.path.exists(fp):
                        try:
                            os.remove(fp)
                        except Exception:
                            pass
                ui_queue.put({"type": "log", "text": f"[LIRIK] Subtitle terbaik disimpan sebagai lirik -> '{title}.lrc'\n"})

            else:
                if manual_subs:
                    best_manual = manual_subs[0]
                    for x in auto_subs:
                        fp = os.path.join(output_dir, x[0])
                        if os.path.exists(fp):
                            try:
                                os.remove(fp)
                            except Exception:
                                pass
                    for x in manual_subs[1:]:
                        fp = os.path.join(output_dir, x[0])
                        if os.path.exists(fp):
                            try:
                                os.remove(fp)
                            except Exception:
                                pass
                    selected_sub_paths.append(best_manual[0])
                    ui_queue.put({"type": "log", "text": f"[SUBTITLE] Menggunakan subtitle manual asli -> '{best_manual[0]}'\n"})
                elif auto_subs:
                    best_auto = auto_subs[0]
                    best_auto_path = os.path.join(output_dir, best_auto[0])
                    target_clean_name = f"{title}.{base_lang}.{best_auto[3]}"
                    target_clean_path = os.path.join(output_dir, target_clean_name)

                    for x in auto_subs[1:]:
                        fp = os.path.join(output_dir, x[0])
                        if os.path.exists(fp):
                            try:
                                os.remove(fp)
                            except Exception:
                                pass

                    if best_auto_path != target_clean_path:
                        try:
                            if os.path.exists(target_clean_path):
                                os.remove(target_clean_path)
                            os.rename(best_auto_path, target_clean_path)
                            ui_queue.put({"type": "log", "text": f"[SUBTITLE] Subtitle otomatis dirapikan -> '{target_clean_name}'\n"})
                            selected_sub_paths.append(target_clean_name)
                        except Exception:
                            selected_sub_paths.append(best_auto[0])
                    else:
                        selected_sub_paths.append(best_auto[0])

        # ── FFmpeg Softsub Embedding (Track P0 - Default Active & ON/OFF) ───
        if embed_subs and not is_audio_only and video_files and selected_sub_paths:
            v_file = video_files[0]
            s_file = selected_sub_paths[0]
            v_path = os.path.join(output_dir, v_file)
            s_path = os.path.join(output_dir, s_file)

            if os.path.exists(v_path) and os.path.exists(s_path):
                ui_queue.put({"type": "log", "text": f"\n[EMBED SUB] Meng-embed '{s_file}' sebagai Softsub P0 (Default Aktif & Bisa ON/OFF)...\n"})
                base_vid, v_ext = os.path.splitext(v_file)
                temp_embed_file = f"{base_vid}_embed{v_ext}"

                # Tentukan codec & bahasa ISO 639-2 untuk metadata stream MP4/MKV
                sub_codec = "mov_text" if v_ext.lower() in (".mp4", ".mov", ".m4v") else "srt"
                
                parts_s = s_file.rsplit('.', 2)
                lang_code = parts_s[1].split('-')[0].lower() if len(parts_s) == 3 else "en"
                iso3_map = {"id": "ind", "en": "eng", "ja": "jpn", "zh": "zho", "ko": "kor", "es": "spa", "fr": "fra", "de": "deu", "ru": "rus"}
                lang_iso3 = iso3_map.get(lang_code, "eng")

                ff_cmd = [
                    FFMPEG_PATH, "-y",
                    "-i", v_file,
                    "-i", s_file,
                    "-map", "0:v",
                    "-map", "0:a?",
                    "-map", "0:t?",
                    "-map", "1:0",
                    "-c:v", "copy",
                    "-c:a", "copy",
                    "-c:s", sub_codec,
                    "-disposition:s:0", "default+forced",
                    "-metadata:s:s:0", f"language={lang_iso3}",
                    "-metadata:s:s:0", f"title={lang_code.upper()}",
                    temp_embed_file
                ]
                
                startupinfo = None
                if os.name == 'nt':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE

                res = subprocess.run(
                    ff_cmd, cwd=output_dir, capture_output=True, text=True,
                    startupinfo=startupinfo, encoding='utf-8', errors='ignore'
                )
                
                temp_embed_path = os.path.join(output_dir, temp_embed_file)
                if res.returncode == 0 and os.path.exists(temp_embed_path):
                    try:
                        os.remove(v_path)
                        os.rename(temp_embed_path, v_path)
                        ui_queue.put({"type": "log", "text": f"[EMBED SUB] Subtitle berhasil di-embed ke track P0! Langsung aktif saat diputar & tetap bisa di-OFF kan.\n"})
                    except Exception as e:
                        ui_queue.put({"type": "log", "text": f"[EMBED ERROR] Gagal mengganti file: {e}\n"})
                else:
                    ui_queue.put({"type": "log", "text": f"[EMBED ERROR] FFmpeg gagal embed subtitle.\n"})

            if not download_subs:
                for sf in selected_sub_paths:
                    sp = os.path.join(output_dir, sf)
                    if os.path.exists(sp):
                        try:
                            os.remove(sp)
                        except Exception:
                            pass

    except Exception as e:
        print(f"Error in process_downloaded_subtitles: {e}")

def download_video_logic(url, mode, audio_format, res, vcodec, acodec, container, download_subs, embed_subs, subs_lang, embed_thumb, use_aria2, download_playlist, custom_path, custom_cmd, browser_cookie="Tidak Ada", share_text=None, ugoira_format="mp4"):
    global current_process
    base_output_dir = custom_path if custom_path else DEFAULT_OUTPUT_DIR
    
    organize = load_organize_by_platform()
    output_dir = resolve_service_output_dir(base_output_dir, url, organize_by_platform=organize)
    
    ui_queue.put({"type": "progress", "value": 0, "text": "Progress: 0.0%"})
    reset_download_phase()  # Reset fase video/audio untuk download baru

    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        
    ui_queue.put({"type": "log", "text": f"\n\n{'='*50}\n"})
    ui_queue.put({"type": "log", "text": f"URL Sumber: {url}\n"}) 
    ui_queue.put({"type": "log", "text": f"Folder Output: {output_dir}\n"})
    
    reset_abort()

    # ── TIER 1: FAST REST ENGINE ──
    if not download_playlist and not custom_cmd:
        platform_name = detect_platform(url)
        tier1_supported = ('tiktok', 'douyin', 'twitter', 'pinterest', 'instagram', 'facebook', 'bilibili', 'pixiv')

        if platform_name in tier1_supported:
            engine_opts = {
                'mode': mode,
                'audio_format': audio_format,
                'res': res,
                'vcodec': vcodec,
                'acodec': acodec,
                'container': container,
                'ugoira_format': ugoira_format
            }
            try:
                fast_success = dispatch_fast_download(
                    url, output_dir, ui_queue, engine_opts,
                    abort_checker=is_abort_requested
                )
                if fast_success:
                    cleanup_orphaned_temp_files(output_dir)
                    ui_queue.put({"type": "download_success_meta", "url": url, "output_dir": output_dir})
                    ui_queue.put({"type": "download_finish"})
                    return
                elif is_abort_requested():
                    cleanup_orphaned_temp_files(output_dir)
                    ui_queue.put({"type": "download_finish"})
                    return
                else:
                    ui_queue.put({"type": "log", "text": f"\n[TIER 2] Melanjutkan ke Engine Fallback (yt-dlp + aria2c)...\n"})
            except Exception as e:
                ui_queue.put({"type": "log", "text": f"[TIER 1 WARNING] Terjadi kendala di Tier 1: {e}\n[TIER 2] Mengalihkan ke yt-dlp...\n"})
        else:
            if platform_name == 'youtube':
                ui_queue.put({"type": "log", "text": "\n[ENGINE] Menjalankan Engine Unduhan YouTube (yt-dlp + aria2c)...\n"})

    options = [
        "--ignore-errors", "--retries", "infinite", 
        "--fragment-retries", "infinite", 
        "--js-runtimes", f"node:{NODE_PATH}",
        "--windows-filenames",
        "--trim-filenames", "100",
        "--embed-metadata",
        "--newline",
    ]
    options.append(f"--ffmpeg-location={FFMPEG_PATH}")
    options.append("--no-config-locations")

    if platform_name == 'youtube':
        options.extend(["--impersonate", "chrome", "--extractor-args", "youtube:player_client=web_embedded,android,web"])
    else:
        options.extend(["--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"])

    proxy_val = load_proxy()
    if proxy_val:
        options.extend(["--proxy", proxy_val])
        ui_queue.put({"type": "log", "text": f"[OPT] Menggunakan Proxy: {proxy_val}\n"})
    
    active_cookie = browser_cookie
    if not active_cookie or active_cookie.lower() == "tidak ada":
        from config import load_browser_cookie
        active_cookie = load_browser_cookie()
    if active_cookie and active_cookie.lower() != "tidak ada":
        options.extend(["--cookies-from-browser", active_cookie.lower()])
        ui_queue.put({"type": "log", "text": f"[OPT] Menggunakan Cookies dari Browser: {active_cookie}\n"})
    
    if not download_playlist:
        options.append("--no-playlist")
        ui_queue.put({"type": "log", "text": "[OPT] Mode Single Video (--no-playlist)\n"})
    else:
        ui_queue.put({"type": "log", "text": "[OPT] Mode Unduh Full Playlist\n"})
    
    if custom_cmd:
        try:
            custom_args = shlex.split(custom_cmd)
            options.extend(custom_args)
            ui_queue.put({"type": "log", "text": f"[MODE] Menggunakan Perintah Custom: {custom_cmd}\n"})
        except:
            ui_queue.put({"type": "log", "text": "[ERROR] Gagal parsing custom command.\n"})
            ui_queue.put({"type": "download_finish"})
            return
    else:
        if use_aria2:
            options.extend([
                "--external-downloader", ARIA2_PATH, 
                "--external-downloader-args", "aria2c:-x 16 -k 1M --summary-interval=1 --allow-overwrite=true"
            ])
            ui_queue.put({"type": "log", "text": "[OPT] Menggunakan Aria2c sebagai downloader.\n"})
            
        if mode in ("audio", "audio_only"):
            effective_afmt = "mp3" if audio_format in ("auto", "best", "") else audio_format
            options.extend(["-f", "bestaudio", "--extract-audio", "--audio-format", effective_afmt])
            ui_queue.put({"type": "log", "text": f"[MODE] Audio Saja ({effective_afmt})\n"})
        else:
            raw_vcodec = str(vcodec or "").lower().strip()
            raw_acodec = str(acodec or "").lower().strip()
            raw_cont = str(container or "").lower().strip()

            effective_container = "mp4" if raw_cont in ("auto", "best", "") else raw_cont
            
            # Normalisasi video codec (None = tidak dibatasi / auto)
            effective_vcodec = None
            if raw_vcodec in ("h264", "avc"):
                effective_vcodec = "h264"
            elif raw_vcodec in ("vp9", "vp09"):
                effective_vcodec = "vp9"
            elif raw_vcodec in ("av1", "av01"):
                effective_vcodec = "av1"

            # Normalisasi audio codec (None = tidak dibatasi / auto)
            effective_acodec = None
            if raw_acodec in ("m4a", "mp4a", "aac"):
                effective_acodec = "m4a"
            elif raw_acodec == "opus":
                effective_acodec = "opus"

            if effective_container == "webm":
                if effective_vcodec == "h264":
                    effective_vcodec = "vp9"
                if effective_acodec == "m4a":
                    effective_acodec = "opus"
            elif effective_container == "mov":
                if effective_vcodec in ["vp9", "av1"]:
                    effective_vcodec = "h264"
                if effective_acodec == "opus":
                    effective_acodec = "m4a"

            vcodec_map = {"h264": "avc", "av1": "av01", "vp9": "vp09"}
            acodec_map = {"m4a": "mp4a", "opus": "opus"}
            
            f_video_parts = ["bestvideo"]
            if res != "best":
                f_video_parts.append(f"[height<={res}]")
            if effective_vcodec and effective_vcodec in vcodec_map:
                f_video_parts.append(f"[vcodec~={vcodec_map[effective_vcodec]}]")
                
            f_audio_parts = ["bestaudio"]
            if effective_acodec and effective_acodec in acodec_map:
                f_audio_parts.append(f"[acodec~={acodec_map[effective_acodec]}]")
                
            f_video_str = "".join(f_video_parts)
            f_audio_str = "".join(f_audio_parts)
            res_str = "" if res == "best" else f"[height<={res}]"
            
            # Tambahkan juga constraint pada format "best" (pre-muxed) dan "bestvideo" saja.
            b_str = f"best{res_str}"
            if effective_vcodec and effective_vcodec in vcodec_map:
                b_str += f"[vcodec~={vcodec_map[effective_vcodec]}]"
            
            # Jika tidak ada constraint sama sekali, pastikan 'high' diprioritaskan sebelum 'best'
            # agar tidak salah pilih 'low' di generic extractor.
            if b_str == "best":
                b_str = "high/best"
            
            format_string = (
                f"{f_video_str}+{f_audio_str}/" 
                f"{f_video_str}+bestaudio/" 
                f"bestvideo{res_str}+{f_audio_str}/" 
                f"{b_str}/"
                f"bestvideo{res_str}+bestaudio/"
                f"bestvideo+bestaudio/"
                f"high/best"
            )
            # Optimasi khusus Bilibili pada fallback yt-dlp jika tanpa cookies login:
            # Akun guest Bilibili di CDN Akamai memutus koneksi (Error 492) jika meminta 1080p.
            # Otomatis batasi ke 720p HD jika tanpa cookies agar tidak gagal / putus di 16KB.
            if detect_platform(url) == 'bilibili' and (not browser_cookie or browser_cookie.lower() == "tidak ada") and res == "best":
                format_string = (
                    "bestvideo[height<=720]+bestaudio/"
                    "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/"
                    "best[height<=720]/best"
                )

            ui_queue.put({"type": "log", "text": f"[MODE] Video (V: {vcodec}, A: {acodec}, R: {res}, C: {container})\n"})
            options.extend(["-f", format_string, "--merge-output-format", effective_container])
            
        if download_subs or embed_subs:
            lang = subs_lang.strip() if subs_lang.strip() else "id,en"
            effective_lang = expand_sub_langs(lang)
            if mode == "audio_only":
                options.extend(["--write-subs", "--write-auto-subs", "--sub-langs", effective_lang, "--convert-subs", "srt"])
                if embed_subs and not download_subs:
                    ui_queue.put({"type": "log", "text": f"[OPT] Mode Audio Saja: Lirik lagu ({lang}) otomatis dibuat sebagai file .lrc di sebelah audio.\n"})
                else:
                    ui_queue.put({"type": "log", "text": f"[OPT] Lirik lagu ({lang}) akan diunduh & disesuaikan sebagai file .lrc.\n"})
            else:
                options.extend(["--write-subs", "--write-auto-subs", "--sub-langs", effective_lang, "--convert-subs", "srt"])
                if embed_subs:
                    ui_queue.put({"type": "log", "text": f"[OPT] Subtitle ({lang}) di-embed sebagai Softsub P0 (Default Aktif & Bisa ON/OFF).\n"})
                if download_subs:
                    options.extend(["--sub-format", "srt"])
                    ui_queue.put({"type": "log", "text": f"[OPT] Subtitle ({lang}) file .srt terpisah.\n"})
                
        if embed_thumb:
            effective_afmt = "mp3" if audio_format in ("auto", "best", "", None) else str(audio_format).lower()
            effective_cont = "mp4" if container in ("auto", "best", "", None) else str(container).lower()
            thumb_supported = False
            if mode == "audio_only":
                if effective_afmt in ["mp3", "m4a", "flac", "opus", "ogg"]:
                    thumb_supported = True
            else:
                if effective_cont in ["mp4", "mkv", "mov"]:
                    thumb_supported = True
                    
            if thumb_supported:
                options.append("--embed-thumbnail")
                options.extend(["--convert-thumbnails", "jpg"])
                ui_queue.put({"type": "log", "text": "[OPT] Injeksi Thumbnail (Album Art) diaktifkan.\n"})
            else:
                target_fmt = effective_afmt if mode == "audio_only" else effective_cont
                ui_queue.put({"type": "log", "text": f"[INFO] Format .{target_fmt} tidak mendukung embed thumbnail. Opsi embed thumbnail dilewati.\n"})
                
        if download_playlist:
            options.extend(["-o", os.path.join(output_dir, "%(playlist_title|Playlist)s", "%(title).100s.%(ext)s")])
        else:
            options.extend(["-o", os.path.join(output_dir, "%(title).100s.%(ext)s")])
        
    command = create_yt_dlp_command(url, options)
    ui_queue.put({
        "type": "log",
        "text": f"\n[EKSEKUSI] Memulai proses unduhan yt-dlp{' (akselerasi aria2c 16x)' if use_aria2 else ''}...\n"
    })
    ui_queue.put({
        "type": "progress",
        "value": 0.05,
        "text": "Menghubungi server & menyiapkan stream...",
        "speed": "-",
        "eta": "-"
    })
    
    try:
        startupinfo = None
        if os.name == 'nt': 
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            
        import time
        download_start_time = time.time() - 3.0

        process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, universal_newlines=True,
            startupinfo=startupinfo, env=get_sanitized_env(), encoding='utf-8', errors='ignore'
        )
        current_process = process
        for line in iter(process.stdout.readline, ''):
            update_progress_bar(line)
        process.wait() 
        if process.returncode == 0:
            ui_queue.put({"type": "log", "text": "\n\n--- UNDUHAN SUKSES ---\n"})
            if download_subs or embed_subs:
                process_downloaded_subtitles(output_dir, download_start_time, mode == "audio_only", embed_subs, download_subs)
            
            # Khusus file generic: jika embed_thumb aktif, tanamkan thumbnail frame via FFmpeg
            if embed_thumb and platform_name == 'generic':
                try:
                    from engines.base import embed_thumbnail_to_media
                    cand_files = []
                    for itm in os.listdir(output_dir):
                        fp = os.path.join(output_dir, itm)
                        if os.path.isfile(fp) and fp.lower().endswith(('.mp4', '.mkv', '.mov', '.mp3', '.m4a')):
                            try:
                                if os.path.getmtime(fp) >= download_start_time:
                                    cand_files.append(fp)
                            except Exception:
                                pass
                    for cf in cand_files:
                        temp_cover = cf + ".tmp_cover.jpg"
                        try:
                            cmd_c = [
                                FFMPEG_PATH, "-y",
                                "-ss", "00:00:03",
                                "-i", cf,
                                "-vframes", "1",
                                "-q:v", "2",
                                temp_cover
                            ]
                            s_info = None
                            if sys.platform == "win32":
                                s_info = subprocess.STARTUPINFO()
                                s_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                                s_info.wShowWindow = subprocess.SW_HIDE
                            c_res = subprocess.run(cmd_c, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, startupinfo=s_info)
                            if c_res.returncode == 0 and os.path.exists(temp_cover) and os.path.getsize(temp_cover) > 500:
                                embed_thumbnail_to_media(cf, temp_cover, ui_queue=ui_queue)
                        finally:
                            if os.path.exists(temp_cover):
                                try: os.remove(temp_cover)
                                except Exception: pass
                except Exception:
                    pass

            cleanup_orphaned_temp_files(output_dir)
            ui_queue.put({"type": "download_success_meta", "url": url, "output_dir": output_dir, "start_time": download_start_time})
        elif current_process is None:
            # Unduhan dibatalkan pengguna
            pass
        else:
            ui_queue.put({"type": "log", "text": f"\n\n--- UNDUHAN GAGAL --- (Kode: {process.returncode})\n"})
            # Sinyal ke UI agar tombol AI Error Analyzer muncul
            ui_queue.put({"type": "download_error"})
    except FileNotFoundError:
        ui_queue.put({"type": "log", "text": "\nERROR: yt-dlp atau aria2c tidak ditemukan."})
    except Exception as e:
        ui_queue.put({"type": "log", "text": f"\nERROR Tak Terduga: {e}"})
    finally:
        current_process = None
        ui_queue.put({"type": "download_finish"})

def get_local_ytdlp_version():
    if not os.path.exists(YT_DLP_PATH):
        return None
    try:
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        res = subprocess.run(
            [YT_DLP_PATH, "--version"], capture_output=True, text=True,
            timeout=5, startupinfo=startupinfo, env=get_sanitized_env(), encoding='utf-8', errors='ignore'
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return None

def get_latest_ytdlp_version(channel: str = "stable"):
    channel = (channel or "stable").lower()
    if channel == "nightly":
        try:
            r = requests.head('https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest', allow_redirects=True, timeout=10)
            tag = r.url.split('/')[-1]
            if tag and tag.lower() != 'latest':
                return tag.lstrip('v')
        except Exception:
            pass
        try:
            r = requests.get('https://api.github.com/repos/yt-dlp/yt-dlp-nightly-builds/releases/latest', timeout=10)
            if r.status_code == 200:
                tag = r.json().get('tag_name', '')
                return tag.lstrip('v')
        except Exception:
            pass
        return None
    else:
        try:
            r = requests.head('https://github.com/yt-dlp/yt-dlp/releases/latest', allow_redirects=True, timeout=10)
            tag = r.url.split('/')[-1]
            if tag and tag.lower() != 'latest':
                return tag.lstrip('v')
        except Exception:
            pass
        try:
            r = requests.get('https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest', timeout=10)
            if r.status_code == 200:
                tag = r.json().get('tag_name', '')
                return tag.lstrip('v')
        except Exception:
            pass
        return None

def update_ytdlp_logic(channel: str = "stable"):
    channel = (channel or "stable").lower()
    channel_title = "NIGHTLY" if channel == "nightly" else "STABLE"
    url = (
        "https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest/download/yt-dlp.exe"
        if channel == "nightly" else
        "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
    )

    ui_queue.put({"type": "progress", "value": 0.05, "text": f"Memeriksa versi ({channel_title})..."})
    ui_queue.put({"type": "log", "text": f"\n\n=== MEMERIKSA UPDATE YT-DLP ({channel_title}) ===\n"})
    
    old_path = YT_DLP_PATH + ".old"
    if not os.path.exists(YT_DLP_PATH) and os.path.exists(old_path):
        try:
            os.rename(old_path, YT_DLP_PATH)
            ui_queue.put({"type": "log", "text": "Memulihkan yt-dlp.exe dari cadangan...\n"})
        except Exception as e:
            ui_queue.put({"type": "log", "text": f"Gagal memulihkan cadangan: {e}\n"})

    local_ver = get_local_ytdlp_version()
    if local_ver:
        ui_queue.put({"type": "log", "text": f"Versi Terpasang : v{local_ver}\n"})
    else:
        ui_queue.put({"type": "log", "text": "Versi Terpasang : Belum Terpasang\n"})

    ui_queue.put({"type": "log", "text": f"Channel Dipilih : {channel_title}\n"})
    ui_queue.put({"type": "log", "text": f"Memeriksa rilis terbaru di GitHub ({channel_title})...\n"})
    latest_ver = get_latest_ytdlp_version(channel)
    
    if latest_ver:
        ui_queue.put({"type": "log", "text": f"Versi Terbaru   : v{latest_ver}\n"})
    else:
        ui_queue.put({"type": "log", "text": f"Versi Terbaru   : Gagal mengambil info versi dari GitHub ({channel_title})\n"})

    if local_ver and latest_ver and local_ver == latest_ver:
        ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
        ui_queue.put({"type": "log", "text": f"\n[INFO] yt-dlp sudah menggunakan versi terbaru (v{local_ver}) untuk channel {channel_title}.\n"})
        ui_queue.put({"type": "log", "text": "=================================\n"})
        return

    if local_ver and latest_ver:
        ui_queue.put({"type": "log", "text": f"\nMemulai pembaruan ({channel_title}): v{local_ver} -> v{latest_ver}...\n"})
    else:
        ui_queue.put({"type": "log", "text": f"\nMemulai pengunduhan yt-dlp ({channel_title})...\n"})

    target_exe = get_ytdlp_update_dest()
    temp_path = target_exe + ".new"
    old_path = target_exe + ".old"
    
    try:
        bin_dir = os.path.dirname(target_exe)
        if not os.path.exists(bin_dir):
            os.makedirs(bin_dir, exist_ok=True)
            
        ui_queue.put({"type": "log", "text": f"Mengunduh file yt-dlp.exe ke {target_exe}...\n"})
        
        proxy_val = load_proxy()
        proxies = {"http": proxy_val, "https": proxy_val} if proxy_val else None
        response = requests.get(url, stream=True, timeout=30, proxies=proxies)
        response.raise_for_status()
        
        total_length = response.headers.get('content-length')
        dl = 0
        total_length = int(total_length) if total_length else 0
        
        with open(temp_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    dl += len(chunk)
                    if total_length:
                        percent = dl / total_length
                        ui_queue.put({"type": "progress", "value": percent, "text": f"Updating: {int(percent*100)}%"})
                        
        if os.path.exists(target_exe):
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except Exception:
                    pass
            try:
                os.rename(target_exe, old_path)
            except Exception:
                pass
            
        os.rename(temp_path, target_exe)
        refresh_binary_paths()
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except Exception:
                pass
            
        final_ver = get_local_ytdlp_version() or latest_ver or "Terbaru"
        ui_queue.put({"type": "log", "text": f"\n--- UPDATE BERHASIL! (yt-dlp diperbarui ke v{final_ver} [{channel_title}]) ---\n"})
    except Exception as e:
        ui_queue.put({"type": "log", "text": f"ERROR saat update: {e}\n"})
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        if not os.path.exists(target_exe) and os.path.exists(old_path):
            try:
                os.rename(old_path, target_exe)
                refresh_binary_paths()
            except Exception:
                pass
    finally:
        ui_queue.put({"type": "update_finish"})
