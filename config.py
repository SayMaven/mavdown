import os
import sys
import json

# Konfigurasi Path yang aman untuk Nuitka & Python murni
if "__compiled__" in globals() or getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Untuk porting ke Android (Flet), kita tidak lagi bergantung pada .exe eksternal.
# Jika membutuhkan FFmpeg khusus, letakkan di path Android atau gunakan modul eksternal.

DEFAULT_OUTPUT_DIR = os.path.expanduser("~/storage/shared/Download/Mavdown")
if not os.path.exists(os.path.expanduser("~/storage/shared/Download")):
    # Fallback ke folder lokal jika tidak berjalan di Android
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

def save_config(path: str = None):
    """
    Simpan folder output unduhan ke config file.
    """
    data = _read_raw_config()
    if path is not None:
        data["output_path"] = path
        if path and not os.path.exists(path):
            try:
                os.makedirs(path, exist_ok=True)
            except Exception:
                pass
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

def get_full_config() -> dict:
    """Mengembalikan semua konfigurasi dengan default fallback."""
    data = _read_raw_config()
    default_config = {
        "output_path": DEFAULT_OUTPUT_DIR,
        "theme": "dark",
        "language": "id"
    }
    # Timpa default dengan apa yang tersimpan
    for k, v in default_config.items():
        if k not in data:
            data[k] = v
    return data

def save_full_config(data: dict):
    """Menimpa keseluruhan konfigurasi."""
    _write_raw_config(data)
