using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Diagnostics;
using System.IO;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using System.Windows.Media.Animation;
using Microsoft.Win32;
using Mavdown.Desktop.Models;
using Mavdown.Desktop.Services;

namespace Mavdown.Desktop
{
    public partial class MainWindow : Window
    {
        private readonly PythonBridge _bridge;
        private string _lastShareText = "";
        private string _outputFolder = "";

        private bool _isCurrentSlide = false;
        private bool _isCurrentUgoira = false;
        private int _currentSlideCount = 0;
        private int _currentWidth = 0;
        private int _currentHeight = 0;
        private bool _currentHasAudio = false;

        private readonly ObservableCollection<QueueItem> _queueItems = new();
        private bool _isQueueRunning = false;

        // Clipboard auto-monitor
        private DispatcherTimer? _clipboardTimer;
        private string _lastClipboardUrl = "";
        private bool _isClipboardMonitorEnabled = false;
        private bool _isApplyingConfig = false;
        private DispatcherTimer? _toastTimer;

        // Pixiv session mask
        private bool _isPixivMasked = true;
        private string _rawPixivSession = "";

        // Platform detection patterns (ui/constants.py)
        private readonly List<(string pattern, string name, string colorHex)> _platformPatterns = new()
        {
            (@"youtu\.be|youtube\.com", "YOUTUBE", "#FF4444"),
            (@"tiktok\.com", "TIKTOK", "#00F2FE"),
            (@"douyin\.com|iesdouyin\.com", "DOUYIN", "#FE2C55"),
            (@"instagram\.com", "INSTAGRAM", "#E1306C"),
            (@"twitter\.com|x\.com", "TWITTER / X", "#1D9BF0"),
            (@"facebook\.com|fb\.watch|fb\.me", "FACEBOOK", "#1877F2"),
            (@"pinterest\.com|pin\.it", "PINTEREST", "#E60023"),
            (@"bilibili\.com|b23\.tv", "BILIBILI", "#00A1D6"),
            (@"pixiv\.net|pixiv\.me", "PIXIV", "#0096FA"),
            (@"soundcloud\.com", "SOUNDCLOUD", "#FF7700"),
            (@"vimeo\.com", "VIMEO", "#1AB7EA"),
            (@"twitch\.tv", "TWITCH", "#9146FF"),
            (@"reddit\.com", "REDDIT", "#FF4500")
        };

        public MainWindow()
        {
            InitializeComponent();

            QueueListBox.ItemsSource = _queueItems;

            string appDir = AppDomain.CurrentDomain.BaseDirectory;
            string rootDir = appDir;

            while (!File.Exists(Path.Combine(rootDir, "mav_core.py")) && 
                   !File.Exists(Path.Combine(rootDir, "mav_core.exe")) && 
                   Directory.GetParent(rootDir) != null)
            {
                rootDir = Directory.GetParent(rootDir)!.FullName;
            }

            _outputFolder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads", "Mavdown");
            SidebarPathText.Text = _outputFolder;

            // Inisialisasi Logo Waifu
            LoadAppLogo(rootDir);

            // Mulai komunikasi IPC Python Bridge
            _bridge = new PythonBridge(rootDir);
            WireBridgeEvents();
            _bridge.Start();

            // Pemantau Papan Klip Otomatis
            _clipboardTimer = new DispatcherTimer
            {
                Interval = TimeSpan.FromMilliseconds(800)
            };
            _clipboardTimer.Tick += OnClipboardTimerTick;

            // Muat konfigurasi lokal secara instan (0ms delay) agar auto-clipboard & preferensi langsung aktif
            LoadInitialLocalConfig();

            Closing += (s, e) =>
            {
                _clipboardTimer?.Stop();
                _bridge.Dispose();
            };
        }

        private void LoadAppLogo(string rootDir)
        {
            try
            {
                string iconPath = Path.Combine(rootDir, "assets", "waifu_icon.png");
                if (!File.Exists(iconPath))
                {
                    iconPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "assets", "waifu_icon.png");
                }
                if (File.Exists(iconPath))
                {
                    var bmp = new BitmapImage();
                    bmp.BeginInit();
                    bmp.CacheOption = BitmapCacheOption.OnLoad;
                    bmp.UriSource = new Uri(Path.GetFullPath(iconPath));
                    bmp.EndInit();
                    bmp.Freeze();
                    AppLogoImage.Source = bmp;
                    if (SettingsLogoImage != null)
                    {
                        SettingsLogoImage.Source = bmp;
                    }
                }
            }
            catch { }
        }

        #region Safe JSON Parsers
        private static string SafeGetString(JsonObject obj, string key, string fallback = "")
        {
            if (obj.TryGetPropertyValue(key, out var node) && node != null)
                return node.ToString();
            return fallback;
        }

        private static long SafeGetLong(JsonObject obj, string key, long fallback = 0)
        {
            if (obj.TryGetPropertyValue(key, out var node) && node != null)
            {
                if (node is JsonValue val && val.TryGetValue<long>(out var l))
                    return l;
                if (long.TryParse(node.ToString(), out var parsed))
                    return parsed;
            }
            return fallback;
        }

        private static int SafeGetInt(JsonObject obj, string key, int fallback = 0)
        {
            if (obj.TryGetPropertyValue(key, out var node) && node != null)
            {
                if (node is JsonValue val && val.TryGetValue<int>(out var i))
                    return i;
                if (int.TryParse(node.ToString(), out var parsed))
                    return parsed;
            }
            return fallback;
        }

        private static bool SafeGetBool(JsonObject obj, string key, bool fallback = false)
        {
            if (obj.TryGetPropertyValue(key, out var node) && node != null)
            {
                if (node is JsonValue val && val.TryGetValue<bool>(out var b))
                    return b;
                if (bool.TryParse(node.ToString(), out var parsed))
                    return parsed;
            }
            return fallback;
        }

        private static string FormatMetricCount(long count)
        {
            if (count >= 1_000_000_000)
                return $"{(count / 1_000_000_000.0).ToString("0.#", System.Globalization.CultureInfo.InvariantCulture)} M";
            if (count >= 1_000_000)
                return $"{(count / 1_000_000.0).ToString("0.#", System.Globalization.CultureInfo.InvariantCulture)} Jt";
            if (count >= 1_000)
                return $"{(count / 1_000.0).ToString("0.#", System.Globalization.CultureInfo.InvariantCulture)} Rb";
            return count.ToString("N0", System.Globalization.CultureInfo.InvariantCulture).Replace(",", ".");
        }
        #endregion

