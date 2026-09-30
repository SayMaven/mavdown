import os
import re
import requests
from engines.base import (
    DEFAULT_HEADERS, sanitize_filename, stream_download_file,
    fast_remux_mp4, extract_audio_from_video, embed_thumbnail_to_media
)

def extract_tweet_id(url: str) -> str:
    """Ekstraksi Tweet ID dari URL twitter.com atau x.com."""
    match = re.search(r'(?:twitter|x)\.com\/(?:[^\/]+\/status\/|status\/|i\/status\/)(\d+)', url or '', re.IGNORECASE)
    return match.group(1) if match else None

def get_fxtwitter_data(tweet_id: str, timeout: int = 12) -> dict:
    """Mengambil metadata status dari FxTwitter REST API."""
    api_url = f"https://api.fxtwitter.com/i/status/{tweet_id}"
    resp = requests.get(api_url, headers=DEFAULT_HEADERS, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data.get('tweet')

def get_twitter_info(url: str) -> dict:
    """Ekstraksi metadata tweet instan untuk preview GUI."""
    tweet_id = extract_tweet_id(url)
    if not tweet_id:
        return None
    try:
        tweet = get_fxtwitter_data(tweet_id)
        if not tweet:
            return None
        
        target = tweet
        if not target.get('media', {}).get('all') and tweet.get('quote', {}).get('media', {}).get('all'):
            target = tweet['quote']

        author_name = target.get('author', {}).get('name', 'Twitter User')
        screen_name = target.get('author', {}).get('screen_name', '')
        author = f"{author_name} (@{screen_name})" if screen_name else author_name
        text = target.get('text', 'Twitter Media')
        
        all_media = target.get('media', {}).get('all', [])
        thumb = ''
        if all_media:
            thumb = all_media[0].get('thumbnail_url') or all_media[0].get('url') or ''

        return {
            'title': f"{author}: {text[:80]}",
            'clean_title': text[:100],
            'author': author,
            'thumbnail': thumb,
            'is_slide': len(all_media) > 1,
            'media_count': len(all_media),
            'platform': 'Twitter/X'
        }
    except Exception:
        return None

def download_twitter(url: str, output_dir: str, ui_queue=None, options=None, abort_checker=None) -> bool:
    """
    Unduh video, animasi GIF, atau foto dari Twitter/X menggunakan FxTwitter Engine.
    """
    if options is None:
        options = {}
    mode = options.get('mode', 'video_audio')
    audio_format = options.get('audio_format', 'mp3')

    tweet_id = extract_tweet_id(url)
    if not tweet_id:
        return False

    if ui_queue:
        ui_queue.put({"type": "log", "text": f"[TIER 1] Menghubungi FxTwitter API (ID: {tweet_id})...\n"})

    try:
        tweet = get_fxtwitter_data(tweet_id)
        if not tweet:
            if ui_queue:
                ui_queue.put({"type": "log", "text": "[TIER 1] Data tweet tidak ditemukan. Beralih ke Tier 2...\n"})
            return False

        target = tweet
        if not target.get('media', {}).get('all') and tweet.get('quote', {}).get('media', {}).get('all'):
            target = tweet['quote']

        author_name = target.get('author', {}).get('name', 'Twitter User')
        screen_name = target.get('author', {}).get('screen_name', '')
        author = f"{author_name} (@{screen_name})" if screen_name else author_name
        raw_title = target.get('text') or 'Twitter Media'
        base_name = sanitize_filename(f"{author} - {raw_title[:60]}")

        all_media = target.get('media', {}).get('all', [])
        if not all_media:
            if ui_queue:
                ui_queue.put({"type": "log", "text": "[TIER 1] Tidak ada media terdeteksi di tweet ini.\n"})
            return False

        # -------------------------------------------------------------
        # 1. KASUS A: Multi-Media / Album Foto Twitter (lebih dari 1 media)
        # -------------------------------------------------------------
        if len(all_media) > 1:
            if ui_queue:
                ui_queue.put({"type": "log", "text": f"[TIER 1] Terdeteksi Multi-Media ({len(all_media)} item).\n"})

            media_folder = os.path.join(output_dir, f"{base_name} [Twitter Media]")
            os.makedirs(media_folder, exist_ok=True)

            for i, m in enumerate(all_media, 1):
                if abort_checker and abort_checker():
                    return False
                m_type = m.get('type')
                m_url = m.get('url')
                if m_type in ('video', 'gif') and m.get('variants'):
                    # Pilih varian video MP4 bitrate tertinggi
                    mp4_variants = [v for v in m['variants'] if v.get('content_type') == 'video/mp4']
                    if mp4_variants:
                        mp4_variants.sort(key=lambda x: x.get('bitrate', 0), reverse=True)
                        m_url = mp4_variants[0].get('url')

                ext = ".mp4" if m_type in ('video', 'gif') else ".jpg"
                dest_path = os.path.join(media_folder, f"media_{i:02d}{ext}")
                label = f"Item {i}/{len(all_media)}"
                stream_download_file(m_url, dest_path, ui_queue, abort_checker, label=label)

            if ui_queue:
                ui_queue.put({"type": "log", "text": f"\n--- UNDUHAN SUKSES (FxTwitter) ---\nFolder: {media_folder}\n"})
                ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
            return True

        # -------------------------------------------------------------
        # 2. KASUS B: 1 Foto Saja
        # -------------------------------------------------------------
        single_media = all_media[0]
        if single_media.get('type') == 'photo':
            img_url = single_media.get('url')
            final_img_path = os.path.join(output_dir, f"{base_name}.jpg")
            success = stream_download_file(img_url, final_img_path, ui_queue, abort_checker, label="Foto Twitter")
            if success and ui_queue:
                ui_queue.put({"type": "log", "text": f"\n--- UNDUHAN SUKSES (Foto Twitter) ---\nTersimpan di: {final_img_path}\n"})
                ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
            return success

        # -------------------------------------------------------------
        # 3. KASUS C: 1 Video atau 1 GIF
        # -------------------------------------------------------------
        if single_media.get('type') in ('video', 'gif'):
            video_url = single_media.get('url')
            if single_media.get('variants'):
                mp4_variants = [v for v in single_media['variants'] if v.get('content_type') == 'video/mp4']
                if mp4_variants:
                    mp4_variants.sort(key=lambda x: x.get('bitrate', 0), reverse=True)
                    video_url = mp4_variants[0].get('url')

            if not video_url:
                return False

            raw_path = os.path.join(output_dir, f"{base_name}_raw.mp4")
            final_path = os.path.join(output_dir, f"{base_name}.mp4")

            success = stream_download_file(
                video_url, raw_path, ui_queue, abort_checker,
                label="Unduh Twitter Video"
            )
            if not success:
                return False

            fast_remux_mp4(raw_path, final_path)

            saved_path = final_path
            if mode == 'audio_only':
                final_audio = os.path.join(output_dir, f"{base_name}.{audio_format}")
                extract_audio_from_video(final_path, final_audio, audio_format)
                if os.path.exists(final_path):
                    try: os.remove(final_path)
                    except Exception: pass
                saved_path = final_audio

            embed_thumb = options.get('embed_thumb', True) if options else True
            thumb_url = single_media.get('thumbnail_url') or single_media.get('url')
            if embed_thumb and thumb_url and saved_path and os.path.exists(saved_path):
                embed_thumbnail_to_media(saved_path, thumb_url, ui_queue, abort_checker)

            if ui_queue:
                ui_queue.put({"type": "log", "text": f"\n--- UNDUHAN SUKSES (FxTwitter HD) ---\nFile: {saved_path}\n"})
                ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
            return True

    except Exception as e:
        if ui_queue:
            ui_queue.put({"type": "log", "text": f"[TIER 1 ERROR] {e}\n"})
        return False

    return False
