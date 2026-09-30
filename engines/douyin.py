import os
import re
import json
import base64
import html
import requests
from engines.base import (
    DEFAULT_HEADERS, sanitize_filename, stream_download_file,
    fast_remux_mp4, extract_audio_from_video, normalize_image_to_jpeg,
    probe_media_stream, postprocess_video, embed_thumbnail_to_media
)

def extract_douyin_share_info(text: str) -> tuple:
    """
    Mengekstrak (clean_url, author, title) dari teks copy-share Douyin jika disertakan user.
    Contoh: '9.23 gOx:/ :1pm r@e.oD 05/10 长大真好 可以让小时候梦想中的房子具像化 # 梦中情屋  https://v.douyin.com/ZPYCy6v_QUs/ 复制此链接，打开Dou音搜索，直接观看视频！'
    """
    if not text:
        return "", "", ""
    raw_str = text.strip()
    
    # Ekstraksi URL bersih
    m_url = re.search(r'https?://[^\s"\'<>]+', raw_str)
    clean_url = m_url.group(0).rstrip('，。！？!?,;)"\'\r\n') if m_url else raw_str

    # Ekstraksi Author / Creator
    author = ""
    m_author = re.search(r'【(.*?)的作品】', raw_str) or re.search(r'@([a-zA-Z0-9_.\u4e00-\u9fa5]+)', raw_str)
    if m_author:
        cand = m_author.group(1).strip()
        if cand.lower() not in ('douyin user', 'douyinuser', 'user', 'none'):
            author = cand

    # Ekstraksi & pembersihan teks judul/caption
    clean_title = raw_str
    clean_title = re.sub(r'https?://[^\s"\'<>]+', '', clean_title)
    clean_title = re.sub(r'复制此链接.*', '', clean_title)
    clean_title = re.sub(r'复制打开[Dd]ou音.*?', '', clean_title)
    clean_title = re.sub(r'复制打开抖音.*?', '', clean_title)
    clean_title = re.sub(r'【.*?的作品】', '', clean_title)
    clean_title = clean_title.replace('打开抖音', '').replace('看看', '').replace('直接观看视频！', '').replace('直接观看视频', '')
    
    # Bersihkan prefix token sharing Douyin (angka/titik/simbol sebelum huruf Mandarin atau hashtag)
    cleaned = re.sub(r'^[0-9.\s\w:/@.-]+?(?=[\u4e00-\u9fa5#])', '', clean_title)
    if cleaned and cleaned != clean_title:
        clean_title = cleaned
    else:
        clean_title = re.sub(r'^[0-9.]+\s+[\w:/@.-]+\s+[\w:/@.-]+\s*', '', clean_title)
    clean_title = re.sub(r'^[0-9.\s，,]+', '', clean_title)
    clean_title = clean_title.strip(' ，。！？!?,\t\r\n')

    return clean_url, author, clean_title

def expand_douyin_url(url: str, timeout: int = 10) -> str:
    """Follow redirect jika URL berupa shortlink v.douyin.com."""
    clean_url = (url or '').strip()
    try:
        r = requests.get(clean_url, headers=DEFAULT_HEADERS, allow_redirects=True, timeout=timeout)
        return r.url
    except Exception:
        return clean_url

def resolve_snapdouyin_url(session: requests.Session, raw_url: str) -> str:
    """
    Mengurai URL proxy SnapDouyin langsung ke mirror CDN tube5s tanpa network blocking.
    """
    if not raw_url:
        return raw_url
    m = re.search(r'file=([^&]+)', raw_url)
    if m:
        return f"https://sv1.tube5s.com/?file={m.group(1)}"
    try:
        r = session.get(raw_url, allow_redirects=False, timeout=3)
        loc = r.headers.get('Location', '')
        m2 = re.search(r'file=([^&]+)', loc)
        if m2:
            return f"https://sv1.tube5s.com/?file={m2.group(1)}"
        if loc and loc.startswith('http'):
            return loc
    except Exception:
        pass
    return raw_url

