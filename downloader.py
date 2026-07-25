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

from config import (
    YT_DLP_PATH, ARIA2_PATH, FFMPEG_PATH, NODE_PATH,
    DEFAULT_OUTPUT_DIR
)

# Antrean pesan untuk thread safety
ui_queue = queue.Queue()

current_process = None

def stop_current_process():
    global current_process
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

def update_progress_bar(line):
    match_yt = re.search(r'\[download\]\s+(\d+\.\d+)%', line)
    match_aria = re.search(r'\((\d+(?:\.\d+)?)%\)', line)
    
    if match_yt:
        percent = float(match_yt.group(1))
        ui_queue.put({"type": "progress", "value": percent / 100.0, "text": f"Progress: {percent:.1f}%"})
    elif match_aria:
        percent = float(match_aria.group(1))
        ui_queue.put({"type": "progress", "value": percent / 100.0, "text": f"Progress: {percent:.1f}%"})
        
    ui_queue.put({"type": "log", "text": line})

def get_video_info(url):
    info_options = ["--skip-download", "--print-json", "--no-playlist", "--js-runtimes", f"node:{NODE_PATH}"]
    info_command = create_yt_dlp_command(url, options=info_options)
    startupinfo = None
    if os.name == 'nt': 
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
    try:
        ui_queue.put({"type": "info_title", "title": "Mengambil Info..."})
        ui_queue.put({"type": "info_thumb", "text": "Mengambil Thumbnail...", "image": None})
        
        result = subprocess.run(info_command, capture_output=True, text=True, check=True, timeout=30, startupinfo=startupinfo)
        stdout_text = result.stdout.strip()
        if not stdout_text:
            raise Exception("Respons info video kosong.")
            
        first_line = stdout_text.splitlines()[0]
        info = json.loads(first_line)
        title = info.get('title', 'Judul Tidak Ditemukan')
        ui_queue.put({"type": "info_title", "title": f"Judul: {title}"})
        
        thumb_url = info.get('thumbnail')
        if thumb_url and thumb_url.startswith('http'):
            image_data = requests.get(thumb_url, timeout=10).content
            image = Image.open(BytesIO(image_data))
            ui_queue.put({"type": "info_thumb_data", "image_data": image_data})
        else:
            ui_queue.put({"type": "info_thumb", "text": "Thumbnail tidak ditemukan.", "image": None})
    except subprocess.CalledProcessError as e:
        ui_queue.put({"type": "info_title", "title": "Gagal mendapatkan info video (url error)."})
        ui_queue.put({"type": "info_thumb", "text": "Gagal mendapatkan info thumbnail.", "image": None})
        ui_queue.put({"type": "log", "text": f"yt-dlp error: {e.stderr}\n"})
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

