import os
import time
import unittest
import tempfile
import json
import shutil

import config
import history
from history import add_history_entry, get_history_entries, delete_history_entry, clear_all_history
from engines.router import detect_platform, get_service_folder_name, resolve_service_output_dir
from engines.base import sanitize_filename, format_bytes, format_time, cleanup_orphaned_temp_files
from engines.douyin import extract_douyin_share_info

class TestMavdownCore(unittest.TestCase):

    def test_platform_detection(self):
        """Uji presisi deteksi platform dari berbagai pola URL."""
        test_cases = [
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"),
            ("https://youtu.be/dQw4w9WgXcQ", "youtube"),
            ("https://archive.org/details/example", "generic"),
            ("https://www.tiktok.com/@user/video/1234567890", "tiktok"),
            ("https://v.douyin.com/ZPYCy6v_QUs/", "douyin"),
            ("https://www.douyin.com/video/71234567890", "douyin"),
            ("https://twitter.com/user/status/123456789", "twitter"),
            ("https://x.com/user/status/123456789", "twitter"),
            ("https://www.instagram.com/reel/C-xyz123/", "instagram"),
            ("https://www.instagram.com/p/C-xyz123/", "instagram"),
            ("https://pin.it/abcXYZ123", "pinterest"),
            ("https://www.pinterest.com/pin/123456789/", "pinterest"),
            ("https://www.bilibili.com/video/BV1xx411c7mD", "bilibili"),
            ("https://b23.tv/xyz123", "bilibili"),
            ("https://www.facebook.com/reel/123456789", "facebook"),
            ("https://fb.watch/xyz123", "facebook")
        ]
        for url, expected in test_cases:
            self.assertEqual(detect_platform(url), expected, f"Failed for {url}")

    def test_service_folder_mapping(self):
        """Uji pemetaan nama folder layanan standar Mavdown_<Platform>."""
        mapping = {
            "youtube": "Mavdown_YouTube",
            "douyin": "Mavdown_Douyin",
            "tiktok": "Mavdown_TikTok",
            "instagram": "Mavdown_Instagram",
            "twitter": "Mavdown_Twitter",
            "x": "Mavdown_Twitter",
            "pinterest": "Mavdown_Pinterest",
            "facebook": "Mavdown_Facebook",
            "bilibili": "Mavdown_Bilibili",
            "generic": "Mavdown_Web",
            "web": "Mavdown_Web",
        }
        for plat, expected in mapping.items():
            self.assertEqual(get_service_folder_name(plat), expected)

    def test_resolve_service_output_dir(self):
        """Uji pembuatan direktori output layanan dan pencegahan duplikasi nesting."""
        temp_dir = tempfile.mkdtemp()
        try:
            # 1. URL YouTube -> Mavdown_YouTube
            yt_out = resolve_service_output_dir(temp_dir, "https://www.youtube.com/watch?v=123", organize_by_platform=True)
            self.assertEqual(os.path.basename(yt_out), "Mavdown_YouTube")
            self.assertTrue(os.path.isdir(yt_out))

            # 2. URL Douyin -> Mavdown_Douyin
            dy_out = resolve_service_output_dir(temp_dir, "https://v.douyin.com/123/", organize_by_platform=True)
            self.assertEqual(os.path.basename(dy_out), "Mavdown_Douyin")

            # 3. Pencegahan duplikasi jika path dasar sudah berupa folder platform
            nested_check = resolve_service_output_dir(yt_out, "https://www.youtube.com/watch?v=456", organize_by_platform=True)
            self.assertEqual(nested_check, yt_out)

            # 4. Jika organize_by_platform False, kembalikan base_dir langsung
            flat_out = resolve_service_output_dir(temp_dir, "https://www.youtube.com/watch?v=123", organize_by_platform=False)
            self.assertEqual(flat_out, temp_dir)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_sanitize_filename(self):
        """Uji sanitasi karakter terlarang Windows."""
        raw = 'Video: Test / Sample * 4K ? <Super> | Cool'
        clean = sanitize_filename(raw)
        for bad_char in [':', '/', '*', '?', '<', '>', '|']:
            self.assertNotIn(bad_char, clean)
        self.assertTrue(len(clean) <= 120)

    def test_format_helpers(self):
        """Uji format bytes dan waktu."""
        self.assertEqual(format_bytes(1024), "1.00KiB")
        self.assertEqual(format_bytes(1048576), "1.00MiB")
        self.assertEqual(format_bytes(1073741824), "1.00GiB")
        self.assertEqual(format_time(65), "01:05")
        self.assertEqual(format_time(3665), "01:01:05")

    def test_douyin_share_extraction(self):
        """Uji pembersihan token acak share text Douyin."""
        share_raw = "9.23 gOx:/ :1pm r@e.oD 05/10 长大真好 可以让小时候梦想中的房子具像化 # 梦中情屋 https://v.douyin.com/ZPYCy6v_QUs/ 复制此链接，打开Douyin搜索，直接观看视频！"
        clean_url, author, title_cand = extract_douyin_share_info(share_raw)
        self.assertTrue(clean_url.startswith("https://v.douyin.com/"))
        self.assertNotIn("9.23", title_cand)
        self.assertTrue("长大真好" in title_cand)

    def test_config_user_data_paths(self):
        """Uji path user data dan isolasi direktori."""
        self.assertTrue(os.path.isdir(config.USER_DATA_DIR))
        self.assertTrue(os.path.isdir(config.DEFAULT_OUTPUT_DIR))
        self.assertTrue(os.path.isabs(config.CONFIG_FILE))

    def test_download_history(self):
        """Uji CRUD riwayat unduhan dengan isolated temporary history file."""
        import history
        temp_dir = tempfile.mkdtemp()
        orig_history_file = history.HISTORY_FILE
        try:
            history.HISTORY_FILE = os.path.join(temp_dir, "test_history.json")
            clear_all_history()
            self.assertEqual(len(get_history_entries()), 0)

            entry1 = add_history_entry(
                title="Video Test TikTok",
                platform="TikTok",
                file_path="C:\\Downloads\\video1.mp4",
                file_size="15.2 MB",
                duration="00:45"
            )
            self.assertEqual(len(get_history_entries()), 1)
            self.assertEqual(get_history_entries()[0]["title"], "Video Test TikTok")

            # Uji pencarian
            self.assertEqual(len(get_history_entries(search="tiktok")), 1)
            self.assertEqual(len(get_history_entries(search="youtube")), 0)

            # Uji hapus per-item
            delete_history_entry(entry1["id"])
            self.assertEqual(len(get_history_entries()), 0)
        finally:
            history.HISTORY_FILE = orig_history_file
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_cleanup_orphaned_temp_files(self):
        """Uji pembersihan file sementara."""
        temp_dir = tempfile.mkdtemp()
        try:
            # Buat file temp buatan
            tmp_file = os.path.join(temp_dir, "test.mp4.tmp")
            with open(tmp_file, "w") as f:
                f.write("dummy")

            # Set mtime ke masa lalu agar terjamin kadaluarsa di semua filesystem
            old_time = time.time() - 60
            os.utime(tmp_file, (old_time, old_time))

            # max_age_seconds=0 agar langsung dibersihkan
            cleaned = cleanup_orphaned_temp_files(temp_dir, max_age_seconds=0)
            self.assertEqual(cleaned, 1)
            self.assertFalse(os.path.exists(tmp_file))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == '__main__':
    unittest.main()
