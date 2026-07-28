import os
import sys
import requests
from PIL import Image
from io import BytesIO
import re
import json
import queue
import yt_dlp
import threading
import time
import zipfile
import tempfile
import stat
import shutil

from config import DEFAULT_OUTPUT_DIR, is_android, BASE_DIR

# Antrean pesan untuk thread safety (ke UI)
ui_queue = queue.Queue()

# Menyimpan status pengunduhan
download_state = {}

def stop_task(task_id):
    if task_id in download_state:
        download_state[task_id]["is_cancelled"] = True
        ui_queue.put({"type": "log", "task_id": task_id, "text": "\n\n[DIBATALKAN] Proses unduhan dihentikan oleh pengguna.\n"})

def get_video_info(url):
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'extract_flat': False,
        'no_playlist': True,
        'youtube_include_dash_manifest': False,
        'youtube_include_hls_manifest': False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        
    if not info:
        raise Exception("Respons info video kosong.")
        
    return info


class UI_Logger:
    def debug(self, msg):
        if not msg.startswith('[debug] '):
            ui_queue.put({"type": "log", "text": msg + "\n"})
    def warning(self, msg):
        if "JavaScript runtime" in msg or "EJS" in msg:
            return
        ui_queue.put({"type": "log", "text": f"[WARN] {msg}\n"})
    def error(self, msg):
        ui_queue.put({"type": "log", "text": f"[ERROR] {msg}\n"})


def expand_sub_langs(subs_lang_str: str) -> str:
    if not subs_lang_str:
        return "id,id-ID,id-orig,id-id,en,en-US,en-GB,en-orig,en-en"
    raw = subs_lang_str.strip().lower()
    if raw in ("all", ".*"):
        return "all"
    
    tokens = [t.strip() for t in subs_lang_str.split(",") if t.strip()]
    expanded = []
    for t in tokens:
        expanded.append(t)
        t_clean = t.split('-')[0].lower()
        if t_clean == "en":
            expanded.extend(["en-US", "en-GB", "en-orig", "en-en"])
        elif t_clean == "id":
            expanded.extend(["id-ID", "id-orig", "id-id"])
        elif t_clean == "ja":
            expanded.extend(["ja-JP", "ja-orig"])
        elif t_clean == "zh":
            expanded.extend(["zh-Hans", "zh-Hant", "zh-CN", "zh-TW"])
        elif t_clean == "ko":
            expanded.extend(["ko-KR", "ko-orig"])
        elif t_clean == "es":
            expanded.extend(["es-ES", "es-419"])
        else:
            expanded.extend([f"{t_clean}-{t_clean}", f"{t_clean}-orig"])
            
    seen = set()
    res = []
    for item in expanded:
        if item not in seen:
            seen.add(item)
            res.append(item)
    return ",".join(res)

def setup_ffmpeg_android(task_id=None):
    if not is_android():
        return None
        
    try:
        ffmpeg_bin_path = os.path.join(BASE_DIR, "bin", "ffmpeg")
        if not os.path.exists(ffmpeg_bin_path):
            if task_id: ui_queue.put({"type": "log", "task_id": task_id, "text": f"[WARN] FFmpeg tidak ditemukan di {ffmpeg_bin_path}\n"})
            return None
            
        cache_dir = tempfile.gettempdir()
        target_ffmpeg = os.path.join(cache_dir, "ffmpeg")
        
        if not os.path.exists(target_ffmpeg) or os.path.getsize(ffmpeg_bin_path) != os.path.getsize(target_ffmpeg):
            if task_id: ui_queue.put({"type": "log", "task_id": task_id, "text": "[INFO] Menyalin FFmpeg khusus Android ke cache...\n"})
            shutil.copy2(ffmpeg_bin_path, target_ffmpeg)
                
        st = os.stat(target_ffmpeg)
        os.chmod(target_ffmpeg, st.st_mode | stat.S_IEXEC)
        
        return target_ffmpeg
    except Exception as e:
        if task_id: ui_queue.put({"type": "log", "task_id": task_id, "text": f"[ERROR] Gagal mengatur FFmpeg: {e}\n"})
        return None