def try_snapdouyin_engine(url: str, timeout: int = 6) -> dict:
    """
    Tier 1A: SnapDouyin 1080p / 4K Engine.
    """
    if '/note/' in (url or ''):
        return None
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Referer': 'https://snapdouyin.app/'
    })
    
    try:
        home_res = session.get('https://snapdouyin.app/', timeout=timeout)
        token_match = re.search(r'name="token"\s+value="([^"]+)"', home_res.text)
        if not token_match:
            return None

        token = token_match.group(1)
        b64_url = base64.b64encode(url.encode('utf-8')).decode('ascii')
        b64_dl = base64.b64encode(b'aio-dl').decode('ascii')
        calc_hash = f"{b64_url}{len(url) + 1000}{b64_dl}"

        api_res = session.post(
            'https://snapdouyin.app/wp-json/mx-downloader/video-data/',
            data={'url': url, 'token': token, 'hash': calc_hash},
            headers={'X-Requested-With': 'XMLHttpRequest'},
            timeout=timeout
        )
        api_res.raise_for_status()
        data = api_res.json()
    except Exception:
        return None

    if data and isinstance(data.get('medias'), list) and len(data['medias']) > 0:
        medias = data['medias']
        raw_title = data.get('title') or ''
        is_synthetic = not raw_title or re.match(r'^Douyin Video\d*$', raw_title.strip(), re.I) or raw_title.strip() == 'Douyin Video'
        title = '' if is_synthetic else raw_title.strip()

        raw_author = data.get('author') or data.get('author_name') or ''
        author = '' if raw_author.lower() in ('douyin user', 'douyinuser', 'user', 'none', '') else raw_author
        thumbnail = data.get('thumbnail') or ''

        # Cek jika berupa album slide foto
        image_medias = [m for m in medias if m.get('extension') in ('jpg', 'jpeg', 'png', 'webp') or m.get('type') == 'image']
        video_medias = [m for m in medias if m.get('extension') == 'mp4' or m.get('type') == 'video']

        if image_medias:
            resolved_images = []
            for m in image_medias:
                u = m.get('url')
                if u:
                    resolved_images.append(resolve_snapdouyin_url(session, u))
            
            resolved_video = None
            if video_medias and video_medias[0].get('url'):
                resolved_video = resolve_snapdouyin_url(session, video_medias[0]['url'])

            return {
                'is_slide': True,
                'title': title,
                'is_synthetic_title': is_synthetic,
                'author': author,
                'thumbnail': thumbnail,
                'images': resolved_images,
                'video_url': resolved_video,
                'engine': f"SnapDouyin Slide ({len(resolved_images)} Foto)"
            }

        # Cek video (pilih varian ukuran terbesar / kualitas tertinggi 4K/2K/1080p)
        if video_medias:
            best_vid = video_medias[0]
            for v in video_medias:
                if (v.get('size') or 0) > (best_vid.get('size') or 0):
                    best_vid = v
            resolved_video = resolve_snapdouyin_url(session, best_vid.get('url'))
            
            meta = probe_media_stream(resolved_video) if resolved_video else {}
            w = meta.get('width')
            h = meta.get('height')
            fps = meta.get('fps')
            res_label = meta.get('resolution_label') or ''
            
            spec_parts = []
            if res_label:
                spec_parts.append(res_label)
            elif w and h:
                spec_parts.append(f"{w}x{h}")
            if fps:
                spec_parts.append(f"{fps}fps")
                
            engine_name = f"SnapDouyin ({' '.join(spec_parts)})" if spec_parts else "SnapDouyin (HD)"
            
            return {
                'isVideo': True,
                'title': title,
                'is_synthetic_title': is_synthetic,
                'author': author,
                'thumbnail': thumbnail,
                'video_url': resolved_video,
                'engine': engine_name,
                'width': w,
                'height': h,
                'fps': fps,
                'duration': meta.get('duration') or 0,
                'codec': meta.get('codec') or '',
                'resolution_label': res_label,
                'formatted_size': best_vid.get('formattedSize', '')
            }
    return None

