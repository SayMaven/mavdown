import os
import re
import time
import json
import hmac
import hashlib
import requests
import subprocess
import tempfile
import shutil
import urllib.request
from engines.base import (
    DEFAULT_HEADERS, FFMPEG_PATH, sanitize_filename, stream_download_file,
    fast_remux_mp4, extract_audio_from_video, postprocess_video,
    probe_media_stream, embed_thumbnail_to_media
)
from engines.pixiv import find_system_browser, get_free_tcp_port, _cdp_ws_connect

SNAPANY_SECRET = 'a5wU-SVyy5gXIyMbPQIfIz7UP7rCBp76U8Z8i-FtDMU'

BILIBILI_MOBILE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
    'Referer': 'https://www.bilibili.com/',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
}

def verify_bilibili_session(session: str) -> tuple[bool, str]:
    """
    Memverifikasi apakah nilai cookie sesi SESSDATA Bilibili valid dan aktif.
    Mengembalikan (is_valid, user_info_string).
    """
    if not session or not session.strip():
        return False, "Sesi Bilibili kosong."

    try:
        clean_s = session.strip()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
            'Referer': 'https://www.bilibili.com/'
        }
        cookies = {'SESSDATA': clean_s}
        resp = requests.get('https://api.bilibili.com/x/web-interface/nav', headers=headers, cookies=cookies, timeout=10)
        if resp.status_code == 200:
            res_j = resp.json()
            data = res_j.get('data') or {}
            if data.get('isLogin'):
                uname = data.get('uname') or 'Akun Bilibili'
                mid = data.get('mid')
                vip_str = " (VIP)" if data.get('vipStatus') == 1 else ""
                label = f"{uname}{vip_str} (MID: {mid})" if mid else uname
                return True, label
    except Exception as e:
        return False, f"Gagal menghubungi server Bilibili: {e}"

    return False, "Sesi Bilibili tidak valid atau kadaluarsa."

def _query_bilibili_session_cookie(port: int) -> tuple[dict, str | None]:
    """
    Memeriksa cookie Bilibili (SESSDATA, DedeUserID, dll) dan URL halaman aktif via CDP.
    """
    try:
        req = urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2)
        pages = json.loads(req.read().decode('utf-8'))
        targets = [x for x in pages if x.get('type') == 'page' and 'webSocketDebuggerUrl' in x]
        if not targets:
            return {}, None
        target = targets[0]
        page_url = target.get('url', '')
        ws_url = target['webSocketDebuggerUrl']
        path = ws_url.split(f":{port}")[1]

        s, send_j, recv_j = _cdp_ws_connect('127.0.0.1', port, path)
        try:
            send_j({
                "id": 1,
                "method": "Network.getCookies",
                "params": {"urls": ["https://www.bilibili.com", "https://passport.bilibili.com"]}
            })
            resp = recv_j(timeout=2.0)
            if resp and "result" in resp:
                raw_cookies = resp["result"].get("cookies", [])
                cookie_map = {}
                for c in raw_cookies:
                    name = c.get("name")
                    val = c.get("value")
                    if name and val:
                        cookie_map[name] = val.strip()
                return cookie_map, page_url
        finally:
            try:
                s.close()
            except Exception:
                pass
    except Exception:
        pass
    return {}, None