def download_video_logic(url, mode, audio_format, res, vcodec, acodec, container, download_subs, embed_subs, subs_lang, embed_thumb, use_aria2, download_playlist, custom_path, custom_cmd):
    global current_process
    output_dir = custom_path if custom_path else DEFAULT_OUTPUT_DIR
    
    ui_queue.put({"type": "progress", "value": 0, "text": "Progress: 0.0%"})
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    ui_queue.put({"type": "log", "text": f"\n\n{'='*50}\n"})
    ui_queue.put({"type": "log", "text": f"URL Sumber: {url}\n"}) 
    ui_queue.put({"type": "log", "text": f"Memulai Unduhan Baru Ke: {output_dir}\n"})
    
    options = ["--retries", "infinite", "--fragment-retries", "infinite", "--js-runtimes", f"node:{NODE_PATH}"]
    options.append(f"--ffmpeg-location={FFMPEG_PATH}")
    
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
                "--external-downloader-args", "aria2c:-x 16 -k 1M --allow-overwrite=true"
            ])
            ui_queue.put({"type": "log", "text": "[OPT] Menggunakan Aria2c sebagai downloader.\n"})
            
        if mode == "audio_only":
            options.extend(["-f", "bestaudio", "--extract-audio", "--audio-format", audio_format])
            ui_queue.put({"type": "log", "text": f"[MODE] Audio Saja ({audio_format})\n"})
        else:
            effective_vcodec = vcodec
            effective_acodec = acodec
            if container == "webm":
                if effective_vcodec == "h264":
                    effective_vcodec = "vp9"
                if effective_acodec == "m4a":
                    effective_acodec = "opus"
            elif container == "mov":
                if effective_vcodec in ["vp9", "av1"]:
                    effective_vcodec = "h264"
                if effective_acodec == "opus":
                    effective_acodec = "m4a"

            vcodec_map = {"h264": "avc", "av1": "av01", "vp9": "vp09"}
            acodec_map = {"m4a": "mp4a", "opus": "opus"}
            
            f_video_parts = ["bestvideo"]
            if res != "best":
                f_video_parts.append(f"[height<={res}]")
            if effective_vcodec != "best":
                f_video_parts.append(f"[vcodec~={vcodec_map[effective_vcodec]}]")
                
            f_audio_parts = ["bestaudio"]
            if effective_acodec != "best":
                f_audio_parts.append(f"[acodec~={acodec_map[effective_acodec]}]")
                
            f_video_str = "".join(f_video_parts)
            f_audio_str = "".join(f_audio_parts)
            res_str = "" if res == "best" else f"[height<={res}]"
            
            format_string = (
                f"{f_video_str}+{f_audio_str}/" 
                f"{f_video_str}+bestaudio/" 
                f"bestvideo{res_str}+{f_audio_str}/" 
                f"bestvideo{res_str}+bestaudio/"
                f"bestvideo+bestaudio/"
                "best"
            )
            ui_queue.put({"type": "log", "text": f"[MODE] Video (V: {vcodec}, A: {acodec}, R: {res}p, C: {container})\n"})
            options.extend(["-f", format_string, "--merge-output-format", container])
            
        if download_subs or embed_subs:
            lang = subs_lang.strip() if subs_lang.strip() else "id,en"
            if mode == "audio_only":
                options.extend(["--write-subs", "--write-auto-subs", "--sub-langs", lang, "--convert-subs", "srt"])
                if embed_subs and not download_subs:
                    ui_queue.put({"type": "log", "text": f"[OPT] Mode Audio Saja: Lirik lagu ({lang}) otomatis dibuat sebagai file .lrc di sebelah audio.\n"})
                else:
                    ui_queue.put({"type": "log", "text": f"[OPT] Lirik lagu ({lang}) akan diunduh & disesuaikan sebagai file .lrc.\n"})
            else:
                options.extend(["--write-subs", "--write-auto-subs", "--sub-langs", lang])
                if embed_subs:
                    options.extend(["--embed-subs", "--convert-subs", "srt", "--postprocessor-args", "EmbedSubtitle:-disposition:s:0 default"])
                    ui_queue.put({"type": "log", "text": f"[OPT] Subtitle ({lang}) di-embed & di-set sebagai default aktif.\n"})
                if download_subs:
                    options.extend(["--sub-format", "srt"])
                    ui_queue.put({"type": "log", "text": f"[OPT] Subtitle ({lang}) file .srt terpisah.\n"})
                
        if embed_thumb:
            thumb_supported = False
            if mode == "audio_only":
                if audio_format in ["mp3", "m4a", "flac", "opus", "ogg"]:
                    thumb_supported = True
            else:
                if container in ["mp4", "mkv", "mov"]:
                    thumb_supported = True
                    
            if thumb_supported:
                options.append("--embed-thumbnail")
                ui_queue.put({"type": "log", "text": "[OPT] Thumbnail di-embed.\n"})
            else:
                target_fmt = audio_format if mode == "audio_only" else container
                ui_queue.put({"type": "log", "text": f"[INFO] Format .{target_fmt} tidak mendukung embed thumbnail. Opsi embed thumbnail dilewati.\n"})
                
        options.extend(["-o", os.path.join(output_dir, "%(title)s.%(ext)s")])
        
    command = create_yt_dlp_command(url, options)
    ui_queue.put({"type": "log", "text": f"\nPerintah: {' '.join(command)}\n"})
    
    try:
        startupinfo = None
        if os.name == 'nt': 
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True, startupinfo=startupinfo)
        current_process = process
        for line in iter(process.stdout.readline, ''):
            update_progress_bar(line)
        process.wait() 
        if process.returncode == 0:
            ui_queue.put({"type": "log", "text": "\n\n--- UNDUHAN SUKSES ---\n"})
            if mode == "audio_only" and (download_subs or embed_subs):
                try:
                    for item in os.listdir(output_dir):
                        file_path = os.path.join(output_dir, item)
                        if not os.path.isfile(file_path):
                            continue
                        
                        item_lower = item.lower()
                        # Memeriksa file subtitle/lirik (.srt, .vtt, .lrc, .ass) untuk semua bahasa
                        if item_lower.endswith(('.srt', '.vtt', '.lrc', '.ass')):
                            # Ekstrak judul lagu utama tanpa akhiran bahasa (misal: "Lagu.ja.srt" atau "Lagu.id.srt" -> "Lagu")
                            parts = item.rsplit('.', 2)
                            if len(parts) == 3 and parts[1].replace('-', '_').isalnum() and len(parts[1]) <= 6:
                                base_name = parts[0]
                            else:
                                base_name = os.path.splitext(item)[0]
                                
                            target_lrc_path = os.path.join(output_dir, base_name + ".lrc")
                            
                            if item_lower.endswith('.lrc'):
                                try:
                                    if os.path.exists(target_lrc_path) and target_lrc_path != file_path:
                                        os.remove(target_lrc_path)
                                    os.rename(file_path, target_lrc_path)
                                    ui_queue.put({"type": "log", "text": f"[LIRIK] Nama file lirik disesuaikan -> '{base_name}.lrc'\n"})
                                except Exception:
                                    pass
                            else:
                                if convert_srt_file_to_lrc(file_path, target_lrc_path):
                                    try:
                                        os.remove(file_path)
                                        ui_queue.put({"type": "log", "text": f"[LIRIK] Subtitle dikonversi ke lirik musik -> '{base_name}.lrc'\n"})
                                    except Exception:
                                        pass
                except Exception as e:
                    pass
            elif embed_subs and not download_subs:
                try:
                    for item in os.listdir(output_dir):
                        if item.endswith(('.srt', '.vtt', '.ass', '.ttml')):
                            file_path = os.path.join(output_dir, item)
                            if os.path.isfile(file_path):
                                try:
                                    os.remove(file_path)
                                    ui_queue.put({"type": "log", "text": f"[CLEANUP] Menghapus file subtitle luar '{item}' (sudah ter-embed ke video).\n"})
                                except Exception:
                                    pass
                except Exception:
                    pass
        elif current_process is None:
            # Unduhan dibatalkan pengguna
            pass
        else:
            ui_queue.put({"type": "log", "text": f"\n\n--- UNDUHAN GAGAL --- (Kode: {process.returncode})\n"})
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
        res = subprocess.run([YT_DLP_PATH, "--version"], capture_output=True, text=True, timeout=5, startupinfo=startupinfo)
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return None

