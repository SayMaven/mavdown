# Maven Downloader (Mavdown) v1.2.0

![Maven Downloader Screenshot](https://res.cloudinary.com/ds4a54vuy/image/upload/v1790796075/Screenshot_mavdown_1_2.png)

**Maven Downloader (Mavdown)** is a modern desktop media downloader built on Python and CustomTkinter, designed to extract and download media (videos, photo slide albums, and audio) from dozens of global platforms with maximum speed and an advanced Multi-Tier Engine architecture.

The application pairs a **Tier 1 Fast REST Scraping Engine** (near-instant media extraction without watermarks for Douyin, TikTok, Instagram, Twitter/X, Pinterest, Facebook, and Bilibili) with a **Tier 2 Fallback Engine** (yt-dlp, aria2c 16x multi-connection acceleration, FFmpeg, and Node.js anti-bot solver), backed by a local visual download history library with on-disk thumbnail caching and secure user data isolation.

---

## Key Features

### 1. Multi-Tier Engine Architecture
- **Tier 1 (Fast REST Engines)**: Connects directly through lightweight API endpoints and mirror scrapers without CPU overhead, producing pure watermark-free HD video streams and master-resolution photo slide albums.
- **Tier 2 (Enterprise Fallback)**: Powered by the latest yt-dlp engine paired with an internal Node.js JavaScript runtime to solve YouTube cipher challenges (Anti-403 Forbidden).
- **Multi-Thread Acceleration**: Native support for aria2c utilizing up to 16 concurrent connections to saturate high-speed network connections.

### 2. Comprehensive Platform Support
- **Douyin**: 
  - Supports video downloads up to 4K / 1080p FHD and master-quality HD Photo Slide Albums.
  - Automatic background music (BGM) extraction.
  - Automatic URL sanitization: extracts and isolates clean URLs from promotional Chinese share text and token strings via both the Paste button and the Ctrl+V keyboard shortcut.
  - Deep probing of stream resolution, FPS, duration, and codec via ffprobe.
- **TikTok**:
  - Watermark-free HD video downloads and automatic sorting of full-resolution photo albums into dedicated folders tagged with `[TikTok Slide]`, alongside original MP3 audio.
- **Instagram**:
  - Downloads Reels, regular video posts, and multi-photo Carousel Albums directly into organized directories.
- **Twitter / X**:
  - Multi-bitrate HD video stream selection and original-resolution photo album downloads.
- **Pinterest**:
  - Pristine MP4 video downloads and automatic upscaling of image Pins to original master resolution (`/originals/`) with adaptive parameter controls.
- **Bilibili**:
  - Multi-resolution stream extraction with automated Akamai CDN rate-limit mitigations (Error 492) to prevent mid-stream connection drops.
- **YouTube**:
  - Support for resolutions up to 4K UHD 60FPS HDR, selective codec filtering (H.264, VP9, AV1), MP3/M4A high-fidelity audio extraction, soft-subtitle embedding, and automated ID3 metadata/cover art injection.
- **Other Platforms**: SoundCloud, Facebook, Vimeo, Twitch, Reddit, Dailymotion, NicoNico, and thousands of platforms supported across the yt-dlp ecosystem.

### 3. Download History Library
- **Visual Thumbnail Previews**:
  - Dedicated 16:9 preview containers (118x70 px) with smooth rounded corners for every history card.
  - Automatic media extractors: video frames are grabbed from the 1st second via FFmpeg, photos/slides are rendered via PIL, and online thumbnails are cached locally inside the user directory.
  - Interactive preview: clicking any thumbnail directly opens or plays the media file in the operating system's default media player.
- **Comprehensive Technical Metadata Chips**:
  - Platform Badges with tailored color identities (YouTube, TikTok, Douyin, Bilibili, Pinterest, Instagram, Twitter/X, Facebook, etc.).
  - Specific Media Format pills (MP4, MKV, SLIDE, JPG, MP3).
  - Creator / Artist attribution extracted from platform metadata or embedded tags.
  - Native Technical Resolution (such as 1080p FHD, 4K UHD, or 736x1308).
  - Duration or Photo Slide Count.
  - Actual disk File Size and Download Timestamp.
- **Context-Aware Action Buttons**:
  - Open: automatically assigned for Photos and Slide Albums.
  - Play: automatically assigned for Video and Audio streams.
  - Folder: reveals the file in Windows File Explorer with the item pre-selected.
  - Copy Link: copies the original source URL back to the clipboard in a single click.
  - Delete & Clear History: safe database management backed by thread-safe locking.
- **Real-Time Search & Filtering**:
  - Instant filter bar allowing users to search download history dynamically by title, creator, platform, or file format.

### 4. Modern Interface & Studio Mode
- **Sleek, Native Dark Theme**: Crafted with CustomTkinter featuring curated color palettes and clean typography with zero emoji characters for maximum cross-platform visual consistency.
- **Auto-Detect & Instant Preview**: Pasting a URL via the Paste button or Ctrl+V automatically cleans the link and triggers instant metadata inspection, duration calculation, and cover art retrieval.
- **Adaptive Parameter Studio**: The interface automatically toggles between Video + Audio Mode, Audio Only Mode, and Photo / Slide Download Parameters based on the inspected content type.
- **Quick Presets**: One-click profile switcher: Super Quality, Music MP3, Data Saver (720p H.264), and Podcast.
- **Metadata & Cover Art Injection**: Direct embedding of high-resolution cover art and metadata (Title, Artist, Date) into MP4, MKV, MP3, and M4A containers via FFmpeg stream disposition.
- **Batch Queue Management**: Queue multiple URLs simultaneously or import batch text files (`.txt`) for automated sequential downloads.
- **Real-Time Telemetry & Log Console**: Live progress bars, transfer speed metrics, ETA calculations, and a detailed diagnostic log console.

### 5. Unified Settings, Networking & Background Utilities
- **Integrated Settings View**: Replaced legacy popup dialogs with a full navigation tab within the main workspace.
- **Custom ThemedDropdown**: Bespoke dark-mode dropdown menus featuring crisp borders, sharp contrast, and OS-borderless popups.
- **Network Proxy Support**: Built-in proxy configuration (HTTP, HTTPS, SOCKS5) to facilitate downloads in restricted environments or bypass regional ISP throttling.
- **Background Clipboard Monitor Daemon**: Lightweight background daemon that automatically detects copied media URLs, pastes them into the input bar, and triggers info inspection without manual intervention.
- **Browser Cookie Session Importer**: Direct cookie extraction from Chrome, Firefox, Edge, Brave, Opera, or Vivaldi to download private media or bypass platform bot verification.
- **Multi-Channel yt-dlp Updater**: Switch between Stable Channel (tested, scheduled releases) and Nightly Channel (daily upstream builds to counter sudden platform API changes).
- **Preferences Reset**: One-click factory reset button to restore default format, codec, and resolution configurations.

### 6. Storage Architecture & System Security
- **User Data Isolation (%LOCALAPPDATA%)**:
  - Configuration files (`config.json`), history database (`history.json`), and thumbnail caches are strictly stored in the user data directory (`%LOCALAPPDATA%\SayMaven\Mavdown\`).
  - Guarantees full read/write permissions without ever triggering Windows User Account Control (UAC) administrator prompts, even when installed in protected directories like `C:\Program Files`.
  - Ensures preferences and download histories persist untouched across updates and reinstallations.
- **Automatic Migration**: Automatically detects and migrates legacy configurations from the portable application folder to the user data directory.

---

## Directory Structure

```text
mavdown/
├── .github/
│   └── workflows/ci.yml # Automated GitHub Actions CI workflow
├── assets/              # Application icons and branding graphics
│   └── old/             # Archived legacy assets
├── bin/                 # Self-contained binaries (yt-dlp.exe, aria2c.exe, ffmpeg.exe, ffprobe.exe, node.exe)
├── downloads/           # Default fallback media downloads directory
├── engines/             # Fast Tier 1 Scraping Engines
│   ├── base.py          # Stream download utilities, ffprobe probing, thumbnail embedding, remuxing
│   ├── router.py        # Platform detection router & intelligent engine dispatcher
│   ├── douyin.py        # Douyin engine (SnapDouyin UHD, Cloud API, Aweme)
│   ├── tiktok.py        # TikTok engine (TikWM, MusicalDown, Lovetik)
│   ├── instagram.py     # Instagram engine (Reels, Posts, Multi-photo Carousels)
│   ├── twitter.py       # Twitter/X engine (Twitsave, REST API)
│   ├── pinterest.py     # Pinterest engine (HD Originals scraper & MP4 videos)
│   ├── bilibili.py      # Bilibili engine (Stream parser & CDN safety)
│   └── facebook.py      # Facebook engine (Public & SD/HD video parser)
├── tests/               # Automated unit test suite
│   ├── __init__.py      # Test package initialization
│   └── test_core.py     # Unit tests (platform router, sanitizer, formatters, history CRUD, temp cleaner)
├── ui/                  # Modular CustomTkinter user interface architecture
│   ├── app.py           # Main GUI controller, event bindings, UI queue processor
│   ├── constants.py     # Color palettes, quick preset configs, platform regex patterns
│   ├── sidebar.py       # Sidebar navigation, quick preset switcher, and status telemetry
│   ├── studio_view.py   # Main media inspection studio & download parameter panel
│   ├── queue_view.py    # Batch download queue & text file URL importer
│   ├── history_view.py  # Visual download library with thumbnail previews & live search
│   ├── log_view.py      # Real-time streaming diagnostic log console
│   ├── settings_view.py # Inline settings panel for directories, proxies, cookies, & updates
│   └── widgets.py       # Custom modern UI widgets (ThemedDropdown)
├── config.py            # Path resolution manager, preferences handler, & AppData isolation
├── config.json          # (Generated) User preferences, update channels, and active cookies
├── downloader.py        # Core download orchestrator, yt-dlp argument builder, & lyric converter
├── gui.py               # Backward-compatibility gateway exporting the App controller
├── history.py           # Thread-safe download history manager, thumbnail caching, & auto-healing
├── mavdown.py           # Primary application entry point
├── requirements.txt     # Python dependency specifications
├── AGENTS.md            # Technical engineering architecture & developer guidelines
├── .gitignore           # Git ignore specifications
└── LICENSE              # MIT License
```

---

## Automated Testing & CI

This repository includes an automated unit test suite to verify core module stability and regression prevention:

```bash
# Execute the full unit test suite
python -m unittest discover tests

# Verify Python bytecode compilation across all modules
python -c "import compileall; compileall.compile_dir('.', quiet=1)"
```

The GitHub Actions CI workflow (`.github/workflows/ci.yml`) automatically executes bytecode verification and the unit test suite on every push and pull request across Windows Server virtual environments.

---

## Building from Source

### 1. Prerequisites
- **Operating System**: Windows 10 or Windows 11 (64-bit recommended).
- **Python**: Version 3.10 or higher.

### 2. Dependency Installation
Clone this repository and install the Python dependencies:
```bash
git clone https://github.com/SayMaven/mavdown.git
cd mavdown
pip install -r requirements.txt
```

### 3. Binary Dependencies (`bin/` Directory)
Ensure the following binaries are placed inside the `bin/` directory:
- `yt-dlp.exe` (Primary fallback download engine)
- `ffmpeg.exe` & `ffprobe.exe` (Media processing, codec probing, and cover art injection)
- `aria2c.exe` (Multi-connection download acceleration)
- `node.exe` (JavaScript runtime for YouTube cipher decryption)

### 4. Running the Application
```bash
python mavdown.py
```

---

## License
This project is licensed under the [MIT License](LICENSE). You are free to use, modify, and distribute it for personal and educational purposes.
