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

# State progress download — reset setiap kali download baru dimulai
_dl_segment_count = 0   # jumlah segmen [download] Destination yang sudah terdeteksi

def reset_download_phase():
    global _dl_segment_count
    _dl_segment_count = 0

def update_progress_bar(line):
    global _dl_segment_count
    progress_data = {"type": "progress"}

    # Deteksi awal segmen baru (yt-dlp log: "[download] Destination: ...")
    # Setiap segmen baru menaikkan counter fase
    if re.search(r'\[download\]\s+Destination:', line):
        _dl_segment_count += 1

    # Persen unduhan (yt-dlp native atau aria2c)
    match_yt = re.search(r'\[download\]\s+([\d.]+)%', line)
    match_aria = re.search(r'\(([\d.]+)%\)', line)

    if match_yt or match_aria:
        raw = match_yt or match_aria
        percent = float(raw.group(1))

        # 2-fase: segmen 1 = video (0–70%), segmen 2 = audio (70–100%)
        # Kalau hanya 1 segmen (audio-only / muxed), pakai 0–100% biasa
        if _dl_segment_count >= 2:
            # Fase audio: 70% + porsi 30%
            unified = 0.70 + (percent / 100.0) * 0.30
            phase_label = f"Audio {percent:.1f}%"
        elif _dl_segment_count == 1:
            # Fase video: porsi 70%
            unified = (percent / 100.0) * 0.70
            phase_label = f"Video {percent:.1f}%"
        else:
            # Belum ada Destination terdeteksi (aria2 dll) — fallback biasa
            unified = percent / 100.0
            phase_label = f"{percent:.1f}%"

        progress_data["value"] = min(unified, 1.0)
        progress_data["text"] = f"Status: {phase_label}"

    # Kecepatan unduhan (contoh: 8.50MiB/s)
    match_speed = re.search(r'at\s+([\d.]+\s*[KMGTk]i?B/s)', line)
    if match_speed:
        progress_data["speed"] = match_speed.group(1).strip()

    # ETA (contoh: ETA 00:35)
    match_eta = re.search(r'ETA\s+([\d:]+)', line)
    if match_eta:
        progress_data["eta"] = match_eta.group(1).strip()

    # Ukuran terunduh / total (contoh: 45.20MiB of 120.50MiB)
    match_size = re.search(r'([\d.]+\s*[KMGTk]i?B)\s+of\s+([\d.]+\s*[KMGTk]i?B)', line)
    if match_size:
        progress_data["size_dl"] = match_size.group(1).strip()
        progress_data["size_total"] = match_size.group(2).strip()

    # Kirim jika ada data progress yang relevan
    if len(progress_data) > 1:
        ui_queue.put(progress_data)

    ui_queue.put({"type": "log", "text": line})


def get_video_info(url, browser_cookie="Tidak Ada"):
    info_options = [
        "--skip-download", "--print-json", "--no-playlist", 
        "--js-runtimes", f"node:{NODE_PATH}",
        "--impersonate", "chrome"
    ]
    if browser_cookie and browser_cookie.lower() != "tidak ada":
        info_options.extend(["--cookies-from-browser", browser_cookie.lower()])
    info_command = create_yt_dlp_command(url, options=info_options)
    startupinfo = None
    if os.name == 'nt': 
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
    try:
        ui_queue.put({"type": "info_title", "title": "Mengambil Info..."})
        ui_queue.put({"type": "info_thumb", "text": "Mengambil Thumbnail...", "image": None})
        
        result = subprocess.run(
            info_command, capture_output=True, text=True, check=True,
            timeout=30, startupinfo=startupinfo, encoding='utf-8', errors='ignore'
        )
        stdout_text = result.stdout.strip()
        if not stdout_text:
            raise Exception("Respons info video kosong.")
            
        first_line = stdout_text.splitlines()[0]
        info = json.loads(first_line)
        title = info.get('title', 'Judul Tidak Ditemukan')
        ui_queue.put({"type": "info_title", "title": f"Judul: {title}"})

        # Kirim full info dict untuk fitur AI & metadata card
        ui_queue.put({"type": "info_data", "data": info})

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
                        ui_queue.put({"type": "log", "text": f"[EMBED SUB] ✨ Subtitle berhasil di-embed ke track P0! Langsung aktif saat diputar & tetap bisa di-OFF kan.\n"})
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

def download_video_logic(url, mode, audio_format, res, vcodec, acodec, container, download_subs, embed_subs, subs_lang, embed_thumb, use_aria2, download_playlist, custom_path, custom_cmd, browser_cookie="Tidak Ada"):
    global current_process
    output_dir = custom_path if custom_path else DEFAULT_OUTPUT_DIR
    
    ui_queue.put({"type": "progress", "value": 0, "text": "Progress: 0.0%"})
    reset_download_phase()  # Reset fase video/audio untuk download baru

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    ui_queue.put({"type": "log", "text": f"\n\n{'='*50}\n"})
    ui_queue.put({"type": "log", "text": f"URL Sumber: {url}\n"}) 
    ui_queue.put({"type": "log", "text": f"Memulai Unduhan Baru Ke: {output_dir}\n"})
    
    options = [
        "--ignore-errors", "--retries", "infinite", 
        "--fragment-retries", "infinite", 
        "--js-runtimes", f"node:{NODE_PATH}",
        "--impersonate", "chrome"
    ]
    options.append(f"--ffmpeg-location={FFMPEG_PATH}")
    
    if browser_cookie and browser_cookie.lower() != "tidak ada":
        options.extend(["--cookies-from-browser", browser_cookie.lower()])
        ui_queue.put({"type": "log", "text": f"[OPT] Menggunakan Cookies dari Browser: {browser_cookie}\n"})
    
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
            
            # Tambahkan juga constraint pada format "best" (pre-muxed) dan "bestvideo" saja.
            b_str = f"best{res_str}"
            if effective_vcodec != "best":
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
            ui_queue.put({"type": "log", "text": f"[MODE] Video (V: {vcodec}, A: {acodec}, R: {res}p, C: {container})\n"})
            options.extend(["-f", format_string, "--merge-output-format", container])
            
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
            
        import time
        download_start_time = time.time() - 3.0

        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, universal_newlines=True,
            startupinfo=startupinfo, encoding='utf-8', errors='ignore'
        )
        current_process = process
        for line in iter(process.stdout.readline, ''):
            update_progress_bar(line)
        process.wait() 
        if process.returncode == 0:
            ui_queue.put({"type": "log", "text": "\n\n--- UNDUHAN SUKSES ---\n"})
            if download_subs or embed_subs:
                process_downloaded_subtitles(output_dir, download_start_time, mode == "audio_only", embed_subs, download_subs)
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
            timeout=5, startupinfo=startupinfo, encoding='utf-8', errors='ignore'
        )
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