        private void WireBridgeEvents()
        {
            _bridge.OnEngineReady += async () =>
            {
                EngineStatusText.Text = "MULTI-TIER ENGINE";
                EngineStatusBadge.Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#065F46"));
                AppendLog("[SYSTEM] Engine Mavdown berhasil terhubung dan siap.\n");
                await _bridge.RequestConfigAsync();
            };

            _bridge.OnLog += text => AppendLog(text);

            _bridge.OnProgress += (val, text, speed, eta) =>
            {
                DownloadProgressBar.Value = Math.Min(100.0, Math.Max(0.0, val * 100.0));
                ProgressStatusText.Text = string.IsNullOrEmpty(text) ? $"Status: {(val * 100.0):F1}%" : text;
                
                string stats = "";
                if (!string.IsNullOrEmpty(speed)) stats += $"Kecepatan: {speed}";
                if (!string.IsNullOrEmpty(eta)) stats += (stats.Length > 0 ? "  |  " : "") + $"ETA {eta}";
                ProgressStatsText.Text = stats;
            };

            _bridge.OnInfoData += data =>
            {
                try
                {
                    string title = SafeGetString(data, "title", "Media Tanpa Judul");
                    string author = SafeGetString(data, "uploader");
                    if (string.IsNullOrEmpty(author)) author = SafeGetString(data, "channel");
                    if (string.IsNullOrEmpty(author)) author = SafeGetString(data, "author");

                    string res = SafeGetString(data, "resolution_label");
                    string fps = SafeGetString(data, "fps");
                    string codec = SafeGetString(data, "codec");
                    if (string.IsNullOrEmpty(codec)) codec = SafeGetString(data, "vcodec");

                    string rawPlatform = SafeGetString(data, "platform", "");
                    string webpageUrl = SafeGetString(data, "webpage_url", "");
                    if (string.IsNullOrEmpty(webpageUrl)) webpageUrl = SafeGetString(data, "url", "");

                    string platform = "Web Media";
                    if (Regex.IsMatch(webpageUrl, @"youtube\.com|youtu\.be", RegexOptions.IgnoreCase) || rawPlatform.Contains("youtube", StringComparison.OrdinalIgnoreCase))
                        platform = "YouTube";
                    else if (Regex.IsMatch(webpageUrl, @"tiktok\.com", RegexOptions.IgnoreCase) || rawPlatform.Contains("tiktok", StringComparison.OrdinalIgnoreCase))
                        platform = "TikTok";
                    else if (Regex.IsMatch(webpageUrl, @"douyin\.com", RegexOptions.IgnoreCase) || rawPlatform.Contains("douyin", StringComparison.OrdinalIgnoreCase))
                        platform = "Douyin";
                    else if (Regex.IsMatch(webpageUrl, @"instagram\.com", RegexOptions.IgnoreCase) || rawPlatform.Contains("instagram", StringComparison.OrdinalIgnoreCase))
                        platform = "Instagram";
                    else if (Regex.IsMatch(webpageUrl, @"twitter\.com|x\.com", RegexOptions.IgnoreCase) || rawPlatform.Contains("twitter", StringComparison.OrdinalIgnoreCase) || rawPlatform.Equals("x", StringComparison.OrdinalIgnoreCase))
                        platform = "Twitter / X";
                    else if (Regex.IsMatch(webpageUrl, @"pinterest\.com|pin\.it", RegexOptions.IgnoreCase) || rawPlatform.Contains("pinterest", StringComparison.OrdinalIgnoreCase))
                        platform = "Pinterest";
                    else if (Regex.IsMatch(webpageUrl, @"bilibili\.com|b23\.tv", RegexOptions.IgnoreCase) || rawPlatform.Contains("bilibili", StringComparison.OrdinalIgnoreCase))
                        platform = "Bilibili";
                    else if (Regex.IsMatch(webpageUrl, @"pixiv\.net", RegexOptions.IgnoreCase) || rawPlatform.Contains("pixiv", StringComparison.OrdinalIgnoreCase))
                        platform = "Pixiv";
                    else if (Regex.IsMatch(webpageUrl, @"facebook\.com|fb\.watch", RegexOptions.IgnoreCase) || rawPlatform.Contains("facebook", StringComparison.OrdinalIgnoreCase))
                        platform = "Facebook";
                    else if (!string.IsNullOrEmpty(rawPlatform))
                        platform = char.ToUpper(rawPlatform[0]) + rawPlatform.Substring(1);

                    string desc = SafeGetString(data, "description");
                    long views = SafeGetLong(data, "view_count");
                    long likes = SafeGetLong(data, "like_count");
                    string durStr = SafeGetString(data, "duration_string");

                    _isCurrentSlide = SafeGetBool(data, "is_slide");
                    _isCurrentUgoira = SafeGetBool(data, "is_ugoira");
                    _currentSlideCount = SafeGetInt(data, "slide_count");
                    _currentWidth = SafeGetInt(data, "width");
                    _currentHeight = SafeGetInt(data, "height");
                    _currentHasAudio = SafeGetBool(data, "has_audio");

                    string cleanTitle = Regex.Replace(title, @"^Judul\s*:\s*", "", RegexOptions.IgnoreCase).Trim();
                    MediaTitleText.Text = string.IsNullOrEmpty(cleanTitle) ? "Media Tanpa Judul" : cleanTitle;
                    MetaPlatformText.Text = platform;

                    string dateStr = SafeGetString(data, "date_string");
                    if (string.IsNullOrEmpty(dateStr))
                    {
                        string rawDate = SafeGetString(data, "upload_date");
                        if (rawDate.Length == 8 && long.TryParse(rawDate, out _))
                            dateStr = $"{rawDate.Substring(6, 2)}/{rawDate.Substring(4, 2)}/{rawDate.Substring(0, 4)}";
                        else if (rawDate.Contains("-") && rawDate.Length >= 10)
                        {
                            var mIso = Regex.Match(rawDate, @"^(\d{4})-(\d{2})-(\d{2})");
                            if (mIso.Success)
                                dateStr = $"{mIso.Groups[3].Value}/{mIso.Groups[2].Value}/{mIso.Groups[1].Value}";
                        }
                    }
                    MetaDateText.Text = dateStr;

                    string displayChannel = author;
                    if (displayChannel.Length > 26)
                        displayChannel = displayChannel.Substring(0, 24) + "..";

                    if (!string.IsNullOrEmpty(displayChannel))
                        MetaChannelText.Text = $"Kreator: {displayChannel}";
                    else if (_isCurrentUgoira)
                        MetaChannelText.Text = "Animasi Pixiv";
                    else if (_isCurrentSlide)
                        MetaChannelText.Text = "Album Slide";
                    else
                        MetaChannelText.Text = $"Media {platform}";

                    if (_isCurrentUgoira)
                    {
                        MetaDurationLabel.Text = "TIPE MEDIA";
                        MetaDurationText.Text = "Ugoira";
                        MetaViewsLabel.Text = "RESOLUSI";
                        MetaViewsText.Text = (_currentWidth > 0 && _currentHeight > 0) ? $"{_currentWidth}x{_currentHeight}" : "Animasi";
                        MetaLikesLabel.Text = "FRAME";
                        MetaLikesText.Text = "Pixiv Frame";
                    }
                    else if (_isCurrentSlide)
                    {
                        MetaDurationLabel.Text = "TOTAL FOTO";
                        MetaDurationText.Text = _currentSlideCount == 1 ? "1 Foto" : (_currentSlideCount > 0 ? $"{_currentSlideCount} Foto" : "Slide");

                        if (views > 0)
                        {
                            MetaViewsLabel.Text = "SAVES";
                            MetaViewsText.Text = FormatMetricCount(views);
                        }
                        else
                        {
                            MetaViewsLabel.Text = "RESOLUSI";
                            MetaViewsText.Text = (_currentWidth > 0 && _currentHeight > 0) ? $"{_currentWidth}x{_currentHeight}" : "HD Asli";
                        }

                        if (likes > 0)
                        {
                            MetaLikesLabel.Text = "LIKES";
                            MetaLikesText.Text = FormatMetricCount(likes);
                        }
                        else
                        {
                            MetaLikesLabel.Text = "AUDIO BGM";
                            MetaLikesText.Text = _currentHasAudio ? "Ada Audio" : "Tanpa BGM";
                        }
                    }
                    else
                    {
                        MetaDurationLabel.Text = "DURASI";
                        string cleanDur = Regex.Replace(durStr ?? "", @"^Durasi\s*:\s*", "", RegexOptions.IgnoreCase).Trim();
                        MetaDurationText.Text = !string.IsNullOrEmpty(cleanDur) ? cleanDur : "-";

                        if (views > 0)
                        {
                            MetaViewsLabel.Text = "VIEWS";
                            MetaViewsText.Text = FormatMetricCount(views);
                        }
                        else if (!string.IsNullOrEmpty(res) && !res.Contains("x"))
                        {
                            MetaViewsLabel.Text = "RESOLUSI";
                            MetaViewsText.Text = res;
                        }
                        else if (_currentWidth > 0 && _currentHeight > 0)
                        {
                            MetaViewsLabel.Text = "RESOLUSI";
                            MetaViewsText.Text = $"{_currentWidth}x{_currentHeight}";
                        }
                        else
                        {
                            MetaViewsLabel.Text = "VIEWS";
                            MetaViewsText.Text = "-";
                        }

                        if (likes > 0)
                        {
                            MetaLikesLabel.Text = "LIKES";
                            MetaLikesText.Text = FormatMetricCount(likes);
                        }
                        else if (!string.IsNullOrEmpty(codec))
                        {
                            MetaLikesLabel.Text = "CODEC";
                            MetaLikesText.Text = codec.ToUpper();
                        }
                        else if (!string.IsNullOrEmpty(fps))
                        {
                            MetaLikesLabel.Text = "FRAMERATE";
                            MetaLikesText.Text = $"{fps} FPS";
                        }
                        else
                        {
                            MetaLikesLabel.Text = "LIKES";
                            MetaLikesText.Text = "-";
                        }
                    }

                    string descRaw = desc;
                    if (string.IsNullOrEmpty(descRaw))
                    {
                        var parts = new List<string>();
                        if (!string.IsNullOrEmpty(author)) parts.Add($"Kreator: {author}");
                        if (_isCurrentSlide)
                        {
                            string dim = (_currentWidth > 0 && _currentHeight > 0) ? $"({_currentWidth}x{_currentHeight})" : "HD";
                            parts.Add(_currentSlideCount == 1 ? $"Foto HD {dim}" : $"Album Slide: {_currentSlideCount} Foto {dim}");
                            if (_currentHasAudio) parts.Add("Musik BGM");
                            parts.Add($"Diunduh via {platform}");
                        }
                        else if (_currentWidth > 0 && _currentHeight > 0)
                        {
                            string resStr = !string.IsNullOrEmpty(res) ? $"{res} ({_currentWidth}x{_currentHeight})" : $"{_currentWidth}x{_currentHeight}";
                            parts.Add($"Resolusi: {resStr}");
                            if (!string.IsNullOrEmpty(fps)) parts.Add($"{fps} FPS");
                            parts.Add($"Diunduh via {platform}");
                        }
                        descRaw = string.Join(" · ", parts);
                    }
                    else
                    {
                        if (!string.IsNullOrEmpty(author) && !descRaw.StartsWith("Kreator:", StringComparison.OrdinalIgnoreCase))
                        {
                            descRaw = $"Kreator: {author} · {descRaw}";
                        }
                    }

                    if (!string.IsNullOrEmpty(descRaw))
                    {
                        string[] lines = descRaw.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries);
                        string preview = string.Join(" · ", lines.Take(2).Select(l => l.Trim()));
                        if (preview.Length > 160) preview = preview.Substring(0, 157) + "...";
                        MetaDescText.Text = preview;
                    }
                    else
                    {
                        MetaDescText.Text = "";
                    }

                    // Update label mode ekstraksi sesuai tipe media
                    RadioVideo.Content = _isCurrentSlide ? "Unduh Semua Slide (+ Audio)" : "Video + Audio";

                    // Render dynamic badges (Gatefold Frosted Glass Pill Tags)
                    BadgesWrapPanel.Children.Clear();
                    if (data.TryGetPropertyValue("computed_badges", out var badgesNode) && badgesNode is JsonArray badgesArr)
                    {
                        foreach (var bNode in badgesArr)
                        {
                            if (bNode is JsonObject bObj)
                            {
                                string bText = SafeGetString(bObj, "text");
                                string bColor = SafeGetString(bObj, "color", "#4F46E5");
                                if (!string.IsNullOrEmpty(bText))
                                {
                                    var border = new Border
                                    {
                                        CornerRadius = new CornerRadius(5),
                                        Padding = new Thickness(10, 4, 10, 4),
                                        Margin = new Thickness(0, 0, 6, 6),
                                        BorderThickness = new Thickness(1)
                                    };
                                    try
                                    {
                                        Color baseColor;
                                        if (bColor.Equals("#4F46E5", StringComparison.OrdinalIgnoreCase) && FindResource("BrushAccentIndigo") is SolidColorBrush acBrush)
                                        {
                                            baseColor = acBrush.Color;
                                        }
                                        else
                                        {
                                            baseColor = (Color)ColorConverter.ConvertFromString(bColor);
                                        }
                                        border.Background = new SolidColorBrush(Color.FromArgb(45, baseColor.R, baseColor.G, baseColor.B));
                                        border.BorderBrush = new SolidColorBrush(Color.FromArgb(170, baseColor.R, baseColor.G, baseColor.B));
                                    }
                                    catch
                                    {
                                        Color fallbackCol = (FindResource("BrushAccentIndigo") is SolidColorBrush fb) ? fb.Color : Color.FromRgb(79, 70, 229);
                                        border.Background = new SolidColorBrush(Color.FromArgb(45, fallbackCol.R, fallbackCol.G, fallbackCol.B));
                                        border.BorderBrush = new SolidColorBrush(Color.FromArgb(170, fallbackCol.R, fallbackCol.G, fallbackCol.B));
                                    }
                                    var tb = new TextBlock
                                    {
                                        Text = bText,
                                        FontSize = 10,
                                        FontWeight = FontWeights.Bold,
                                        Foreground = new SolidColorBrush(Color.FromRgb(241, 245, 249))
                                    };
                                    border.Child = tb;
                                    BadgesWrapPanel.Children.Add(border);
                                }
                            }
                        }
                    }

                    UpdatePlatformBadge(platform);
                    ArtworkPlaceholder.Visibility = Visibility.Collapsed;

                    ApplyStudioModeAdaptation();

                    BtnDownload.IsEnabled = true;
                    ProgressStatusText.Text = "Status: Siap Mengunduh";
                    AppendLog($"[INFO] Metadata terdeteksi: {cleanTitle}\n");
                }
                catch (Exception ex)
                {
                    AppendLog($"[INFO ERROR] Gagal parse metadata: {ex.Message}\n");
                }
            };

