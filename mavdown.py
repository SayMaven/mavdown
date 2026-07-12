import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog 
import subprocess
import threading
import os
import sys
import shlex 
import requests 
from PIL import Image, ImageTk 
from io import BytesIO 
import re 
import json 

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    _meipass = sys._MEIPASS 
    YT_DLP_PATH = os.path.join(_meipass, "bin", "yt-dlp.exe")
    ARIA2_PATH = os.path.join(_meipass, "bin", "aria2c.exe")
    FFMPEG_PATH = os.path.join(_meipass, "bin", "ffmpeg.exe") 
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    YT_DLP_PATH = os.path.join(BASE_DIR, "bin", "yt-dlp.exe")
    ARIA2_PATH = os.path.join(BASE_DIR, "bin", "aria2c.exe")
    FFMPEG_PATH = os.path.join(BASE_DIR, "bin", "ffmpeg.exe") 
    
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
                return DEFAULT_OUTPUT_DIR
        except Exception as e:
            print(f"ERROR loading config: {e}")
            return DEFAULT_OUTPUT_DIR
    return DEFAULT_OUTPUT_DIR

def create_yt_dlp_command(url, options=[]):
    command = [YT_DLP_PATH]
    command.extend(options)
    command.append(url)
    return command

def select_output_directory(output_path_var):
    chosen_path = filedialog.askdirectory(title="Pilih Folder Output")
    if chosen_path:
        output_path_var.set(chosen_path)
        save_config(chosen_path) 

def open_output_directory(output_path_var, default_path):
    current_path = output_path_var.get()
    if not current_path:
        current_path = default_path 
    if os.path.exists(current_path):
        try:
            if sys.platform == "win32":
                os.startfile(current_path)
            elif sys.platform == "darwin": 
                subprocess.Popen(["open", current_path])
            else: 
                subprocess.Popen(["xdg-open", current_path])
        except Exception as e:
            messagebox.showerror("Error", f"Gagal membuka folder: {e}")
    else:
        messagebox.showerror("Error", f"Folder tidak ditemukan: {current_path}")

def update_progress_bar(log_area, progress_var, progress_label, line):
    match = re.search(r'(\d+\.\d+)%', line)
    if match:
        percent = float(match.group(1))
        progress_var.set(percent)
        progress_label.config(text=f"Progress: {percent:.1f}%")
    log_area.insert(tk.END, line)
    log_area.see(tk.END) 
    log_area.update_idletasks() 

def get_video_info(url, thumb_label, title_label):
    info_options = ["--skip-download", "--print-json"]
    info_command = create_yt_dlp_command(url, options=info_options)
    startupinfo = None
    if os.name == 'nt': 
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
    try:
        title_label.config(text="Mengambil Info...")
        thumb_label.config(text="Mengambil Thumbnail...", image='')
        thumb_label.image = None
        result = subprocess.run(info_command, capture_output=True, text=True, check=True, startupinfo=startupinfo)
        info = json.loads(result.stdout.strip())
        title = info.get('title', 'Judul Tidak Ditemukan')
        title_label.config(text=f"Judul: {title}")
        thumb_url = info.get('thumbnail')
        if thumb_url and thumb_url.startswith('http'):
            image_data = requests.get(thumb_url).content
            image = Image.open(BytesIO(image_data))
            max_size = (380, 300) 
            image.thumbnail(max_size)
            photo = ImageTk.PhotoImage(image)
            thumb_label.config(image=photo, text="")
            thumb_label.image = photo 
        else:
            thumb_label.config(text="Thumbnail tidak ditemukan.")
            thumb_label.image = None
    except subprocess.CalledProcessError as e:
        title_label.config(text=f"Gagal mendapatkan info video (url error). Cek log.")
        print(f"yt-dlp error: {e.stderr}")
        thumb_label.config(text="Gagal mendapatkan info thumbnail.")
    except FileNotFoundError:
        title_label.config(text="ERROR: yt-dlp.exe tidak ditemukan di paket PyInstaller.")
        thumb_label.config(text="Pastikan Anda menggunakan --add-data 'yt-dlp.exe;.' saat kompilasi.")
    except Exception as e:
        title_label.config(text=f"Error Info: {type(e).__name__}: {e}")