def login_bilibili_via_browser(status_callback=None, timeout: int = 300) -> tuple[bool, str]:
    """
    Membuka jendela browser isolated (Edge/Chrome app mode) khusus untuk login akun Bilibili.
    Secara otomatis memantau proses login via CDP, menangkap cookie sesi SESSDATA,
    menutup browser, membersihkan profil sementara, dan mengembalikan (True, sessdata).
    """
    browser_exe = find_system_browser()
    if not browser_exe:
        return False, "Browser berbasis Chromium (Google Chrome / Edge) tidak ditemukan pada sistem."

    port = get_free_tcp_port()
    temp_profile = tempfile.mkdtemp(prefix="mavdown_bilibili_login_")

    login_target_url = "https://passport.bilibili.com/login"
    args = [
        browser_exe,
        f"--app={login_target_url}",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={temp_profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=560,780",
    ]

    proc = None
    try:
        proc = subprocess.Popen(args)
        if status_callback:
            status_callback("Jendela browser login dibuka. Silakan masuk ke akun Bilibili Anda...")

        start_time = time.time()
        time.sleep(1.5)
        last_verify_time = 0

        while True:
            if proc.poll() is not None:
                return False, "Jendela browser ditutup sebelum proses login selesai."

            if time.time() - start_time > timeout:
                return False, "Batas waktu login Bilibili telah habis (5 menit)."

            cookies, page_url = _query_bilibili_session_cookie(port)
            sess = cookies.get("SESSDATA")

            if sess:
                is_on_home = bool(page_url and "bilibili.com" in page_url and "passport.bilibili.com" not in page_url)
                has_user_id = bool(cookies.get("DedeUserID"))

                if has_user_id or is_on_home:
                    now = time.time()
                    if now - last_verify_time > 1.5:
                        last_verify_time = now
                        is_valid, user_info = verify_bilibili_session(sess)
                        if is_valid:
                            if status_callback:
                                status_callback(f"Login berhasil sebagai {user_info}! Menyelesaikan...")
                            return True, sess

            time.sleep(0.8)

    except Exception as e:
        return False, f"Terjadi kesalahan saat login: {e}"
    finally:
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if os.path.exists(temp_profile):
            for _ in range(3):
                try:
                    shutil.rmtree(temp_profile, ignore_errors=True)
                    break
                except Exception:
                    time.sleep(0.5)

def expand_bilibili_url(raw_url: str) -> str:
    """
    Ekspansi shortlink b23.tv ke URL kanonikal bilibili.com serta membersihkan query string pelacak.
    """
    clean_url = (raw_url or '').strip()
    if 'b23.tv' in clean_url:
        try:
            resp = requests.get(clean_url, allow_redirects=True, headers=DEFAULT_HEADERS, timeout=8)
            clean_url = resp.url if resp.url else clean_url
        except Exception:
            pass

    m_bv = re.search(r'(BV[0-9a-zA-Z]+)', clean_url)
    if m_bv:
        return f"https://www.bilibili.com/video/{m_bv.group(1)}"

    return clean_url.split('?')[0] if '?' in clean_url else clean_url

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

def get_bilibili_cookies(browser_name: str = None) -> dict:
    """
    Mengambil cookies Bilibili:
    1. Memprioritaskan Sesi Akun Bilibili (SESSDATA) tersimpan di konfigurasi Mavdown.
    2. Fallback ke cookies browser (Brave, Chrome, Edge) jika sesi tersimpan kosong.
    """
    try:
        from config import load_bilibili_session
        saved_sess = load_bilibili_session()
        if saved_sess and saved_sess.strip():
            return {'SESSDATA': saved_sess.strip()}
    except Exception:
        pass

    try:
        from config import load_browser_cookie, USER_DATA_DIR, YT_DLP_PATH
    except ImportError:
        return {}

    if not browser_name:
        browser_name = load_browser_cookie()

    if not browser_name or browser_name.lower() in ('tidak ada', 'none', ''):
        return {}

    b_clean = browser_name.strip().lower()
    cookie_file = os.path.join(USER_DATA_DIR, f"cookies_{b_clean}.txt")

    needs_refresh = True
    if os.path.exists(cookie_file) and os.path.getsize(cookie_file) > 100:
        file_age = time.time() - os.path.getmtime(cookie_file)
        if file_age < 21600:  # 6 jam
            needs_refresh = False

    if needs_refresh and os.path.exists(YT_DLP_PATH):
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
            cmd = [
                YT_DLP_PATH,
                "--cookies-from-browser", b_clean,
                "--cookies", cookie_file,
                "--skip-download",
                "https://www.bilibili.com/robots.txt"
            ]
            subprocess.run(cmd, capture_output=True, timeout=12, startupinfo=startupinfo)
        except Exception:
            pass

    cookie_jar = {}
    if os.path.exists(cookie_file):
        try:
            with open(cookie_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split('\t')
                    if len(parts) >= 7 and 'bilibili.com' in parts[0]:
                        cookie_jar[parts[5]] = parts[6]
        except Exception:
            pass

    return cookie_jar

def get_bilibili_page_meta(url: str) -> dict:
    """
    Ekstraksi metadata asli web Bilibili via Mobile SSR Scraper untuk judul, uploader, cover, dan durasi akurat.
    """
    try:
        resp = requests.get(url, headers=BILIBILI_MOBILE_HEADERS, timeout=8)
        if resp.status_code == 200:
            resp.encoding = 'utf-8'
            m = re.search(r'window\.__INITIAL_STATE__\s*=\s*({[\s\S]*?});', resp.text)
            if m:
                data = json.loads(m.group(1))
                video = data.get('video') or {}
                viewInfo = video.get('viewInfo') or {}
                upInfo = video.get('upInfo') or {}
                owner = viewInfo.get('owner') or {}

                uploader = owner.get('name') or upInfo.get('name') or ''
                title = viewInfo.get('title') or ''

                thumbnail = viewInfo.get('pic') or ''
                if thumbnail.startswith('//'):
                    thumbnail = 'https:' + thumbnail
                elif thumbnail.startswith('http://'):
                    thumbnail = 'https://' + thumbnail[7:]

                duration_sec = int(viewInfo.get('duration') or 0)
                dur_str = f"{duration_sec // 60}:{duration_sec % 60:02d}" if duration_sec else ""

                stat = viewInfo.get('stat') or {}
                cid = viewInfo.get('cid')
                bvid = video.get('bvid') or viewInfo.get('bvid') or ''

                play_url = None
                play_url_info = video.get('playUrlInfo') or []
                if isinstance(play_url_info, list) and play_url_info:
                    play_url = play_url_info[0].get('url')

                return {
                    'uploader': uploader,
                    'title': title,
                    'thumbnail': thumbnail,
                    'duration': duration_sec,
                    'duration_string': dur_str,
                    'view_count': stat.get('view', 0),
                    'like_count': stat.get('like', 0),
                    'comment_count': stat.get('reply', 0),
                    'share_count': stat.get('share', 0),
                    'pubdate': viewInfo.get('pubdate'),
                    'desc': viewInfo.get('desc', ''),
                    'cid': cid,
                    'bvid': bvid,
                    'play_url': play_url
                }
    except Exception:
        pass
    return None

def fetch_bilibili_native_playurl(bvid: str, cid: str | int, preferred_qn: int = 64) -> dict:
    """
    Mengambil direct stream URL dari official Bilibili HTML5 API (720p HD / 360p pre-muxed MP4).
    """
    try:
        api_url = f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&qn={preferred_qn}&platform=html5&high_quality=1"
        headers = {
            'User-Agent': BILIBILI_MOBILE_HEADERS['User-Agent'],
            'Referer': f"https://m.bilibili.com/video/{bvid}"
        }
        resp = requests.get(api_url, headers=headers, timeout=8)
        if resp.status_code == 200:
            res_json = resp.json()
            if res_json.get('code') == 0:
                data = res_json.get('data') or {}
                durl = data.get('durl') or []
                if durl and durl[0].get('url'):
                    quality = data.get('quality', preferred_qn)
                    res_label = "720p HD" if quality >= 64 else "480p" if quality >= 32 else "360p"
                    return {
                        'url': durl[0]['url'],
                        'backup_urls': durl[0].get('backup_url') or [],
                        'quality': quality,
                        'res_label': res_label,
                        'size': durl[0].get('size', 0)
                    }
    except Exception:
        pass
    return None

def fetch_bilibili_native_dash(bvid: str, cid: str | int, cookies: dict = None) -> dict:
    """
    Mengambil data DASH stream (video dan pure audio stream terpisah dengan bitrate tertinggi).
    Mendukung resolusi 1080p FHD jika cookies login disertakan.
    """
    try:
        api_url = f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&qn=80&fnval=16&fnver=0&fourk=1"
        headers = {
            'User-Agent': BILIBILI_MOBILE_HEADERS['User-Agent'],
            'Referer': f"https://m.bilibili.com/video/{bvid}"
        }
        resp = requests.get(api_url, headers=headers, cookies=cookies or None, timeout=8)
        if resp.status_code == 200:
            res_json = resp.json()
            if res_json.get('code') == 0:
                return (res_json.get('data') or {}).get('dash') or {}
    except Exception:
        pass
    return None

def fetch_bilibili_snapany(target_url: str) -> dict:
    """
    Mengambil data stream video dan audio Bilibili via SnapAny Cloud Engine.
    """
    try:
        headers = get_snapany_headers(target_url)
        resp = requests.post(
            'https://api.snapany.com/v1/extract/post',
            json={'link': target_url},
            headers=headers,
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()
            if data and data.get('medias'):
                return data
    except Exception:
        pass
    return None

def get_bilibili_info(url: str) -> dict:
    """
    Ekstraksi info Bilibili secara instan (< 1-2s) untuk pratinjau judul, thumbnail, dan statistik.
    """
    clean_url = (url or '').strip()
    target_url = expand_bilibili_url(clean_url)

    # 1. Ekstraksi langsung via Native Mobile SSR Scraper (Anti-limit)
    page_meta = get_bilibili_page_meta(target_url) or {}

    # 2. Coba SnapAny untuk kemungkinan varian 1080p FHD tanpa login
    snap_data = None
    try:
        snap_data = fetch_bilibili_snapany(target_url)
    except Exception:
        snap_data = None

    if not snap_data and not page_meta:
        return None

    clean_title = (page_meta.get('title') or (snap_data or {}).get('title') or (snap_data or {}).get('text') or 'Bilibili Video').strip()
    author = (page_meta.get('uploader') or ((snap_data or {}).get('author') or {}).get('name') or 'Bilibili Creator').strip()
    display_title = f"{author} - {clean_title}" if author and author != 'Bilibili Creator' else clean_title

    medias = (snap_data or {}).get('medias', [])
    m0 = medias[0] if medias else {}

    # Kumpulkan kandidat thumbnail cadangan dari server Bilibili
    candidates = []
    for cand in [page_meta.get('thumbnail'), m0.get('preview_url'), (snap_data or {}).get('thumbnail')]:
        if cand and isinstance(cand, str):
            c_clean = cand.strip()
            if c_clean.startswith('//'):
                c_clean = 'https:' + c_clean
            elif c_clean.startswith('http://'):
                c_clean = 'https://' + c_clean[7:]
            if c_clean.startswith('https://') and c_clean not in candidates:
                candidates.append(c_clean)
    thumbnail = candidates[0] if candidates else ''

    # Durasi
    duration = page_meta.get('duration', 0)
    dur_str = page_meta.get('duration_string', '')
    if not dur_str and duration:
        dur_str = f"{duration // 60}:{duration % 60:02d}"

    # Metrik engagement
    stats = (snap_data or {}).get('stats') or {}
    view_count = page_meta.get('view_count') or stats.get('view_count', 0)
    like_count = page_meta.get('like_count') or stats.get('like_count', 0)
    comment_count = page_meta.get('comment_count') or stats.get('comment_count', 0)
    share_count = page_meta.get('share_count') or stats.get('share_count', 0)

    # Tanggal rilis
    upload_date = ""
    date_string = ""
    pubdate = page_meta.get('pubdate') or (snap_data or {}).get('pubdate') or (snap_data or {}).get('created_at') or (snap_data or {}).get('date')
    if pubdate:
        try:
            if isinstance(pubdate, (int, float)) or (isinstance(pubdate, str) and pubdate.isdigit()):
                from datetime import datetime, timezone
                dt = datetime.fromtimestamp(int(pubdate), tz=timezone.utc)
                upload_date = dt.strftime('%Y%m%d')
                date_string = dt.strftime('%d/%m/%Y')
            elif isinstance(pubdate, str):
                m_iso = re.search(r'(\d{4})-(\d{2})-(\d{2})', pubdate)
                if m_iso:
                    upload_date = f"{m_iso.group(1)}{m_iso.group(2)}{m_iso.group(3)}"
                    date_string = f"{m_iso.group(3)}/{m_iso.group(2)}/{m_iso.group(1)}"
        except Exception:
            pass

    # Deskripsi
    desc = page_meta.get('desc') or (snap_data or {}).get('description') or clean_title

    # Resolusi & codec
    variants = m0.get('variants', [])
    best_variant = None
    if variants:
        best_variant = next((v for v in variants if (v.get('video_codec') or '').lower().startswith(('hevc', 'h265'))), None)
        if not best_variant:
            best_variant = variants[0]

    fps_val = 30
    if best_variant:
        res_label = best_variant.get('quality_label', "1080p FHD")
        codec = best_variant.get('video_codec') or 'h264'
        w, h = 1920, 1080
        ql = (res_label or '').lower()
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
    else:
        # Cek jika pengguna memiliki sesi browser login yang membuka akses 1080p
        cookies = get_bilibili_cookies()
        if cookies and 'SESSDATA' in cookies:
            res_label = "1080p FHD"
            codec = 'h264'
            w, h = 1920, 1080
        else:
            res_label = "720p HD"
            codec = 'h264'
            w, h = 1280, 720

    return {
        'title': display_title,
        'clean_title': clean_title,
        'author': author,
        'thumbnail': thumbnail,
        'thumbnails': candidates,
        'duration': duration,
        'duration_string': dur_str,
        'is_slide': False,
        'width': w,
        'height': h,
        'fps': fps_val,
        'codec': codec,
        'resolution_label': res_label,
        'view_count': view_count,
        'like_count': like_count,
        'comment_count': comment_count,
        'share_count': share_count,
        'upload_date': upload_date,
        'date_string': date_string,
        'description': desc,
        'platform': 'Bilibili',
        'webpage_url': target_url
    }

def _download_bilibili_snapany(target_url: str, snap_data: dict, output_dir: str, ui_queue=None, options=None, abort_checker=None) -> bool:
    """
    Eksekusi unduhan via stream SnapAny jika tersedia.
    """
    if options is None:
        options = {}
    mode = options.get('mode', 'video_audio')
    audio_format = options.get('audio_format', 'mp3')
    embed_thumb = options.get('embed_thumb', True)

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

    if mode == 'audio_only':
        audio_url = None
        if variants:
            audio_v = next((v for v in variants if v.get('audio_url')), None)
            if audio_v:
                audio_url = audio_v['audio_url']
        if not audio_url:
            audio_url = m0.get('resource_url')

        if not audio_url:
            return False

        raw_audio_path = os.path.join(output_dir, f"{base_name}_raw_audio.mp4")
        final_audio_path = os.path.join(output_dir, f"{base_name}.{audio_format}")

        if ui_queue:
            ui_queue.put({"type": "log", "text": "[TIER 1] Mengunduh stream audio Bilibili (SnapAny)...\n"})

        dl_ok = stream_download_file(audio_url, raw_audio_path, ui_queue, abort_checker, headers=req_headers, label="Unduh Audio Bilibili")
        if not dl_ok:
            return False

        extract_audio_from_video(raw_audio_path, final_audio_path, audio_format)
        if os.path.exists(raw_audio_path):
            try: os.remove(raw_audio_path)
            except Exception: pass

        if embed_thumb and thumbnail and os.path.exists(final_audio_path):
            embed_thumbnail_to_media(final_audio_path, thumbnail, ui_queue, abort_checker)

        if ui_queue:
            ui_queue.put({"type": "log", "text": f"\n--- UNDUHAN SUKSES (Bilibili Audio) ---\nFile tersimpan di: {final_audio_path}\n"})
            ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
        return True

    chosen_video_url = None
    chosen_audio_url = None

    if variants:
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
        return False

    raw_container = options.get('container', 'auto') if options else 'auto'
    container = 'mp4' if raw_container in ('auto', 'best', '', None) else str(raw_container).lower()
    ext = f".{container}"

    raw_video_path = os.path.join(output_dir, f"{base_name}_raw_video.mp4")
    raw_audio_path = os.path.join(output_dir, f"{base_name}_raw_audio.m4a")
    muxed_video_path = os.path.join(output_dir, f"{base_name}_muxed.{container}")
    final_video_path = os.path.join(output_dir, f"{base_name}{ext}")

    if ui_queue:
        ui_queue.put({"type": "log", "text": "[TIER 1] Mengunduh stream video Bilibili (SnapAny)...\n"})

    dl_v_ok = stream_download_file(chosen_video_url, raw_video_path, ui_queue, abort_checker, headers=req_headers, label="Unduh Video Bilibili")
    if not dl_v_ok:
        return False

    if chosen_audio_url:
        if ui_queue:
            ui_queue.put({"type": "log", "text": "[TIER 1] Mengunduh stream audio Bilibili...\n"})

        dl_a_ok = stream_download_file(chosen_audio_url, raw_audio_path, ui_queue, abort_checker, headers=req_headers, label="Unduh Audio Bilibili")
        if dl_a_ok and os.path.exists(raw_audio_path) and os.path.getsize(raw_audio_path) > 100:
            if ui_queue:
                ui_queue.put({"type": "log", "text": "[FFMPEG] Menggabungkan stream video & audio DASH (Copy Mux)...\n"})

            cmd = [
                FFMPEG_PATH, "-y",
                "-i", raw_video_path,
                "-i", raw_audio_path,
                "-c", "copy"
            ]
            if container in ('mp4', 'mov', 'm4v'):
                cmd.extend(["-movflags", "+faststart"])
            cmd.append(muxed_video_path)
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

    postprocess_video(source_for_postprocess, final_video_path, options, ui_queue, abort_checker)

    for temp_f in (raw_video_path, raw_audio_path, muxed_video_path):
        if os.path.exists(temp_f):
            try: os.remove(temp_f)
            except Exception: pass

    if embed_thumb and thumbnail and os.path.exists(final_video_path):
        embed_thumbnail_to_media(final_video_path, thumbnail, ui_queue, abort_checker)

    if ui_queue:
        ui_queue.put({"type": "log", "text": f"\n--- UNDUHAN SUKSES (Bilibili HD) ---\nFile tersimpan di: {final_video_path}\n"})
        ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
    return True

def _download_bilibili_native(target_url: str, output_dir: str, ui_queue=None, options=None, abort_checker=None) -> bool:
    """
    Eksekusi unduhan media Bilibili via Native Engine (Anti-limit Bilibili HTML5 API & Mobile SSR).
    Mendukung resolusi 1080p FHD resmi jika cookies browser tersedia.
    """
    if options is None:
        options = {}
    mode = options.get('mode', 'video_audio')
    audio_format = options.get('audio_format', 'mp3')
    embed_thumb = options.get('embed_thumb', True)

    page_meta = get_bilibili_page_meta(target_url)
    if not page_meta:
        if ui_queue:
            ui_queue.put({"type": "log", "text": "[TIER 1] Gagal mengekstraksi metadata Bilibili.\n"})
        return False

    bvid = page_meta.get('bvid')
    if not bvid:
        m_bv = re.search(r'(BV[0-9a-zA-Z]+)', target_url)
        if m_bv:
            bvid = m_bv.group(1)

    cid = page_meta.get('cid')
    title = page_meta.get('title') or 'Bilibili Video'
    author = page_meta.get('uploader') or ''
    thumbnail = page_meta.get('thumbnail') or ''
    base_name = sanitize_filename(f"{author} - {title}" if author and author != 'Bilibili Creator' else title)

    req_headers = {
        'User-Agent': BILIBILI_MOBILE_HEADERS['User-Agent'],
        'Referer': 'https://www.bilibili.com/'
    }

    cookies = get_bilibili_cookies()

    # -------------------------------------------------------------
    # 1. MODE AUDIO SAJA
    # -------------------------------------------------------------
    if mode == 'audio_only':
        audio_url = None
        if bvid and cid:
            dash = fetch_bilibili_native_dash(bvid, cid, cookies=cookies)
            if dash and dash.get('audio'):
                audios = sorted(dash['audio'], key=lambda x: x.get('bandwidth', 0), reverse=True)
                audio_url = audios[0].get('baseUrl') or (audios[0].get('backupUrl') or [None])[0]

        if not audio_url:
            play_data = fetch_bilibili_native_playurl(bvid, cid, 64) if (bvid and cid) else None
            audio_url = (play_data or {}).get('url') or page_meta.get('play_url')

        if not audio_url:
            if ui_queue:
                ui_queue.put({"type": "log", "text": "[TIER 1] Stream audio Bilibili tidak ditemukan.\n"})
            return False

        raw_audio_path = os.path.join(output_dir, f"{base_name}_raw_audio.mp4")
        final_audio_path = os.path.join(output_dir, f"{base_name}.{audio_format}")

        if ui_queue:
            ui_queue.put({"type": "log", "text": "[TIER 1] Mengunduh stream audio Bilibili (HQ AAC)...\n"})

        dl_ok = stream_download_file(audio_url, raw_audio_path, ui_queue, abort_checker, headers=req_headers, label="Unduh Audio Bilibili")
        if not dl_ok:
            return False

        extract_audio_from_video(raw_audio_path, final_audio_path, audio_format)
        if os.path.exists(raw_audio_path):
            try: os.remove(raw_audio_path)
            except Exception: pass

        if embed_thumb and thumbnail and os.path.exists(final_audio_path):
            embed_thumbnail_to_media(final_audio_path, thumbnail, ui_queue, abort_checker)

        if ui_queue:
            ui_queue.put({"type": "log", "text": f"\n--- UNDUHAN SUKSES (Bilibili Audio) ---\nFile tersimpan di: {final_audio_path}\n"})
            ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
        return True

    # -------------------------------------------------------------
    # 2. MODE VIDEO (+ AUDIO)
    # -------------------------------------------------------------
    # Coba DASH stream terlebih dahulu (Mendukung 1080p FHD jika cookies login ada)
    dash = fetch_bilibili_native_dash(bvid, cid, cookies=cookies) if (bvid and cid) else None
    chosen_video_url = None
    chosen_audio_url = None
    res_text = "720p HD"

    if dash and dash.get('video') and dash.get('audio'):
        v_list = dash['video']
        v_1080 = [v for v in v_list if v.get('id') == 80]
        pref_codec = (options.get('video_codec', 'best') or 'best').lower()

        target_pool = v_1080 if v_1080 else v_list
        if v_1080:
            res_text = "1080p FHD (Sesi Browser)" if cookies else "1080p FHD"

        best_v = None
        if pref_codec in ('hevc', 'h265', 'hvc1'):
            best_v = next((v for v in target_pool if any(c in (v.get('codecs') or '').lower() for c in ('hevc', 'h265', 'hvc1'))), None)
        elif pref_codec == 'av1':
            best_v = next((v for v in target_pool if 'av1' in (v.get('codecs') or '').lower()), None)
        else:
            best_v = next((v for v in target_pool if any(c in (v.get('codecs') or '').lower() for c in ('avc', 'h264'))), None)

        if not best_v:
            best_v = target_pool[0]

        chosen_video_url = best_v.get('baseUrl') or (best_v.get('backupUrl') or [None])[0]

        audios = sorted(dash['audio'], key=lambda x: x.get('bandwidth', 0), reverse=True)
        chosen_audio_url = audios[0].get('baseUrl') or (audios[0].get('backupUrl') or [None])[0]

    # Jalur DASH (Video 1080p/720p + Audio Terpisah dimuxing cepat dengan FFmpeg)
    if chosen_video_url and chosen_audio_url:
        raw_container = options.get('container', 'auto') if options else 'auto'
        container = 'mp4' if raw_container in ('auto', 'best', '', None) else str(raw_container).lower()
        ext = f".{container}"

        raw_video_path = os.path.join(output_dir, f"{base_name}_raw_video.m4s")
        raw_audio_path = os.path.join(output_dir, f"{base_name}_raw_audio.m4s")
        muxed_video_path = os.path.join(output_dir, f"{base_name}_muxed.{container}")
        final_video_path = os.path.join(output_dir, f"{base_name}{ext}")

        if ui_queue:
            ui_queue.put({"type": "log", "text": f"[TIER 1] Mengunduh stream video Bilibili ({res_text})...\n"})

        dl_v_ok = stream_download_file(chosen_video_url, raw_video_path, ui_queue, abort_checker, headers=req_headers, label="Unduh Video Bilibili")
        if not dl_v_ok:
            return False

        if ui_queue:
            ui_queue.put({"type": "log", "text": "[TIER 1] Mengunduh stream audio Bilibili...\n"})

        dl_a_ok = stream_download_file(chosen_audio_url, raw_audio_path, ui_queue, abort_checker, headers=req_headers, label="Unduh Audio Bilibili")
        if not dl_a_ok:
            return False

        if ui_queue:
            ui_queue.put({"type": "log", "text": "[FFMPEG] Menggabungkan stream video & audio DASH (Copy Mux)...\n"})

        cmd = [
            FFMPEG_PATH, "-y",
            "-i", raw_video_path,
            "-i", raw_audio_path,
            "-c", "copy"
        ]
        if container in ('mp4', 'mov', 'm4v'):
            cmd.extend(["-movflags", "+faststart"])
        cmd.append(muxed_video_path)
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        res = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
            startupinfo=startupinfo, encoding='utf-8', errors='ignore'
        )
        source_for_postprocess = muxed_video_path if (res.returncode == 0 and os.path.exists(muxed_video_path)) else raw_video_path

        postprocess_video(source_for_postprocess, final_video_path, options, ui_queue, abort_checker)

        for temp_f in (raw_video_path, raw_audio_path, muxed_video_path):
            if os.path.exists(temp_f):
                try: os.remove(temp_f)
                except Exception: pass

        if embed_thumb and thumbnail and os.path.exists(final_video_path):
            embed_thumbnail_to_media(final_video_path, thumbnail, ui_queue, abort_checker)

        if ui_queue:
            ui_queue.put({"type": "log", "text": f"\n--- UNDUHAN SUKSES (Bilibili HD) ---\nFile tersimpan di: {final_video_path}\n"})
            ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
        return True

    # Jalur Fallback: Progressive MP4 HTML5 API (720p HD)
    play_data = fetch_bilibili_native_playurl(bvid, cid, 64) if (bvid and cid) else None
    stream_url = (play_data or {}).get('url') or page_meta.get('play_url')

    if not stream_url:
        if ui_queue:
            ui_queue.put({"type": "log", "text": "[TIER 1] Stream video Bilibili tidak ditemukan.\n"})
        return False

    raw_container = options.get('container', 'auto') if options else 'auto'
    container = 'mp4' if raw_container in ('auto', 'best', '', None) else str(raw_container).lower()
    ext = f".{container}"

    raw_video_path = os.path.join(output_dir, f"{base_name}_raw_video.mp4")
    final_video_path = os.path.join(output_dir, f"{base_name}{ext}")

    res_fallback = (play_data or {}).get('res_label', '720p HD')
    if ui_queue:
        ui_queue.put({"type": "log", "text": f"[TIER 1] Mengunduh stream video Bilibili ({res_fallback})...\n"})

    dl_v_ok = stream_download_file(stream_url, raw_video_path, ui_queue, abort_checker, headers=req_headers, label="Unduh Video Bilibili")
    if not dl_v_ok:
        return False

    postprocess_video(raw_video_path, final_video_path, options, ui_queue, abort_checker)
    if os.path.exists(raw_video_path) and raw_video_path != final_video_path:
        try: os.remove(raw_video_path)
        except Exception: pass

    if embed_thumb and thumbnail and os.path.exists(final_video_path):
        embed_thumbnail_to_media(final_video_path, thumbnail, ui_queue, abort_checker)

    if ui_queue:
        ui_queue.put({"type": "log", "text": f"\n--- UNDUHAN SUKSES (Bilibili HD) ---\nFile tersimpan di: {final_video_path}\n"})
        ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
    return True

def download_bilibili(url: str, output_dir: str, ui_queue=None, options=None, abort_checker=None) -> bool:
    """
    Unduh media Bilibili (Video 1080p/720p atau Audio HQ).
    Mendukung Cloud Engine (SnapAny) dengan fallback instan ke Native Bilibili Engine (Anti-limit).
    """
    if options is None:
        options = {}

    clean_url = (url or '').strip()
    target_url = expand_bilibili_url(clean_url)

    # 1. Coba SnapAny lebih dulu jika tersedia (1080p FHD instan tanpa login)
    snap_data = None
    try:
        if ui_queue:
            ui_queue.put({"type": "log", "text": "[TIER 1] Menghubungi Bilibili Cloud Engine (SnapAny)...\n"})
        snap_data = fetch_bilibili_snapany(target_url)
    except Exception:
        snap_data = None

    if snap_data and snap_data.get('medias'):
        success = _download_bilibili_snapany(target_url, snap_data, output_dir, ui_queue, options, abort_checker)
        if success:
            return True

    # 2. Native Bilibili Engine (Akses Langsung HD dengan dukungan Sesi Browser)
    if ui_queue:
        ui_queue.put({"type": "log", "text": "[TIER 1] Menggunakan Bilibili Native Engine (Akses Langsung HD)...\n"})

    success = _download_bilibili_native(target_url, output_dir, ui_queue, options, abort_checker)
    if success:
        return True

    if ui_queue:
        ui_queue.put({"type": "log", "text": "[TIER 1] Beralih ke Engine Fallback Tier 2 (yt-dlp)...\n"})
    return False
