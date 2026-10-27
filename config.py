import os
import sys
import json

# Konfigurasi Path yang aman untuk Nuitka & Python murni
if "__compiled__" in globals() or getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Direktori Data Pengguna (Standar Windows AppData & Cross-Platform)
# Menjamin izin menulis selalu tersedia meski aplikasi diinstal di C:\Program Files
if os.name == 'nt':
    _local_appdata = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    USER_DATA_DIR = os.path.join(_local_appdata, 'SayMaven', 'Mavdown')
else:
    USER_DATA_DIR = os.path.join(os.path.expanduser('~'), '.mavdown')

try:
    os.makedirs(USER_DATA_DIR, exist_ok=True)
except Exception:
    USER_DATA_DIR = BASE_DIR

USER_BIN_DIR = os.path.join(USER_DATA_DIR, "bin")
try:
    os.makedirs(USER_BIN_DIR, exist_ok=True)
except Exception:
    pass

# Dynamic resolver untuk executable (prioritas: updated binary di User Data, fallback: bundled di BASE_DIR/bin)
def _resolve_binary(name: str) -> str:
    user_bin = os.path.join(USER_BIN_DIR, name)
    if os.path.isfile(user_bin) and os.path.getsize(user_bin) > 1024:
        return user_bin
    return os.path.join(BASE_DIR, "bin", name)

YT_DLP_PATH = _resolve_binary("yt-dlp.exe")
ARIA2_PATH = _resolve_binary("aria2c.exe")
FFMPEG_PATH = _resolve_binary("ffmpeg.exe") 
FFPROBE_PATH = _resolve_binary("ffprobe.exe")
NODE_PATH = _resolve_binary("node.exe")

def refresh_binary_paths():
    """Segarkan path biner setelah update atau pemulihan selesai."""
    global YT_DLP_PATH, ARIA2_PATH, FFMPEG_PATH, FFPROBE_PATH, NODE_PATH
    YT_DLP_PATH = _resolve_binary("yt-dlp.exe")
    ARIA2_PATH = _resolve_binary("aria2c.exe")
    FFMPEG_PATH = _resolve_binary("ffmpeg.exe") 
    FFPROBE_PATH = _resolve_binary("ffprobe.exe")
    NODE_PATH = _resolve_binary("node.exe")

def get_sanitized_env() -> dict:
    """
    Menghasilkan copy os.environ dengan PATH yang disanitasi:
    1. Memprioritaskan folder bin internal Mavdown (USER_BIN_DIR dan BASE_DIR/bin) di urutan pertama.
    2. Menyaring junction/reparse point yang tidak terpercaya (seperti scoop\\apps) yang memicu
       [WinError 448] (STATUS_UNTRUSTED_MOUNT_POINT) di Windows 11 saat proses berjalan di context elevated.
    3. Memastikan setiap direktori di PATH dapat diakses tanpa memicu OSError.
    """
    env = os.environ.copy()
    raw_path = env.get("PATH", "")
    paths = raw_path.split(os.pathsep)

    clean_paths = []
    base_bin = os.path.join(BASE_DIR, "bin")

    if os.path.isdir(USER_BIN_DIR) and USER_BIN_DIR not in clean_paths:
        clean_paths.append(USER_BIN_DIR)
    if os.path.isdir(base_bin) and base_bin not in clean_paths:
        clean_paths.append(base_bin)

    for p in paths:
        p_clean = p.strip().strip('"')
        if not p_clean or p_clean in clean_paths:
            continue
        p_lower = p_clean.lower()
        if r"scoop\apps" in p_lower:
            continue
        try:
            os.stat(p_clean)
            clean_paths.append(p_clean)
        except OSError:
            continue

    env["PATH"] = os.pathsep.join(clean_paths)
    return env

def sanitize_current_process_env():
    """Terapkan PATH yang bersih ke proses saat ini secara instan."""
    try:
        clean_env = get_sanitized_env()
        os.environ["PATH"] = clean_env.get("PATH", os.environ.get("PATH", ""))
    except Exception:
        pass

# Bersihkan environment saat modul config diimpor pertama kali
sanitize_current_process_env()

def get_ytdlp_update_dest() -> str:
    """Mengembalikan path writeable di User Data untuk menyimpan pembaruan yt-dlp."""
    return os.path.join(USER_BIN_DIR, "yt-dlp.exe")

# Standar folder unduhan pengguna di OS Windows/Linux
DEFAULT_OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "Mavdown")
try:
    os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
except Exception:
    DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "downloads")

CONFIG_FILE = os.path.join(USER_DATA_DIR, "config.json")
LEGACY_CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
HISTORY_FILE = os.path.join(USER_DATA_DIR, "history.json")

