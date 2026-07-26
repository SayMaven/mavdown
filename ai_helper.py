"""
ai_helper.py — Integrasi Gemini AI untuk Maven Downloader
Menggunakan google-genai (Official Google AI Python SDK)

Fitur:
  1. analyze_download_error   — Analisis error yt-dlp dan beri solusi bahasa Indonesia
  2. clean_media_metadata     — Ekstrak metadata ID3 bersih dari judul video
  3. recommend_download_settings — Rekomendasikan pengaturan unduhan terbaik
  4. test_api_connection      — Validasi API key
"""
import json
import threading


def _get_client(api_key: str):
    """Buat Gemini client dengan API key yang diberikan."""
    from google import genai
    return genai.Client(api_key=api_key)


# ---------------------------------------------------------------------------
# 1. AI Error Analyzer
# ---------------------------------------------------------------------------
def analyze_download_error(log_text: str, api_key: str, callback):
    """
    Analisis log error yt-dlp dan kembalikan penjelasan ramah + solusi.
    Berjalan di background thread, memanggil callback(result_str) saat selesai.
    """
    def _run():
        try:
            client = _get_client(api_key)
            prompt = f"""Kamu adalah asisten troubleshooter ahli untuk aplikasi Maven Downloader yang menggunakan yt-dlp.
Berikut adalah log error dari yt-dlp:

---
{log_text[-4000:]}
---

Analisis error di atas dan berikan respons dengan format PERSIS ini (tanpa markdown heading, langsung isinya):

❌ MASALAH:
[penjelasan singkat masalah, 1-2 kalimat, bahasa Indonesia yang mudah dipahami pengguna awam]

💡 SOLUSI:
1. [langkah pertama yang konkret]
2. [langkah kedua jika ada]
3. [langkah ketiga jika ada]

🔧 TIPS TEKNIS (jika relevan):
[argumen yt-dlp atau informasi teknis tambahan yang berguna]

Gunakan bahasa Indonesia yang ramah. Jika error tidak bisa diidentifikasi dengan jelas, sarankan pengguna untuk memeriksa koneksi internet atau memperbarui yt-dlp."""

            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            callback(response.text.strip())
        except Exception as e:
            callback(
                f"❌ MASALAH:\nGagal menghubungi Gemini AI.\n\n"
                f"💡 SOLUSI:\n1. Periksa API Key di ⚙️ Pengaturan\n"
                f"2. Pastikan koneksi internet aktif\n\n"
                f"🔧 DETAIL ERROR:\n{str(e)}"
            )

    threading.Thread(target=_run, daemon=True).start()


# ---------------------------------------------------------------------------
# 2. AI Metadata Cleaner
# ---------------------------------------------------------------------------
def clean_media_metadata(title: str, uploader: str, api_key: str, callback):
    """
    Ekstrak metadata ID3 yang bersih dari judul video yang berantakan.
    Memanggil callback(dict) dengan keys: artist, song_title, genre, year, album, confidence
    Atau: {"not_music": True, "reason": "..."} jika bukan video musik
    Atau: {"error": "..."} jika gagal
    """
    def _run():
        try:
            client = _get_client(api_key)
            prompt = f"""Kamu adalah sistem ekstraksi metadata musik otomatis yang sangat akurat.
Dari informasi video berikut, ekstrak metadata yang bersih untuk tag ID3 file audio.

Judul Video  : "{title}"
Nama Channel : "{uploader}"

INSTRUKSI:
- Jika ini video musik, kembalikan HANYA JSON valid berikut (tidak ada teks lain apapun):
{{
  "artist": "Nama Artis yang tepat",
  "song_title": "Judul lagu bersih tanpa kata-kata seperti MV, Official, HD, 4K, dll",
  "album": "Nama Album jika bisa diketahui dari konteks, atau string kosong",
  "genre": "Genre utama (contoh: Pop, K-Pop, R&B, Rock, Hip-Hop, Electronic, Classical, dll)",
  "year": "Tahun rilis jika ada dalam judul atau bisa diperkirakan, atau string kosong",
  "confidence": "high, medium, atau low — seberapa yakin kamu dengan hasil ini"
}}

- Jika ini BUKAN video musik (tutorial, vlog, podcast, film, gaming, news, dsb.), kembalikan HANYA:
{{"not_music": true, "reason": "Alasan singkat dalam bahasa Indonesia"}}

Kembalikan JSON saja, tidak ada penjelasan tambahan."""

            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )

            text = response.text.strip()
            # Bersihkan markdown code block jika ada
            if "```" in text:
                parts = text.split("```")
                for part in parts:
                    part = part.strip()
                    if part.startswith("json"):
                        part = part[4:].strip()
                    if part.startswith("{"):
                        text = part
                        break

            result = json.loads(text.strip())
            callback(result)
        except json.JSONDecodeError:
            callback({"error": "Respons AI tidak dapat diparse. Coba lagi."})
        except Exception as e:
            callback({"error": f"Gagal menghubungi AI: {str(e)}"})

    threading.Thread(target=_run, daemon=True).start()


