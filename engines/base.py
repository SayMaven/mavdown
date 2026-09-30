import os
import sys
import re
import time
import subprocess
import json
import requests

# Import path biner dari config Mavdown
try:
    from config import FFMPEG_PATH, FFPROBE_PATH, DEFAULT_OUTPUT_DIR
except ImportError:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    FFMPEG_PATH = os.path.join(BASE_DIR, "bin", "ffmpeg.exe")
    FFPROBE_PATH = os.path.join(BASE_DIR, "bin", "ffprobe.exe")
    DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "downloads")

# User-Agent standar modern
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7'
}

def sanitize_filename(name: str, max_length: int = 120) -> str:
    """
    Membersihkan string agar aman digunakan sebagai nama file di OS Windows.
    Menghapus karakter terlarang: \\ / : * ? " < > | dan emoji berlebih jika perlu.
    """
    if not name:
        return "downloaded_media"
    
    # Hapus karakter terlarang Windows
    clean = re.sub(r'[\\/*?:"<>|\r\n\t]', '_', name)
    # Rapatkan spasi duplikat
    clean = re.sub(r'\s+', ' ', clean).strip(' ._')
    
    if not clean:
        clean = "downloaded_media"
        
    if len(clean) > max_length:
        clean = clean[:max_length].strip(' ._')
        
    return clean

def format_bytes(size: float) -> str:
    """Konversi ukuran byte ke representasi terformat KiB/MiB/GiB."""
    for unit in ['B', 'KiB', 'MiB', 'GiB', 'TiB']:
        if abs(size) < 1024.0:
            return f"{size:.2f}{unit}"
        size /= 1024.0
    return f"{size:.2f}PiB"

def format_time(seconds: float) -> str:
    """Format detik ke format MM:SS atau HH:MM:SS."""
    if seconds < 0 or seconds > 86400:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def stream_download_file(
    url: str, 
    dest_path: str, 
    ui_queue=None, 
    abort_checker=None, 
    headers=None, 
    timeout: int = 30,
    label: str = "Mengunduh"
) -> bool:
    """
    Mengunduh file dari URL secara streaming dengan kalkulasi progress, speed, ETA,
    serta mengirim update berkala ke ui_queue Mavdown.
    Mendukung pengecekan pembatalan (abort_checker).
    """
    req_headers = dict(DEFAULT_HEADERS)
    if headers:
        req_headers.update(headers)

    temp_path = dest_path + ".tmp"
    
    try:
        dest_dir = os.path.dirname(dest_path)
        if dest_dir and not os.path.exists(dest_dir):
            os.makedirs(dest_dir, exist_ok=True)
            
        with requests.get(url, stream=True, headers=req_headers, timeout=timeout) as response:
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            start_time = time.time()
            last_ui_update = 0.0
            last_dl_bytes = 0
            speed_str = "--MiB/s"
            eta_str = "--:--"
            
            with open(temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=65536):
                    # Cek apakah ada permintaan pembatalan dari pengguna
                    if abort_checker and abort_checker():
                        if ui_queue:
                            ui_queue.put({"type": "log", "text": "\n[DIBATALKAN] Pengunduhan dibatalkan oleh pengguna.\n"})
                        if os.path.exists(temp_path):
                            try: os.remove(temp_path)
                            except Exception: pass
                        return False
                        
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        current_time = time.time()
                        # Update progress ke UI setiap 0.2 detik agar GUI tetap responsif
                        if current_time - last_ui_update >= 0.2:
                            elapsed = current_time - start_time
                            interval = current_time - last_ui_update
                            
                            # Hitung kecepatan instan
                            delta_bytes = downloaded - last_dl_bytes
                            speed_bps = delta_bytes / interval if interval > 0 else 0
                            speed_str = f"{format_bytes(speed_bps)}/s"
                            
                            # Hitung persentase & ETA
                            if total_size > 0:
                                percent = downloaded / total_size
                                remaining_bytes = total_size - downloaded
                                if speed_bps > 0:
                                    eta_sec = remaining_bytes / speed_bps
                                    eta_str = f"ETA {format_time(eta_sec)}"
                                else:
                                    eta_str = "ETA --:--"
                                    
                                if ui_queue:
                                    ui_queue.put({
                                        "type": "progress",
                                        "value": min(percent, 1.0),
                                        "text": f"Status: {label} ({int(percent * 100)}%)",
                                        "speed": speed_str,
                                        "eta": eta_str,
                                        "size_dl": format_bytes(downloaded),
                                        "size_total": format_bytes(total_size)
                                    })
                            else:
                                if ui_queue:
                                    ui_queue.put({
                                        "type": "progress",
                                        "value": 0.5,
                                        "text": f"Status: {label} {format_bytes(downloaded)}",
                                        "speed": speed_str,
                                        "eta": "--:--",
                                        "size_dl": format_bytes(downloaded),
                                        "size_total": "Ukuran tidak diketahui"
                                    })
                                    
                            last_ui_update = current_time
                            last_dl_bytes = downloaded

        # Selesai unduh, rename .tmp ke nama final
        if os.path.exists(dest_path):
            try: os.remove(dest_path)
            except Exception: pass
            
        os.rename(temp_path, dest_path)
        
        if ui_queue and total_size > 0:
            ui_queue.put({
                "type": "progress",
                "value": 1.0,
                "text": f"Status: {label} Selesai (100%)",
                "speed": speed_str,
                "eta": "00:00",
                "size_dl": format_bytes(total_size),
                "size_total": format_bytes(total_size)
            })
        return True

    except Exception as e:
        if os.path.exists(temp_path):
            try: os.remove(temp_path)
            except Exception: pass
        if ui_queue:
            ui_queue.put({"type": "log", "text": f"\n[STREAM ERROR] Gagal mengunduh file: {e}\n"})
        return False