            _bridge.OnInfoTitle += title =>
            {
                if (string.IsNullOrWhiteSpace(title)) return;

                bool isErr = title.Contains("tidak tersedia", StringComparison.OrdinalIgnoreCase) ||
                             title.Contains("Gagal", StringComparison.OrdinalIgnoreCase) ||
                             title.Contains("Error", StringComparison.OrdinalIgnoreCase) ||
                             title.Contains("privat", StringComparison.OrdinalIgnoreCase) ||
                             title.Contains("dibatasi", StringComparison.OrdinalIgnoreCase);

                if (isErr)
                {
                    MediaTitleText.Text = title;
                    MetaDescText.Text = title;
                    ProgressStatusText.Text = $"Status: {title}";
                    ArtworkPlaceholder.Visibility = Visibility.Visible;
                    MediaThumbnail.Source = null;
                    BtnDownload.IsEnabled = false;
                }
                else
                {
                    string cleanTitle = Regex.Replace(title, @"^Judul\s*:\s*", "", RegexOptions.IgnoreCase).Trim();
                    MediaTitleText.Text = string.IsNullOrEmpty(cleanTitle) ? "Media Tanpa Judul" : cleanTitle;
                }
            };

            _bridge.OnInspectError += err =>
            {
                MediaTitleText.Text = "Gagal Menginspeksi Media";
                MetaDescText.Text = err;
                ProgressStatusText.Text = "Status: Gagal memeriksa media (URL Error / Offline)";
                ArtworkPlaceholder.Visibility = Visibility.Visible;
                MediaThumbnail.Source = null;
                BtnDownload.IsEnabled = false;
            };

            _bridge.OnInspectComplete += () =>
            {
                if (ProgressStatusText.Text == "Status: Menginspeksi metadata...")
                {
                    if (MediaTitleText.Text.Contains("tidak tersedia", StringComparison.OrdinalIgnoreCase) ||
                        MediaTitleText.Text.Contains("Gagal", StringComparison.OrdinalIgnoreCase) ||
                        MediaTitleText.Text.Contains("Error", StringComparison.OrdinalIgnoreCase))
                    {
                        ProgressStatusText.Text = "Status: Gagal (Media Tidak Ditemukan)";
                    }
                    else
                    {
                        ProgressStatusText.Text = "Status: Selesai memeriksa";
                    }
                }
            };

            _bridge.OnThumbReady += (path, b64) =>
            {
                try
                {
                    BitmapImage? bmp = null;
                    if (!string.IsNullOrEmpty(path) && File.Exists(path))
                    {
                        bmp = new BitmapImage();
                        bmp.BeginInit();
                        bmp.CacheOption = BitmapCacheOption.OnLoad;
                        bmp.UriSource = new Uri(path);
                        bmp.EndInit();
                        bmp.Freeze();
                    }
                    else if (!string.IsNullOrEmpty(b64))
                    {
                        byte[] bytes = Convert.FromBase64String(b64);
                        using var ms = new MemoryStream(bytes);
                        bmp = new BitmapImage();
                        bmp.BeginInit();
                        bmp.CacheOption = BitmapCacheOption.OnLoad;
                        bmp.StreamSource = ms;
                        bmp.EndInit();
                        bmp.Freeze();
                    }

                    if (bmp != null)
                    {
                        MediaThumbnail.Source = bmp;
                        ArtworkPlaceholder.Visibility = Visibility.Collapsed;

                        // Gatefold Cover-Adaptive Dynamic Palette
                        if (GatePaletteService.CurrentThemeMode != "static")
                        {
                            Task.Run(() =>
                            {
                                try
                                {
                                    var palette = GatePaletteService.ExtractPalette(bmp, GatePaletteService.CurrentThemeMode);
                                    GatePaletteService.ApplyToWindow(this, palette, true);
                                }
                                catch (Exception ex)
                                {
                                    AppendLog($"[PALETTE] Error ekstraksi palet cover: {ex.Message}\n");
                                }
                            });
                        }
                    }
                }
                catch (Exception ex)
                {
                    AppendLog($"[THUMB] Gagal render gambar: {ex.Message}\n");
                }
            };

            _bridge.OnDownloadFinish += () =>
            {
                BtnDownload.IsEnabled = true;
                DownloadProgressBar.Value = 100;
                ProgressStatusText.Text = "Status: Selesai!";
                ProgressStatsText.Text = "Tersimpan";
                AppendLog("\n[SELESAI] File berhasil diunduh dan diproses.\n");
                ShowToast("Unduhan selesai!", "success");
            };

            _bridge.OnDownloadError += err =>
            {
                BtnDownload.IsEnabled = true;
                ProgressStatusText.Text = "Status: Gagal Mengunduh";
                AppendLog($"\n[ERROR] {err}\n");
                ShowToast("Unduhan gagal. Buka tab Log untuk detail.", "error");
            };

            _bridge.OnHistoryLoaded += arr =>
            {
                var list = new List<HistoryItem>();
                foreach (var node in arr)
                {
                    if (node is JsonObject obj)
                    {
                        list.Add(new HistoryItem
                        {
                            Id = obj["id"]?.ToString() ?? "",
                            Title = obj["title"]?.ToString() ?? "Media Unduhan",
                            Platform = obj["platform"]?.ToString() ?? "Web",
                            Author = obj["author"]?.ToString() ?? "",
                            Resolution = obj["resolution"]?.ToString() ?? "",
                            MediaFormat = obj["media_format"]?.ToString() ?? "",
                            FilePath = obj["file_path"]?.ToString() ?? "",
                            FileSize = obj["file_size"]?.ToString() ?? "",
                            Thumbnail = obj["thumbnail"]?.ToString() ?? "",
                            LocalThumbnail = obj["local_thumbnail"]?.ToString() ?? "",
                            IsSlide = obj["is_slide"]?.GetValue<bool>() ?? false,
                            Duration = obj["duration"]?.ToString() ?? "",
                            SourceUrl = obj["source_url"]?.ToString() ?? "",
                            Timestamp = obj["timestamp"]?.ToString() ?? ""
                        });
                    }
                }

                HistoryListBox.ItemsSource = list;
                HistoryCountText.Text = $"{list.Count} Media";
            };
            _bridge.OnConfigLoaded += cfg => ApplyConfigData(cfg);

            _bridge.OnPixivLoginStatus += msg =>
            {
                TxtPixivStatus.Text = $"Status: {msg}";
                TxtPixivStatus.Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#9CA3AF"));
                if (msg.Contains("login", StringComparison.OrdinalIgnoreCase) && !msg.Contains("terdeteksi", StringComparison.OrdinalIgnoreCase))
                {
                    BtnLoginBrowserPixiv.Content = "Menunggu Login...";
                }
            };

            _bridge.OnPixivLoginComplete += (success, result, userName) =>
            {
                BtnLoginBrowserPixiv.IsEnabled = true;
                BtnLoginBrowserPixiv.Content = "Login Browser";

                if (success && !string.IsNullOrEmpty(result))
                {
                    _rawPixivSession = result;
                    SettingsPixivBox.Text = _isPixivMasked ? new string('•', result.Length) : result;
                    ShowToast("Login berhasil! Memverifikasi sesi...", "info");
                    VerifyAndSavePixivSession(result);
                }
                else
                {
                    string errMsg = !string.IsNullOrEmpty(result) ? result : "Login dibatalkan atau gagal.";
                    TxtPixivStatus.Text = $"Status: {errMsg}";
                    TxtPixivStatus.Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#EF4444"));
                    ShowToast(errMsg, "warning");
                }
            };

