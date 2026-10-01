import os
import sys
import re
import json
import time
import socket
import base64
import struct
import zipfile
import shutil
import tempfile
import requests
import subprocess
import urllib.request

from config import FFMPEG_PATH, load_pixiv_session
from engines.base import (
    DEFAULT_HEADERS, sanitize_filename, stream_download_file,
    normalize_image_to_jpeg, format_bytes
)

PIXIV_BASE_URL = "https://www.pixiv.net"
PIXIV_REFERER = "https://www.pixiv.net/"

def extract_pixiv_id(url: str) -> str:
    """
    Mengekstrak Artwork ID dari berbagai format URL Pixiv:
    - https://www.pixiv.net/artworks/12345678
    - https://www.pixiv.net/en/artworks/12345678
    - https://www.pixiv.net/member_illust.php?mode=medium&illust_id=12345678
    - https://pixiv.net/i/12345678
    """
    clean = (url or '').strip()
    match = re.search(r'artworks\/(\d+)', clean, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r'illust_id=(\d+)', clean, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r'pixiv\.net\/i\/(\d+)', clean, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r'^\d+$', clean)
    if match:
        return match.group(0)
    return None

def get_pixiv_headers(session: str = None, referer: str = None) -> dict:
    """Membuat HTTP headers standar dengan anti-hotlink referer dan cookie sesi Pixiv."""
    sess_val = (session if session is not None else load_pixiv_session()) or ""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Referer': referer or PIXIV_REFERER,
        'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8,id;q=0.7',
    }
    if sess_val.strip():
        headers['Cookie'] = f"PHPSESSID={sess_val.strip()}"
    return headers

def verify_pixiv_session(session: str) -> tuple[bool, str]:
    """
    Memverifikasi apakah nilai cookie sesi PHPSESSID valid dan masih aktif.
    Mengembalikan (is_valid, username_or_error_msg).
    """
    if not session or not session.strip():
        return False, "Sesi kosong"
    
    headers = get_pixiv_headers(session=session.strip())
    try:
        # Panggil endpoint profil login pengguna
        resp = requests.get(
            f"{PIXIV_BASE_URL}/ajax/user/extra",
            headers=headers,
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            if not data.get('error'):
                body = data.get('body', {})
                name = body.get('userName') or body.get('name') or "Pengguna Pixiv"
                user_id = body.get('userId') or ""
                label = f"{name} (ID: {user_id})" if user_id else name
                return True, label
        # Coba endpoint fallback
        resp2 = requests.get(f"{PIXIV_BASE_URL}/ajax/top/illust", headers=headers, timeout=10)
        if resp2.status_code == 200:
            data2 = resp2.json()
            body2 = data2.get('body', {})
            # Jika userLoggedIn true
            if body2.get('userLoggedIn') or data2.get('userLoggedIn'):
                return True, "Sesi Aktif"
    except Exception as e:
        return False, f"Gagal menghubungi Pixiv: {e}"

    return False, "Sesi kadaluarsa atau tidak valid"

def find_system_browser() -> str | None:
    """
    Mendeteksi path executable browser berbasis Chromium (Google Chrome, Microsoft Edge, Brave)
    pada sistem operasi untuk membuka jendela login Pixiv secara isolated.
    """
    if os.name == 'nt':
        import winreg
        reg_keys = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\brave.exe"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths\brave.exe"),
        ]
        for root_key, sub_key in reg_keys:
            try:
                with winreg.OpenKey(root_key, sub_key) as k:
                    val, _ = winreg.QueryValueEx(k, "")
                    if val and os.path.exists(val):
                        return val
            except Exception:
                pass

        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        ]
        for p in candidates:
            if p and os.path.exists(p):
                return p

    for name in ["google-chrome", "chromium", "microsoft-edge", "brave-browser"]:
        which_p = shutil.which(name)
        if which_p:
            return which_p

    return None