def download_video_logic(url, url_entry_ref, mode_var, audio_only_format_var, resolution_var, video_codec_var, audio_codec_var, container_var, download_subs_var, embed_subs_var, subs_lang_var, embed_thumb_var, use_aria2_var, custom_output_path_var, custom_cmd_var, log_area, download_button, progress_var, progress_label):
    custom_path = custom_output_path_var.get().strip()
    if custom_path:
        output_dir = custom_path
    else:
        output_dir = DEFAULT_OUTPUT_DIR
    download_button.config(state=tk.DISABLED)
    progress_var.set(0) 
    progress_label.config(text="Progress: 0.0%")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    log_area.insert(tk.END, f"\n\n======================================================\n")
    log_area.insert(tk.END, f"URL Sumber: {url}\n") 
    log_area.insert(tk.END, f"Memulai Unduhan Baru Ke: {output_dir}\n")
    options = ["--retries", "infinite", "--fragment-retries", "infinite"]
    options.append(f"--ffmpeg-location={FFMPEG_PATH}")
    custom_command = custom_cmd_var.get().strip()
    if custom_command:
        try:
            custom_args = shlex.split(custom_command)
            options.extend(custom_args)
            log_area.insert(tk.END, f"[MODE] Menggunakan Perintah Custom: {custom_command}\n")
        except:
            log_area.insert(tk.END, "[ERROR] Gagal parsing custom command.\n")
            download_button.config(state=tk.NORMAL)
            url_entry_ref.config(state=tk.NORMAL)
            return
    else:
        mode = mode_var.get()
        subs_lang_raw = subs_lang_var.get().strip()
        if use_aria2_var.get():
            options.extend([
                "--external-downloader", ARIA2_PATH, 
                "--external-downloader-args", "-x 16 -k 1M --allow-overwrite=true"
            ])
            log_area.insert(tk.END, "[OPT] Menggunakan Aria2c sebagai external downloader.\n")
        if mode == "audio_only":
            audio_format = audio_only_format_var.get()
            options.extend(["-f", "bestaudio", "--extract-audio", "--audio-format", audio_format])
            log_area.insert(tk.END, f"[MODE] Mode: Audio Saja ({audio_format})\n")
        else:
            res = resolution_var.get()
            vcodec = video_codec_var.get()
            acodec = audio_codec_var.get()
            container = container_var.get()
            vcodec_map = {"h264": "avc", "av1": "av01", "vp9": "vp09", "h265": "hevc"}
            acodec_map = {"m4a": "m4a", "opus": "opus"}
            f_video_parts = ["bestvideo"]
            if res != "best":
                f_video_parts.append(f"[height<={res}]")
            if vcodec != "best":
                f_video_parts.append(f"[vcodec~={vcodec_map[vcodec]}]")
            f_audio_parts = ["bestaudio"]
            if acodec != "best":
                f_audio_parts.append(f"[acodec~={acodec_map[acodec]}]")
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
            log_area.insert(tk.END, f"[MODE] Video (V: {vcodec}, A: {acodec}, R: {res}p, C: {container})\n")
            log_area.insert(tk.END, f"[DEBUG] Format string: {format_string}\n")
            options.extend(["-f", format_string, "--merge-output-format", container])
        if download_subs_var.get() or embed_subs_var.get():
            subs_lang = subs_lang_raw if subs_lang_raw else "all" 
            options.extend(["--write-subs", "--sub-langs", subs_lang]) 
            if embed_subs_var.get():
                options.append("--embed-subs")
                log_area.insert(tk.END, f"[OPT] Subtitle ({subs_lang}) di-embed.\n")
            if download_subs_var.get():
                sub_format = "lrc" if mode == "audio_only" else "srt"
                options.extend(["--sub-format", sub_format])
                log_area.insert(tk.END, f"[OPT] Subtitle ({subs_lang}) diunduh terpisah (. {sub_format}).\n")
        if embed_thumb_var.get():
            options.append("--embed-thumbnail")
            log_area.insert(tk.END, "[OPT] Thumbnail akan di-embed.\n")
        options.extend(["-o", os.path.join(output_dir, "%(title)s.%(ext)s")])
    command = create_yt_dlp_command(url, options)
    log_area.insert(tk.END, f"\nPerintah Final: {' '.join(command)}\n")
    try:
        startupinfo = None
        if os.name == 'nt': 
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True, startupinfo=startupinfo)
        for line in iter(process.stdout.readline, ''):
            update_progress_bar(log_area, progress_var, progress_label, line)
        process.wait() 
        if process.returncode == 0:
            log_area.insert(tk.END, "\n\n--- UNDUHAN SUKSES ---\n")
        else:
            log_area.insert(tk.END, f"\n\n--- UNDUHAN GAGAL --- (Kode Keluar: {process.returncode})\n")
    except FileNotFoundError:
        log_area.insert(tk.END, f"\nERROR: '{YT_DLP_PATH}' atau Aria2c tidak ditemukan. Pastikan sudah disertakan dengan benar menggunakan '--add-data'.")
    except Exception as e:
        log_area.insert(tk.END, f"\nERROR Tak Terduga: {type(e).__name__}: {e}")
    finally:
        download_button.config(state=tk.NORMAL)
        url_entry_ref.config(state=tk.NORMAL) 
        if progress_var.get() < 100:
            progress_var.set(100)
            progress_label.config(text="Progress: Selesai")