def postprocess_video(
    raw_video_path: str,
    final_output_path: str,
    options: dict = None,
    ui_queue=None,
    abort_checker=None
) -> bool:
    """
    Memproses video yang telah diunduh:
    - Jika opsi default ('best'): melakukan Fast Remux (-c copy -movflags +faststart) instan tanpa beban CPU.
    - Jika opsi custom:
      * Menyesuaikan resolusi (downscaling proporsional 1080p, 720p, 480p, 360p).
      * Mengonversi video codec (H.264, VP9, AV1) dengan preset fast.
      * Menyesuaikan audio codec & container (MP4, MKV, WEBM, MOV).
    """
    if not os.path.exists(raw_video_path) or os.path.getsize(raw_video_path) == 0:
        return False

    if not os.path.exists(FFMPEG_PATH):
        try:
            if os.path.exists(final_output_path):
                os.remove(final_output_path)
            os.rename(raw_video_path, final_output_path)
            return True
        except Exception:
            return False

    if options is None:
        options = {}

    target_res = options.get('resolution', 'best')
    target_vcodec = (options.get('video_codec', 'best') or 'best').lower()
    target_acodec = (options.get('audio_codec', 'best') or 'best').lower()
    raw_container = options.get('container', 'auto') if options else 'auto'
    target_container = 'mp4' if raw_container in ('auto', 'best', '', None) else str(raw_container).lower()

    # Probe metadata stream lokal
    meta = probe_media_stream(raw_video_path)
    src_w = meta.get('width') or 0
    src_h = meta.get('height') or 0
    src_vcodec = (meta.get('codec') or '').lower()

    needs_scale = False
    scale_filter = None
    if target_res and str(target_res).lower() != "best" and str(target_res).isdigit():
        target_dim = int(target_res)
        min_src = min(src_w, src_h) if (src_w and src_h) else 0
        if min_src > 0 and target_dim < min_src:
            needs_scale = True
            # Jika video vertikal (portrait, misal 2160x3840 -> 720x1280)
            if src_w <= src_h:
                scale_filter = f"scale={target_dim}:-2"
            else:
                scale_filter = f"scale=-2:{target_dim}"

    needs_vcodec_transcode = False
    if needs_scale:
        needs_vcodec_transcode = True
    else:
        if target_vcodec == "h264" and src_vcodec not in ("h264", "avc", "avc1"):
            needs_vcodec_transcode = True
        elif target_vcodec == "vp9" and src_vcodec not in ("vp9", "vp09"):
            needs_vcodec_transcode = True
        elif target_vcodec == "av1" and src_vcodec not in ("av1", "av01"):
            needs_vcodec_transcode = True
        elif target_container == "webm" and src_vcodec not in ("vp9", "vp8", "av1"):
            needs_vcodec_transcode = True

    needs_acodec_transcode = False
    if target_acodec == "opus" or target_container == "webm":
        needs_acodec_transcode = True

    # Cek apakah container output berbeda atau perlu transcode
    ext = os.path.splitext(final_output_path)[1].lower().lstrip('.')
    container_mismatch = (ext != 'mp4' and ext != '')

    # Jika semua parameter standar / cocok dengan sumber asli: FAST REMUX (-c copy)
    if not needs_scale and not needs_vcodec_transcode and not needs_acodec_transcode and not container_mismatch:
        return fast_remux_mp4(raw_video_path, final_output_path)

    # Bila membutuhkan transcode / downscaling / re-encode
    action_notes = []
    if needs_scale:
        action_notes.append(f"Resolusi: {target_res}p")
    if needs_vcodec_transcode:
        v_label = target_vcodec.upper() if target_vcodec != 'best' else 'H.264'
        action_notes.append(f"Video Codec: {v_label}")
    if needs_acodec_transcode:
        action_notes.append("Audio Codec: OPUS")
    if target_container and target_container != 'mp4':
        action_notes.append(f"Container: .{target_container}")

    if ui_queue:
        ui_queue.put({"type": "log", "text": f"\n[FFMPEG] Menyesuaikan parameter media ({', '.join(action_notes)})...\n"})
        ui_queue.put({"type": "progress", "value": 0.85, "text": "Status: Mengonversi Video (FFmpeg)..."})

    base_stem, out_ext = os.path.splitext(final_output_path)
    if not out_ext:
        out_ext = f".{target_container}" if target_container else ".mp4"
    temp_out = f"{base_stem}.transcode{out_ext}"

    cmd = [FFMPEG_PATH, "-y", "-i", raw_video_path]

    if scale_filter:
        cmd.extend(["-vf", scale_filter])

    if needs_vcodec_transcode:
        if target_vcodec == "vp9" or target_container == "webm":
            cmd.extend(["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0"])
        elif target_vcodec == "av1":
            cmd.extend(["-c:v", "libaom-av1", "-crf", "32", "-b:v", "0"])
        else:
            # Default H.264 fast encoding
            cmd.extend(["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p"])
    else:
        cmd.extend(["-c:v", "copy"])

    if needs_acodec_transcode:
        cmd.extend(["-c:a", "libopus", "-b:a", "128k"])
    else:
        cmd.extend(["-c:a", "copy"])

    if final_output_path.lower().endswith(".mp4") or final_output_path.lower().endswith(".mov"):
        cmd.extend(["-movflags", "+faststart"])

    cmd.append(temp_out)

    startupinfo = None
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            startupinfo=startupinfo, text=True, encoding='utf-8', errors='ignore'
        )
        stderr_chunks = []
        while True:
            if abort_checker and abort_checker():
                proc.kill()
                if os.path.exists(temp_out):
                    try: os.remove(temp_out)
                    except Exception: pass
                if ui_queue:
                    ui_queue.put({"type": "log", "text": "[FFMPEG] Konversi dibatalkan oleh pengguna.\n"})
                return False

            try:
                _, err = proc.communicate(timeout=0.5)
                if err:
                    stderr_chunks.append(err)
                break
            except subprocess.TimeoutExpired:
                continue

        if proc.returncode == 0 and os.path.exists(temp_out) and os.path.getsize(temp_out) > 0:
            if os.path.exists(final_output_path):
                try: os.remove(final_output_path)
                except Exception: pass
            os.rename(temp_out, final_output_path)
            if os.path.exists(raw_video_path):
                try: os.remove(raw_video_path)
                except Exception: pass
            if ui_queue:
                ui_queue.put({"type": "log", "text": "[FFMPEG] Berhasil mengonversi dan menyimpan video!\n"})
            return True
        else:
            stderr_out = "".join(stderr_chunks)
            if ui_queue and stderr_out:
                err_lines = [l for l in stderr_out.splitlines() if 'error' in l.lower() or 'fatal' in l.lower()]
                if err_lines:
                    ui_queue.put({"type": "log", "text": f"[FFMPEG WARNING] {err_lines[-1]}\n"})
    except Exception as e:
        if ui_queue:
            ui_queue.put({"type": "log", "text": f"[FFMPEG ERROR] Terjadi kesalahan: {e}\n"})

    if os.path.exists(temp_out):
        try: os.remove(temp_out)
        except Exception: pass

    # Fallback jika transcode gagal: gunakan fast_remux
    return fast_remux_mp4(raw_video_path, final_output_path)

