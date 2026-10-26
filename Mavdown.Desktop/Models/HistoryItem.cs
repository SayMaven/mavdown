using System;
using System.IO;
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
        public string SourceUrl { get; set; } = "";
        public string Timestamp { get; set; } = "";

        public string PlayButtonLabel => (IsSlide || MediaFormat == "SLIDE" || MediaFormat == "PNG" || MediaFormat == "JPG") ? "Buka" : "Putar";

        public BitmapImage? ThumbnailImage
        {
            get
            {
                try
                {
                    if (!string.IsNullOrEmpty(LocalThumbnail) && File.Exists(LocalThumbnail))
                    {
                        var bmp = new BitmapImage();
                        bmp.BeginInit();
                        bmp.CacheOption = BitmapCacheOption.OnLoad;
                        bmp.UriSource = new Uri(LocalThumbnail);
                        bmp.EndInit();
                        bmp.Freeze();
                        return bmp;
                    }
                }
                catch { }
                return null;
            }
        }
    }
}
