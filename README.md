# Maven Downloader

Maven Downloader adalah aplikasi GUI berbasis Python untuk mengunduh video dan audio dari berbagai platform dengan mudah. Aplikasi ini memanfaatkan `yt-dlp` sebagai *engine* utama, `aria2c` untuk mempercepat proses unduhan (*multi-connection*), dan `ffmpeg` untuk konversi media.

## Fitur Utama

- **Antarmuka Grafis (GUI)**: Desain antarmuka pengguna berbasis `tkinter` yang mudah digunakan.
- **Unduh Video & Audio**: Mendukung format video (mp4, mkv, webm) hingga resolusi tinggi (4K/1080p) dan ekstraksi audio murni (mp3, m4a, dll.).
- **Akselerasi Download**: Terintegrasi dengan `aria2c` untuk kecepatan unduh yang maksimal.
- **Dukungan Subtitle & Thumbnail**: Opsi untuk mengunduh dan menyematkan (*embed*) subtitle serta thumbnail langsung ke dalam file video.

## Struktur Direktori

```text
mavdown/
├── assets/           # Berisi gambar dan icon UI (waifu_icon.png, waifu_icon.ico)
├── bin/              # Harus berisi dependencies pihak ketiga (yt-dlp.exe, aria2c.exe, ffmpeg.exe, ffprobe.exe)
├── mavdown.py        # Kode sumber utama aplikasi
├── mavdown.spec      # Konfigurasi PyInstaller untuk mem-build aplikasi menjadi .exe
└── requirements.txt  # Daftar library Python yang dibutuhkan
```

> **Catatan:** File eksekutabel (`.exe`) pihak ketiga di dalam folder `bin/` tidak disertakan di repositori ini untuk menghemat ruang. Anda harus mengunduh dan memasukkannya secara manual ke folder `bin/` jika ingin menjalankan aplikasi dari kode sumber.

## Persyaratan (Requirements)

Jika Anda ingin menjalankan aplikasi langsung dari kode sumber (`mavdown.py`):

1. Pastikan Anda telah menginstal Python 3.x.
2. Instal pustaka yang dibutuhkan menggunakan perintah:
   ```bash
   pip install -r requirements.txt
   ```
3. Unduh *tools* berikut dan letakkan di dalam folder `bin/`:
   - [yt-dlp](https://github.com/yt-dlp/yt-dlp)
   - [aria2](https://github.com/aria2/aria2)
   - [FFmpeg](https://ffmpeg.org/download.html) (pastikan `ffmpeg.exe` dan `ffprobe.exe` ada)

## Membangun (Build) ke EXE

Untuk mem-*build* aplikasi ini menjadi satu file mandiri (`.exe`) yang siap didistribusikan:

1. Instal PyInstaller:
   ```bash
   pip install pyinstaller
   ```
2. Jalankan perintah build:
   ```bash
   pyinstaller mavdown.spec
   ```
3. Hasil aplikasi (`MavenDownloader.exe`) akan tersedia di dalam folder `dist/`.

## Lisensi

Proyek ini dilisensikan di bawah [MIT License](LICENSE). Anda bebas untuk memodifikasi dan mendistribusikan ulang kode ini sesuai dengan ketentuan yang berlaku.
