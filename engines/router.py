import os
import re
from engines.tiktok import get_tiktok_info, download_tiktok
from engines.douyin import get_douyin_info, download_douyin
from engines.twitter import get_twitter_info, download_twitter
from engines.pinterest import get_pinterest_info, download_pinterest
from engines.instagram import get_instagram_info, download_instagram
from engines.facebook import get_facebook_info, download_facebook
from engines.bilibili import get_bilibili_info, download_bilibili
from engines.pixiv import get_pixiv_info, download_pixiv

SERVICE_FOLDER_MAP = {
    'youtube': 'Mavdown_YouTube',
    'douyin': 'Mavdown_Douyin',
    'tiktok': 'Mavdown_TikTok',
    'instagram': 'Mavdown_Instagram',
    'twitter': 'Mavdown_Twitter',
    'x': 'Mavdown_Twitter',
    'twitter/x': 'Mavdown_Twitter',
    'pinterest': 'Mavdown_Pinterest',
    'facebook': 'Mavdown_Facebook',
    'bilibili': 'Mavdown_Bilibili',
    'pixiv': 'Mavdown_Pixiv',
    'threads': 'Mavdown_Threads',
    'reddit': 'Mavdown_Reddit',
    'vimeo': 'Mavdown_Vimeo',
    'soundcloud': 'Mavdown_Soundcloud',
    'twitch': 'Mavdown_Twitch',
    'generic': 'Mavdown_Web',
    'web': 'Mavdown_Web',
}

def get_service_folder_name(platform: str) -> str:
    """Mengembalikan nama folder standar per platform (misal: Mavdown_YouTube, Mavdown_Douyin)."""
    key = (platform or '').lower().strip()
    if key in SERVICE_FOLDER_MAP:
        return SERVICE_FOLDER_MAP[key]
    return f"Mavdown_{platform.capitalize()}" if platform else "Mavdown_Web"

def resolve_service_output_dir(base_dir: str, platform_or_url: str, organize_by_platform: bool = True) -> str:
    """
    Menghasilkan direktori penyimpanan berdasarkan platform atau URL.
    Contoh: C:\\Downloads -> C:\\Downloads\\Mavdown_YouTube
    Cegah duplikasi jika base_dir sudah berakhiran nama folder layanan tersebut.
    """
    if not base_dir:
        from config import DEFAULT_OUTPUT_DIR
        base_dir = DEFAULT_OUTPUT_DIR
        
    if not organize_by_platform:
        return base_dir

    if platform_or_url and (platform_or_url.startswith(('http://', 'https://')) or '://' in platform_or_url):
        platform = detect_platform(platform_or_url)
    else:
        platform = platform_or_url or 'generic'

    folder_name = get_service_folder_name(platform)
    
    # Cegah duplikasi nesting jika direktori sudah berakhiran nama folder platform tersebut
    base_norm = os.path.normpath(base_dir)
    if os.path.basename(base_norm).lower() == folder_name.lower():
        return base_dir

    target_dir = os.path.join(base_dir, folder_name)
    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception:
        pass
    return target_dir

def detect_platform(url: str) -> str:
    """Deteksi platform berdasarkan pola URL."""
    url_lower = (url or '').lower().strip()
    if 'youtube.com' in url_lower or 'youtu.be' in url_lower:
        return 'youtube'
    elif 'tiktok.com' in url_lower:
        return 'tiktok'
    elif 'douyin.com' in url_lower or 'iesdouyin.com' in url_lower:
        return 'douyin'
    elif 'twitter.com' in url_lower or 'x.com' in url_lower:
        return 'twitter'
    elif 'pinterest.com' in url_lower or 'pin.it' in url_lower:
        return 'pinterest'
    elif 'instagram.com' in url_lower:
        return 'instagram'
    elif 'facebook.com' in url_lower or 'fb.watch' in url_lower or 'fb.me' in url_lower:
        return 'facebook'
    elif 'bilibili.com' in url_lower or 'b23.tv' in url_lower:
        return 'bilibili'
    elif 'pixiv.net' in url_lower or 'pixiv.me' in url_lower:
        return 'pixiv'
    elif 'threads.net' in url_lower:
        return 'threads'
    elif 'reddit.com' in url_lower:
        return 'reddit'
    elif 'vimeo.com' in url_lower:
        return 'vimeo'
    elif 'soundcloud.com' in url_lower:
        return 'soundcloud'
    elif 'twitch.tv' in url_lower:
        return 'twitch'
    return 'generic'

def resolve_fast_info(url: str, share_text: str = None) -> dict:
    """
    Mengambil metadata video/media secara instan (< 1 detik)
    menggunakan Fast Tier 1 Engine.
    Mengembalikan dict metadata atau None jika platform belum didukung / gagal.
    """
    platform = detect_platform(url)
    try:
        if platform == 'tiktok':
            return get_tiktok_info(url)
        elif platform == 'douyin':
            return get_douyin_info(url, share_text=share_text)
        elif platform == 'twitter':
            return get_twitter_info(url)
        elif platform == 'pinterest':
            return get_pinterest_info(url)
        elif platform == 'instagram':
            return get_instagram_info(url)
        elif platform == 'facebook':
            return get_facebook_info(url)
        elif platform == 'bilibili':
            return get_bilibili_info(url)
        elif platform == 'pixiv':
            return get_pixiv_info(url)
    except Exception:
        pass
    return None

def dispatch_fast_download(url: str, output_dir: str, ui_queue=None, options=None, abort_checker=None) -> bool:
    """
    Mengarahkan unduhan ke Tier 1 Fast Engine yang sesuai.
    Mengembalikan True jika sukses, False jika gagal atau harus beralih ke Tier 2 (yt-dlp).
    """
    platform = detect_platform(url)
    tier1_supported = ('tiktok', 'douyin', 'twitter', 'pinterest', 'instagram', 'facebook', 'bilibili', 'pixiv')
    if platform not in tier1_supported:
        # Bukan platform Tier 1, langsung serahkan ke yt-dlp
        return False

    if options is None:
        options = {}

    try:
        if platform == 'tiktok':
            return download_tiktok(url, output_dir, ui_queue, options, abort_checker)
        elif platform == 'douyin':
            return download_douyin(url, output_dir, ui_queue, options, abort_checker)
        elif platform == 'twitter':
            return download_twitter(url, output_dir, ui_queue, options, abort_checker)
        elif platform == 'pinterest':
            return download_pinterest(url, output_dir, ui_queue, options, abort_checker)
        elif platform == 'instagram':
            return download_instagram(url, output_dir, ui_queue, options, abort_checker)
        elif platform == 'facebook':
            return download_facebook(url, output_dir, ui_queue, options, abort_checker)
        elif platform == 'bilibili':
            return download_bilibili(url, output_dir, ui_queue, options, abort_checker)
        elif platform == 'pixiv':
            return download_pixiv(url, output_dir, ui_queue, options, abort_checker)
    except Exception as e:
        if ui_queue:
            ui_queue.put({"type": "log", "text": f"[TIER 1 EXCEPTION] {e}\n"})
        return False

    return False