def get_latest_ytdlp_version():
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

def update_ytdlp_logic():
    ui_queue.put({"type": "progress", "value": 0.05, "text": "Memeriksa versi..."})
    ui_queue.put({"type": "log", "text": "\n\n=== MEMERIKSA UPDATE YT-DLP ===\n"})
    
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

    ui_queue.put({"type": "log", "text": "Memeriksa versi terbaru di GitHub...\n"})
    latest_ver = get_latest_ytdlp_version()
    
    if latest_ver:
        ui_queue.put({"type": "log", "text": f"Versi Terbaru   : v{latest_ver}\n"})
    else:
        ui_queue.put({"type": "log", "text": "Versi Terbaru   : Gagal mengambil info versi dari GitHub\n"})

    if local_ver and latest_ver and local_ver == latest_ver:
        ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
        ui_queue.put({"type": "log", "text": f"\n[INFO] yt-dlp sudah menggunakan versi terbaru (v{local_ver}). Tidak perlu di-update.\n"})
        ui_queue.put({"type": "log", "text": "=================================\n"})
        return

    if local_ver and latest_ver:
        ui_queue.put({"type": "log", "text": f"\nMemulai pembaruan: v{local_ver} -> v{latest_ver}...\n"})
    else:
        ui_queue.put({"type": "log", "text": "\nMemulai pengunduhan yt-dlp...\n"})

    url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
    temp_path = YT_DLP_PATH + ".new"
    
    try:
        bin_dir = os.path.dirname(YT_DLP_PATH)
        if not os.path.exists(bin_dir):
            os.makedirs(bin_dir, exist_ok=True)
            
        ui_queue.put({"type": "log", "text": "Mengunduh file yt-dlp.exe...\n"})
        
        response = requests.get(url, stream=True, timeout=30)
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
                        
        if os.path.exists(YT_DLP_PATH):
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except Exception:
                    pass
            os.rename(YT_DLP_PATH, old_path)
            
        os.rename(temp_path, YT_DLP_PATH)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except Exception:
                pass
            
        final_ver = get_local_ytdlp_version() or latest_ver or "Terbaru"
        ui_queue.put({"type": "log", "text": f"\n--- UPDATE BERHASIL! (yt-dlp diperbarui ke v{final_ver}) ---\n"})
    except Exception as e:
        ui_queue.put({"type": "log", "text": f"ERROR saat update: {e}\n"})
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        if not os.path.exists(YT_DLP_PATH) and os.path.exists(old_path):
            try:
                os.rename(old_path, YT_DLP_PATH)
            except Exception:
                pass
    finally:
        ui_queue.put({"type": "update_finish"})
