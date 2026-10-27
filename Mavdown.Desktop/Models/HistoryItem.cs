using System;
using System.IO;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace Mavdown.Desktop.Models
{
    public class HistoryItem
    {
        public string Id { get; set; } = "";
        public string Title { get; set; } = "Media";
        public string Platform { get; set; } = "Web";
        public string Author { get; set; } = "";
        public string Resolution { get; set; } = "";
        public string MediaFormat { get; set; } = "";
        public string FilePath { get; set; } = "";
        public string FileSize { get; set; } = "";
        public string Thumbnail { get; set; } = "";
        public string LocalThumbnail { get; set; } = "";
        public bool IsSlide { get; set; }
        public int SlideCount { get; set; }
        public string Duration { get; set; } = "";
        public string Codec { get; set; } = "";
        public string Fps { get; set; } = "";
        public string SourceUrl { get; set; } = "";
        public string Timestamp { get; set; } = "";

        public string PlayButtonLabel => (IsSlide || MediaFormat == "SLIDE" || MediaFormat == "PNG" || MediaFormat == "JPG") ? "Buka" : "Putar";

        public string DisplayDuration
        {
            get
            {
                if (IsSlide || MediaFormat == "SLIDE")
                    return SlideCount > 1 ? $"{SlideCount} Foto" : "1 Foto HD";

                if (string.IsNullOrWhiteSpace(Duration)) return "";
                string d = Duration.Trim();
                if (double.TryParse(d, System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out double sec))
                {
                    int totalSec = (int)Math.Round(sec);
                    int m = totalSec / 60;
                    int s = totalSec % 60;
                    int h = m / 60;
                    m %= 60;
                    return h > 0 ? $"{h}:{m:D2}:{s:D2}" : $"{m}:{s:D2}";
                }
                return d;
            }
        }

        public bool HasDuration => !string.IsNullOrWhiteSpace(DisplayDuration);
        public bool HasCodec => !string.IsNullOrWhiteSpace(Codec);
        public bool HasFps => !string.IsNullOrWhiteSpace(Fps);
        public bool HasResolution => !string.IsNullOrWhiteSpace(Resolution);
        public bool HasAuthor => !string.IsNullOrWhiteSpace(Author);
        public bool HasFileSize => !string.IsNullOrWhiteSpace(FileSize);
        public bool HasSourceUrl => !string.IsNullOrWhiteSpace(SourceUrl);
        public bool HasMediaFormat => !string.IsNullOrWhiteSpace(MediaFormat);

        public bool FileExists
        {
            get
            {
                if (string.IsNullOrWhiteSpace(FilePath)) return false;
                try
                {
                    return File.Exists(FilePath) || Directory.Exists(FilePath);
                }
                catch
                {
                    return false;
                }
            }
        }

        public string PlatformBadgeText => string.IsNullOrWhiteSpace(Platform) ? "WEB" : Platform.ToUpper();

        public Brush PlatformColorBrush => new SolidColorBrush(GetPlatformColor(Platform));
        public Brush PlatformBgBrush
        {
            get
            {
                var c = GetPlatformColor(Platform);
                return new SolidColorBrush(Color.FromArgb(40, c.R, c.G, c.B));
            }
        }
        public Brush PlatformBorderBrush
        {
            get
            {
                var c = GetPlatformColor(Platform);
                return new SolidColorBrush(Color.FromArgb(140, c.R, c.G, c.B));
            }
        }

        private static Color GetPlatformColor(string plat)
        {
            string p = plat.ToLowerInvariant();
            if (p.Contains("youtube")) return Color.FromRgb(239, 68, 68);    // #EF4444 Red
            if (p.Contains("tiktok")) return Color.FromRgb(6, 182, 212);     // #06B6D4 Cyan
            if (p.Contains("douyin")) return Color.FromRgb(254, 44, 85);     // #FE2C55 Pink/Red
            if (p.Contains("instagram")) return Color.FromRgb(225, 48, 108);  // #E1306C Magenta
            if (p.Contains("twitter") || p.Contains(" x")) return Color.FromRgb(56, 189, 248); // #38BDF8 Sky Blue
            if (p.Contains("bilibili")) return Color.FromRgb(0, 161, 214);   // #00A1D6 Bilibili Blue
            if (p.Contains("pixiv")) return Color.FromRgb(0, 150, 250);      // #0096FA Pixiv Blue
            if (p.Contains("facebook")) return Color.FromRgb(24, 119, 242);  // #1877F2 Facebook Blue
            if (p.Contains("pinterest")) return Color.FromRgb(230, 0, 35);   // #E60023 Pinterest Red
            return Color.FromRgb(99, 102, 241);                             // #6366F1 Indigo Accent
        }

        private BitmapImage? _thumbnailImage;
        private bool _thumbnailLoaded;

        public BitmapImage? ThumbnailImage
        {
            get
            {
                if (_thumbnailLoaded) return _thumbnailImage;

                // 1. Coba muat dari file thumbnail lokal menggunakan FileStream yang aman dan bebas lock
                try
                {
                    if (!string.IsNullOrEmpty(LocalThumbnail) && File.Exists(LocalThumbnail))
                    {
                        using (var fs = new FileStream(LocalThumbnail, FileMode.Open, FileAccess.Read, FileShare.Read))
                        {
                            var bmp = new BitmapImage();
                            bmp.BeginInit();
                            bmp.CacheOption = BitmapCacheOption.OnLoad;
                            bmp.DecodePixelWidth = 240;
                            bmp.StreamSource = fs;
                            bmp.EndInit();
                            bmp.Freeze();
                            _thumbnailImage = bmp;
                            _thumbnailLoaded = true;
                            return _thumbnailImage;
                        }
                    }
                }
                catch { }

                // 2. Fallback: Muat dari URL web thumbnail jika tersedia
                try
                {
                    if (!string.IsNullOrEmpty(Thumbnail) && (Thumbnail.StartsWith("http://", StringComparison.OrdinalIgnoreCase) || Thumbnail.StartsWith("https://", StringComparison.OrdinalIgnoreCase)))
                    {
                        var bmp = new BitmapImage();
                        bmp.BeginInit();
                        bmp.CacheOption = BitmapCacheOption.OnLoad;
                        bmp.DecodePixelWidth = 240;
                        bmp.UriSource = new Uri(Thumbnail);
                        bmp.EndInit();
                        bmp.Freeze();
                        _thumbnailImage = bmp;
                        _thumbnailLoaded = true;
                        return _thumbnailImage;
                    }
                }
                catch { }

                // Jika belum berhasil dimuat (misal file thumbnail sedang dibuat di background), jangan set _thumbnailLoaded
                return null;
            }
        }
    }
}