def fast_remux_mp4(raw_mp4_path: str, final_mp4_path: str, timeout: int = 20) -> bool:
    """
    Fast Stream Remux MP4 menggunakan FFmpeg (-c copy -movflags +faststart)
    Memindahkan moov atom ke depan agar video langsung dapat diputar seketika
    dengan penggunaan CPU mendekati 0%.
    """
    if not os.path.exists(raw_mp4_path) or os.path.getsize(raw_mp4_path) == 0:
        return False

    if not os.path.exists(FFMPEG_PATH):
        try:
            if os.path.exists(final_mp4_path):
                os.remove(final_mp4_path)
            os.rename(raw_mp4_path, final_mp4_path)
            return True
        except Exception:
            return False

    temp_remux = final_mp4_path + ".remux.mp4"
    cmd = [
        FFMPEG_PATH, "-y",
        "-i", raw_mp4_path,
        "-c", "copy",
        "-movflags", "+faststart",
        temp_remux
    ]
    
    startupinfo = None
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE

    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            startupinfo=startupinfo, encoding='utf-8', errors='ignore'
        )
        if res.returncode == 0 and os.path.exists(temp_remux) and os.path.getsize(temp_remux) > 0:
            if os.path.exists(final_mp4_path):
                os.remove(final_mp4_path)
            os.rename(temp_remux, final_mp4_path)
            try: os.remove(raw_mp4_path)
            except Exception: pass
            return True
    except Exception:
        pass
        
    if os.path.exists(temp_remux):
        try: os.remove(temp_remux)
        except Exception: pass

    # Fallback jika remux gagal: salin file mentah langsung
    try:
        if os.path.exists(final_mp4_path):
            os.remove(final_mp4_path)
        os.rename(raw_mp4_path, final_mp4_path)
        return True
    except Exception:
        return False

