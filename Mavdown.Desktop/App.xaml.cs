using System;
using System.IO;
using System.Windows;
using System.Windows.Threading;

namespace Mavdown.Desktop
{
    public partial class App : Application
    {
        public App()
        {
            DispatcherUnhandledException += App_DispatcherUnhandledException;
            AppDomain.CurrentDomain.UnhandledException += CurrentDomain_UnhandledException;
        }

        protected override void OnStartup(StartupEventArgs e)
        {
            base.OnStartup(e);
            try
            {
                // Initialize high-performance procedural sand grain texture brush
                Resources["BrushNoiseOverlay"] = Services.GatePaletteService.CreateNoiseBrush();
            }
            catch { }
        }

        private void App_DispatcherUnhandledException(object sender, DispatcherUnhandledExceptionEventArgs e)
        {
            LogCrash("DispatcherUnhandledException", e.Exception);
            MessageBox.Show(e.Exception.ToString(), "Mavdown Error (Dispatcher)", MessageBoxButton.OK, MessageBoxImage.Error);
            e.Handled = true;
        }

        private void CurrentDomain_UnhandledException(object sender, UnhandledExceptionEventArgs e)
        {
            if (e.ExceptionObject is Exception ex)
            {
                LogCrash("CurrentDomain_UnhandledException", ex);
                MessageBox.Show(ex.ToString(), "Mavdown Error (Domain)", MessageBoxButton.OK, MessageBoxImage.Error);
            }
        }

        private static void LogCrash(string context, Exception ex)
        {
            try
            {
                string path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "crash.log");
                File.AppendAllText(path, $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] [{context}]\n{ex}\n\n");
            }
            catch { }
        }
    }
}