def start_download_thread(url_entry, mode_var, audio_only_format_var, resolution_var, video_codec_var, audio_codec_var, container_var, download_subs_var, embed_subs_var, subs_lang_var, embed_thumb_var, use_aria2_var, custom_output_path_var, custom_cmd_var, log_area, download_button, progress_var, progress_label):
    url = url_entry.get().strip()
    if not url:
        messagebox.showwarning("Input Kosong", "Masukkan URL video!")
        return
    url_entry.config(state=tk.DISABLED)
    download_thread = threading.Thread(
        target=download_video_logic, 
        args=(url, url_entry, mode_var, audio_only_format_var, resolution_var, video_codec_var, audio_codec_var, container_var, download_subs_var, embed_subs_var, subs_lang_var, embed_thumb_var, use_aria2_var, custom_output_path_var, custom_cmd_var, log_area, download_button, progress_var, progress_label),
        daemon=True
    )
    download_thread.start()

def get_info_thread(url_entry, thumb_label, title_label, root):
    url = url_entry.get().strip()
    if not url:
        title_label.config(text='Masukkan URL untuk melihat info.')
        thumb_label.config(image='', text='Preview Thumbnail')
        thumb_label.image = None
        return
    title_label.config(text='Mengambil Info...')
    thumb_label.config(text='Mengambil Thumbnail...', image='')
    thumb_label.image = None
    thread = threading.Thread(target=get_video_info, args=(url, thumb_label, title_label), daemon=True)
    thread.start()

def toggle_options(mode_var, audio_only_frame, video_options_frame):
    mode = mode_var.get()
    if mode == "audio_only":
        audio_only_frame.pack(fill=tk.X, pady=5)
        video_options_frame.pack_forget()
    else:
        audio_only_frame.pack_forget()
        video_options_frame.pack(fill=tk.X, pady=5)
        
def update_ytdlp_logic(log_area, progress_var, progress_label, update_button):
    update_button.config(state=tk.DISABLED)
    progress_var.set(10)
    progress_label.config(text="Progress: Updating yt-dlp...")
    log_area.insert(tk.END, "\n\n======================================================\n")
    log_area.insert(tk.END, "Memulai Update yt-dlp...\n")
    log_area.see(tk.END)
    command = [YT_DLP_PATH, "-U"]
    try:
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True, startupinfo=startupinfo)
        for line in iter(process.stdout.readline, ''):
            log_area.insert(tk.END, line)
            log_area.see(tk.END)
            log_area.update_idletasks()
        process.wait()
        if process.returncode == 0:
            log_area.insert(tk.END, "--- Update Selesai ---\n")
        else:
            log_area.insert(tk.END, f"--- Update Gagal (Kode Keluar: {process.returncode}) ---\n")
    except Exception as e:
        log_area.insert(tk.END, f"ERROR: {e}\n")
    finally:
        progress_var.set(100)
        progress_label.config(text="Progress: Selesai")
        update_button.config(state=tk.NORMAL)

