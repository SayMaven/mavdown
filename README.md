# Maven Downloader (Mavdown) v1.2.0

![Maven Downloader Screenshot](https://res.cloudinary.com/ds4a54vuy/image/upload/v1785133143/Screenshot_mavdown_1_7.png)

**Maven Downloader (Mavdown)** adalah aplikasi desktop modern berbasis Python & CustomTkinter yang dirancang untuk mengunduh media (video, album slide foto, dan audio) dari berbagai platform global dengan kecepatan maksimal dan arsitektur *Multi-Tier Engine*.

Aplikasi ini menggabungkan **Tier 1 Fast REST Scraping Engine** (ekstraksi instan < 1 detik tanpa watermark untuk Douyin, TikTok, Instagram, Twitter/X, Pinterest, Facebook, dan Bilibili) dengan **Tier 2 Fallback Engine** (`yt-dlp` + `aria2c` multi-connection 16x speed + `ffmpeg` + `node.js` anti-bot solver).

---

## 🚀 Fitur Unggulan

### 1. Multi-Tier Engine Architecture
- **Tier 1 (Fast REST Engines)**: Mengunduh langsung melalui endpoint API & mirror scraper tanpa membebani CPU. Mendukung video HD murni tanpa watermark dan album slide multi-foto.
- **Tier 2 (Enterprise Fallback)**: Didukung oleh `yt-dlp` terbaru yang terintegrasi dengan JavaScript runtime (`node.exe`) untuk menembus proteksi enkripsi YouTube terbaru (Anti 403 Forbidden).
- **Akselerasi Unduhan**: Dukungan opsi `aria2c` dengan 16 thread paralel untuk memaksimalkan bandwidth internet Anda.

### 2. Platform Media yang Didukung Lengkap
- **Douyin**: 
  - Mendukung video resolusi hingga 4K/1080p FHD dan Album Slide Foto HD.
  - Ekstraksi musik BGM otomatis.
  - **Auto-Isolate Share URL**: Otomatis membersihkan teks awalan dan akhiran bahasa Mandarin/token saat menekan tombol **Tempel** maupun menggunakan shortcut **`Ctrl+V`**.
  - Deep Probe resolusi, FPS, durasi, dan codec via ffprobe.
- **TikTok**:
  - Unduh Video HD tanpa watermark dan Slide Foto HD asli + Musik BGM (`.mp3`).
- **Instagram**:
  - Mendukung Reels, Video post, dan **Carousel Slide Album** (ekstraksi seluruh foto potret/HD ke dalam folder khusus).
- **Twitter / X**:
  - Unduh video HD berbagai bitrate dan album multi-foto.
- **Pinterest**:
  - Unduh video MP4 jernih dan foto Pin resolusi original (mode slide parameter adaptif).
- **Bilibili**:
  - Parser multi-kualitas dengan mitigasi proteksi rate-limit CDN Akamai (auto-cap 720p jika tanpa akun login untuk mencegah *broken connection*).
- **YouTube**:
  - Dukungan resolusi hingga 4K UHD 60FPS HDR, filter codec selektif (H.264, VP9, AV1), ekstraksi MP3/M4A, embed subtitle (Softsub P0), serta injeksi thumbnail cover art dan metadata ID3.
- **Platform Lain**: SoundCloud, Facebook, Vimeo, Twitch, Reddit, Dailymotion, NicoNico, dan ribuan situs yang didukung yt-dlp.

### 3. Antarmuka Modern & Cerdas (Studio Mode)
- **Desain Futuristik Dark Mode**: Dibangun menggunakan CustomTkinter dengan palet warna modern, badge platform dinamis, dan responsif.
- **Pembersihan URL & Auto-Preview**:
  - Tempel link langsung mengisolasi URL murni dari teks pengantar/caption.
  - Menekan tombol **Tempel** atau **`Ctrl+V`** seketika menjalankan inspeksi pratinjau info, thumbnail, dan metadata teknis.
- **Adaptif Studio Parameter**:
  - Beralih otomatis antara **Mode Video + Audio** dan **Mode Slide Foto** saat mendeteksi album foto (Instagram Carousel, Douyin Note, TikTok Photo).
- **Antrean Batch (Batch Queue)**:
  - Masukkan daftar banyak URL atau impor file teks `.txt` untuk mengunduh puluhan media sekaligus secara berurutan.
- **Preset Cepat**:
  - Akses satu klik untuk profil favorit: *Super Quality*, *Musik MP3*, *Hemat Data (H.264 720p)*, dan *Podcast*.
- **Injeksi Thumbnail & Metadata**:
  - Opsi menanamkan cover art asli dan metadata (Judul, Kreator, Tanggal) ke dalam berkas media `.mp4`, `.mkv`, `.mp3`, `.m4a`.

---

## 📁 Struktur Direktori

```text
mavdown/
├── assets/           # Ikon aplikasi dan aset grafis
├── bin/              # Pustaka biner mandiri (yt-dlp.exe, aria2c.exe, ffmpeg.exe, ffprobe.exe, node.exe)
├── dist/             # (Otomatis) Hasil rilis kompilasi Nuitka
├── downloads/        # Folder bawaan hasil unduhan media
├── engines/          # Arsitektur Fast Tier 1 Engines
│   ├── base.py       # Utilitas stream download, ffprobe probe, embed thumbnail, remux
│   ├── router.py     # Router pendeteksi platform & dispatcher cerdas
│   ├── douyin.py     # Engine Douyin (UHD SnapDouyin, Cloud API, Aweme)
│   ├── tiktok.py     # Engine TikTok (TikWM, MusicalDown, Lovetik)
│   ├── instagram.py  # Engine Instagram (Reels, Post, Multi-photo Carousel)
│   ├── twitter.py    # Engine Twitter/X (Twitsave, API)
│   ├── pinterest.py  # Engine Pinterest (Scraper HD Originals & MP4 video)
│   ├── bilibili.py   # Engine Bilibili (Stream parser & CDN safety)
│   └── facebook.py   # Engine Facebook video
├── ui/               # Arsitektur antarmuka modular
│   ├── app.py        # Controller utama GUI, event binding, UI queue worker
│   ├── constants.py  # Palet tema, konfigurasi preset, pola platform regex
│   └── settings.py   # Jendela dialog pengaturan direktori & cookies
├── config.py         # Manajer konfigurasi path & pembaca file config.json
├── config.json       # (Otomatis) Preferensi folder dan browser cookies tersimpan
├── downloader.py     # Core controller unduhan, orchestrator yt-dlp, dan lirik konverter
├── gui.py            # Gateway backward-compatibility untuk modul UI
├── mavdown.py        # Titik masuk utama aplikasi (Entry Point)
├── requirements.txt  # Daftar dependensi pustaka Python
├── .gitignore        # Berkas pengecualian Git
└── LICENSE           # Lisensi MIT
```

---

## 🛠️ Panduan Menjalankan dari Kode Sumber

### 1. Prasyarat Sistem
- **Sistem Operasi**: Windows 10 atau Windows 11 (64-bit direkomendasikan).
- **Python**: Versi 3.10 atau yang lebih baru.

### 2. Instalasi Dependensi
Clone repositori ini dan instal dependensi pustaka Python:
```bash
git clone https://github.com/SayMaven/mavdown.git
cd mavdown
pip install -r requirements.txt
```

### 3. Komponen Biner Tambahan (Folder `bin/`)
Pastikan file biner berikut tersedia di dalam folder `bin/` untuk mengaktifkan seluruh fitur:
- `yt-dlp.exe` (Engine unduhan utama)
- `ffmpeg.exe` & `ffprobe.exe` (Pemrosesan media, probe codec, injeksi thumbnail)
- `aria2c.exe` (Akselerasi download multi-thread)
- `node.exe` (JavaScript runtime untuk pemecahan cipher YouTube)

### 4. Jalankan Aplikasi
```bash
python mavdown.py
```

---

## ⚙️ Kompilasi ke Executable (.exe)

Proyek ini telah dikonfigurasi untuk dikompilasi secara mandiri menggunakan **Nuitka** agar menghasilkan performa tinggi tanpa dependensi Python di komputer pengguna:

```bash
pip install nuitka
python -m nuitka --standalone --windows-disable-console --enable-plugin=tk-inter --include-data-dir=assets=assets --include-data-dir=bin=bin --output-dir=dist mavdown.py
```

---

## 📄 Lisensi
Proyek ini dilisensikan di bawah lisensi [MIT License](LICENSE). Bebas digunakan, dimodifikasi, dan didistribusikan untuk keperluan personal maupun edukasi.
