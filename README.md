# Maven Downloader (V1.7)

![Maven Downloader Screenshot](https://res.cloudinary.com/ds4a54vuy/image/upload/v1785133143/Screenshot_mavdown_1_7.png)

Maven Downloader adalah aplikasi GUI berbasis Python untuk mengunduh video dan audio dari berbagai platform dengan mudah. Aplikasi ini memanfaatkan `yt-dlp` sebagai *engine* utama, `aria2c` untuk mempercepat proses unduhan (*multi-connection*), dan `ffmpeg` untuk konversi media.

Versi terbaru (V1.6) hadir dengan antarmuka modern yang ditenagai oleh `customtkinter`, perlindungan sistem dari *freeze* (komunikasi UI berbasis antrean/*thread-safe*), dan migrasi penuh ke Nuitka & Inno Setup.

## Fitur Utama

- **Modern GUI**: Desain antarmuka minimalis dan responsif yang mendukung mode gelap/terang (Dark/Light mode) secara otomatis.
- **Anti 403 Forbidden**: Terintegrasi dengan mesin JavaScript internal (`node.exe`) di folder bin untuk memecahkan *signature* dekripsi YouTube dan mencegah pemblokiran.
- **Resolusi & Codec Lengkap**: Pilihan resolusi mulai dari 144p hingga 4K, dengan filter codec cerdas (H.264, VP9, AV1, MP3, M4A, Opus).
- **Akselerasi Download**: Terintegrasi opsional dengan `aria2c` (16 koneksi paralel) untuk menembus batas kecepatan unduhan.
- **Subtitle & Thumbnail**: Menyediakan fitur injeksi (*embed*) thumbnail dan subtitle langsung ke *metadata* video, maupun unduh terpisah.

## Struktur Direktori

```text
mavdown/
├── assets/           # Berisi icon UI (waifu_icon.ico)
├── bin/              # Dependencies pihak ketiga (yt-dlp.exe, aria2c.exe, ffmpeg.exe, node.exe)
├── dist/             # (Otomatis dibuat) Hasil kompilasi Nuitka beserta bundel bin/
├── config.py         # Pengaturan direktori & konfigurasi aplikasi
├── downloader.py     # Engine logika unduhan, yt-dlp, konversi lirik (.lrc), & update
├── gui.py            # Antarmuka modern (Dark Slate UI, CustomTkinter)
├── mavdown.py        # Entry point utama aplikasi
├── build_nuitka.bat  # Skrip otomatisasi kompilasi Nuitka & penyalinan bin/
├── setup.iss         # Skrip pembuatan installer resmi (.exe) via Inno Setup
└── requirements.txt  # Daftar pustaka Python yang dibutuhkan
```

## Cara Menjalankan Kode Sumber

1. Pastikan Anda telah menginstal Python 3.10+.
2. Instal pustaka pendukung (seperti `customtkinter` dan `Pillow`):
   ```bash
   pip install -r requirements.txt
   ```
3. Unduh *tools* berikut dan letakkan di dalam folder `bin/` (jika Anda menjalankan ini dari repo kosong):
   - `yt-dlp.exe`
   - `aria2c.exe`
   - `ffmpeg.exe`
   - `node.exe` (Standalone Windows)

4. Jalankan aplikasi:
   ```bash
   python mavdown.py
   ```

## Lisensi

Proyek ini dilisensikan di bawah [MIT License](LICENSE). 