# ---------------------------------------------------------------------------
# 3. AI Smart Settings Recommender
# ---------------------------------------------------------------------------
def recommend_download_settings(video_info: dict, api_key: str, callback):
    """
    Rekomendasikan pengaturan unduhan optimal berdasarkan metadata video.
    Memanggil callback(dict) dengan recommended settings.
    """
    def _run():
        try:
            client = _get_client(api_key)

            title = video_info.get('title', 'Unknown')
            duration = video_info.get('duration', 0)
            duration_str = video_info.get('duration_string', f"{int(duration//60)}:{int(duration%60):02d}" if duration else "N/A")
            categories = video_info.get('categories', [])
            tags = video_info.get('tags', [])[:8]
            formats = video_info.get('formats', [])
            uploader = video_info.get('uploader', video_info.get('channel', ''))

            # Deteksi resolusi tertinggi tersedia
            heights = sorted(set(
                f.get('height', 0) for f in formats if f.get('height')
            ), reverse=True)
            max_height = heights[0] if heights else 0

            # Deteksi FPS
            fps_list = [f.get('fps', 0) for f in formats if f.get('fps')]
            has_60fps = any(f >= 59 for f in fps_list)

            # Deteksi HDR
            has_hdr = any(
                str(f.get('dynamic_range', '')).upper() in ('HDR', 'HDR10', 'HDR10+', 'DOVI', 'HLG')
                for f in formats
            )

            prompt = f"""Kamu adalah asisten rekomendasi pengaturan unduhan video yang sangat membantu.

Analisis informasi video berikut dan rekomendasikan pengaturan unduhan terbaik untuk pengguna umum:

Judul     : "{title}"
Channel   : "{uploader}"
Durasi    : {duration_str}
Kategori  : {', '.join(categories) if categories else 'Tidak tersedia'}
Tag       : {', '.join(tags) if tags else 'Tidak tersedia'}
Resolusi tersedia: {heights[:6]} (pixel height, tertinggi ke terendah)
60 FPS tersedia  : {'Ya' if has_60fps else 'Tidak'}
HDR tersedia     : {'Ya' if has_hdr else 'Tidak'}

PILIHAN YANG TERSEDIA DI APLIKASI:
- Mode       : "video_audio" atau "audio_only"
- Container  : mp4, mkv, webm, mov, avi
- Audio Format (jika audio_only): mp3, m4a, flac, wav, opus
- Resolusi   : best, 2160, 1440, 1080, 720, 480, 360
- Video Codec: best, h264, vp9, av1
- Audio Codec: best, m4a, opus
- Embed Thumb: true atau false

PANDUAN REKOMENDASI:
- Video musik → pertimbangkan audio_only dengan mp3/m4a
- Video panjang (>30 menit) → 1080p H.264 MP4 untuk kompatibilitas
- Video singkat berkualitas tinggi → bisa sarankan best/4K
- Podcast/audio lecture → audio_only m4a atau opus
- Tutorial/gaming → 1080p atau 720p MP4
- Selalu embed thumbnail untuk semua mode

Kembalikan HANYA JSON valid (tidak ada teks lain):
{{
  "mode": "video_audio atau audio_only",
  "container": "format container terbaik",
  "audio_format": "format audio jika audio_only, atau string kosong",
  "resolution": "nilai resolusi (best/2160/1440/1080/720/480/360)",
  "video_codec": "best/h264/vp9/av1",
  "audio_codec": "best/m4a/opus",
  "embed_thumb": true atau false,
  "reasoning": "Penjelasan singkat 1-2 kalimat DALAM BAHASA INDONESIA mengapa settings ini direkomendasikan"
}}"""

            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )

            text = response.text.strip()
            if "```" in text:
                parts = text.split("```")
                for part in parts:
                    part = part.strip()
                    if part.startswith("json"):
                        part = part[4:].strip()
                    if part.startswith("{"):
                        text = part
                        break

            result = json.loads(text.strip())
            callback(result)
        except json.JSONDecodeError:
            callback({"error": "Respons AI tidak dapat diparse. Coba lagi."})
        except Exception as e:
            callback({"error": f"Gagal menghubungi AI: {str(e)}"})

    threading.Thread(target=_run, daemon=True).start()


# ---------------------------------------------------------------------------
# 4. API Key Test
# ---------------------------------------------------------------------------
def test_api_connection(api_key: str, callback):
    """
    Validasi API key dengan request sederhana.
    Memanggil callback(success: bool, message: str) saat selesai.
    """
    def _run():
        if not api_key or not api_key.strip():
            callback(False, "❌ API Key tidak boleh kosong.")
            return
        try:
            client = _get_client(api_key.strip())
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents='Reply with exactly: CONNECTED',
            )
            if response.text and "CONNECTED" in response.text.upper():
                callback(True, "✅ Koneksi berhasil! Gemini AI siap digunakan.")
            else:
                callback(True, "✅ Koneksi berhasil! (Respons: " + response.text[:50] + ")")
        except Exception as e:
            err = str(e)
            if "API_KEY_INVALID" in err or "invalid" in err.lower():
                callback(False, "❌ API Key tidak valid. Periksa kembali key Anda.")
            elif "quota" in err.lower():
                callback(False, "❌ Kuota API habis. Cek dashboard Google AI Studio.")
            else:
                callback(False, f"❌ Koneksi gagal: {err[:120]}")

    threading.Thread(target=_run, daemon=True).start()