def extract_audio_from_video(video_path: str, output_audio_path: str, fmt: str = "mp3") -> bool:
    """
    Ekstraksi audio dari file video menggunakan FFmpeg.
    """
    if not os.path.exists(video_path) or not os.path.exists(FFMPEG_PATH):
        return False

    cmd = [
        FFMPEG_PATH, "-y",
        "-i", video_path,
        "-vn"
    ]
    if fmt == "mp3":
        cmd.extend(["-c:a", "libmp3lame", "-q:a", "2"])
    elif fmt == "m4a":
        cmd.extend(["-c:a", "aac", "-b:a", "192k"])
    else:
        cmd.extend(["-c:a", "copy"])
    cmd.append(output_audio_path)

    startupinfo = None
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE

    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            startupinfo=startupinfo, encoding='utf-8', errors='ignore'
        )
        return res.returncode == 0 and os.path.exists(output_audio_path)
    except Exception:
        return False

def normalize_image_to_jpeg(file_path: str) -> bool:
    """
    Memastikan file gambar disimpan sebagai format JPEG valid.
    Jika file aslinya adalah WEBP atau format lain tapi diberi ekstensi .jpg,
    viewer seperti JPEGView atau Windows Photos mungkin gagal membuka file tersebut.
    Fungsi ini membaca image header via Pillow dan menulis ulang sebagai JPEG murni.
    """
    if not os.path.exists(file_path) or os.path.getsize(file_path) < 100:
        return False
    try:
        from PIL import Image
        with Image.open(file_path) as im:
            if im.format != 'JPEG' or im.mode in ('RGBA', 'P'):
                rgb_im = im.convert('RGB')
                rgb_im.save(file_path, 'JPEG', quality=95)
        return True
    except Exception:
        return False