def start_update_thread(log_area, progress_var, progress_label, update_button):
    threading.Thread(target=update_ytdlp_logic, args=(log_area, progress_var, progress_label, update_button), daemon=True).start()

if __name__ == "__main__":
    root = tk.Tk()
    root.title("Maven Downloader (By SayMaven) V1.4") 
    root.geometry("1440x750") 
    try:
        ICON_NAME_ICO = 'waifu_icon.ico' 
        ICON_NAME_PNG = 'waifu_icon.png' 
        if getattr(sys, 'frozen', False):
             icon_path = os.path.join(sys._MEIPASS, "assets", ICON_NAME_ICO)
        else:
             icon_path = os.path.join(BASE_DIR, "assets", ICON_NAME_ICO)
        root.iconbitmap(icon_path) 
    except Exception:
        try:
            if getattr(sys, 'frozen', False):
                 png_path = os.path.join(sys._MEIPASS, "assets", ICON_NAME_PNG)
            else:
                 png_path = os.path.join(BASE_DIR, "assets", ICON_NAME_PNG)
            image = Image.open(png_path) 
            photo = ImageTk.PhotoImage(image)
            root.iconphoto(True, photo) 
        except:
             pass 
    TITLE_FONT = ("TkDefaultFont", 12, "bold") 
    initial_output_path = load_config() 
    mode_var = tk.StringVar(value="video_audio")
    custom_cmd_var = tk.StringVar()
    custom_output_path_var = tk.StringVar(value=initial_output_path) 
    audio_only_format_var = tk.StringVar(value="mp3")
    resolution_var = tk.StringVar(value="1080")
    video_codec_var = tk.StringVar(value="h264")
    audio_codec_var = tk.StringVar(value="m4a")
    container_var = tk.StringVar(value="mp4")
    download_subs_var = tk.BooleanVar(value=False)
    embed_subs_var = tk.BooleanVar(value=False)
    subs_lang_var = tk.StringVar(value="id,en")
    embed_thumb_var = tk.BooleanVar(value=False)
    use_aria2_var = tk.BooleanVar(value=True)
    progress_var = tk.DoubleVar()
    main_frame = ttk.Frame(root, padding="10")
    main_frame.pack(fill=tk.BOTH, expand=True)
    top_frame = ttk.Frame(main_frame)
    top_frame.pack(fill=tk.X)
    url_label = ttk.Label(top_frame, text="1. Masukkan URL Video:")
    url_label.pack(fill=tk.X)
    url_entry = ttk.Entry(top_frame, width=100)
    url_entry.pack(fill=tk.X, ipady=5, pady=(0, 5))
    info_download_frame = ttk.Frame(top_frame)
    info_download_frame.pack(fill=tk.X, pady=(0, 10))
    get_info_button = ttk.Button(
        info_download_frame, 
        text="Get Info (Judul & Preview)",
        command=lambda: get_info_thread(url_entry, thumb_label, title_label, root)
    )
    get_info_button.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, padx=(0, 5)) 
    download_button = ttk.Button(
        info_download_frame, 
        text="START DOWNLOAD", 
        command=lambda: start_download_thread(
            url_entry, 
            mode_var, audio_only_format_var,
            resolution_var, video_codec_var, audio_codec_var, container_var,
            download_subs_var, embed_subs_var, subs_lang_var, embed_thumb_var, 
            use_aria2_var, 
            custom_output_path_var, 
            custom_cmd_var, log_area, download_button, progress_var, progress_label
        )
    )
    download_button.pack(side=tk.RIGHT, fill=tk.X, expand=True, ipady=5, padx=(5, 0)) 
    output_path_frame = ttk.Frame(top_frame)
    output_path_frame.pack(fill=tk.X, pady=(5, 10))
    output_label = ttk.Label(output_path_frame, text="Folder Output:")
    output_label.pack(side=tk.LEFT, padx=(0, 5))
    output_display_label = ttk.Label(output_path_frame, 
                                     textvariable=custom_output_path_var, 
                                     relief=tk.SUNKEN, 
                                     anchor="w", 
                                     foreground='blue')
    output_display_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
    select_button = ttk.Button(
        output_path_frame, 
        text="Pilih Folder Output",
        command=lambda: select_output_directory(custom_output_path_var)
    )
    select_button.pack(side=tk.LEFT, padx=5)
    open_button = ttk.Button(
        output_path_frame, 
        text="Buka Folder Hasil",
        command=lambda: open_output_directory(custom_output_path_var, DEFAULT_OUTPUT_DIR)
    )
    open_button.pack(side=tk.LEFT)
    
    update_button = ttk.Button(output_path_frame, text="Update yt-dlp")
    update_button.pack(side=tk.LEFT, padx=(5, 0))
    
    progress_frame = ttk.Frame(top_frame)
    progress_frame.pack(fill=tk.X, pady=(0, 10))
    progress_label = ttk.Label(progress_frame, text="Progress: Siap", anchor="w")
    progress_label.pack(side=tk.LEFT, padx=5, pady=5)
    progress_bar = ttk.Progressbar(progress_frame, variable=progress_var, maximum=100)
    progress_bar.pack(fill=tk.X, expand=True, padx=5)
    mid_content_frame = ttk.Frame(main_frame)
    mid_content_frame.pack(fill=tk.BOTH, expand=True, pady=10)
    preview_panel = ttk.Frame(mid_content_frame, width=400) 
    preview_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
    preview_panel.pack_propagate(False) 
    thumb_frame = ttk.LabelFrame(preview_panel, text="1. Info Video", padding="10")
    thumb_frame.pack(fill=tk.BOTH, expand=True, pady=0) 
    title_label = tk.Label(thumb_frame, text="Judul: (Tekan Get Info)", anchor="w", font=TITLE_FONT, justify=tk.LEFT, wraplength=370)
    title_label.pack(fill=tk.X, pady=(0, 5))
    thumb_label = ttk.Label(thumb_frame, text="Preview Thumbnail", anchor="center")
    thumb_label.pack(fill=tk.BOTH, expand=True)
    options_panel = ttk.Frame(mid_content_frame)
    options_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)
    options_frame = ttk.LabelFrame(options_panel, text="2. Pilihan Download & Kualitas", padding="10")
    options_frame.pack(fill=tk.X, pady=5)
    mode_frame = ttk.Frame(options_frame)
    mode_frame.pack(fill=tk.X)
    mode_label = ttk.Label(mode_frame, text="Mode Download:")
    mode_label.pack(side=tk.LEFT, padx=5, pady=5)
    rb_video = ttk.Radiobutton(mode_frame, text="Video + Audio", variable=mode_var, value="video_audio")
    rb_video.pack(side=tk.LEFT, padx=5, pady=5)
    rb_audio = ttk.Radiobutton(mode_frame, text="Audio Only", variable=mode_var, value="audio_only")
    rb_audio.pack(side=tk.LEFT, padx=5, pady=5)
    audio_only_frame = ttk.Frame(options_frame)
    audio_format_label = ttk.Label(audio_only_frame, text="Format Audio:")
    audio_format_label.pack(side=tk.LEFT, padx=5, pady=5)
    ttk.Radiobutton(audio_only_frame, text="MP3 (Kompatibilitas)", variable=audio_only_format_var, value="mp3").pack(side=tk.LEFT, padx=5, pady=5)
    ttk.Radiobutton(audio_only_frame, text="M4A (Kualitas Asli)", variable=audio_only_format_var, value="m4a").pack(side=tk.LEFT, padx=5, pady=5)
    video_options_frame = ttk.Frame(options_frame)
    vid_codec_label = ttk.Label(video_options_frame, text="Video Codec:")
    vid_codec_label.grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
    vcodecs = [("H.264", "h264"), ("VP9", "vp9"), ("AV1", "av1"), ("H.265", "h265"), ("Best", "best")]
    for i, (text, val) in enumerate(vcodecs):
        ttk.Radiobutton(video_options_frame, text=text, variable=video_codec_var, value=val).grid(row=0, column=i+1, padx=2, sticky=tk.W)
    aud_codec_label = ttk.Label(video_options_frame, text="Audio Codec:")
    aud_codec_label.grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
    acodecs = [("M4A", "m4a"), ("Opus", "opus"), ("Best", "best")]
    for i, (text, val) in enumerate(acodecs):
        ttk.Radiobutton(video_options_frame, text=text, variable=audio_codec_var, value=val).grid(row=1, column=i+1, padx=2, sticky=tk.W)
    container_label = ttk.Label(video_options_frame, text="Container:")
    container_label.grid(row=2, column=0, padx=5, pady=5, sticky=tk.W)
    containers = [("MP4", "mp4"), ("MKV", "mkv")]
    for i, (text, val) in enumerate(containers):
        ttk.Radiobutton(video_options_frame, text=text, variable=container_var, value=val).grid(row=2, column=i+1, padx=2, sticky=tk.W)
    res_label = ttk.Label(video_options_frame, text="Max. Resolusi:")
    res_label.grid(row=3, column=0, padx=5, pady=5, sticky=tk.W)
    res_options = ["360", "480", "720", "1080", "1440", "2160", "best"]
    for i, res in enumerate(res_options):
         ttk.Radiobutton(video_options_frame, text=f"{res}p" if res != "best" else "Best", 
                         variable=resolution_var, value=res).grid(row=3, column=i + 1, padx=2, sticky=tk.W)
    rb_video.config(command=lambda: toggle_options(mode_var, audio_only_frame, video_options_frame))
    rb_audio.config(command=lambda: toggle_options(mode_var, audio_only_frame, video_options_frame))
    extras_frame = ttk.LabelFrame(options_panel, text="3. Opsi Downloader, Metadata & Subtitle", padding="10")
    extras_frame.pack(fill=tk.X, pady=5)
    aria2_check = ttk.Checkbutton(extras_frame, text="Gunakan Aria2c (Multi-thread Download)", variable=use_aria2_var)
    aria2_check.grid(row=0, column=0, columnspan=2, padx=5, pady=5, sticky=tk.W)
    thumb_check = ttk.Checkbutton(extras_frame, text="Gabungkan Thumbnail ke File", variable=embed_thumb_var)
    thumb_check.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky=tk.W)
    subs_check = ttk.Checkbutton(extras_frame, text="Download Subtitle (SRT/LRC Terpisah)", variable=download_subs_var)
    subs_check.grid(row=2, column=0, columnspan=2, padx=5, pady=5, sticky=tk.W)
    embed_subs_check = ttk.Checkbutton(extras_frame, text="Gabungkan Subtitle ke File", variable=embed_subs_var)
    embed_subs_check.grid(row=3, column=0, columnspan=2, padx=5, pady=5, sticky=tk.W)
    subs_lang_label = ttk.Label(extras_frame, text="Bahasa (misal: id,en,ja,all):")
    subs_lang_label.grid(row=4, column=0, padx=5, pady=5, sticky=tk.W)
    subs_lang_entry = ttk.Entry(extras_frame, textvariable=subs_lang_var, width=15)
    subs_lang_entry.grid(row=4, column=1, padx=5, pady=5, sticky=tk.W)
    custom_frame = ttk.LabelFrame(options_panel, text="4. Custom Command", padding="10")
    custom_frame.pack(fill=tk.X, pady=5)
    custom_cmd_entry = ttk.Entry(custom_frame, textvariable=custom_cmd_var, width=100)
    custom_cmd_entry.pack(fill=tk.X, ipady=5)
    custom_cmd_label_hint = ttk.Label(custom_frame, text="Contoh: --skip-download --write-thumbnail. Untuk download thumbnail saja.", foreground='blue')
    custom_cmd_label_hint.pack(fill=tk.X, pady=(5, 0))
    log_panel = ttk.LabelFrame(mid_content_frame, text="5. Status/Log Unduhan (Real-time)", padding="10")
    log_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
    log_area = scrolledtext.ScrolledText(log_panel, height=35, wrap=tk.WORD, state=tk.NORMAL)
    log_area.pack(fill=tk.BOTH, expand=True) 

    update_button.config(command=lambda: start_update_thread(log_area, progress_var, progress_label, update_button))

    toggle_options(mode_var, audio_only_frame, video_options_frame)
    root.mainloop()