def try_douyin_cloud_engine(url: str, original_url: str = None, timeout: int = 10) -> dict:
    """
    Tier 1B: BTCH Douyin SnapCDN Engine (Porting dari WhatsBot douyinService.js).
    Mencoba backend2.tioo.eu.org & backend1.tioo.eu.org dengan header btch/3.3.4.
    Mendukung URL shortlink v.douyin.com maupun web note/video URL.
    """
    backends = [
        "https://backend2.tioo.eu.org/douyin",
        "https://backend1.tioo.eu.org/douyin"
    ]
    
    # Kumpulkan target URL: prioritaskan original_url (shortlink v.douyin.com)
    urls_to_try = []
    if original_url and original_url.strip():
        urls_to_try.append(original_url.strip())
    if url and url.strip() and url.strip() not in urls_to_try:
        urls_to_try.append(url.strip())

    clean_urls = []
    for u in urls_to_try:
        if u not in clean_urls:
            clean_urls.append(u)
        no_q = u.split('?')[0].strip()
        if no_q and no_q not in clean_urls:
            clean_urls.append(no_q)

    for api_base in backends:
        for target_u in clean_urls:
            try:
                r = requests.get(
                    f"{api_base}?url={target_u}",
                    headers={'User-Agent': 'btch/3.3.4'},
                    timeout=timeout
                )
                if r.status_code != 200:
                    continue
                res_json = r.json()
                data = res_json.get('data') or res_json.get('result', {})
                if not data:
                    continue

                raw_title = data.get('title') or ''
                is_synthetic = not raw_title or re.match(r'^Douyin Video\d*$', raw_title.strip(), re.I) or raw_title.strip() == 'Douyin Video'
                title = '' if is_synthetic else raw_title.strip()

                raw_author = data.get('author') or data.get('author_name') or data.get('nickname') or ''
                author = '' if str(raw_author).lower() in ('douyin user', 'douyinuser', 'user', 'none', '') else str(raw_author)
                thumbnail = html.unescape(data.get('thumbnail') or '')

                # Decode token links untuk deteksi akurat antara Slide Foto vs Video MP4
                raw_links = data.get('links', [])
                parsed_links = []
                for l in raw_links:
                    u = l.get('url', '')
                    if 'token=' in u:
                        try:
                            token_part = u.split('token=')[1].split('.')[1]
                            token_part = token_part.replace('-', '+').replace('_', '/')
                            token_part += '=' * (-len(token_part) % 4)
                            payload = json.loads(base64.b64decode(token_part).decode('utf-8'))
                            parsed_links.append({
                                'quality': l.get('quality'),
                                'url': u,
                                'direct_url': payload.get('url'),
                                'filename': payload.get('filename', '')
                            })
                            continue
                        except Exception:
                            pass
                    parsed_links.append({
                        'quality': l.get('quality'),
                        'url': u,
                        'direct_url': u,
                        'filename': ''
                    })

                image_links = [
                    l for l in parsed_links
                    if re.search(r'\.(jpe?g|png|webp)', l['filename'], re.I) or 'douyinpic.com' in (l.get('direct_url') or '')
                ]
                audio_links = [
                    l for l in parsed_links
                    if l['filename'].lower().endswith('.mp3') or 'douyinstatic.com' in (l.get('direct_url') or '')
                ]
                video_links = [
                    l for l in parsed_links
                    if l['filename'].lower().endswith('.mp4') or (l.get('direct_url') or '').endswith('.mp4') or (l.get('quality') and l not in image_links and l not in audio_links)
                ]

                if image_links:
                    # dl.snapcdn.app proxy link tidak terhalang 403 Forbidden
                    images = [l['url'] or l['direct_url'] for l in image_links]
                    audio_url = (audio_links[0]['url'] or audio_links[0]['direct_url']) if audio_links else None
                    return {
                        'is_slide': True,
                        'title': title,
                        'is_synthetic_title': is_synthetic,
                        'author': author,
                        'thumbnail': thumbnail or (images[0] if images else ''),
                        'images': images,
                        'audio_url': audio_url,
                        'engine': f"Douyin Cloud Slide ({len(images)} Foto)"
                    }

                if video_links:
                    best_v = None
                    for vl in video_links:
                        if '_hd.mp4' in vl['filename'] or (vl.get('quality') and 'Quality 2' in str(vl['quality'])):
                            best_v = vl
                            break
                    if not best_v and video_links:
                        best_v = video_links[0]
                    v_url = best_v.get('url') or best_v.get('direct_url')
                    return {
                        'isVideo': True,
                        'title': title,
                        'is_synthetic_title': is_synthetic,
                        'author': author,
                        'thumbnail': thumbnail,
                        'video_url': v_url,
                        'engine': "Douyin Cloud HD"
                    }
            except Exception:
                continue
    return None