def get_free_tcp_port() -> int:
    """Mendapatkan port TCP lokal yang sedang bebas."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

def _cdp_ws_connect(host: str, port: int, path: str):
    """
    Koneksi WebSocket minimal pure-Python ke Chrome DevTools Protocol (CDP).
    Tidak memerlukan dependensi pihak ketiga eksternal.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect((host, port))

    key = base64.b64encode(os.urandom(16)).decode('ascii')
    req = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    )
    s.sendall(req.encode('utf-8'))
    resp = s.recv(4096).decode('utf-8', errors='ignore')
    if "101 " not in resp:
        s.close()
        raise RuntimeError("Handshake WebSocket CDP gagal: " + resp)

    def send_json(data: dict):
        msg = json.dumps(data).encode('utf-8')
        length = len(msg)
        mask_key = os.urandom(4)
        header = bytearray([0x81])
        if length <= 125:
            header.append(0x80 | length)
        elif length <= 65535:
            header.append(0x80 | 126)
            header.extend(struct.pack('>H', length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack('>Q', length))
        header.extend(mask_key)
        masked = bytearray(b ^ mask_key[i % 4] for i, b in enumerate(msg))
        s.sendall(header + masked)

    def recv_json(timeout: float = 3.0):
        s.settimeout(timeout)
        buf = bytearray()
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            buf.extend(chunk)
            if len(buf) >= 2:
                payload_len = buf[1] & 0x7F
                offset = 2
                if payload_len == 126:
                    if len(buf) < 4:
                        continue
                    payload_len = struct.unpack('>H', buf[2:4])[0]
                    offset = 4
                elif payload_len == 127:
                    if len(buf) < 10:
                        continue
                    payload_len = struct.unpack('>Q', buf[2:10])[0]
                    offset = 10
                if len(buf) >= offset + payload_len:
                    payload = buf[offset:offset + payload_len]
                    return json.loads(payload.decode('utf-8', errors='ignore'))
        return None

    return s, send_json, recv_json

def _query_pixiv_session_cookie(port: int) -> tuple[str | None, str | None]:
    """
    Memeriksa cookie PHPSESSID dan URL halaman aktif via CDP.
    Mengembalikan (phpsessid, current_page_url).
    """
    try:
        req = urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2)
        pages = json.loads(req.read().decode('utf-8'))
        targets = [x for x in pages if x.get('type') == 'page' and 'webSocketDebuggerUrl' in x]
        if not targets:
            return None, None
        target = targets[0]
        page_url = target.get('url', '')
        ws_url = target['webSocketDebuggerUrl']
        path = ws_url.split(f":{port}")[1]

        s, send_j, recv_j = _cdp_ws_connect('127.0.0.1', port, path)
        try:
            send_j({
                "id": 1,
                "method": "Network.getCookies",
                "params": {"urls": ["https://www.pixiv.net", "https://accounts.pixiv.net"]}
            })
            resp = recv_j(timeout=2.0)
            if resp and "result" in resp:
                cookies = resp["result"].get("cookies", [])
                best_cookie = None
                for c in cookies:
                    if c.get("name") == "PHPSESSID" and c.get("value"):
                        val = c["value"].strip()
                        # Jika diawali user ID (format sesi akun login: <user_id>_<token>), utamakan ini langsung
                        if re.match(r'^\d+_[a-zA-Z0-9]+', val):
                            best_cookie = val
                            break
                        elif not best_cookie:
                            best_cookie = val
                return best_cookie, page_url
        finally:
            try:
                s.close()
            except Exception:
                pass
    except Exception:
        pass
    return None, None