def probe_media_stream(stream_url: str, timeout: int = 8) -> dict:
    """
    Mengambil metadata teknis (resolusi, fps, durasi, codec) dari URL stream secara cepat
    menggunakan ffprobe.
    """
    if not stream_url or not os.path.exists(FFPROBE_PATH):
        return {}
    cmd = [
        FFPROBE_PATH, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,duration,codec_name:format=duration",
        "-of", "json",
        stream_url
    ]
    startupinfo = None
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            startupinfo=startupinfo, encoding='utf-8', errors='ignore'
        )
        if res.returncode == 0 and res.stdout:
            data = json.loads(res.stdout)
            streams = data.get('streams', [])
            stream = streams[0] if streams else {}
            format_info = data.get('format', {})
            
            width = stream.get('width')
            height = stream.get('height')
            codec = stream.get('codec_name', '')
            
            # FPS parsing ("30/1" -> 30, "60000/1001" -> 60)
            fps_str = str(stream.get('r_frame_rate', ''))
            fps = 0
            if '/' in fps_str:
                parts = fps_str.split('/', 1)
                num = float(parts[0]) if parts[0] else 0
                den = float(parts[1]) if len(parts) > 1 and parts[1] else 1
                if den > 0:
                    fps = round(num / den)
            elif fps_str:
                try: fps = round(float(fps_str))
                except Exception: pass
                
            duration = 0.0
            raw_dur = stream.get('duration') or format_info.get('duration')
            if raw_dur:
                try: duration = float(raw_dur)
                except Exception: pass
            
            # Label resolusi (e.g. 4K UHD, 1080p, dsb)
            max_dim = max(width or 0, height or 0)
            min_dim = min(width or 0, height or 0)
            res_label = ""
            if max_dim >= 3840 or min_dim >= 2160:
                res_label = "4K UHD"
            elif max_dim >= 2560 or min_dim >= 1440:
                res_label = "2K QHD"
            elif max_dim >= 1920 or min_dim >= 1080:
                res_label = "1080p FHD"
            elif max_dim >= 1280 or min_dim >= 720:
                res_label = "720p HD"
            elif height:
                res_label = f"{min_dim}p"

            return {
                'width': width,
                'height': height,
                'fps': fps,
                'duration': duration,
                'codec': codec,
                'resolution_label': res_label
            }
    except Exception:
        pass
    return {}