def try_tikwm_douyin(url: str, timeout: int = 15) -> dict:
    """Tier 1C: TikWM Cloud API untuk Douyin."""
    try:
        resp = requests.post(
            'https://www.tikwm.com/api/',
            data={'url': url, 'hd': 1},
            headers=DEFAULT_HEADERS,
            timeout=timeout
        )
        if resp.status_code == 200:
            res_json = resp.json()
            data = res_json.get('data')
            if data:
                raw_title = data.get('title') or ''
                is_synthetic = not raw_title or re.match(r'^Douyin Video\d*$', raw_title.strip(), re.I)
                title = '' if is_synthetic else raw_title.strip()

                raw_author = data.get('author', {}).get('nickname') or ''
                author = '' if raw_author.lower() in ('douyin user', 'douyinuser', 'user', 'none', '') else raw_author
                thumbnail = data.get('cover') or data.get('origin_cover') or ''
                
                if data.get('images'):
                    return {
                        'is_slide': True,
                        'title': title,
                        'author': author,
                        'thumbnail': thumbnail,
                        'images': data['images'],
                        'audio_url': data.get('music'),
                        'engine': 'TikWM Douyin'
                    }
                v_url = data.get('hdplay') or data.get('play')
                if v_url:
                    return {
                        'isVideo': True,
                        'title': title,
                        'author': author,
                        'thumbnail': thumbnail,
                        'video_url': v_url,
                        'audio_url': data.get('music'),
                        'engine': 'TikWM Douyin'
                    }
    except Exception:
        pass
    return None

def try_aweme_api(url: str, timeout: int = 10) -> dict:
    """Tier 1D: Direct Aweme Item API resolver (Iesdouyin / Douyin Web)."""
    try:
        item_id_match = re.search(r'video/(\d+)', url) or re.search(r'modal_id=(\d+)', url) or re.search(r'note/(\d+)', url) or re.search(r'(\d{15,22})', url)
        if item_id_match:
            item_id = item_id_match.group(1)
            detail_res = requests.get(
                f"https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids={item_id}",
                headers={
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15',
                    'Referer': 'https://www.douyin.com/'
                },
                timeout=timeout
            )
            data = detail_res.json()
            item = data.get('item_list', [{}])[0]
            if item:
                title = item.get('desc') or ''
                raw_author = item.get('author', {}).get('nickname') or ''
                author = '' if raw_author.lower() in ('douyin user', 'douyinuser', 'user', 'none', '') else raw_author
                
                if item.get('images'):
                    img_list = []
                    for img in item['images']:
                        url_list = img.get('url_list', [])
                        if url_list:
                            img_list.append(url_list[0])
                    if img_list:
                        return {
                            'is_slide': True,
                            'title': title,
                            'author': author,
                            'images': img_list,
                            'engine': 'Aweme Direct API'
                        }
                        
                play_url = item.get('video', {}).get('play_addr', {}).get('url_list', [None])[0]
                if play_url:
                    clean_play_url = play_url.replace('playwm', 'play')
                    return {
                        'isVideo': True,
                        'title': title,
                        'author': author,
                        'video_url': clean_play_url,
                        'engine': 'Aweme Direct API'
                    }
    except Exception:
        pass
    return None

