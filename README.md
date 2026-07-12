# Maven Downloader (V1.5)

Maven Downloader adalah aplikasi GUI berbasis Python untuk mengunduh video dan audio dari berbagai platform dengan mudah. Aplikasi ini memanfaatkan `yt-dlp` sebagai *engine* utama, `aria2c` untuk mempercepat proses unduhan (*multi-connection*), dan `ffmpeg` untuk konversi media.

Versi terbaru (V1.5) hadir dengan antarmuka modern yang ditenagai oleh `customtkinter`, perlindungan sistem dari *freeze* (komunikasi UI berbasis antrean/*thread-safe*), dan migrasi penuh ke Nuitka & Inno Setup.

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
├── dist/             # (Otomatis dibuat) Hasil kompilasi tingkat hardware dari Nuitka
├── mavdown.py        # Kode sumber utama aplikasi
├── build_nuitka.bat  # Skrip build mandiri
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

## Membangun Aplikasi (Build ke EXE Installer)

Aplikasi ini menggunakan **Nuitka** (bukan PyInstaller) untuk menghasilkan performa maksimal dan sulit di-*decompile*, serta **Inno Setup** untuk membuat program instalasinya.

1. Jalankan klik dua kali pada skrip `build_nuitka.bat`. (Pastikan modul `nuitka` sudah terinstall via pip).
2. Nuitka akan membungkus aplikasi beserta aset `bin/` ke dalam folder `dist/`. Tunggu hingga selesai.
3. Unduh dan pasang [Inno Setup](https://jrsoftware.org/isinfo.php).
4. Buka file `setup.iss` melalui Inno Setup, lalu klik menu **Build > Compile**.
5. Hasil akhirnya adalah `MavenDownloader_Setup_v1.5.exe` di dalam folder `Output/`, yang siap Anda distribusikan ke pengguna lain!

## Lisensi

Proyek ini dilisensikan di bawah [MIT License](LICENSE). Bebas digunakan, dimodifikasi, dan disebarluaskan.
