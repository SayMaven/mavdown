# Maven Downloader (Mavdown) v1.3.0

![Maven Downloader Screenshot](https://res.cloudinary.com/ds4a54vuy/image/upload/v1790796075/Screenshot_mavdown_1_2.png)

**Maven Downloader (Mavdown)** is an enterprise-grade desktop media studio designed to extract and download video streams, full-resolution photo slide albums, and master audio from dozens of global platforms with high throughput and an advanced Multi-Tier Engine architecture.

Mavdown offers two synchronized frontends:
1. **Mavdown C# .NET 10 Desktop Edition** (`Mavdown.Desktop`): A state-of-the-art WPF studio application featuring subtle noise backdrop textures, cover-adaptive dynamic color grading, hardware-accelerated sub-pixel rendering, and asynchronous JSON-RPC IPC communication.
2. **Mavdown Python Native Edition** (`mavdown.py`): A cross-platform CustomTkinter studio interface with instant clipboard detection, queuing workflows, and integrated telemetry.

Both editions interface directly with a unified backend consisting of a **Tier 1 Fast REST & Scraper Engine** (sub-second media extraction without watermarks for Douyin, TikTok, Instagram, Twitter/X, Pinterest, Facebook, and Bilibili) and an enterprise **Tier 2 Fallback Engine** (yt-dlp, aria2c 16x multi-connection acceleration, FFmpeg, and an embedded Node.js JavaScript runtime).

---

## Key Features

### 1. Dual-Frontend Studio Architecture
- **C# .NET 10 WPF Frontend**:
  - High-performance, memory-efficient desktop interface built with modern XAML and Windows Presentation Foundation.
  - Cover-Adaptive Gatefold Dynamic Palette: Extracts dominant visual accents from media thumbnails and shifts ambient theme lighting smoothly.
  - Studio Layout: 50% enlarged media inspector panel, integrated single-click URL clear button, contextual column telemetry headers (Views, Likes, Comments, Shares, Upload Dates), and responsive quality chips.
  - Asynchronous IPC: Communicates with `mav_core.py` over bidirectional UTF-8 JSON-RPC streams.
- **Python CustomTkinter Frontend**:
  - Native Python desktop interface built on CustomTkinter with real-time UI queue polling and inline settings management.

### 2. Multi-Tier Engine Architecture
- **Tier 1 (Fast REST Engines)**: Connects directly through lightweight API endpoints and mirror scrapers without CPU overhead, producing pure watermark-free HD video streams and master-resolution photo slide albums in under one second.
- **Tier 2 (Enterprise Fallback)**: Powered by yt-dlp paired with an internal Node.js JavaScript runtime to solve YouTube cipher challenges (Anti-403 Forbidden).
- **Multi-Thread Acceleration**: Native support for aria2c utilizing up to 16 concurrent connections to saturate high-speed network connections.

### 3. Multi-Candidate Thumbnail Fallback System
- **Intelligent Variant Scoring**: Automatically gathers all available thumbnail candidate URLs from platform CDN servers (creator-curated cover art, dynamic WebP animations, and origin frame captures).
- **Creator Artwork Prioritization**: Resolves custom high-resolution creator covers (such as Douyin `sc=cover` and TikTok `cover`) over raw frame-0 images.
- **Pillow Byte Verification**: Every candidate thumbnail is tested and verified for format integrity using Pillow (`Image.open().verify()`) before rendering.
- **FFmpeg Stream Frame Capture**: If remote image CDNs fail or return 403 Forbidden, Mavdown automatically invokes FFmpeg to capture a clean 1-second video frame directly from the media stream (`ffmpeg -ss 00:00:01 -i <video_url> ...`).
- **YouTube Thumbnail Progression**: In Tier 2, if YouTube's `maxresdefault.jpg` returns HTTP 404, the system automatically walks down the resolution chain (`sddefault.jpg`, `hqdefault.jpg`, `mqdefault.jpg`) without displaying placeholder errors.

### 4. Comprehensive Platform Support
- **Douyin**: 
  - Dual-engine parallel execution combining SnapDouyin and Cloud Engine for 2K/4K UHD resolution, creator cover art, and complete multi-line descriptions.
  - Automatic background music (BGM) extraction and lossless photo slide album separation.
  - Automatic share-text sanitization: extracts and isolates clean URLs from promotional Chinese text via paste actions and keyboard shortcuts.
- **TikTok**:
  - Watermark-free HD video downloads and automatic sorting of full-resolution photo albums into dedicated folders tagged with `[TikTok Slide]`, alongside original MP3 audio.
  - Multi-candidate cover art detection (`cover`, `dynamic_cover`, `origin_cover`).
- **Instagram**:
  - Downloads Reels, regular video posts, and multi-photo Carousel Albums directly into organized directories.
- **Twitter / X**:
  - Multi-bitrate HD video stream selection, original-resolution photo album downloads, and engagement statistics.
- **Pinterest**:
  - Pristine MP4 video downloads and automatic upscaling of image Pins to original master resolution (`/originals/`) with adaptive parameter controls.
- **Bilibili**:
  - Multi-resolution stream extraction with automated Akamai CDN rate-limit mitigations (Error 492) to prevent mid-stream connection drops.
- **YouTube**:
  - Support for resolutions up to 4K UHD 60FPS HDR, selective codec filtering (H.264, VP9, AV1), MP3/M4A high-fidelity audio extraction, soft-subtitle embedding, and automated ID3 metadata/cover art injection.
- **Other Platforms**: SoundCloud, Facebook, Vimeo, Twitch, Reddit, Dailymotion, NicoNico, and thousands of platforms supported across the yt-dlp ecosystem.

### 5. Download History Library
- **Visual Thumbnail Previews**: Dedicated 16:9 preview containers with smooth rounded corners for every history item.
- **Comprehensive Technical Metadata**: Platform badges, container tags, creator attribution, exact pixel dimensions, duration, and file size.
- **Context-Aware Action Buttons**: Contextual playback for videos and direct folder navigation in Windows File Explorer.
- **Real-Time Search & Filtering**: Instant filter bar allowing users to search download history dynamically by title, creator, platform, or file format.

### 6. Storage Architecture & System Security
- **User Data Isolation (%LOCALAPPDATA%)**:
  - Configuration files (`config.json`), history database (`history.json`), and thumbnail caches are stored strictly in `%LOCALAPPDATA%\SayMaven\Mavdown\`.
  - Guarantees full read/write permissions without triggering Windows User Account Control (UAC) administrator prompts, even when installed in protected directories like `C:\Program Files`.
  - Ensures preferences and download histories persist untouched across updates and reinstallations.
- **Automatic Migration**: Automatically detects and migrates legacy configurations from the portable application folder to the user data directory.

---

## Directory Structure

```text
mavdown/
├── .github/
│   └── workflows/ci.yml   # Automated GitHub Actions CI workflow
├── assets/                # Application icons and branding graphics
├── bin/                   # Self-contained binaries (yt-dlp.exe, aria2c.exe, ffmpeg.exe, ffprobe.exe, node.exe)
├── downloads/             # Default media downloads directory
├── engines/               # Fast Tier 1 Scraping Engines
│   ├── base.py            # Stream download utilities, ffprobe probing, thumbnail embedding, remuxing
│   ├── router.py          # Platform detection router & intelligent engine dispatcher
│   ├── douyin.py          # Douyin engine (SnapDouyin UHD, Cloud API, Aweme)
│   ├── tiktok.py          # TikTok engine (TikWM, multi-candidate cover resolver)
│   ├── instagram.py       # Instagram engine (Reels, Posts, Multi-photo Carousels)
│   ├── twitter.py         # Twitter/X engine (REST API, multi-media extractor)
│   ├── pinterest.py       # Pinterest engine (HD Originals scraper & MP4 videos)
│   ├── bilibili.py        # Bilibili engine (Stream parser & CDN safety)
│   └── facebook.py        # Facebook engine (Public & SD/HD video parser)
├── Mavdown.Desktop/       # C# .NET 10 WPF Desktop Application
│   ├── App.xaml           # WPF Application definition & resources
│   ├── MainWindow.xaml    # Main WPF Studio layout & styling
│   ├── MainWindow.xaml.cs # WPF Studio logic, dynamic palette, & UI queue dispatcher
│   ├── Models/            # Data models (HistoryItem, QueueItem)
│   ├── Services/          # PythonBridge IPC daemon & GatePaletteService
│   └── Assets/            # Noise backdrop texture & UI icons
├── tests/                 # Automated unit test suite
│   ├── __init__.py        # Test package initialization
│   └── test_core.py       # Unit tests (platform router, sanitizer, formatters, history CRUD, temp cleaner)
├── ui/                    # Modular CustomTkinter user interface architecture
│   ├── app.py             # Main GUI controller, event bindings, UI queue processor
│   ├── constants.py       # Color palettes, quick preset configs, platform regex patterns
│   ├── sidebar.py         # Sidebar navigation, quick preset switcher, and status telemetry
│   ├── studio_view.py     # Media inspection studio & download parameter panel
│   ├── queue_view.py      # Batch download queue & text file URL importer
│   ├── history_view.py    # Visual download library with thumbnail previews & live search
│   ├── log_view.py        # Real-time streaming diagnostic log console
│   ├── settings_view.py   # Inline settings panel for directories, proxies, cookies, & updates
│   └── widgets.py         # Custom modern UI widgets (ThemedDropdown)
├── config.py              # Path resolution manager, preferences handler, & AppData isolation
├── config.json            # (Generated) User preferences, update channels, and active cookies
├── downloader.py          # Core download orchestrator, multi-candidate thumbnail resolver, & yt-dlp builder
├── gui.py                 # Backward-compatibility gateway exporting the App controller
├── history.py             # Thread-safe download history manager, thumbnail caching, & auto-healing
├── mav_core.py            # Headless JSON-RPC / IPC Core Daemon for C# WPF Frontend
├── mavdown.py             # Python CustomTkinter application entry point
├── requirements.txt       # Python dependency specifications
├── AGENTS.md              # Technical engineering architecture & developer guidelines
├── .gitignore             # Git ignore specifications
└── LICENSE                # MIT License
```

---

## Getting Started

### Prerequisites
- **Operating System**: Windows 10 or Windows 11 (64-bit).
- **Python**: Version 3.10 or higher.
- **.NET SDK** (for C# WPF Edition): .NET 10.0 SDK.

### Installation
Clone this repository and install the Python dependencies:
```bash
git clone https://github.com/SayMaven/mavdown.git
cd mavdown
pip install -r requirements.txt
```

### Binary Dependencies (`bin/` Directory)
Ensure the following binaries are placed inside the `bin/` directory:
- `yt-dlp.exe` (Primary fallback download engine)
- `ffmpeg.exe` & `ffprobe.exe` (Media processing, codec probing, and cover art injection)
- `aria2c.exe` (Multi-connection download acceleration)
- `node.exe` (JavaScript runtime for YouTube cipher decryption)

---

## Running the Application

### Option A: C# .NET 10 Desktop Edition (Recommended)
Run the modern WPF studio interface:
```bash
dotnet run --project Mavdown.Desktop
```

Or build a release executable:
```bash
dotnet build Mavdown.Desktop -c Release
```

### Option B: Python CustomTkinter Edition
Run the Python native desktop interface:
```bash
python mavdown.py
```

---

## Automated Testing & CI

Execute the unit test suite and verify Python bytecode compilation:

```bash
# Execute the full unit test suite
python -m unittest discover tests

# Verify Python bytecode compilation across all modules
python -c "import compileall; compileall.compile_dir('.', quiet=1)"
```

The GitHub Actions CI workflow (`.github/workflows/ci.yml`) automatically executes bytecode verification and the unit test suite on every push and pull request across Windows Server virtual environments.

---

## License
This project is licensed under the [MIT License](LICENSE). You are free to use, modify, and distribute it for personal and educational purposes.