def get_douyin_info(url: str, share_text: str = None) -> dict:
    """Ekstraksi metadata Douyin secara cepat beserta probe resolusi/fps presisi."""
    text_to_extract = share_text or url
    clean_url, share_author, share_title = extract_douyin_share_info(text_to_extract)
    if not clean_url or not clean_url.startswith('http'):
        clean_url = url
    canonical = expand_douyin_url(clean_url or url)
    is_note_url = '/note/' in canonical or '/note/' in (clean_url or url)

    data = None
    cloud_data = None

    if is_note_url:
        # Note album slide tidak didukung SnapDouyin, langsung utamakan Cloud Engine
        cloud_data = try_douyin_cloud_engine(canonical, original_url=clean_url or url, timeout=10)
        data = cloud_data
    else:
        # 1. Coba SnapDouyin (UHD 4K/2K/1080p Engine)
        data = try_snapdouyin_engine(canonical, timeout=6)

        # 2. Coba Cloud Engine jika SnapDouyin gagal, judulnya terpotong (#hashtag pendek),
        # atau dimensi/resolusi video belum ada
        need_cloud = (
            not data
            or data.get('is_synthetic_title')
            or not data.get('title')
            or (data.get('title', '').startswith('#') and len(data.get('title', '')) < 15)
            or not data.get('width')
        )
        if need_cloud:
            cloud_data = try_douyin_cloud_engine(canonical, original_url=clean_url or url, timeout=10)
            if not data and cloud_data:
                data = cloud_data

    # 3. Fallback ke TikWM / Aweme
    if not data:
        data = try_tikwm_douyin(canonical) or try_aweme_api(canonical)

    if data:
        # Prioritaskan judul yang paling lengkap/panjang di antara semua kandidat
        candidates = [
            data.get('title', '') if not data.get('is_synthetic_title') else '',
            cloud_data.get('title', '') if cloud_data and not cloud_data.get('is_synthetic_title') else '',
            share_title
        ]
        valid_titles = [t.strip() for t in candidates if t and t.strip()]
        title = max(valid_titles, key=len) if valid_titles else ('Foto Slide Douyin' if data.get('is_slide') else 'Video Douyin')

        # Author / Creator
        author = data.get('author') or (cloud_data and cloud_data.get('author')) or share_author or ''
        if author.lower() in ('douyin user', 'douyinuser', 'user', 'none', 'douyin video', 'kreator douyin', 'akun douyin'):
            author = share_author or ''

        display_title = f"{author} - {title}" if author else title
        is_slide = data.get('is_slide', False) or (cloud_data and cloud_data.get('is_slide', False))
        images = (cloud_data and cloud_data.get('images')) or data.get('images', [])
        if not images and data.get('images'):
            images = data['images']

        slide_count = len(images) if is_slide else 0
        w = data.get('width') or (1080 if is_slide else None)
        h = data.get('height') or (1511 if is_slide else None)
        fps = data.get('fps')
        dur = data.get('duration') or 0
        codec = data.get('codec') or ''
        res_label = 'HD Slide' if is_slide else data.get('resolution_label')

        # Untuk video jika resolusi/durasi/fps belum ada, lakukan probing stream video
        if not is_slide and (not w or not dur or not fps):
            v_probe_url = (cloud_data and cloud_data.get('video_url')) or data.get('video_url')
            if v_probe_url:
                meta = probe_media_stream(v_probe_url, timeout=5)
                if meta:
                    w = meta.get('width') or w
                    h = meta.get('height') or h
                    fps = meta.get('fps') or fps
                    dur = meta.get('duration') or dur
                    codec = meta.get('codec') or codec
                    res_label = meta.get('resolution_label') or res_label

        dur_str = ""
        if is_slide:
            dur_str = f"{slide_count} Foto Slide"
        elif dur:
            m_tot, s_tot = divmod(int(dur), 60)
            h_tot, m_tot = divmod(m_tot, 60)
            dur_str = f"{h_tot}:{m_tot:02d}:{s_tot:02d}" if h_tot else f"{m_tot:02d}:{s_tot:02d}"

        raw_thumb = data.get('thumbnail') or (cloud_data and cloud_data.get('thumbnail')) or ''
        thumb_clean = html.unescape(raw_thumb) if raw_thumb else (images[0] if images else '')
        fmt_size = data.get('formatted_size') or (cloud_data and cloud_data.get('formatted_size'))

        return {
            'title': display_title,
            'clean_title': title,
            'description': title,
            'author': author,
            'thumbnail': thumb_clean,
            'is_slide': is_slide,
            'slide_count': slide_count,
            'has_audio': bool(data.get('audio_url') or (cloud_data and cloud_data.get('audio_url')) or data.get('video_url')),
            'platform': 'Douyin',
            'width': w,
            'height': h,
            'fps': fps,
            'duration': dur,
            'duration_string': dur_str,
            'codec': codec,
            'resolution_label': res_label,
            'formatted_size': fmt_size,
            'webpage_url': canonical,
            'url': canonical,
            'video_url': data.get('video_url') or (cloud_data and cloud_data.get('video_url'))
        }
    return None