def download_video_logic(task_id, url, mode, audio_format, res, vcodec, acodec, container, download_subs, embed_subs, subs_lang, embed_thumb, download_playlist, custom_path, custom_cmd=""):
    output_dir = custom_path if custom_path else DEFAULT_OUTPUT_DIR
    
    download_state[task_id] = {"is_cancelled": False, "url": url}
    
    ui_queue.put({"type": "progress", "task_id": task_id, "value": 0, "text": "Progress: 0.0%"})

    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir, exist_ok=True)
        except Exception as e:
            ui_queue.put({"type": "log", "task_id": task_id, "text": f"Error membuat folder: {e}\n"})
            ui_queue.put({"type": "download_finish", "task_id": task_id})
            return
            
    ui_queue.put({"type": "log", "task_id": task_id, "text": f"\n\n{'='*50}\n"})
    ui_queue.put({"type": "log", "task_id": task_id, "text": f"URL Sumber: {url}\n"}) 
    ui_queue.put({"type": "log", "task_id": task_id, "text": f"Lokasi Output: {output_dir}\n"})

    def task_hook(d):
        if download_state.get(task_id, {}).get("is_cancelled"):
            raise Exception("Download cancelled by user")

        if d['status'] == 'downloading':
            percent_str = d.get('_percent_str', '0%').strip()
            percent_str = re.sub(r'\x1b\[[0-9;]*m', '', percent_str)
            percent_clean = percent_str.replace('%', '')
            
            try:
                percent_val = float(percent_clean) / 100.0
            except ValueError:
                percent_val = 0.0
                
            speed = d.get('_speed_str', '')
            speed = re.sub(r'\x1b\[[0-9;]*m', '', speed).strip()
            
            eta = d.get('_eta_str', '')
            eta = re.sub(r'\x1b\[[0-9;]*m', '', eta).strip()
            
            size_dl = d.get('_downloaded_bytes_str', '')
            size_dl = re.sub(r'\x1b\[[0-9;]*m', '', size_dl).strip()
            
            size_total = d.get('_total_bytes_str', '') or d.get('_total_bytes_estimate_str', '')
            size_total = re.sub(r'\x1b\[[0-9;]*m', '', size_total).strip()

            state = download_state.get(task_id, {})
            current_filename = d.get('filename', '')
            if state.get("current_filename") != current_filename:
                state["current_filename"] = current_filename
                state["part_index"] = state.get("part_index", 0) + 1

            part = ""
            if mode != "audio_only":
                part_idx = state.get("part_index", 1)
                if part_idx == 1:
                    part = "Video"
                elif part_idx == 2:
                    part = "Audio"
                else:
                    part = "Proses Tambahan"

            ui_queue.put({
                "type": "progress",
                "task_id": task_id,
                "value": min(percent_val, 1.0),
                "text": f"Status: {percent_str}",
                "speed": speed,
                "eta": eta,
                "size_dl": size_dl,
                "size_total": size_total,
                "part": part
            })
    
    ydl_opts = {
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'logger': UI_Logger(),
        'progress_hooks': [task_hook],
        'ignoreerrors': True,
        'noplaylist': not download_playlist,
        'concurrent_fragment_downloads': 8,
    }
    
    if is_android():
        ffmpeg_path = setup_ffmpeg_android(task_id)
        if ffmpeg_path:
            ydl_opts['ffmpeg_location'] = ffmpeg_path


    if mode == "audio_only":
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': audio_format if audio_format else 'mp3',
            'preferredquality': '192',
        }]
        ui_queue.put({"type": "log", "text": f"[MODE] Audio Saja ({audio_format})\n"})
    else:
        vcodec_map = {"h264": "avc", "av1": "av01", "vp9": "vp09"}
        acodec_map = {"m4a": "mp4a", "opus": "opus"}

        f_video_parts = ["bestvideo"]
        if res and res != "best":
            f_video_parts.append(f"[height<={res}]")
        if vcodec and vcodec != "best" and vcodec in vcodec_map:
            f_video_parts.append(f"[vcodec~={vcodec_map[vcodec]}]")
            
        f_audio_parts = ["bestaudio"]
        if acodec and acodec != "best" and acodec in acodec_map:
            f_audio_parts.append(f"[acodec~={acodec_map[acodec]}]")
            
        if vcodec and vcodec.startswith("override:"):
            format_string = vcodec.replace("override:", "")
            ydl_opts['format'] = format_string
            ui_queue.put({"type": "log", "text": f"[MODE] Kustom Format Override: {format_string}\n"})
        else:
            f_video_str = "".join(f_video_parts)
            f_audio_str = "".join(f_audio_parts)
            res_str = "" if not res or res == "best" else f"[height<={res}]"

            format_string = (
                f"{f_video_str}+{f_audio_str}/" 
                f"{f_video_str}+bestaudio/" 
                f"bestvideo{res_str}+{f_audio_str}/" 
                f"bestvideo{res_str}+bestaudio/"
                f"bestvideo+bestaudio/"
                "best"
            )
            ydl_opts['format'] = format_string
            ydl_opts['merge_output_format'] = container if container else 'mp4'
            ui_queue.put({"type": "log", "text": f"[MODE] Video (V: {vcodec}, A: {acodec}, R: {res}p, C: {container})\n"})

    if embed_thumb:
        ydl_opts['writethumbnail'] = True
        postprocessors = ydl_opts.get('postprocessors', [])
        postprocessors.append({'key': 'FFmpegMetadata'})
        postprocessors.append({'key': 'EmbedThumbnail'})
        ydl_opts['postprocessors'] = postprocessors
        ui_queue.put({"type": "log", "text": "[OPT] Thumbnail di-embed.\n"})

    if download_subs or embed_subs:
        effective_lang = expand_sub_langs(subs_lang)
        ydl_opts['writesubtitles'] = True
        ydl_opts['writeautomaticsub'] = True
        ydl_opts['subtitleslangs'] = effective_lang.split(',')
        ydl_opts['subtitlesformat'] = 'srt'
        
        if embed_subs and mode != "audio_only":
            postprocessors = ydl_opts.get('postprocessors', [])
            postprocessors.append({'key': 'FFmpegEmbedSubtitle'})
            ydl_opts['postprocessors'] = postprocessors
        ui_queue.put({"type": "log", "text": f"[OPT] Subtitle/Lirik ({subs_lang}) diaktifkan.\n"})

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ui_queue.put({"type": "log", "task_id": task_id, "text": "Memulai pengunduhan internal (Multi-threaded)...\n"})
            ydl.download([url])
            
        if download_state.get(task_id, {}).get("is_cancelled"):
            ui_queue.put({"type": "log", "task_id": task_id, "text": "\n--- UNDUHAN DIBATALKAN ---\n"})
        else:
            ui_queue.put({"type": "log", "task_id": task_id, "text": "\n\n--- UNDUHAN SUKSES ---\n"})
            ui_queue.put({"type": "progress", "task_id": task_id, "value": 1.0, "text": "Progress: Selesai"})
            
    except Exception as e:
        msg = str(e)
        if "Download cancelled" in msg:
            ui_queue.put({"type": "log", "task_id": task_id, "text": "\n\n--- UNDUHAN DIBATALKAN ---\n"})
        else:
            ui_queue.put({"type": "log", "task_id": task_id, "text": f"\n\n--- UNDUHAN GAGAL --- ({msg})\n"})
            ui_queue.put({"type": "download_error", "task_id": task_id})
    finally:
        ui_queue.put({"type": "download_finish", "task_id": task_id})


def update_ytdlp_logic():
    ui_queue.put({"type": "log", "text": "\n\n[INFO] Versi yt-dlp menggunakan modul Python resmi.\n"})
    ui_queue.put({"type": "progress", "value": 1.0, "text": "Selesai"})
    ui_queue.put({"type": "update_finish"})
