import os
import sys
import json

# Konfigurasi Path yang aman untuk Nuitka & Python murni
if "__compiled__" in globals() or getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

YT_DLP_PATH = os.path.join(BASE_DIR, "bin", "yt-dlp.exe")
ARIA2_PATH = os.path.join(BASE_DIR, "bin", "aria2c.exe")
FFMPEG_PATH = os.path.join(BASE_DIR, "bin", "ffmpeg.exe") 
NODE_PATH = os.path.join(BASE_DIR, "bin", "node.exe")

DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "downloads")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

def _read_raw_config() -> dict:
    """Baca config dict mentah dari file."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _write_raw_config(data: dict):
    """Tulis config dict ke file."""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"ERROR saving config: {e}")

def save_config(path: str = None, browser_cookie: str = None):
    """
    Simpan folder output unduhan dan setting browser cookie ke config file.
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
        
    _write_raw_config(data)

def load_config() -> str:
    """Kembalikan path output yang tersimpan (backward-compatible)."""
    if not os.path.exists(DEFAULT_OUTPUT_DIR):
        os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
    data = _read_raw_config()
    saved_path = data.get("output_path", DEFAULT_OUTPUT_DIR)
    if saved_path and os.path.isdir(saved_path):
        return saved_path
    return DEFAULT_OUTPUT_DIR

def load_browser_cookie() -> str:
    """Kembalikan pengaturan browser cookie."""
    data = _read_raw_config()
    return data.get("browser_cookie", "chrome")