def login_pixiv_via_browser(status_callback=None, timeout: int = 300) -> tuple[bool, str]:
    """
    Membuka jendela browser isolated (Edge/Chrome app mode) khusus untuk login akun Pixiv.
    Secara otomatis memantau proses login, menangkap cookie sesi PHPSESSID yang telah diautentikasi,
    menutup browser, membersihkan profil sementara, dan mengembalikan (True, phpsessid).
    """
    browser_exe = find_system_browser()
    if not browser_exe:
        return False, "Browser berbasis Chromium (Google Chrome / Edge) tidak ditemukan pada sistem."

    port = get_free_tcp_port()
    temp_profile = tempfile.mkdtemp(prefix="mavdown_pixiv_login_")

    login_target_url = "https://accounts.pixiv.net/login?return_to=https%3A%2F%2Fwww.pixiv.net%2F"
    args = [
        browser_exe,
        f"--app={login_target_url}",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={temp_profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=540,760",
    ]

    proc = None
    try:
        proc = subprocess.Popen(args)
        if status_callback:
            status_callback("Jendela browser login dibuka. Silakan masuk ke akun Pixiv Anda...")

        start_time = time.time()
        time.sleep(1.5)

        # Catat cookie guest awal yang diberikan halaman login saat pertama kali dimuat
        initial_guest_cookie = None
        for _ in range(6):
            c_val, _ = _query_pixiv_session_cookie(port)
            if c_val:
                initial_guest_cookie = c_val
                break
            time.sleep(0.4)

        last_verify_time = 0

        while True:
            # 1. Cek apakah user menutup browser secara manual
            if proc.poll() is not None:
                return False, "Jendela browser ditutup sebelum proses login selesai."

            # 2. Cek batas waktu (timeout)
            if time.time() - start_time > timeout:
                return False, "Batas waktu login Pixiv telah habis (5 menit)."

            # 3. Periksa keberadaan cookie PHPSESSID dan URL halaman aktif
            sess, page_url = _query_pixiv_session_cookie(port)

            if sess:
                # Pola 1: Sesi login akun Pixiv yang valid umumnya berformat <user_id>_<token>
                has_user_id_prefix = bool(re.search(r'^\d+_[a-zA-Z0-9]+', sess))

                # Pola 2: Browser telah berhasil berpindah dari halaman login ke situs utama Pixiv
                is_on_pixiv_home = bool(page_url and "pixiv.net" in page_url and "login" not in page_url and "signup" not in page_url and "accounts.pixiv.net" not in page_url)

                # Pola 3: Nilai cookie telah berubah dari guest cookie awal
                cookie_changed = (initial_guest_cookie is not None and sess != initial_guest_cookie)

                # Hanya verifikasi jika ada tanda nyata bahwa user telah login:
                if has_user_id_prefix or (is_on_pixiv_home and cookie_changed):
                    # Lakukan verifikasi aktual ke server Pixiv
                    now = time.time()
                    if now - last_verify_time > 1.5:
                        last_verify_time = now
                        is_valid, user_info = verify_pixiv_session(sess)
                        if is_valid:
                            if status_callback:
                                status_callback(f"Login berhasil sebagai {user_info}! Menyelesaikan...")
                            return True, sess

            time.sleep(1.2)

    except Exception as e:
        return False, f"Terjadi kesalahan saat menjalankan browser login: {e}"

    finally:
        # Bersihkan proses browser dan profil sementara
        if proc:
            try:
                if os.name == 'nt':
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
                else:
                    proc.terminate()
            except Exception:
                pass
        time.sleep(0.4)
        shutil.rmtree(temp_profile, ignore_errors=True)

def get_pixiv_info(url: str, session: str = None) -> dict:
    """
    Mengambil metadata artwork Pixiv (Ilustrasi, Manga, atau Ugoira).
    Mendeteksi otomatis apakah konten membutuhkan login sesi (R-18 / Restricted).
    """
    illust_id = extract_pixiv_id(url)
    if not illust_id:
        return None

    headers = get_pixiv_headers(session=session, referer=f"{PIXIV_BASE_URL}/artworks/{illust_id}")
    ajax_url = f"{PIXIV_BASE_URL}/ajax/illust/{illust_id}"

    try:
        resp = requests.get(ajax_url, headers=headers, timeout=10)
        
        # Penanganan Kasus Butuh Login (Restricted / R-18 tanpa sesi)
        if resp.status_code in (403, 404):
            return {
                'requires_login': True,
                'platform': 'Pixiv',
                'illust_id': illust_id,
                'title': f"Karya Pixiv #{illust_id} (Perlu Login)",
                'clean_title': f"Pixiv_{illust_id}",
                'author': "Pixiv Artist",
                'thumbnail': "",
                'is_slide': False,
                'is_ugoira': False,
                'resolution_label': "Perlu Login",
                'error_message': "Karya ini dibatasi (R-18 atau Members-Only) dan memerlukan sesi login aktif."
            }

        data = resp.json()
        if data.get('error'):
            msg = data.get('message', '')
            is_restricted = any(k in msg.lower() for k in ['login', 'restrict', 'r-18', 'limit', 'not found'])
            return {
                'requires_login': is_restricted,
                'platform': 'Pixiv',
                'illust_id': illust_id,
                'title': f"Karya Pixiv #{illust_id} (Perlu Login)" if is_restricted else "Media Pixiv",
                'clean_title': f"Pixiv_{illust_id}",
                'author': "Pixiv Artist",
                'thumbnail': "",
                'is_slide': False,
                'is_ugoira': False,
                'resolution_label': "Perlu Login" if is_restricted else "Error",
                'error_message': msg or "Konten tidak dapat diakses."
            }

        body = data.get('body', {})
        if not body:
            return None

        raw_title = body.get('title') or f"Pixiv Artwork {illust_id}"
        author = body.get('userName') or body.get('userAccount') or "Pixiv Artist"
        illust_type = body.get('illustType', 0)  # 0: Illust, 1: Manga, 2: Ugoira
        is_ugoira = (illust_type == 2)
        page_count = int(body.get('pageCount', 1))
        x_restrict = body.get('xRestrict', 0)    # 0: General, 1: R-18, 2: R-18G
        width = int(body.get('width', 0))
        height = int(body.get('height', 0))

        urls = body.get('urls', {})
        has_media_urls = any(urls.get(k) for k in ['original', 'regular', 'small', 'thumb'])
        requires_login = False
        if not has_media_urls or (x_restrict > 0 and (not session or not session.strip())):
            requires_login = True

        raw_thumb = urls.get('regular') or urls.get('small') or urls.get('thumb') or urls.get('original') or ''

        # Proxy / directly resolve thumbnail
        display_title = f"{author} - {raw_title}" if author else raw_title

        if requires_login:
            res_label = "Perlu Login (R-18)" if x_restrict > 0 else "Perlu Login"
        else:
            res_label = f"{width}x{height}" if width and height else ("Ugoira HD" if is_ugoira else "HD")
            if x_restrict > 0:
                res_label += " (R-18)"

        is_slide = (page_count > 1 and not is_ugoira)
        slide_count = page_count if not is_ugoira else 0

        dur_str = ""
        if is_ugoira:
            dur_str = "Animasi Ugoira"
        elif is_slide:
            dur_str = f"{page_count} Halaman"

        return {
            'title': display_title,
            'clean_title': raw_title,
            'author': author,
            'thumbnail': raw_thumb,
            'platform': 'Pixiv',
            'illust_id': illust_id,
            'illust_type': illust_type,
            'is_ugoira': is_ugoira,
            'is_slide': is_slide,
            'page_count': page_count,
            'slide_count': slide_count,
            'width': width,
            'height': height,
            'resolution_label': res_label,
            'duration_string': dur_str,
            'duration': 0,
            'has_audio': False,
            'webpage_url': f"{PIXIV_BASE_URL}/artworks/{illust_id}",
            'url': f"{PIXIV_BASE_URL}/artworks/{illust_id}",
            'requires_login': requires_login,
            'x_restrict': x_restrict
        }
    except Exception as e:
        print(f"Error fetching Pixiv info: {e}")
        return None

def convert_ugoira_to_media(zip_path: str, frames_data: list, dest_path: str, format_type: str = 'mp4', ui_queue=None, abort_checker=None) -> bool:
    """
    Mengekstrak file ZIP animasi Ugoira dan merakitnya menjadi file Video MP4 atau Animasi GIF menggunakan FFmpeg.
    Mendukung penanganan jeda milidetik per frame yang presisi.
    """
    if not os.path.exists(zip_path) or not frames_data:
        return False

    temp_extract_dir = tempfile.mkdtemp(prefix="pixiv_ugoira_")
    try:
        # 1. Ekstrak frame dari arsip ZIP
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(temp_extract_dir)

        # 2. Susun file concat demuxer untuk FFmpeg
        concat_txt_path = os.path.join(temp_extract_dir, "frames.txt")
        with open(concat_txt_path, 'w', encoding='utf-8') as f:
            for item in frames_data:
                fname = item.get('file')
                delay_ms = item.get('delay', 125)
                delay_sec = max(delay_ms / 1000.0, 0.01)
                full_frame_path = os.path.join(temp_extract_dir, fname).replace('\\', '/')
                f.write(f"file '{full_frame_path}'\n")
                f.write(f"duration {delay_sec:.4f}\n")
            # Ulangi frame terakhir sesuai spesifikasi concat demuxer FFmpeg
            if frames_data:
                last_fname = frames_data[-1].get('file')
                full_last = os.path.join(temp_extract_dir, last_fname).replace('\\', '/')
                f.write(f"file '{full_last}'\n")

        if abort_checker and abort_checker():
            return False

        # 3. Panggil FFmpeg
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        format_lower = (format_type or 'mp4').lower()
        if format_lower == 'gif':
            # Render GIF berkualitas tinggi dengan dua-pass palettegen
            ff_cmd = [
                FFMPEG_PATH, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_txt_path,
                "-vf", "split[s0][s1];[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3",
                dest_path
            ]
        else:
            # Render MP4 (H.264 / yuv420p)
            ff_cmd = [
                FFMPEG_PATH, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_txt_path,
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                dest_path
            ]

        res = subprocess.run(
            ff_cmd,
            capture_output=True,
            startupinfo=startupinfo,
            encoding='utf-8',
            errors='ignore'
        )

        return (res.returncode == 0 and os.path.exists(dest_path) and os.path.getsize(dest_path) > 100)

    except Exception as e:
        if ui_queue:
            ui_queue.put({"type": "log", "text": f"[FFMPEG UGOIRA ERROR] {e}\n"})
        return False
    finally:
        shutil.rmtree(temp_extract_dir, ignore_errors=True)

def download_pixiv(url: str, output_dir: str, ui_queue=None, options=None, abort_checker=None) -> bool:
    """
    Unduh media Pixiv (Ilustrasi, Manga Multi-Halaman, atau Animasi Ugoira).
    Hasil unduhan selalu disimpan ke dalam subfolder khusus sesuai judul karya di dalam folder Pixiv:
    output_dir/Mavdown_Pixiv/<Judul Karya>/
    """
    if options is None:
        options = {}

    illust_id = extract_pixiv_id(url)
    if not illust_id:
        if ui_queue:
            ui_queue.put({"type": "log", "text": "[TIER 1] Format URL Pixiv tidak valid.\n"})
        return False

    session = load_pixiv_session()
    headers = get_pixiv_headers(session=session, referer=f"{PIXIV_BASE_URL}/artworks/{illust_id}")

    if ui_queue:
        ui_queue.put({"type": "log", "text": f"[TIER 1] Menghubungi Pixiv Engine (ID: {illust_id})...\n"})

    # 1. Ambil Metadata Karya
    info = get_pixiv_info(url, session=session)
    if not info:
        if ui_queue:
            ui_queue.put({"type": "log", "text": "[TIER 1] Gagal mengambil informasi karya dari Pixiv.\n"})
        return False

    # Jika konten memerlukan login dan pengguna belum login / sesi tidak valid
    if info.get('requires_login'):
        if ui_queue:
            ui_queue.put({"type": "pixiv_login_required", "url": url})
            ui_queue.put({
                "type": "log",
                "text": "\n[PIXIV LOGIN DIPERLUKAN] Karya ini dibatasi (R-18 atau Members-Only).\nSilakan masukkan sesi login Pixiv Anda di menu Pengaturan.\n"
            })
        return False

    raw_title = info.get('clean_title') or f"Pixiv_{illust_id}"
    clean_title = sanitize_filename(raw_title)
    title_suffix = f" {clean_title}" if clean_title else ""
    author = info.get('author') or ""
    is_ugoira = info.get('is_ugoira', False)
    page_count = info.get('page_count', 1)

    # Nama subfolder bersih berdasarkan judul karya
    base_folder_name = sanitize_filename(f"{author} - {raw_title}" if author else raw_title)
    if not base_folder_name:
        base_folder_name = f"Pixiv_{illust_id}"

    work_folder = os.path.join(output_dir, base_folder_name)
    os.makedirs(work_folder, exist_ok=True)

    if ui_queue:
        ui_queue.put({"type": "log", "text": f"[TIER 1] Folder Tujuan: {work_folder}\n"})

    # =========================================================================
    # KASUS A: ANIMASI UGOIRA
    # =========================================================================
    if is_ugoira:
        # Preferensi format dari user: 'mp4' atau 'gif'
        ugoira_fmt = options.get('ugoira_format')
        if not ugoira_fmt:
            # Fallback ke container atau default mp4
            c_val = str(options.get('container', '')).lower()
            ugoira_fmt = 'gif' if c_val == 'gif' else 'mp4'
        ugoira_fmt = ugoira_fmt.lower()

        if ui_queue:
            ui_queue.put({"type": "log", "text": f"[TIER 1] Terdeteksi Animasi Ugoira. Format target: {ugoira_fmt.upper()}\n"})

        # Ambil metadata ugoira
        ugoira_api = f"{PIXIV_BASE_URL}/ajax/illust/{illust_id}/ugoira_meta"
        try:
            r = requests.get(ugoira_api, headers=headers, timeout=12)
            if r.status_code != 200:
                if ui_queue:
                    ui_queue.put({"type": "log", "text": "[TIER 1 ERROR] Gagal mendapatkan endpoint ugoira_meta.\n"})
                return False
            ug_json = r.json()
            ug_body = ug_json.get('body', {})
            zip_url = ug_body.get('src')
            frames = ug_body.get('frames', [])

            if not zip_url or not frames:
                if ui_queue:
                    ui_queue.put({"type": "log", "text": "[TIER 1 ERROR] Data ZIP Ugoira tidak tersedia.\n"})
                return False

            temp_zip = os.path.join(work_folder, f"_temp_ugoira_{illust_id}.zip")
            if ui_queue:
                ui_queue.put({"type": "log", "text": "Mengunduh arsip frame animasi Ugoira...\n"})

            dl_ok = stream_download_file(
                zip_url, temp_zip, ui_queue, abort_checker,
                headers=headers, label="Unduh Ugoira ZIP"
            )
            if not dl_ok or not os.path.exists(temp_zip):
                return False

            final_media_path = os.path.join(work_folder, f"{illust_id}{title_suffix}.{ugoira_fmt}")
            if ui_queue:
                ui_queue.put({"type": "log", "text": f"Mengonversi {len(frames)} frame ke {ugoira_fmt.upper()} via FFmpeg...\n"})

            conv_ok = convert_ugoira_to_media(
                temp_zip, frames, final_media_path,
                format_type=ugoira_fmt, ui_queue=ui_queue, abort_checker=abort_checker
            )

            # Bersihkan file ZIP sementara
            if os.path.exists(temp_zip):
                try:
                    os.remove(temp_zip)
                except Exception:
                    pass

            if conv_ok and os.path.exists(final_media_path):
                if ui_queue:
                    ui_queue.put({
                        "type": "log",
                        "text": f"\n--- UNDUHAN SUKSES (Pixiv Ugoira) ---\nFile: {final_media_path}\n"
                    })
                    ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
                return True
            else:
                if ui_queue:
                    ui_queue.put({"type": "log", "text": "[ERROR] Konversi FFmpeg Ugoira gagal.\n"})
                return False

        except Exception as e:
            if ui_queue:
                ui_queue.put({"type": "log", "text": f"[TIER 1 EXCEPTION] {e}\n"})
            return False

    # =========================================================================
    # KASUS B: MULTI-PAGE MANGA / ALBUM ILUSTRASI
    # =========================================================================
    if page_count > 1:
        if ui_queue:
            ui_queue.put({"type": "log", "text": f"[TIER 1] Terdeteksi Album Manga / Multi-Page ({page_count} gambar).\n"})

        pages_api = f"{PIXIV_BASE_URL}/ajax/illust/{illust_id}/pages"
        try:
            r = requests.get(pages_api, headers=headers, timeout=12)
            if r.status_code in (403, 404):
                if ui_queue:
                    ui_queue.put({"type": "pixiv_login_required", "url": url})
                    ui_queue.put({
                        "type": "log",
                        "text": "[TIER 1] Endpoint album dibatasi (HTTP 404/403). Diperlukan sesi login Pixiv aktif.\n"
                    })
                return False
            pages_data = r.json().get('body', []) if r.status_code == 200 else []
        except Exception:
            pages_data = []

        if not pages_data:
            if ui_queue:
                if not session:
                    ui_queue.put({"type": "pixiv_login_required", "url": url})
                ui_queue.put({"type": "log", "text": "[TIER 1 ERROR] Gagal mengambil daftar halaman multi-page (Perlu login untuk karya ini).\n"})
            return False

        downloaded_count = 0
        total_p = len(pages_data)
        for i, page in enumerate(pages_data, 1):
            if abort_checker and abort_checker():
                return False

            orig_url = page.get('urls', {}).get('original')
            if not orig_url:
                continue

            # Tentukan ekstensi asli (.png / .jpg)
            ext = ".png" if ".png" in orig_url.lower() else ".jpg"
            dest_file = os.path.join(work_folder, f"{illust_id}_p{i}{title_suffix}{ext}")
            label = f"Halaman {i}/{total_p}"

            if ui_queue:
                ui_queue.put({"type": "log", "text": f"Mengunduh {label}...\n"})

            dl_ok = stream_download_file(
                orig_url, dest_file, ui_queue, abort_checker,
                headers=headers, label=label
            )
            if dl_ok and os.path.exists(dest_file) and os.path.getsize(dest_file) > 100:
                downloaded_count += 1
            else:
                if ui_queue:
                    ui_queue.put({"type": "log", "text": f"[PERINGATAN] Gagal mengunduh {label}.\n"})

        if downloaded_count > 0:
            if ui_queue:
                ui_queue.put({
                    "type": "log",
                    "text": f"\n--- UNDUHAN SUKSES (Pixiv Manga) ---\nFolder: {work_folder}\nBerhasil mengunduh {downloaded_count} halaman HD!\n"
                })
                ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
            return True
        return False

    # =========================================================================
    # KASUS C: SINGLE IMAGE ARTWORK
    # =========================================================================
    try:
        ajax_url = f"{PIXIV_BASE_URL}/ajax/illust/{illust_id}"
        r = requests.get(ajax_url, headers=headers, timeout=12)
        body = r.json().get('body', {})
        orig_url = body.get('urls', {}).get('original')

        if not orig_url:
            # Fallback ke halaman 0 jika urls.original tidak ada di root
            p0_api = f"{PIXIV_BASE_URL}/ajax/illust/{illust_id}/pages"
            r_p0 = requests.get(p0_api, headers=headers, timeout=12)
            pages = r_p0.json().get('body', []) if r_p0.status_code == 200 else []
            if pages:
                orig_url = pages[0].get('urls', {}).get('original')

        if not orig_url:
            if ui_queue:
                if not session:
                    ui_queue.put({"type": "pixiv_login_required", "url": url})
                ui_queue.put({"type": "log", "text": "[TIER 1 ERROR] Tidak dapat menemukan URL gambar resolusi asli (Perlu login untuk karya ini).\n"})
            return False

        ext = ".png" if ".png" in orig_url.lower() else ".jpg"
        dest_file = os.path.join(work_folder, f"{illust_id}_p1{title_suffix}{ext}")

        if ui_queue:
            ui_queue.put({"type": "log", "text": "Mengunduh gambar Pixiv resolusi asli...\n"})

        dl_ok = stream_download_file(
            orig_url, dest_file, ui_queue, abort_checker,
            headers=headers, label="Unduh Gambar Asli"
        )
        if dl_ok and os.path.exists(dest_file) and os.path.getsize(dest_file) > 100:
            if ui_queue:
                ui_queue.put({
                    "type": "log",
                    "text": f"\n--- UNDUHAN SUKSES (Pixiv Artwork) ---\nFile: {dest_file}\n"
                })
                ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
            return True
        return False

    except Exception as e:
        if ui_queue:
            ui_queue.put({"type": "log", "text": f"[TIER 1 EXCEPTION] {e}\n"})
        return False
