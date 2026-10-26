using System.ComponentModel;
using System.Runtime.CompilerServices;

namespace Mavdown.Desktop.Models
{
    public class QueueItem : INotifyPropertyChanged
    {
        private string _status = "Menunggu";
        private string _title = "";
        private double _progress = 0;

        public string Url { get; set; } = "";
        
        public string Title
        {
            get => string.IsNullOrEmpty(_title) ? Url : _title;
            set { _title = value; OnPropertyChanged(); }
        }

        public string Status
        {
            get => _status;
            set { _status = value; OnPropertyChanged(); }
        }

        public double Progress
        {
            get => _progress;
            set { _progress = value; OnPropertyChanged(); }
        }

        public event PropertyChangedEventHandler? PropertyChanged;
        protected void OnPropertyChanged([CallerMemberName] string? name = null)
        {
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));
        }
    }
}