def _read_raw_config() -> dict:
    """Baca config dict mentah dari file dengan migrasi otomatis dari legacy path."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass

    # Migrasi otomatis jika config lama ada di folder instalasi
    if os.path.exists(LEGACY_CONFIG_FILE):
        try:
            with open(LEGACY_CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                _write_raw_config(data)
                return data
        except Exception:
            pass

    return {}

def _write_raw_config(data: dict):
    """Tulis config dict ke file di USER_DATA_DIR."""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"ERROR saving config: {e}")

def save_config(path: str = None, browser_cookie: str = None, proxy: str = None, clipboard_monitor: bool = None, organize_by_platform: bool = None):
    """
    Simpan folder output unduhan, cookie browser, proxy, dan preferensi clipboard ke config file.
    """
    data = _read_raw_config()
    if path is not None:
        data["output_path"] = path
        if path and not os.path.exists(path):
            try:
                os.makedirs(path, exist_ok=True)
            except Exception:
                pass
    if browser_cookie is not None:
        data["browser_cookie"] = browser_cookie
    if proxy is not None:
        data["proxy"] = proxy.strip()
    if clipboard_monitor is not None:
        data["clipboard_monitor"] = bool(clipboard_monitor)
    if organize_by_platform is not None:
        data["organize_by_platform"] = bool(organize_by_platform)
        
    _write_raw_config(data)

def save_organize_by_platform(enabled: bool):
    """Simpan preferensi pengelompokan folder per layanan/platform."""
    data = _read_raw_config()
    data["organize_by_platform"] = bool(enabled)
    _write_raw_config(data)

def load_organize_by_platform() -> bool:
    """Muat preferensi pengelompokan folder per layanan (default: True)."""
    data = _read_raw_config()
    return bool(data.get("organize_by_platform", True))

def save_pixiv_session(session: str):
    """Simpan cookie sesi PHPSESSID Pixiv ke config file."""
    data = _read_raw_config()
    clean = session.strip() if session else ""
    data["pixiv_session"] = clean
    if not clean:
        data["pixiv_account_name"] = ""
    _write_raw_config(data)

def load_pixiv_session() -> str:
    """Muat cookie sesi PHPSESSID Pixiv tersimpan."""
    data = _read_raw_config()
    return data.get("pixiv_session", "")

def save_pixiv_account_name(name: str):
    """Simpan label/nama akun Pixiv yang telah terverifikasi."""
    data = _read_raw_config()
    data["pixiv_account_name"] = name.strip() if name else ""
    _write_raw_config(data)

def load_pixiv_account_name() -> str:
    """Muat nama akun Pixiv terverifikasi tersimpan."""
    data = _read_raw_config()
    return data.get("pixiv_account_name", "")

def save_bilibili_session(session: str):
    """Simpan cookie sesi SESSDATA Bilibili ke config file."""
    data = _read_raw_config()
    clean = session.strip() if session else ""
    data["bilibili_session"] = clean
    if not clean:
        data["bilibili_account_name"] = ""
    _write_raw_config(data)

def load_bilibili_session() -> str:
    """Muat cookie sesi SESSDATA Bilibili tersimpan."""
    data = _read_raw_config()
    return data.get("bilibili_session", "")

def save_bilibili_account_name(name: str):
    """Simpan label/nama akun Bilibili yang telah terverifikasi."""
    data = _read_raw_config()
    data["bilibili_account_name"] = name.strip() if name else ""
    _write_raw_config(data)

def load_bilibili_account_name() -> str:
    """Muat nama akun Bilibili terverifikasi tersimpan."""
    data = _read_raw_config()
    return data.get("bilibili_account_name", "")

def load_config() -> str:
    """Kembalikan path output yang tersimpan (backward-compatible)."""
    if not os.path.exists(DEFAULT_OUTPUT_DIR):
        try:
            os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
        except Exception:
            pass
    data = _read_raw_config()
    saved_path = data.get("output_path", DEFAULT_OUTPUT_DIR)
    if saved_path and os.path.isdir(saved_path):
        return saved_path
    return DEFAULT_OUTPUT_DIR

def load_browser_cookie() -> str:
    """Kembalikan pengaturan browser cookie."""
    data = _read_raw_config()
    return data.get("browser_cookie", "")

def save_proxy(proxy: str):
    """Simpan alamat proxy jaringan (misal: http://127.0.0.1:7890)."""
    data = _read_raw_config()
    data["proxy"] = proxy.strip() if proxy else ""
    _write_raw_config(data)

def load_proxy() -> str:
    """Muat alamat proxy jaringan tersimpan."""
    data = _read_raw_config()
    return data.get("proxy", "")

def save_clipboard_monitor(enabled: bool):
    """Simpan status pemantauan clipboard otomatis."""
    data = _read_raw_config()
    data["clipboard_monitor"] = bool(enabled)
    _write_raw_config(data)

def load_clipboard_monitor() -> bool:
    """Muat status pemantauan clipboard (default: False)."""
    data = _read_raw_config()
    return bool(data.get("clipboard_monitor", False))

def save_preferences(prefs: dict):
    """Simpan preferensi UI lengkap ke config file."""
    data = _read_raw_config()
    data["preferences"] = prefs
    _write_raw_config(data)

def load_preferences() -> dict:
    """Muat preferensi UI tersimpan."""
    data = _read_raw_config()
    return data.get("preferences", {})

def is_aria2_available() -> bool:
    """Cek apakah aria2c.exe tersedia di direktori bin."""
    return os.path.isfile(ARIA2_PATH)

def save_ytdlp_channel(channel: str):
    """Simpan channel update yt-dlp ('stable' atau 'nightly')."""
    data = _read_raw_config()
    data["ytdlp_channel"] = channel
    _write_raw_config(data)

def load_ytdlp_channel() -> str:
    """Muat channel update yt-dlp tersimpan (default: 'stable')."""
    data = _read_raw_config()
    return data.get("ytdlp_channel", "stable")

