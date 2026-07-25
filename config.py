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

def save_config(path):
    try:
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({"output_path": path}, f)
    except Exception as e:
        print(f"ERROR saving config: {e}")

def load_config():
    if not os.path.exists(DEFAULT_OUTPUT_DIR):
        os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                saved_path = config.get('output_path', DEFAULT_OUTPUT_DIR)
                if saved_path and os.path.isdir(saved_path):
                    return saved_path
        except Exception:
            pass
    return DEFAULT_OUTPUT_DIR
