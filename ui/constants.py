# ---------------------------------------------------------------------------
# MAVDOWN UI CONSTANTS & PALETTES (v1.2.0)
# ---------------------------------------------------------------------------

APP_VERSION = "1.2.0"
APP_TITLE = f"Maven Downloader v{APP_VERSION}"

# Pemetaan Bahasa Subtitle / Lirik
LANG_PRESETS = {
    "Indonesia & English": "id,en",
    "Bahasa Indonesia": "id",
    "English": "en",
    "Jepang (Japanese)": "ja",
    "Cina (Chinese)": "zh",
    "Korea (Korean)": "ko",
    "Spanyol (Spanish)": "es",
    "Semua Bahasa (All)": "all",
    "Custom / Manual": "custom"
}

# Deteksi Platform dari URL
PLATFORM_PATTERNS = [
    (r'youtu\.be|youtube\.com',       "YouTube",       "#FF4444"),
    (r'tiktok\.com',                   "TikTok",        "#00F2FE"),
    (r'douyin\.com|iesdouyin\.com',    "Douyin",        "#FE2C55"),
    (r'instagram\.com',                "Instagram",     "#E1306C"),
    (r'twitter\.com|x\.com',           "Twitter / X",   "#1D9BF0"),
    (r'facebook\.com|fb\.watch|fb\.me',"Facebook",      "#1877F2"),
    (r'pinterest\.com|pin\.it',        "Pinterest",     "#E60023"),
    (r'soundcloud\.com',               "SoundCloud",    "#FF7700"),
    (r'vimeo\.com',                    "Vimeo",         "#1AB7EA"),
    (r'twitch\.tv',                    "Twitch",        "#9146FF"),
    (r'nicovideo\.jp|nico\.ms',        "NicoNico",      "#E6E6E6"),
    (r'dailymotion\.com',              "Dailymotion",   "#0066DC"),
    (r'reddit\.com',                   "Reddit",        "#FF4500"),
    (r'bilibili\.com|b23\.tv',         "Bilibili",      "#00A1D6"),
]

# Quick Preset Profiles
QUICK_PRESETS = {
    "Super Quality": {
        "mode": "video_audio", "container": "auto", "resolution": "best",
        "video_codec": "best", "audio_codec": "best",
        "audio_format": "auto", "embed_thumb": True,
        "label_v": "Auto", "label_c": "Auto", "label_a": "Auto", "label_r": "Auto"
    },
    "Musik MP3": {
        "mode": "audio_only", "container": "auto", "resolution": "best",
        "video_codec": "best", "audio_codec": "best",
        "audio_format": "mp3", "embed_thumb": True,
        "label_v": "Auto", "label_c": "Auto", "label_a": "Auto", "label_r": "Auto"
    },
    "Hemat Data": {
        "mode": "video_audio", "container": "mp4", "resolution": "720",
        "video_codec": "h264", "audio_codec": "best",
        "audio_format": "mp3", "embed_thumb": True,
        "label_v": "MP4", "label_c": "H.264", "label_a": "Auto", "label_r": "720p"
    },
    "Podcast": {
        "mode": "audio_only", "container": "auto", "resolution": "best",
        "video_codec": "best", "audio_codec": "best",
        "audio_format": "m4a", "embed_thumb": True,
        "label_v": "Auto", "label_c": "Auto", "label_a": "Auto", "label_r": "Auto"
    },
}

# Theme Color Palette
THEME = {
    "bg_master": "#090A10",
    "sidebar_bg": "#0E101A",
    "card_bg": "#111320",
    "card_inner": "#090A12",
    "border": "#1E2032",
    "border_light": "#25283C",
    "accent_indigo": "#4F46E5",
    "accent_indigo_hover": "#4338CA",
    "accent_emerald": "#10B981",
    "accent_emerald_hover": "#059669",
    "accent_rose": "#EF4444",
    "accent_rose_hover": "#DC2626",
    "accent_amber": "#D97706",
    "accent_amber_hover": "#B45309",
    "text_title": "#F9FAFB",
    "text_body": "#E5E7EB",
    "text_muted": "#9CA3AF",
    "text_dim": "#6B7280",
    "text_accent": "#38BDF8"
}