            _bridge.OnPixivVerifyResult += (isValid, userInfo) =>
            {
                BtnSavePixivSession.IsEnabled = true;
                BtnSavePixivSession.Content = "Simpan & Cek";

                if (isValid)
                {
                    TxtPixivStatus.Text = $"Status: Terhubung ({userInfo})";
                    TxtPixivStatus.Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#34D399"));
                    ShowToast($"Sesi Pixiv berhasil terhubung: {userInfo}", "success");
                }
                else
                {
                    TxtPixivStatus.Text = $"Status: {userInfo}";
                    TxtPixivStatus.Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#EF4444"));
                    ShowToast("Sesi Pixiv tidak valid atau kadaluarsa.", "error");
                }
            };
        }

        private void LoadInitialLocalConfig()
        {
            try
            {
                string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
                string cfgPath = Path.Combine(localAppData, "SayMaven", "Mavdown", "config.json");
                if (!File.Exists(cfgPath))
                {
                    string rootDir = AppDomain.CurrentDomain.BaseDirectory;
                    cfgPath = Path.Combine(rootDir, "config.json");
                }

                if (File.Exists(cfgPath))
                {
                    string json = File.ReadAllText(cfgPath);
                    var cfg = JsonNode.Parse(json)?.AsObject();
                    if (cfg != null)
                    {
                        ApplyConfigData(cfg);
                    }
                }
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"[Config Local Load Error] {ex.Message}");
            }
        }

        private void ApplyConfigData(JsonObject cfg)
        {
            _isApplyingConfig = true;
            try
            {
                if (cfg["output_dir"] != null || cfg["output_path"] != null)
                {
                    _outputFolder = (cfg["output_dir"] ?? cfg["output_path"])!.ToString();
                    SettingsPathBox.Text = _outputFolder;
                    SidebarPathText.Text = _outputFolder;
                }
                if (cfg["proxy"] != null)
                {
                    SettingsProxyBox.Text = cfg["proxy"]!.ToString();
                }
                if (cfg["organize_by_platform"] != null)
                {
                    CheckOrganizePlatform.IsChecked = cfg["organize_by_platform"]!.GetValue<bool>();
                }
                if (cfg["clipboard_monitor"] != null)
                {
                    _isClipboardMonitorEnabled = cfg["clipboard_monitor"]!.GetValue<bool>();
                    CheckClipboardMonitor.IsChecked = _isClipboardMonitorEnabled;
                    if (_isClipboardMonitorEnabled) _clipboardTimer?.Start();
                    else _clipboardTimer?.Stop();
                }
                if (cfg["browser_cookie"] != null)
                {
                    string bc = cfg["browser_cookie"]!.ToString();
                    foreach (var item in ComboBrowserCookie.Items)
                    {
                        if (item is ComboBoxItem cbi && string.Equals(cbi.Content?.ToString(), bc, StringComparison.OrdinalIgnoreCase))
                        {
                            ComboBrowserCookie.SelectedItem = cbi;
                            break;
                        }
                    }
                }
                if (cfg["pixiv_session"] != null)
                {
                    _rawPixivSession = cfg["pixiv_session"]!.ToString();
                    SettingsPixivBox.Text = _isPixivMasked ? (string.IsNullOrEmpty(_rawPixivSession) ? "" : new string('•', _rawPixivSession.Length)) : _rawPixivSession;
                    if (TxtPixivStatus != null)
                    {
                        if (!string.IsNullOrEmpty(_rawPixivSession))
                        {
                            TxtPixivStatus.Text = "Status: Sesi Tersimpan";
                            TxtPixivStatus.Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#34D399"));
                        }
                        else
                        {
                            TxtPixivStatus.Text = "Status: Belum Terhubung (Sesi Kosong)";
                            TxtPixivStatus.Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#6B7280"));
                        }
                    }
                }
                if (cfg["preferences"] is JsonObject prefs)
                {
                    if (prefs["embed_thumbnail"] != null)
                        CheckEmbedThumb.IsChecked = prefs["embed_thumbnail"]!.GetValue<bool>();
                    if (prefs["use_aria2"] != null)
                        CheckUseAria2.IsChecked = prefs["use_aria2"]!.GetValue<bool>();
                    if (prefs["download_subs"] != null)
                        CheckDownloadSubs.IsChecked = prefs["download_subs"]!.GetValue<bool>();
                    if (prefs["embed_subs"] != null)
                        CheckEmbedSubs.IsChecked = prefs["embed_subs"]!.GetValue<bool>();
                    if (prefs["subs_lang"] != null)
                        SubsLangEntry.Text = prefs["subs_lang"]!.ToString();
                    if (prefs["download_playlist"] != null)
                        CheckPlaylist.IsChecked = prefs["download_playlist"]!.GetValue<bool>();
                }
                if (cfg["ytdlp_version"] != null)
                {
                    YtdlpVersionText.Text = $"Versi yt-dlp: {cfg["ytdlp_version"]}";
                }
                if (cfg["is_aria2_available"] != null)
                {
                    bool aria = cfg["is_aria2_available"]!.GetValue<bool>();
                    TxtStatusAria2.Text = aria ? "Tersedia (16x)" : "Tidak Tersedia";
                    TxtStatusAria2.Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString(aria ? "#34D399" : "#F87171"));
                    if (TxtInfoAria2 != null)
                    {
                        TxtInfoAria2.Text = $"aria2c 16-thread {(aria ? "(Tersedia)" : "(Tidak ditemukan)")}";
                    }
                }
            }
            finally
            {
                _isApplyingConfig = false;
            }
        }

        private void AppendLog(string text)
        {
            LogConsoleFull.AppendText(text);
            LogConsoleFull.ScrollToEnd();
        }

        #region Adaptasi Mode Studio (toggle_opts Tkinter 100% Parity)
        private void ApplyStudioModeAdaptation()
        {
            if (_isCurrentSlide || _isCurrentUgoira)
            {
                // Mode Slide Foto / Ugoira
                if (_isCurrentUgoira)
                {
                    FormatTitleLabel.Text = RadioAudio.IsChecked == true ? "PARAMETER FORMAT AUDIO (BGM)" : "PARAMETER ANIMASI PIXIV UGOIRA";
                    SlideBannerTitle.Text = "MODE ANIMASI PIXIV UGOIRA";
                    SlideBadgeLbl.Text = "Ugoira";
                    SlideBadgeBox.Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#0055A5"));
                    SlideStatusLbl.Text = "Pixiv Ugoira terdiri dari susunan frame gambar berseri yang dirakit otomatis menjadi video MP4 atau animasi GIF.";
                    SlidePCount.Text = "Tipe: Animasi Berseri";
                    string fmtVal = RadioUgoiraGif.IsChecked == true ? "GIF" : "MP4";
                    SlidePFormat.Text = $"Target: Video/Animasi ({fmtVal})";
                    SlidePRes.Text = (_currentWidth > 0 && _currentHeight > 0) ? $"Dimensi: {_currentWidth}x{_currentHeight} (Asli)" : "Dimensi: HD Original";
                    SlidePAudio.Text = "Audio: Tanpa Musik (Murni Animasi)";
                    UgoiraContainer.Visibility = Visibility.Visible;
                }
                else
                {
                    FormatTitleLabel.Text = RadioAudio.IsChecked == true ? "PARAMETER FORMAT AUDIO (BGM)" : (_currentSlideCount == 1 ? "PARAMETER FOTO HD" : "PARAMETER ALBUM SLIDE FOTO");
                    SlideBannerTitle.Text = "MODE ALBUM SLIDE FOTO";
                    SlideBadgeLbl.Text = "HD Original";
                    SlideBadgeBox.Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#312E81"));
                    SlideStatusLbl.Text = "MavDown akan mengunduh semua file gambar asli HD tanpa watermark ke subfolder album khusus beserta file musik BGM.";
                    SlidePCount.Text = _currentSlideCount == 1 ? "Total: 1 Foto HD" : (_currentSlideCount > 0 ? $"Total: {_currentSlideCount} Foto Slide" : "Total: Album Slide");
                    SlidePFormat.Text = "Format: JPEG HD (Lossless)";
                    SlidePRes.Text = (_currentWidth > 0 && _currentHeight > 0) ? $"Dimensi: {_currentWidth}x{_currentHeight} (Asli)" : "Dimensi: HD Original";
                    SlidePAudio.Text = _currentHasAudio ? "Audio: Musik BGM (.mp3)" : "Audio: Tanpa Musik";
                    UgoiraContainer.Visibility = Visibility.Collapsed;
                }

                if (RadioAudio.IsChecked == true)
                {
                    SlideOptsPanel.Visibility = Visibility.Collapsed;
                    VideoOptsPanel.Visibility = Visibility.Collapsed;
                    AudioOptsPanel.Visibility = Visibility.Visible;
                }
                else
                {
                    SlideOptsPanel.Visibility = Visibility.Visible;
                    VideoOptsPanel.Visibility = Visibility.Collapsed;
                    AudioOptsPanel.Visibility = Visibility.Collapsed;
                }

                // Sembunyikan Subtitle di Slide Mode
                SecSubPanel.Visibility = Visibility.Collapsed;

                // ATURAN MUTLAK USER & AGENTS.md: Di mode album slide foto HANYA muncul injeksi thumbnail dan aria2c saja!
                CheckEmbedSubs.Visibility = Visibility.Collapsed;
                CheckDownloadSubs.Visibility = Visibility.Collapsed;
                CheckPlaylist.Visibility = Visibility.Collapsed;
                CheckEmbedThumb.Visibility = Visibility.Visible;
                CheckUseAria2.Visibility = Visibility.Visible;
            }
            else
            {
                // Mode Video / Audio Reguler
                FormatTitleLabel.Text = RadioAudio.IsChecked == true ? "PARAMETER FORMAT AUDIO (BGM)" : "PARAMETER FORMAT & KUALITAS";
                SlideOptsPanel.Visibility = Visibility.Collapsed;
                SecSubPanel.Visibility = Visibility.Visible;

                // Tampilkan kembali semua opsi checkbox
                CheckEmbedSubs.Visibility = Visibility.Visible;
                CheckDownloadSubs.Visibility = Visibility.Visible;
                CheckPlaylist.Visibility = Visibility.Visible;
                CheckEmbedThumb.Visibility = Visibility.Visible;
                CheckUseAria2.Visibility = Visibility.Visible;

                if (RadioAudio.IsChecked == true)
                {
                    VideoOptsPanel.Visibility = Visibility.Collapsed;
                    AudioOptsPanel.Visibility = Visibility.Visible;

                    LangLabel.Text = "LIRIK LAGU & BAHASA AUDIO";
                    CheckEmbedSubs.Content = "Embed Lirik Lagu";
                    CheckDownloadSubs.Content = "Unduh Lirik Terpisah (.lrc)";
                }
                else
                {
                    VideoOptsPanel.Visibility = Visibility.Visible;
                    AudioOptsPanel.Visibility = Visibility.Collapsed;

                    LangLabel.Text = "SUBTITLE & LIRIK OTOMATIS";
                    CheckEmbedSubs.Content = "Embed Softsub P0 (Default Aktif)";
                    CheckDownloadSubs.Content = "Unduh Subtitle Terpisah (.srt)";
                }
            }
        }

        private void OnModeSegmentChange(object sender, RoutedEventArgs e)
        {
            if (IsLoaded)
                ApplyStudioModeAdaptation();
        }

        private void OnUgoiraFormatChange(object sender, RoutedEventArgs e)
        {
            if (IsLoaded && _isCurrentUgoira)
            {
                string fmt = RadioUgoiraGif.IsChecked == true ? "GIF" : "MP4";
                SlidePFormat.Text = $"Target: Video/Animasi ({fmt})";
            }
        }

        private void OnLangPresetChange(object sender, SelectionChangedEventArgs e)
        {
            if (!IsLoaded || SubsLangEntry == null || ComboSubsLang == null) return;
            if (ComboSubsLang.SelectedItem is ComboBoxItem item)
            {
                string txt = item.Content?.ToString() ?? "";
                if (txt.Contains("Indonesia & English")) SubsLangEntry.Text = "id,en";
                else if (txt.Contains("Bahasa Indonesia")) SubsLangEntry.Text = "id";
                else if (txt.Contains("English")) SubsLangEntry.Text = "en";
                else if (txt.Contains("Jepang")) SubsLangEntry.Text = "ja";
                else if (txt.Contains("Cina")) SubsLangEntry.Text = "zh";
                else if (txt.Contains("Korea")) SubsLangEntry.Text = "ko";
                else if (txt.Contains("Spanyol")) SubsLangEntry.Text = "es";
                else if (txt.Contains("Semua")) SubsLangEntry.Text = "all";
            }
        }
        #endregion

        #region Platform Pill Detection
        private void OnUrlInputTextChanged(object sender, TextChangedEventArgs e)
        {
            if (!IsLoaded || UrlInput == null || PlatformBadge == null) return;
            string url = UrlInput.Text.Trim();
            UrlPlaceholder.Visibility = string.IsNullOrEmpty(url) ? Visibility.Visible : Visibility.Collapsed;
            if (BtnClearUrl != null)
            {
                BtnClearUrl.Visibility = string.IsNullOrEmpty(url) ? Visibility.Collapsed : Visibility.Visible;
            }

            if (string.IsNullOrEmpty(url))
            {
                PlatformBadge.Visibility = Visibility.Collapsed;
                return;
            }

            UpdatePlatformBadge(url);
        }

        private void UpdatePlatformBadge(string nameOrUrl, string colorHex = "")
        {
            if (string.IsNullOrWhiteSpace(nameOrUrl))
            {
                PlatformBadge.Visibility = Visibility.Collapsed;
                return;
            }

            string displayName = nameOrUrl.Trim();
            string finalColor = colorHex;

            // Jika input adalah URL atau diawali http
            if (displayName.StartsWith("http://", StringComparison.OrdinalIgnoreCase) || 
                displayName.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
            {
                displayName = "WEB";
                finalColor = "#4B5563";
                foreach (var (pattern, name, color) in _platformPatterns)
                {
                    if (Regex.IsMatch(nameOrUrl, pattern, RegexOptions.IgnoreCase))
                    {
                        displayName = name;
                        finalColor = color;
                        break;
                    }
                }
            }
            else if (string.IsNullOrEmpty(finalColor))
            {
                // Jika input nama platform (misal "Douyin", "TikTok", "YouTube")
                foreach (var (_, name, color) in _platformPatterns)
                {
                    if (name.Equals(displayName, StringComparison.OrdinalIgnoreCase))
                    {
                        displayName = name;
                        finalColor = color;
                        break;
                    }
                }
                if (string.IsNullOrEmpty(finalColor))
                {
                    finalColor = "#4F46E5";
                }
            }

            PlatformBadge.Visibility = Visibility.Visible;
            PlatformBadgeText.Text = displayName.ToUpper();

            try
            {
                PlatformBadge.Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString(finalColor));
            }
            catch { }
        }
        #endregion

        #region Quick Presets
        private void OnPresetSuperQualityClick(object sender, RoutedEventArgs e)
        {
            RadioVideo.IsChecked = true;
            RadContAuto.IsChecked = true;
            RadVCodecAuto.IsChecked = true;
            RadACodecAuto.IsChecked = true;
            RadResAuto.IsChecked = true;
            CheckEmbedThumb.IsChecked = true;
            ApplyStudioModeAdaptation();
            AppendLog("[PRESET] Preset 'Super Quality' diterapkan.\n");
            ShowToast("Preset 'Super Quality' diterapkan.", "info");
        }

        private void OnPresetMusikMp3Click(object sender, RoutedEventArgs e)
        {
            RadioAudio.IsChecked = true;
            RadAudioMp3.IsChecked = true;
            RadBitrate320.IsChecked = true;
            CheckEmbedThumb.IsChecked = true;
            ApplyStudioModeAdaptation();
            AppendLog("[PRESET] Preset 'Musik MP3' diterapkan.\n");
            ShowToast("Preset 'Musik MP3' diterapkan.", "info");
        }

        private void OnPresetHematDataClick(object sender, RoutedEventArgs e)
        {
            RadioVideo.IsChecked = true;
            RadContMp4.IsChecked = true;
            RadVCodecH264.IsChecked = true;
            RadACodecAuto.IsChecked = true;
            RadRes720.IsChecked = true;
            CheckEmbedThumb.IsChecked = true;
            ApplyStudioModeAdaptation();
            AppendLog("[PRESET] Preset 'Hemat Data' (720p H.264) diterapkan.\n");
            ShowToast("Preset 'Hemat Data' diterapkan.", "info");
        }

        private void OnPresetPodcastClick(object sender, RoutedEventArgs e)
        {
            RadioAudio.IsChecked = true;
            RadAudioM4a.IsChecked = true;
            RadBitrate192.IsChecked = true;
            CheckEmbedThumb.IsChecked = true;
            ApplyStudioModeAdaptation();
            AppendLog("[PRESET] Preset 'Podcast' (M4A) diterapkan.\n");
            ShowToast("Preset 'Podcast' diterapkan.", "info");
        }
        #endregion

        #region Helper Segmented RadioButton Selectors
        private string GetSelectedContainer()
        {
            if (RadContMp4.IsChecked == true) return "mp4";
            if (RadContMkv.IsChecked == true) return "mkv";
            if (RadContWebm.IsChecked == true) return "webm";
            if (RadContMov.IsChecked == true) return "mov";
            return "mp4";
        }

        private string GetSelectedVideoCodec()
        {
            if (RadVCodecH264.IsChecked == true) return "h264";
            if (RadVCodecVp9.IsChecked == true) return "vp9";
            if (RadVCodecAv1.IsChecked == true) return "av01";
            return "auto";
        }

        private string GetSelectedAudioCodec()
        {
            if (RadACodecM4a.IsChecked == true) return "m4a";
            if (RadACodecOpus.IsChecked == true) return "opus";
            return "auto";
        }

        private string GetSelectedResolution()
        {
            if (RadRes4k.IsChecked == true) return "2160";
            if (RadRes1440.IsChecked == true) return "1440";
            if (RadRes1080.IsChecked == true) return "1080";
            if (RadRes720.IsChecked == true) return "720";
            if (RadRes480.IsChecked == true) return "480";
            if (RadRes360.IsChecked == true) return "360";
            return "best";
        }

        private string GetSelectedAudioFormat()
        {
            if (RadAudioM4a.IsChecked == true) return "m4a";
            if (RadAudioFlac.IsChecked == true) return "flac";
            if (RadAudioWav.IsChecked == true) return "wav";
            if (RadAudioOpus.IsChecked == true) return "opus";
            return "mp3";
        }

        private string GetSelectedBrowserCookie()
        {
            if (ComboBrowserCookie?.SelectedItem is ComboBoxItem cbi)
            {
                string val = cbi.Content?.ToString() ?? "Tidak Ada";
                return val;
            }
            return "Tidak Ada";
        }
        #endregion

        #region Universal Command Bar Actions
        private async void OnInspectClick(object sender, RoutedEventArgs e)
        {
            string url = UrlInput.Text.Trim();
            if (string.IsNullOrEmpty(url))
            {
                AppendLog("[PERINGATAN] Silakan tempel URL terlebih dahulu.\n");
                return;
            }

            AppendLog($"\n[INSPEKSI] Memeriksa tautan: {url}...\n");
            
            // Segarkan tampilan pratinjau agar data lama (misal Pixiv) tidak tertinggal
            ArtworkPlaceholder.Visibility = Visibility.Visible;
            MediaThumbnail.Source = null;
            MediaTitleText.Text = "Menginspeksi media...";
            MetaPlatformText.Text = "Media";
            MetaDateText.Text = "";
            MetaChannelText.Text = "Kreator: -";
            MetaDurationLabel.Text = "DURASI";
            MetaDurationText.Text = "-";
            MetaViewsLabel.Text = "VIEWS";
            MetaViewsText.Text = "-";
            MetaLikesLabel.Text = "LIKES";
            MetaLikesText.Text = "-";
            MetaDescText.Text = "";
            BadgesWrapPanel.Children.Clear();
            ProgressStatusText.Text = "Status: Menginspeksi metadata...";

            SwitchToStudio();
            await _bridge.InspectUrlAsync(url, _lastShareText, GetSelectedBrowserCookie());
        }

        private async void OnDownloadClick(object sender, RoutedEventArgs e)
        {
            string url = UrlInput.Text.Trim();
            if (string.IsNullOrEmpty(url))
            {
                AppendLog("[PERINGATAN] URL tidak boleh kosong.\n");
                return;
            }

            BtnDownload.IsEnabled = false;
            ProgressStatusText.Text = "Status: Memulai unduhan...";
            DownloadProgressBar.Value = 0;

            string mode = RadioAudio.IsChecked == true ? "audio" : "video";
            string audioFormat = GetSelectedAudioFormat();
            string container = GetSelectedContainer();
            string res = GetSelectedResolution();
            string vcodec = GetSelectedVideoCodec();
            string acodec = GetSelectedAudioCodec();

            string subsLang = SubsLangEntry.Text.Trim();
            if (string.IsNullOrEmpty(subsLang)) subsLang = "id,en";

            bool downloadSubs = CheckDownloadSubs.IsChecked ?? false;
            bool embedSubs = CheckEmbedSubs.IsChecked ?? true;
            bool embedThumb = CheckEmbedThumb.IsChecked ?? true;
            bool useAria2 = CheckUseAria2.IsChecked ?? true;
            bool downloadPlaylist = CheckPlaylist.IsChecked ?? false;
            string ugoiraFormat = RadioUgoiraGif.IsChecked == true ? "gif" : "mp4";

            await _bridge.StartDownloadAsync(
                url: url,
                mode: mode,
                audioFormat: audioFormat,
                res: res,
                vcodec: vcodec,
                acodec: acodec,
                container: container,
                downloadSubs: downloadSubs,
                embedSubs: embedSubs,
                subsLang: subsLang,
                embedThumb: embedThumb,
                useAria2: useAria2,
                downloadPlaylist: downloadPlaylist,
                customPath: _outputFolder,
                cookie: GetSelectedBrowserCookie(),
                ugoiraFormat: ugoiraFormat
            );
        }

        private void OnPasteClick(object sender, RoutedEventArgs e)
        {
            try
            {
                if (Clipboard.ContainsText())
                {
                    string raw = Clipboard.GetText();
                    var match = Regex.Match(raw, @"https?://[^\s""'<>]+");
                    if (match.Success)
                    {
                        string cleanUrl = match.Value.TrimEnd('，', '。', '！', '!', '?', ',', ';', ')', '"', '\'', '\r', '\n');
                        _lastShareText = raw;
                        UrlInput.Text = cleanUrl;
                        UrlPlaceholder.Visibility = Visibility.Collapsed;
                        OnInspectClick(sender, e);
                    }
                    else
                    {
                        UrlInput.Text = raw.Trim();
                        UrlPlaceholder.Visibility = string.IsNullOrEmpty(UrlInput.Text) ? Visibility.Visible : Visibility.Collapsed;
                    }
                }
            }
            catch (Exception ex)
            {
                AppendLog($"[CLIPBOARD] Gagal membaca clipboard: {ex.Message}\n");
            }
        }

        private void OnClearUrlClick(object sender, RoutedEventArgs e)
        {
            UrlInput.Clear();
            if (BtnClearUrl != null)
            {
                BtnClearUrl.Visibility = Visibility.Collapsed;
            }
            _lastShareText = "";
            PlatformBadge.Visibility = Visibility.Collapsed;
            MediaTitleText.Text = "Judul video atau media akan muncul di sini setelah memasukkan URL.";
            MediaThumbnail.Source = null;
            ArtworkPlaceholder.Visibility = Visibility.Visible;
            _isCurrentSlide = false;
            _isCurrentUgoira = false;
            ApplyStudioModeAdaptation();
            UrlInput.Focus();
        }

        private void OnUrlInputKeyDown(object sender, KeyEventArgs e)
        {
            if (e.Key == Key.Enter)
            {
                OnInspectClick(sender, e);
            }
        }
        #endregion

        #region Navigasi 5 Tab
        private void ResetNavTabStyles()
        {
            TabStudioBtn.Background = Brushes.Transparent;
            TabQueueBtn.Background = Brushes.Transparent;
            TabHistoryBtn.Background = Brushes.Transparent;
            TabLogBtn.Background = Brushes.Transparent;
            TabSettingsBtn.Background = Brushes.Transparent;

            TxtNavStudio.Foreground = (Brush)FindResource("BrushTextMuted");
            TxtNavQueue.Foreground = (Brush)FindResource("BrushTextMuted");
            TxtNavHistory.Foreground = (Brush)FindResource("BrushTextMuted");
            TxtNavLog.Foreground = (Brush)FindResource("BrushTextMuted");
            TxtNavSettings.Foreground = (Brush)FindResource("BrushTextMuted");

            StudioPanel.Visibility = Visibility.Collapsed;
            QueuePanel.Visibility = Visibility.Collapsed;
            HistoryPanel.Visibility = Visibility.Collapsed;
            LogPanel.Visibility = Visibility.Collapsed;
            SettingsPanel.Visibility = Visibility.Collapsed;
        }

        private int _currentTabIndex = 0;

        public void UpdateActiveTabHighlight()
        {
            Dispatcher.Invoke(() =>
            {
                var activeBg = (Brush)FindResource("BrushNavActiveBg");
                var activeFg = (Brush)FindResource("BrushNavActiveFg");
                var mutedFg = (Brush)FindResource("BrushTextMuted");

                TabStudioBtn.Background = _currentTabIndex == 0 ? activeBg : Brushes.Transparent;
                TxtNavStudio.Foreground = _currentTabIndex == 0 ? activeFg : mutedFg;

                TabQueueBtn.Background = _currentTabIndex == 1 ? activeBg : Brushes.Transparent;
                TxtNavQueue.Foreground = _currentTabIndex == 1 ? activeFg : mutedFg;

                TabHistoryBtn.Background = _currentTabIndex == 2 ? activeBg : Brushes.Transparent;
                TxtNavHistory.Foreground = _currentTabIndex == 2 ? activeFg : mutedFg;

                TabLogBtn.Background = _currentTabIndex == 3 ? activeBg : Brushes.Transparent;
                TxtNavLog.Foreground = _currentTabIndex == 3 ? activeFg : mutedFg;

                TabSettingsBtn.Background = _currentTabIndex == 4 ? activeBg : Brushes.Transparent;
                TxtNavSettings.Foreground = _currentTabIndex == 4 ? activeFg : mutedFg;
            });
        }

        private void SwitchToStudio()
        {
            ResetNavTabStyles();
            _currentTabIndex = 0;
            UpdateActiveTabHighlight();
            StudioPanel.Visibility = Visibility.Visible;
        }

        private void OnTabStudioClick(object sender, MouseButtonEventArgs e) => SwitchToStudio();

        private void OnTabQueueClick(object sender, MouseButtonEventArgs e)
        {
            ResetNavTabStyles();
            _currentTabIndex = 1;
            UpdateActiveTabHighlight();
            QueuePanel.Visibility = Visibility.Visible;
        }

        private async void OnTabHistoryClick(object sender, MouseButtonEventArgs e)
        {
            ResetNavTabStyles();
            _currentTabIndex = 2;
            UpdateActiveTabHighlight();
            HistoryPanel.Visibility = Visibility.Visible;

            await _bridge.RequestHistoryAsync(HistorySearchInput.Text.Trim());
        }

        private void OnTabLogClick(object sender, MouseButtonEventArgs e)
        {
            ResetNavTabStyles();
            _currentTabIndex = 3;
            UpdateActiveTabHighlight();
            LogPanel.Visibility = Visibility.Visible;
        }

        private async void OnTabSettingsClick(object sender, MouseButtonEventArgs e)
        {
            ResetNavTabStyles();
            _currentTabIndex = 4;
            UpdateActiveTabHighlight();
            SettingsPanel.Visibility = Visibility.Visible;

            await _bridge.RequestConfigAsync();
        }
        #endregion

        #region Antrean Batch Actions
        private void OnAddToQueueClick(object sender, RoutedEventArgs e)
        {
            string raw = BatchUrlsInput.Text;
            var matches = Regex.Matches(raw, @"https?://[^\s""'<>]+");
            int added = 0;
            foreach (Match m in matches)
            {
                string u = m.Value.TrimEnd('，', '。', '！', '!', '?', ',', ';', ')', '"', '\'', '\r', '\n');
                if (!string.IsNullOrEmpty(u))
                {
                    _queueItems.Add(new QueueItem { Url = u, Status = "Menunggu" });
                    added++;
                }
            }

            BatchUrlsInput.Clear();
            AppendLog($"[ANTREAN] Berhasil menambahkan {added} tautan ke antrean massal.\n");
            if (added == 0)
            {
                ShowToast("Tidak ada URL yang valid.", "warning");
            }
            else
            {
                ShowToast($"{added} URL ditambahkan ke antrean.", "success");
            }
        }

        private async void OnStartQueueClick(object sender, RoutedEventArgs e)
        {
            if (_isQueueRunning) return;
            if (_queueItems.Count == 0)
            {
                AppendLog("[ANTREAN] Antrean unduhan masih kosong.\n");
                ShowToast("Antrean kosong.", "warning");
                return;
            }

            _isQueueRunning = true;
            BtnStartQueue.IsEnabled = false;

            AppendLog($"\n[ANTREAN] Memulai proses batch unduhan ({_queueItems.Count} item)...\n");
            ShowToast($"Memulai {_queueItems.Count} unduhan dalam antrean...", "info");

            foreach (var item in _queueItems)
            {
                if (item.Status == "Selesai") continue;

                item.Status = "Mengunduh";
                AppendLog($"\n[ANTREAN] Mengunduh: {item.Url}...\n");

                var tcs = new TaskCompletionSource<bool>();

                Action onFinish = null!;
                Action<string> onError = null!;

                onFinish = () =>
                {
                    item.Status = "Selesai";
                    item.Progress = 100;
                    _bridge.OnDownloadFinish -= onFinish;
                    _bridge.OnDownloadError -= onError;
                    tcs.TrySetResult(true);
                };

                onError = (err) =>
                {
                    item.Status = "Gagal";
                    _bridge.OnDownloadFinish -= onFinish;
                    _bridge.OnDownloadError -= onError;
                    tcs.TrySetResult(false);
                };

                _bridge.OnDownloadFinish += onFinish;
                _bridge.OnDownloadError += onError;

                await _bridge.StartDownloadAsync(item.Url, mode: "video", container: "mp4");
                await tcs.Task;
            }

            _isQueueRunning = false;
            BtnStartQueue.IsEnabled = true;
            AppendLog("\n[ANTREAN] Seluruh antrean unduhan telah selesai diproses.\n");
        }

        private void OnImportQueueTxtClick(object sender, RoutedEventArgs e)
        {
            var ofd = new OpenFileDialog
            {
                Filter = "Text Files (*.txt)|*.txt|All Files (*.*)|*.*",
                Title = "Pilih File Berisi Daftar URL"
            };

            if (ofd.ShowDialog() == true)
            {
                try
                {
                    string content = File.ReadAllText(ofd.FileName);
                    BatchUrlsInput.Text = content;
                    OnAddToQueueClick(sender, e);
                }
                catch (Exception ex)
                {
                    AppendLog($"[IMPORT] Gagal membaca file: {ex.Message}\n");
                }
            }
        }

        private void OnClearQueueClick(object sender, RoutedEventArgs e)
        {
            _queueItems.Clear();
            AppendLog("[ANTREAN] Antrean unduhan telah dikosongkan.\n");
            ShowToast("Antrean dikosongkan.", "info");
        }
        #endregion

        #region Riwayat Actions
        private async void OnHistorySearchChanged(object sender, TextChangedEventArgs e)
        {
            if (!IsLoaded || HistorySearchInput == null || HistorySearchPlaceholder == null) return;
            string query = HistorySearchInput.Text.Trim();
            HistorySearchPlaceholder.Visibility = string.IsNullOrEmpty(query) ? Visibility.Visible : Visibility.Collapsed;
            await _bridge.RequestHistoryAsync(query);
        }

        private async void OnResetSearchClick(object sender, RoutedEventArgs e)
        {
            HistorySearchInput.Clear();
            await _bridge.RequestHistoryAsync("");
        }

        private void OnPlayHistoryItemClick(object sender, RoutedEventArgs e)
        {
            if (sender is Button btn && btn.Tag is string fpath && !string.IsNullOrEmpty(fpath))
            {
                if (File.Exists(fpath) || Directory.Exists(fpath))
                {
                    try
                    {
                        Process.Start(new ProcessStartInfo { FileName = fpath, UseShellExecute = true });
                    }
                    catch (Exception ex)
                    {
                        AppendLog($"[PUTAR] Gagal memutar media: {ex.Message}\n");
                    }
                }
                else
                {
                    AppendLog("[PUTAR] File media sudah tidak ada di lokasi penyimpanan.\n");
                }
            }
        }

        private void OnOpenHistoryFolderClick(object sender, RoutedEventArgs e)
        {
            if (sender is Button btn && btn.Tag is string fpath && !string.IsNullOrEmpty(fpath))
            {
                try
                {
                    if (File.Exists(fpath))
                    {
                        Process.Start("explorer.exe", $"/select,\"{fpath}\"");
                    }
                    else if (Directory.Exists(fpath))
                    {
                        Process.Start("explorer.exe", fpath);
                    }
                    else
                    {
                        OnOpenFolderClick(sender, e);
                    }
                }
                catch (Exception ex)
                {
                    AppendLog($"[EXPLORER] Gagal membuka folder: {ex.Message}\n");
                }
            }
        }

        private async void OnDeleteHistoryItemClick(object sender, RoutedEventArgs e)
        {
            if (sender is Button btn && btn.Tag is string entryId && !string.IsNullOrEmpty(entryId))
            {
                var result = MessageBox.Show(
                    "Hapus entri ini dari riwayat?",
                    "Konfirmasi Hapus",
                    MessageBoxButton.YesNo,
                    MessageBoxImage.Question
                );

                if (result == MessageBoxResult.Yes)
                {
                    await _bridge.SendCommandAsync(new
                    {
                        action = "delete_history",
                        entry_id = entryId,
                        delete_file = false
                    });
                    await _bridge.RequestHistoryAsync(HistorySearchInput.Text.Trim());
                }
            }
        }

        private async void OnClearHistoryClick(object sender, RoutedEventArgs e)
        {
            var result = MessageBox.Show(
                "Apakah Anda yakin ingin membersihkan seluruh riwayat unduhan?",
                "Bersihkan Riwayat",
                MessageBoxButton.YesNo,
                MessageBoxImage.Warning
            );

            if (result == MessageBoxResult.Yes)
            {
                await _bridge.SendCommandAsync(new { action = "clear_history" });
                await _bridge.RequestHistoryAsync();
                ShowToast("Seluruh riwayat unduhan telah dibersihkan.", "info");
            }
        }
        #endregion

        #region Konsol Log Actions
        private void OnCopyLogClick(object sender, RoutedEventArgs e)
        {
            Clipboard.SetText(LogConsoleFull.Text);
            AppendLog("[LOG] Seluruh log disalin ke clipboard.\n");
            ShowToast("Seluruh log disalin ke clipboard.", "info");
        }

        private void OnClearLogClick(object sender, RoutedEventArgs e)
        {
            LogConsoleFull.Clear();
        }
        #endregion

        #region Pengaturan & yt-dlp Actions
        private void OnSelectFolderClick(object sender, RoutedEventArgs e)
        {
            var dialog = new OpenFolderDialog
            {
                Title = "Pilih Folder Penyimpanan Utama"
            };

            if (dialog.ShowDialog() == true)
            {
                SettingsPathBox.Text = dialog.FolderName;
                SidebarPathText.Text = dialog.FolderName;
                _outputFolder = dialog.FolderName;
                if (_bridge != null)
                {
                    _ = _bridge.SendCommandAsync(new { action = "set_config", key = "output_path", value = _outputFolder });
                }
                ShowToast($"Folder penyimpanan diatur ke {_outputFolder}", "success");
            }
        }

        private void OnOpenFolderClick(object sender, RoutedEventArgs e)
        {
            try
            {
                if (!Directory.Exists(_outputFolder))
                    Directory.CreateDirectory(_outputFolder);
                Process.Start("explorer.exe", _outputFolder);
            }
            catch (Exception ex)
            {
                AppendLog($"[EXPLORER] Gagal membuka folder: {ex.Message}\n");
            }
        }

        private async void OnOrganizePlatformChanged(object sender, RoutedEventArgs e)
        {
            if (!IsLoaded || _isApplyingConfig) return;
            bool organize = CheckOrganizePlatform.IsChecked ?? true;
            if (_bridge != null)
            {
                await _bridge.SendCommandAsync(new { action = "set_config", key = "organize_by_platform", value = organize });
            }
            string statusStr = organize ? "diaktifkan" : "dinonaktifkan";
            ShowToast($"Pengelompokan folder platform {statusStr}.", "info");
        }

        private async void OnBrowserCookieChanged(object sender, SelectionChangedEventArgs e)
        {
            if (!IsLoaded || _isApplyingConfig) return;
            string cookie = (ComboBrowserCookie.SelectedItem as ComboBoxItem)?.Content?.ToString() ?? "Tidak Ada";
            if (cookie == "Tidak Ada") cookie = "";
            if (_bridge != null)
            {
                await _bridge.SendCommandAsync(new { action = "set_config", key = "browser_cookie", value = cookie.ToLowerInvariant() });
            }
            ShowToast("Cookie browser diperbarui.", "success");
        }

        private void OnOpenPixivWebClick(object sender, RoutedEventArgs e)
        {
            try
            {
                Process.Start(new ProcessStartInfo { FileName = "https://www.pixiv.net/", UseShellExecute = true });
            }
            catch { }
        }

        private async void OnUpdateYtdlpClick(object sender, RoutedEventArgs e)
        {
            SidebarUpdateBtn.IsEnabled = false;
            SidebarUpdateBtn.Content = "Memeriksa...";
            AppendLog("\n[UPDATE] Memeriksa pembaruan yt-dlp...\n");

            string channel = "stable";
            if (ComboYtdlpChannel?.SelectedItem is ComboBoxItem item && (item.Content?.ToString()?.Contains("Nightly") ?? false))
            {
                channel = "nightly";
            }

            await _bridge.UpdateYtdlpAsync(channel);

            await Task.Delay(4000);
            SidebarUpdateBtn.IsEnabled = true;
            SidebarUpdateBtn.Content = "Update yt-dlp";
        }

        private void OnClipboardTimerTick(object? sender, EventArgs e)
        {
            if (!_isClipboardMonitorEnabled) return;
            try
            {
                if (Clipboard.ContainsText())
                {
                    string raw = Clipboard.GetText();
                    if (!string.IsNullOrWhiteSpace(raw) && raw != _lastClipboardUrl)
                    {
                        _lastClipboardUrl = raw;
                        var match = Regex.Match(raw, @"https?://[^\s""'<>]+");
                        if (match.Success)
                        {
                            string detectedUrl = match.Value.TrimEnd('，', '。', '！', '？', '!', '?', ',', ';', ')', '"', '\'', '\r', '\n');
                            string currentUrl = UrlInput.Text.Trim();
                            if (detectedUrl != currentUrl)
                            {
                                bool isMedia = false;
                                string platName = "Media";
                                foreach (var (pattern, name, _) in _platformPatterns)
                                {
                                    if (Regex.IsMatch(detectedUrl, pattern, RegexOptions.IgnoreCase))
                                    {
                                        isMedia = true;
                                        platName = name;
                                        break;
                                    }
                                }

                                if (isMedia)
                                {
                                    UrlInput.Text = detectedUrl;
                                    _lastShareText = raw;
                                    UpdatePlatformBadge(detectedUrl);
                                    AppendLog($"[CLIPBOARD] Link {platName} terdeteksi dari Clipboard: {detectedUrl}\n");
                                    ShowToast($"Link {platName} terdeteksi dari Clipboard!", "info");

                                    // Beralih ke Studio jika sedang di tab lain
                                    OnTabStudioClick(this, null!);

                                    // Picu inspeksi media otomatis
                                    OnInspectClick(this, new RoutedEventArgs());
                                }
                            }
                        }
                    }
                }
            }
            catch { }
        }

        private async void OnClipboardMonitorChanged(object sender, RoutedEventArgs e)
        {
            if (!IsLoaded || _isApplyingConfig) return;

            _isClipboardMonitorEnabled = CheckClipboardMonitor.IsChecked == true;
            if (_isClipboardMonitorEnabled)
            {
                _clipboardTimer?.Start();
                AppendLog("[PENGATURAN] Pemantau papan klip otomatis diaktifkan.\n");
            }
            else
            {
                _clipboardTimer?.Stop();
                AppendLog("[PENGATURAN] Pemantau papan klip otomatis dinonaktifkan.\n");
            }

            if (_bridge != null)
            {
                await _bridge.SendCommandAsync(new
                {
                    action = "set_config",
                    key = "clipboard_monitor",
                    value = _isClipboardMonitorEnabled
                });
            }

            string statusStr = _isClipboardMonitorEnabled ? "diaktifkan" : "dinonaktifkan";
            ShowToast($"Pemantau papan klip {statusStr}.", "info");
        }

        private async void OnSaveProxyClick(object sender, RoutedEventArgs e)
        {
            string proxy = SettingsProxyBox.Text.Trim();
            if (_bridge != null)
            {
                await _bridge.SendCommandAsync(new
                {
                    action = "set_config",
                    key = "proxy",
                    value = proxy
                });
            }

            if (!string.IsNullOrEmpty(proxy))
            {
                AppendLog($"[PENGATURAN] Proxy disimpan: {proxy}\n");
                ShowToast($"Proxy disimpan: {proxy}", "success");
            }
            else
            {
                AppendLog("[PENGATURAN] Proxy dikosongkan (Koneksi langsung).\n");
                ShowToast("Proxy dikosongkan (Koneksi langsung).", "info");
            }
        }

        private void OnTogglePixivMaskClick(object sender, RoutedEventArgs e)
        {
            _isPixivMasked = !_isPixivMasked;
            if (_isPixivMasked)
            {
                BtnTogglePixivMask.Content = "Lihat";
                _rawPixivSession = SettingsPixivBox.Text;
                SettingsPixivBox.Text = string.IsNullOrEmpty(_rawPixivSession) ? "" : new string('•', _rawPixivSession.Length);
            }
            else
            {
                BtnTogglePixivMask.Content = "Sembunyikan";
                if (!string.IsNullOrEmpty(_rawPixivSession))
                    SettingsPixivBox.Text = _rawPixivSession;
            }
        }

        private void OnSavePixivSessionClick(object sender, RoutedEventArgs e)
        {
            string session = _isPixivMasked && !string.IsNullOrEmpty(_rawPixivSession)
                ? _rawPixivSession
                : SettingsPixivBox.Text.Trim();

            if (string.IsNullOrEmpty(session))
            {
                ShowToast("Sesi Pixiv tidak boleh kosong.", "warning");
                return;
            }

            VerifyAndSavePixivSession(session);
        }

        private async void VerifyAndSavePixivSession(string session)
        {
            if (string.IsNullOrWhiteSpace(session))
            {
                ShowToast("Sesi Pixiv tidak boleh kosong.", "warning");
                return;
            }

            BtnSavePixivSession.IsEnabled = false;
            BtnSavePixivSession.Content = "Memeriksa...";
            TxtPixivStatus.Text = "Status: Memverifikasi sesi...";
            TxtPixivStatus.Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#9CA3AF"));

            if (_bridge != null)
            {
                await _bridge.SendCommandAsync(new
                {
                    action = "set_config",
                    key = "pixiv_session",
                    value = session
                });
                await _bridge.VerifyPixivSessionAsync(session);
            }
        }

        private async void OnLoginBrowserPixivClick(object sender, RoutedEventArgs e)
        {
            BtnLoginBrowserPixiv.IsEnabled = false;
            BtnLoginBrowserPixiv.Content = "Membuka Browser...";
            TxtPixivStatus.Text = "Status: Membuka jendela login browser...";
            TxtPixivStatus.Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#9CA3AF"));

            if (_bridge != null)
            {
                await _bridge.PixivLoginBrowserAsync();
            }
        }

        private async void OnClearPixivSessionClick(object sender, RoutedEventArgs e)
        {
            _rawPixivSession = "";
            SettingsPixivBox.Text = "";
            if (_bridge != null)
            {
                await _bridge.SendCommandAsync(new
                {
                    action = "set_config",
                    key = "pixiv_session",
                    value = ""
                });
            }
            TxtPixivStatus.Text = "Status: Belum Terhubung (Sesi Kosong)";
            TxtPixivStatus.Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#6B7280"));
            ShowToast("Sesi Pixiv berhasil dihapus.", "info");
        }

        private void OnOpenGitHubRepoClick(object sender, RoutedEventArgs e)
        {
            try
            {
                Process.Start(new ProcessStartInfo { FileName = "https://github.com/SayMaven/mavdown", UseShellExecute = true });
            }
            catch (Exception ex)
            {
                AppendLog($"[EXPLORER] Gagal membuka browser: {ex.Message}\n");
            }
        }

        private void OnReportBugClick(object sender, RoutedEventArgs e)
        {
            try
            {
                Process.Start(new ProcessStartInfo { FileName = "https://github.com/SayMaven/mavdown/issues", UseShellExecute = true });
            }
            catch (Exception ex)
            {
                AppendLog($"[EXPLORER] Gagal membuka browser: {ex.Message}\n");
            }
        }
        #endregion

        #region Toast Notification (Tkinter show_toast Parity)
        public void ShowToast(string message, string toastType = "info")
        {
            Dispatcher.Invoke(() =>
            {
                if (ToastCard == null || ToastText == null) return;
                _toastTimer?.Stop();

                string colorHex = toastType switch
                {
                    "success" => "#10B981",
                    "error" => "#EF4444",
                    "warning" => "#D97706",
                    _ => "#4F46E5"
                };

                ToastCard.Background = new SolidColorBrush((Color)ColorConverter.ConvertFromString(colorHex));
                ToastText.Text = message;
                ToastCard.Visibility = Visibility.Visible;

                var fadeIn = new DoubleAnimation(0, 1, TimeSpan.FromMilliseconds(200));
                ToastCard.BeginAnimation(UIElement.OpacityProperty, fadeIn);

                _toastTimer = new DispatcherTimer
                {
                    Interval = TimeSpan.FromMilliseconds(3500)
                };
                _toastTimer.Tick += (s, e) =>
                {
                    _toastTimer.Stop();
                    DismissToast();
                };
                _toastTimer.Start();
            });
        }

        private void DismissToast()
        {
            var fadeOut = new DoubleAnimation(1, 0, TimeSpan.FromMilliseconds(250));
            fadeOut.Completed += (s, e) =>
            {
                if (ToastCard.Opacity == 0)
                    ToastCard.Visibility = Visibility.Collapsed;
            };
            ToastCard.BeginAnimation(UIElement.OpacityProperty, fadeOut);
        }

        private void OnDismissToastClick(object sender, RoutedEventArgs e)
        {
            _toastTimer?.Stop();
            DismissToast();
        }

        #region Gatefold Cover-Adaptive Dynamic Palette
        private void OnThemeModeChanged(object sender, RoutedEventArgs e)
        {
            if (RadioThemeDarkAdaptive?.IsChecked == true)
                GatePaletteService.CurrentThemeMode = "dark";
            else if (RadioThemeFullAuto?.IsChecked == true)
                GatePaletteService.CurrentThemeMode = "auto";
            else
                GatePaletteService.CurrentThemeMode = "static";

            if (MediaThumbnail?.Source is BitmapSource bmp)
            {
                if (GatePaletteService.CurrentThemeMode == "static")
                {
                    var defPalette = GatePaletteService.GetDefaultMavdownPalette();
                    GatePaletteService.ApplyToWindow(this, defPalette, true);
                }
                else
                {
                    Task.Run(() =>
                    {
                        try
                        {
                            var palette = GatePaletteService.ExtractPalette(bmp, GatePaletteService.CurrentThemeMode);
                            GatePaletteService.ApplyToWindow(this, palette, true);
                        }
                        catch (Exception ex)
                        {
                            AppendLog($"[PALETTE] Error ekstraksi palet cover: {ex.Message}\n");
                        }
                    });
                }
            }
        }

        public void UpdateCoverPaletteSwatches(List<Color> swatches)
        {
            Dispatcher.Invoke(() =>
            {
                if (CoverPaletteSwatchesPanel == null) return;
                CoverPaletteSwatchesPanel.Children.Clear();
                if (swatches == null || swatches.Count == 0)
                {
                    CoverPaletteSwatchesPanel.Children.Add(new TextBlock
                    {
                        Text = "Belum ada thumbnail media yang dimuat.",
                        FontSize = 11,
                        Foreground = (Brush)FindResource("BrushTextDim")
                    });
                    return;
                }

                foreach (var col in swatches)
                {
                    var swatchBorder = new Border
                    {
                        Width = 24,
                        Height = 24,
                        CornerRadius = new CornerRadius(5),
                        Background = new SolidColorBrush(col),
                        BorderBrush = new SolidColorBrush(Color.FromArgb(80, 255, 255, 255)),
                        BorderThickness = new Thickness(1),
                        Margin = new Thickness(0, 0, 6, 4),
                        ToolTip = $"#{col.R:X2}{col.G:X2}{col.B:X2}"
                    };
                    CoverPaletteSwatchesPanel.Children.Add(swatchBorder);
                }
            });
        }
        #endregion
        #endregion
    }
}