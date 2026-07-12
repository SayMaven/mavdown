import customtkinter as ctk
from tkinter import messagebox, filedialog
import subprocess
import threading
import os
import sys
import shlex
import requests
from PIL import Image
from io import BytesIO
import re
import json
import queue

# Konfigurasi Path yang aman untuk Nuitka & Python murni
if "__compiled__" in globals() or getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

YT_DLP_PATH = os.path.join(BASE_DIR, "bin", "yt-dlp.exe")
ARIA2_PATH = os.path.join(BASE_DIR, "bin", "aria2c.exe")
FFMPEG_PATH = os.path.join(BASE_DIR, "bin", "ffmpeg.exe") 
NODE_PATH = os.path.join(BASE_DIR, "bin", "node.exe")

DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "downloads")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# Antrean pesan untuk thread safety
ui_queue = queue.Queue()

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
    info_options = ["--skip-download", "--print-json", "--js-runtimes", f"nodejs:{NODE_PATH}"]
    info_command = create_yt_dlp_command(url, options=info_options)
    startupinfo = None
    if os.name == 'nt': 
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
    try:
        ui_queue.put({"type": "info_title", "title": "Mengambil Info..."})
        ui_queue.put({"type": "info_thumb", "text": "Mengambil Thumbnail...", "image": None})
        
        result = subprocess.run(info_command, capture_output=True, text=True, check=True, startupinfo=startupinfo)
        info = json.loads(result.stdout.strip())
        title = info.get('title', 'Judul Tidak Ditemukan')
        ui_queue.put({"type": "info_title", "title": f"Judul: {title}"})
        
        thumb_url = info.get('thumbnail')
        if thumb_url and thumb_url.startswith('http'):
            image_data = requests.get(thumb_url).content
            image = Image.open(BytesIO(image_data))
            # CustomTkinter Image
            ctk_image = ctk.CTkImage(light_image=image, size=(380, 250))
            ui_queue.put({"type": "info_thumb", "text": "", "image": ctk_image})
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

def download_video_logic(url, mode, audio_format, res, vcodec, acodec, container, download_subs, embed_subs, subs_lang, embed_thumb, use_aria2, custom_path, custom_cmd):
    output_dir = custom_path if custom_path else DEFAULT_OUTPUT_DIR
    
    ui_queue.put({"type": "progress", "value": 0, "text": "Progress: 0.0%"})
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    ui_queue.put({"type": "log", "text": f"\n\n{'='*50}\n"})
    ui_queue.put({"type": "log", "text": f"URL Sumber: {url}\n"}) 
    ui_queue.put({"type": "log", "text": f"Memulai Unduhan Baru Ke: {output_dir}\n"})
    
    options = ["--retries", "infinite", "--fragment-retries", "infinite", "--js-runtimes", f"nodejs:{NODE_PATH}"]
    options.append(f"--ffmpeg-location={FFMPEG_PATH}")
    
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
                "--external-downloader-args", "-x 16 -k 1M --allow-overwrite=true"
            ])
            ui_queue.put({"type": "log", "text": "[OPT] Menggunakan Aria2c sebagai downloader.\n"})
            
        if mode == "audio_only":
            options.extend(["-f", "bestaudio", "--extract-audio", "--audio-format", audio_format])
            ui_queue.put({"type": "log", "text": f"[MODE] Audio Saja ({audio_format})\n"})
        else:
            vcodec_map = {"h264": "avc", "av1": "av01", "vp9": "vp09"}
            acodec_map = {"m4a": "mp4a", "opus": "opus"}
            
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
            ui_queue.put({"type": "log", "text": f"[MODE] Video (V: {vcodec}, A: {acodec}, R: {res}p, C: {container})\n"})
            options.extend(["-f", format_string, "--merge-output-format", container])
            
        if download_subs or embed_subs:
            lang = subs_lang if subs_lang else "all" 
            options.extend(["--write-subs", "--sub-langs", lang]) 
            if embed_subs:
                options.append("--embed-subs")
                ui_queue.put({"type": "log", "text": f"[OPT] Subtitle ({lang}) di-embed.\n"})
            if download_subs:
                sub_format = "lrc" if mode == "audio_only" else "srt"
                options.extend(["--sub-format", sub_format])
                ui_queue.put({"type": "log", "text": f"[OPT] Subtitle ({lang}) . {sub_format} terpisah.\n"})
                
        if embed_thumb:
            options.append("--embed-thumbnail")
            ui_queue.put({"type": "log", "text": "[OPT] Thumbnail di-embed.\n"})
            
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
        for line in iter(process.stdout.readline, ''):
            update_progress_bar(line)
        process.wait() 
        if process.returncode == 0:
            ui_queue.put({"type": "log", "text": "\n\n--- UNDUHAN SUKSES ---\n"})
        else:
            ui_queue.put({"type": "log", "text": f"\n\n--- UNDUHAN GAGAL --- (Kode: {process.returncode})\n"})
    except FileNotFoundError:
        ui_queue.put({"type": "log", "text": "\nERROR: yt-dlp atau aria2c tidak ditemukan."})
    except Exception as e:
        ui_queue.put({"type": "log", "text": f"\nERROR Tak Terduga: {e}"})
    finally:
        ui_queue.put({"type": "download_finish"})