def embed_thumbnail_to_media(
    media_path: str,
    thumb_url_or_path: str,
    ui_queue=None,
    abort_checker=None
) -> bool:
    """
    Menginjeksi gambar thumbnail cover asli (Album Art) ke dalam metadata file media (Video/Audio).
    Mendukung format video: .mp4, .mkv, .mov
    Mendukung format audio: .mp3, .m4a, .flac
    """
    if not media_path or not os.path.exists(media_path) or os.path.getsize(media_path) == 0:
        return False
    if not thumb_url_or_path or not os.path.exists(FFMPEG_PATH):
        return False

    ext = os.path.splitext(media_path)[1].lower()
    if ext not in ('.mp4', '.mkv', '.mov', '.mp3', '.m4a', '.flac'):
        return False

    temp_thumb_dl = None
    temp_cover_jpg = None
    temp_media_out = media_path + f".embed_thumb{ext}"

    try:
        # 1. Dapatkan file JPEG lokal
        if thumb_url_or_path.startswith(('http://', 'https://')):
            temp_thumb_dl = media_path + ".thumb_dl.tmp"
            temp_cover_jpg = media_path + ".thumb_cover.jpg"
            
            resp = requests.get(thumb_url_or_path, headers=DEFAULT_HEADERS, timeout=12)
            if resp.status_code != 200 or len(resp.content) < 100:
                return False
            with open(temp_thumb_dl, 'wb') as f:
                f.write(resp.content)
            
            if os.path.exists(temp_cover_jpg):
                try: os.remove(temp_cover_jpg)
                except Exception: pass
            os.rename(temp_thumb_dl, temp_cover_jpg)
            normalize_image_to_jpeg(temp_cover_jpg)
            cover_path = temp_cover_jpg
        else:
            if not os.path.exists(thumb_url_or_path):
                return False
            cover_path = thumb_url_or_path

        if not os.path.exists(cover_path) or os.path.getsize(cover_path) < 100:
            return False

        # 2. Susun perintah FFmpeg sesuai format container
        if ext in ('.mp4', '.mov'):
            cmd = [
                FFMPEG_PATH, "-y",
                "-i", media_path,
                "-i", cover_path,
                "-map", "0",
                "-map", "1",
                "-c", "copy",
                "-disposition:v:1", "attached_pic",
                "-movflags", "+faststart",
                temp_media_out
            ]
        elif ext == '.mkv':
            cmd = [
                FFMPEG_PATH, "-y",
                "-i", media_path,
                "-attach", cover_path,
                "-metadata:s:t", "mimetype=image/jpeg",
                "-c", "copy",
                temp_media_out
            ]
        elif ext == '.mp3':
            cmd = [
                FFMPEG_PATH, "-y",
                "-i", media_path,
                "-i", cover_path,
                "-map", "0:a",
                "-map", "1",
                "-c:a", "copy",
                "-c:v", "mjpeg",
                "-id3v2_version", "3",
                "-metadata:s:v", "title=Album cover",
                "-metadata:s:v", "comment=Cover (front)",
                temp_media_out
            ]
        elif ext in ('.m4a', '.flac'):
            cmd = [
                FFMPEG_PATH, "-y",
                "-i", media_path,
                "-i", cover_path,
                "-map", "0:a",
                "-map", "1",
                "-c", "copy",
                "-disposition:v:0", "attached_pic",
                temp_media_out
            ]
        else:
            return False

        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        if ui_queue:
            ui_queue.put({"type": "log", "text": "[THUMBNAIL] Menginjeksi thumbnail cover asli ke dalam file...\n"})

        res = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            startupinfo=startupinfo, encoding='utf-8', errors='ignore'
        )

        if res.returncode == 0 and os.path.exists(temp_media_out) and os.path.getsize(temp_media_out) > 0:
            if os.path.exists(media_path):
                try: os.remove(media_path)
                except Exception: pass
            os.rename(temp_media_out, media_path)
            if ui_queue:
                ui_queue.put({"type": "log", "text": "[THUMBNAIL] Injeksi thumbnail (Album Art) berhasil!\n"})
            return True

    except Exception as e:
        if ui_queue:
            ui_queue.put({"type": "log", "text": f"[THUMBNAIL WARNING] Gagal menginjeksi thumbnail: {e}\n"})
    finally:
        for p in (temp_thumb_dl, temp_cover_jpg, temp_media_out):
            if p and os.path.exists(p):
                try: os.remove(p)
                except Exception: pass

    return False