def download_douyin(url: str, output_dir: str, ui_queue=None, options=None, abort_checker=None) -> bool:
    """Unduh media Douyin dengan arsitektur multi-tier anti-gagal."""
    if options is None:
        options = {}
    mode = options.get('mode', 'video_audio')
    audio_format = options.get('audio_format', 'mp3')
    share_text = options.get('share_text')

    if ui_queue:
        ui_queue.put({"type": "log", "text": "[TIER 1] Menghubungkan ke Engine Douyin (SnapDouyin / Cloud / TikWM)...\n"})

    text_to_extract = share_text or url
    clean_url, share_author, share_title = extract_douyin_share_info(text_to_extract)
    if not clean_url or not clean_url.startswith('http'):
        clean_url = url
    canonical = expand_douyin_url(clean_url or url)
    is_note_url = '/note/' in canonical or '/note/' in (clean_url or url)
    
    data = None
    cloud_data = None
    if is_note_url:
        cloud_data = try_douyin_cloud_engine(canonical, original_url=clean_url or url, timeout=10)
        data = cloud_data
    else:
        # 1. Coba SnapDouyin (UHD 4K/2K/1080p) & Cloud Engine
        try:
            data = try_snapdouyin_engine(canonical, timeout=6)
        except Exception:
            pass

        need_cloud = (
            not data 
            or data.get('is_synthetic_title') 
            or not data.get('title') 
            or (data.get('title', '').startswith('#') and len(data.get('title', '')) < 15)
        )
        if need_cloud:
            cloud_data = try_douyin_cloud_engine(canonical, original_url=clean_url or url, timeout=10)
            if not data and cloud_data:
                data = cloud_data
        
    # 2. Coba TikWM
    if not data:
        data = try_tikwm_douyin(canonical)
        
    # 3. Coba Aweme API
    if not data:
        data = try_aweme_api(canonical)

    if not data:
        if ui_queue:
            ui_queue.put({"type": "log", "text": "[TIER 1] Semua sub-engine Douyin tidak merespons. Beralih ke Tier 2 (yt-dlp)...\n"})
        return False

    engine_name = data.get('engine', 'Douyin Engine')
    if ui_queue:
        ui_queue.put({"type": "log", "text": f"[TIER 1] Berhasil mendapatkan stream via {engine_name}!\n"})

    # Tentukan judul asli & nama author
    candidates = [
        data.get('title', '') if not data.get('is_synthetic_title') else '',
        cloud_data.get('title', '') if cloud_data and not cloud_data.get('is_synthetic_title') else '',
        share_title
    ]
    valid_titles = [t.strip() for t in candidates if t and t.strip()]
    raw_title = max(valid_titles, key=len) if valid_titles else ('Foto Slide Douyin' if data.get('is_slide') else 'Video Douyin')

    raw_author = data.get('author') or (cloud_data and cloud_data.get('author')) or share_author or ''
    author = '' if raw_author.lower() in ('douyin user', 'douyinuser', 'user', 'none', 'douyin video') else raw_author

    # Penamaan folder & file: jangan pernah menambahkan 'Douyin User' jika author tidak ada!
    base_name = sanitize_filename(f"{author} - {raw_title}" if author else raw_title)

    # A. Kasus Slide Foto
    is_slide = data.get('is_slide', False) or (cloud_data and cloud_data.get('is_slide', False))
    if is_slide:
        images = (cloud_data and cloud_data.get('images')) or data.get('images', [])
        if not images and data.get('images'):
            images = data['images']
            
        slide_folder = os.path.join(output_dir, f"{base_name} [Douyin Slide]")
        os.makedirs(slide_folder, exist_ok=True)

        total_img = len(images)
        downloaded_count = 0
        for i, img_url in enumerate(images, 1):
            if abort_checker and abort_checker():
                return False
            img_path = os.path.join(slide_folder, f"foto_{i:02d}.jpg")
            label = f"Slide {i}/{total_img}"
            
            dl_ok = stream_download_file(img_url, img_path, ui_queue, abort_checker, label=label)
            if dl_ok and os.path.exists(img_path) and os.path.getsize(img_path) > 100:
                normalize_image_to_jpeg(img_path)
                downloaded_count += 1
            else:
                if ui_queue:
                    ui_queue.put({"type": "log", "text": f"[PERINGATAN] Gagal mengunduh {label} dari mirror.\n"})

        if downloaded_count == 0:
            if ui_queue:
                ui_queue.put({"type": "log", "text": "[TIER 1] Gagal mengunduh file gambar slide Douyin. Beralih ke Tier 2...\n"})
            return False

        # Unduh file musik / video slideshow jika ada
        audio_url = (cloud_data and cloud_data.get('audio_url')) or data.get('audio_url')
        if audio_url:
            stream_download_file(audio_url, os.path.join(slide_folder, "music.mp3"), ui_queue, abort_checker, label="Musik BGM")
        elif data.get('video_url'):
            vid_temp = os.path.join(slide_folder, "slideshow_raw.mp4")
            vid_final = os.path.join(slide_folder, "video_slideshow.mp4")
            if stream_download_file(data['video_url'], vid_temp, ui_queue, abort_checker, label="Video Slideshow"):
                fast_remux_mp4(vid_temp, vid_final)
                extract_audio_from_video(vid_final, os.path.join(slide_folder, "music.mp3"), "mp3")

        if ui_queue:
            ui_queue.put({"type": "log", "text": f"\n--- UNDUHAN SUKSES ({engine_name}) ---\nFolder: {slide_folder}\nBerhasil mengunduh {downloaded_count} foto HD!\n"})
            ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
        return True

    # B. Kasus Video
    video_url = data.get('video_url') or (cloud_data and cloud_data.get('video_url'))
    if video_url:
        raw_container = options.get('container', 'auto') if options else 'auto'
        container = 'mp4' if raw_container in ('auto', 'best', '', None) else str(raw_container).lower()
        ext = f".{container}"
        raw_video_path = os.path.join(output_dir, f"{base_name}_raw.mp4")
        final_video_path = os.path.join(output_dir, f"{base_name}{ext}")

        success = stream_download_file(
            video_url, raw_video_path, ui_queue, abort_checker,
            label=f"Unduh Douyin ({engine_name})"
        )
        if not success:
            return False

        if mode == 'audio_only':
            final_audio_path = os.path.join(output_dir, f"{base_name}.{audio_format}")
            extract_audio_from_video(raw_video_path, final_audio_path, audio_format)
            if os.path.exists(raw_video_path):
                try: os.remove(raw_video_path)
                except Exception: pass
            saved_path = final_audio_path
        else:
            postprocess_video(raw_video_path, final_video_path, options, ui_queue, abort_checker)
            saved_path = final_video_path

        embed_thumb = options.get('embed_thumb', True) if options else True
        thumb_url = data.get('cover') or (cloud_data and cloud_data.get('cover')) or data.get('dynamic_cover') or data.get('origin_cover')
        if embed_thumb and thumb_url and saved_path and os.path.exists(saved_path):
            embed_thumbnail_to_media(saved_path, thumb_url, ui_queue, abort_checker)

        if ui_queue:
            ui_queue.put({"type": "log", "text": f"\n--- UNDUHAN SUKSES ({engine_name}) ---\nFile tersimpan di: {saved_path}\n"})
            ui_queue.put({"type": "progress", "value": 1.0, "text": "Progress: Selesai"})
        return True

    return False
