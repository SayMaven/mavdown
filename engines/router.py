import re
from engines.tiktok import get_tiktok_info, download_tiktok
from engines.douyin import get_douyin_info, download_douyin
from engines.twitter import get_twitter_info, download_twitter
from engines.pinterest import get_pinterest_info, download_pinterest
from engines.instagram import get_instagram_info, download_instagram
from engines.facebook import get_facebook_info, download_facebook
from engines.bilibili import get_bilibili_info, download_bilibili

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
    except Exception:
        pass
    return None

def dispatch_fast_download(url: str, output_dir: str, ui_queue=None, options=None, abort_checker=None) -> bool:
    """
    Mengarahkan unduhan ke Tier 1 Fast Engine yang sesuai.
    Mengembalikan True jika sukses, False jika gagal atau harus beralih ke Tier 2 (yt-dlp).
    """
    platform = detect_platform(url)
    if platform in ('generic', 'youtube'):
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
    except Exception as e:
        if ui_queue:
            ui_queue.put({"type": "log", "text": f"[TIER 1 EXCEPTION] {e}\n"})
        return False

    return False