def update_ytdlp_logic():
    ui_queue.put({"type": "progress", "value": 0.1, "text": "Updating yt-dlp..."})
    ui_queue.put({"type": "log", "text": "\n\nMemulai Update yt-dlp...\n"})
    
    command = [YT_DLP_PATH, "-U"]
    try:
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True, startupinfo=startupinfo)
        for line in iter(process.stdout.readline, ''):
            ui_queue.put({"type": "log", "text": line})
        process.wait()
        if process.returncode == 0:
            ui_queue.put({"type": "log", "text": "--- Update Selesai ---\n"})
        else:
            ui_queue.put({"type": "log", "text": f"--- Update Gagal ({process.returncode}) ---\n"})
    except Exception as e:
        ui_queue.put({"type": "log", "text": f"ERROR: {e}\n"})
    finally:
        ui_queue.put({"type": "update_finish"})

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Maven Downloader (By SayMaven) V1.5")
        self.geometry("1400x800")
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")
        
        try:
            icon_path = os.path.join(BASE_DIR, "assets", "waifu_icon.ico")
            self.iconbitmap(icon_path)
        except Exception:
            pass
            
        self.mode_var = ctk.StringVar(value="video_audio")
        self.custom_cmd_var = ctk.StringVar()
        self.custom_output_path_var = ctk.StringVar(value=load_config())
        self.audio_only_format_var = ctk.StringVar(value="mp3")
        self.resolution_var = ctk.StringVar(value="1080")
        self.video_codec_var = ctk.StringVar(value="h264")
        self.audio_codec_var = ctk.StringVar(value="m4a")
        self.container_var = ctk.StringVar(value="mp4")
        self.download_subs_var = ctk.BooleanVar(value=False)
        self.embed_subs_var = ctk.BooleanVar(value=False)
        self.subs_lang_var = ctk.StringVar(value="id,en")
        self.embed_thumb_var = ctk.BooleanVar(value=False)
        self.use_aria2_var = ctk.BooleanVar(value=True)

        self.setup_ui()
        self.after(100, self.process_ui_queue)

    def process_ui_queue(self):
        try:
            while True:
                msg = ui_queue.get_nowait()
                msg_type = msg.get("type")
                if msg_type == "log":
                    self.log_area.insert("end", msg["text"])
                    self.log_area.see("end")
                elif msg_type == "progress":
                    self.progress_bar.set(msg["value"])
                    self.progress_label.configure(text=msg["text"])
                elif msg_type == "info_title":
                    self.title_label.configure(text=msg["title"])
                elif msg_type == "info_thumb":
                    if msg.get("image"):
                        self.thumb_label.configure(image=msg["image"], text="")
                    else:
                        self.thumb_label.configure(text=msg.get("text", ""), image="")
                elif msg_type == "download_finish":
                    self.download_button.configure(state="normal")
                    self.url_entry.configure(state="normal")
                    self.progress_bar.set(1.0)
                    self.progress_label.configure(text="Progress: Selesai")
                elif msg_type == "update_finish":
                    self.update_button.configure(state="normal")
                    self.progress_bar.set(1.0)
                    self.progress_label.configure(text="Progress: Selesai")
        except queue.Empty:
            pass
        self.after(100, self.process_ui_queue)

    def setup_ui(self):
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Header / URL Input
        top_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        top_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(top_frame, text="1. Masukkan URL Video:", font=ctk.CTkFont(weight="bold", size=14)).pack(anchor="w")
        
        input_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        input_frame.pack(fill="x", pady=5)
        
        self.url_entry = ctk.CTkEntry(input_frame, placeholder_text="https://www.youtube.com/watch?v=...", height=40)
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        ctk.CTkButton(input_frame, text="Get Info", command=self.on_get_info, width=120, height=40, fg_color="#3B82F6", hover_color="#2563EB").pack(side="left", padx=(0, 10))
        self.download_button = ctk.CTkButton(input_frame, text="START DOWNLOAD", command=self.on_download, width=150, height=40, fg_color="#10B981", hover_color="#059669")
        self.download_button.pack(side="left")

        # Output Folder Section
        folder_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        folder_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(folder_frame, text="Folder Output:").pack(side="left")
        
        output_disp = ctk.CTkLabel(folder_frame, textvariable=self.custom_output_path_var, text_color="#3B82F6", font=ctk.CTkFont(weight="bold"))
        output_disp.pack(side="left", padx=10)
        
        ctk.CTkButton(folder_frame, text="Pilih Folder", command=self.select_folder, width=100, height=30).pack(side="left", padx=5)
        ctk.CTkButton(folder_frame, text="Buka Folder", command=self.open_folder, width=100, height=30).pack(side="left", padx=5)
        self.update_button = ctk.CTkButton(folder_frame, text="Update yt-dlp", command=self.on_update, width=100, height=30, fg_color="#F59E0B", hover_color="#D97706")
        self.update_button.pack(side="left", padx=5)

        # Progress
        prog_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        prog_frame.pack(fill="x", pady=5)
        self.progress_label = ctk.CTkLabel(prog_frame, text="Progress: Siap")
        self.progress_label.pack(side="left", padx=(0, 10))
        self.progress_bar = ctk.CTkProgressBar(prog_frame)
        self.progress_bar.pack(side="left", fill="x", expand=True)
        self.progress_bar.set(0)

        # Mid Content (Preview & Options)
        mid_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        mid_frame.pack(fill="both", expand=True)

        # Left Panel - Preview
        preview_panel = ctk.CTkFrame(mid_frame, width=400)
        preview_panel.pack(side="left", fill="y", padx=(0, 10))
        preview_panel.pack_propagate(False)
        ctk.CTkLabel(preview_panel, text="Video Info", font=ctk.CTkFont(weight="bold", size=14)).pack(pady=10)
        self.title_label = ctk.CTkLabel(preview_panel, text="Judul: (Tekan Get Info)", wraplength=380, justify="left")
        self.title_label.pack(fill="x", padx=10, pady=5)
        self.thumb_label = ctk.CTkLabel(preview_panel, text="Preview Thumbnail", width=380, height=250, fg_color=("gray80", "gray20"), corner_radius=8)
        self.thumb_label.pack(pady=10, padx=10)

        # Right Panel - Options & Logs
        right_panel = ctk.CTkFrame(mid_frame, fg_color="transparent")
        right_panel.pack(side="left", fill="both", expand=True)
        
        opts_frame = ctk.CTkFrame(right_panel)
        opts_frame.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(opts_frame, text="Opsi Download", font=ctk.CTkFont(weight="bold", size=14)).pack(anchor="w", padx=10, pady=(10, 0))

        # Mode Selection
        self.mode_frame = ctk.CTkFrame(opts_frame, fg_color="transparent")
        self.mode_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(self.mode_frame, text="Mode:").pack(side="left", padx=(0, 10))
        ctk.CTkRadioButton(self.mode_frame, text="Video + Audio", variable=self.mode_var, value="video_audio", command=self.toggle_opts).pack(side="left", padx=5)
        ctk.CTkRadioButton(self.mode_frame, text="Audio Only", variable=self.mode_var, value="audio_only", command=self.toggle_opts).pack(side="left", padx=5)
        
        # Audio Opts (Hidden by default or shown)
        self.audio_opts = ctk.CTkFrame(opts_frame, fg_color="transparent")
        ctk.CTkLabel(self.audio_opts, text="Format Audio:").pack(side="left", padx=(0, 10))
        ctk.CTkRadioButton(self.audio_opts, text="MP3", variable=self.audio_only_format_var, value="mp3").pack(side="left", padx=5)
        ctk.CTkRadioButton(self.audio_opts, text="M4A", variable=self.audio_only_format_var, value="m4a").pack(side="left", padx=5)

        # Video Opts
        self.video_opts = ctk.CTkFrame(opts_frame, fg_color="transparent")
        self.video_opts.pack(fill="x", padx=10, pady=5)
        
        # Grid layout for video opts
        v_codec = ctk.CTkFrame(self.video_opts, fg_color="transparent")
        v_codec.pack(fill="x", pady=2)
        ctk.CTkLabel(v_codec, text="Video Codec:", width=100, anchor="w").pack(side="left")
        for text, val in [("H.264", "h264"), ("VP9", "vp9"), ("AV1", "av1"), ("Best", "best")]:
            ctk.CTkRadioButton(v_codec, text=text, variable=self.video_codec_var, value=val).pack(side="left", padx=5)
            
        a_codec = ctk.CTkFrame(self.video_opts, fg_color="transparent")
        a_codec.pack(fill="x", pady=2)
        ctk.CTkLabel(a_codec, text="Audio Codec:", width=100, anchor="w").pack(side="left")
        for text, val in [("M4A", "m4a"), ("Opus", "opus"), ("Best", "best")]:
            ctk.CTkRadioButton(a_codec, text=text, variable=self.audio_codec_var, value=val).pack(side="left", padx=5)
            

        
        # Adding a scrollable frame or wrapping it since there are many resolutions now, or just two lines of frames.
        # Wait, since there are many radio buttons, they might overflow the window horizontally. Let's wrap them or keep them in one line if they fit.
        # It's better to wrap them in two rows if needed, but let's just use grid instead of pack for res_frame.
        
        res_grid = ctk.CTkFrame(self.video_opts, fg_color="transparent")
        res_grid.pack(fill="x", pady=2)
        ctk.CTkLabel(res_grid, text="Resolusi Max:", width=100, anchor="w").grid(row=0, column=0, rowspan=2, padx=5, sticky="w")
        
        resolutions = [("Best", "best"), ("4K", "2160"), ("1440p", "1440"), ("1080p", "1080"), 
                       ("720p", "720"), ("480p", "480"), ("360p", "360"), ("240p", "240"), ("144p", "144")]
        for i, (text, val) in enumerate(resolutions):
            row = i // 5
            col = (i % 5) + 1
            ctk.CTkRadioButton(res_grid, text=text, variable=self.resolution_var, value=val).grid(row=row, column=col, padx=5, pady=2, sticky="w")

        # Extras
        extras = ctk.CTkFrame(opts_frame, fg_color="transparent")
        extras.pack(fill="x", padx=10, pady=10)
        ctk.CTkCheckBox(extras, text="Download Sub", variable=self.download_subs_var).pack(side="left", padx=5)
        ctk.CTkCheckBox(extras, text="Embed Sub", variable=self.embed_subs_var).pack(side="left", padx=5)
        ctk.CTkEntry(extras, textvariable=self.subs_lang_var, width=80, placeholder_text="id,en").pack(side="left", padx=5)
        ctk.CTkCheckBox(extras, text="Embed Thumb", variable=self.embed_thumb_var).pack(side="left", padx=5)
        ctk.CTkCheckBox(extras, text="Gunakan Aria2c", variable=self.use_aria2_var).pack(side="left", padx=5)
        
        # Log Area
        ctk.CTkLabel(right_panel, text="Log Proses", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        self.log_area = ctk.CTkTextbox(right_panel, font=ctk.CTkFont(family="Consolas", size=12))
        self.log_area.pack(fill="both", expand=True, pady=(5, 0))

        # Initial toggle
        self.toggle_opts()

    def toggle_opts(self):
        if hasattr(self, 'mode_frame'):
            if self.mode_var.get() == "audio_only":
                self.video_opts.pack_forget()
                self.audio_opts.pack(fill="x", padx=10, pady=5, after=self.mode_frame)
            else:
                self.audio_opts.pack_forget()
                self.video_opts.pack(fill="x", padx=10, pady=5, after=self.mode_frame)

    def select_folder(self):
        path = filedialog.askdirectory(title="Pilih Folder Output")
        if path:
            self.custom_output_path_var.set(path)
            save_config(path)

    def open_folder(self):
        path = self.custom_output_path_var.get() or DEFAULT_OUTPUT_DIR
        if os.path.exists(path):
            if sys.platform == "win32":
                os.startfile(path)
            else:
                subprocess.Popen(["xdg-open", path])

    def on_get_info(self):
        url = self.url_entry.get().strip()
        if not url: return
        threading.Thread(target=get_video_info, args=(url,), daemon=True).start()

    def on_download(self):
        url = self.url_entry.get().strip()
        if not url: return
        self.download_button.configure(state="disabled")
        self.url_entry.configure(state="disabled")
        
        threading.Thread(target=download_video_logic, args=(
            url, self.mode_var.get(), self.audio_only_format_var.get(),
            self.resolution_var.get(), self.video_codec_var.get(), self.audio_codec_var.get(),
            self.container_var.get(), self.download_subs_var.get(), self.embed_subs_var.get(),
            self.subs_lang_var.get().strip(), self.embed_thumb_var.get(), self.use_aria2_var.get(),
            self.custom_output_path_var.get(), self.custom_cmd_var.get().strip()
        ), daemon=True).start()

    def on_update(self):
        self.update_button.configure(state="disabled")
        threading.Thread(target=update_ytdlp_logic, daemon=True).start()

if __name__ == "__main__":
    app = App()
    app.mainloop()