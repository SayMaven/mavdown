using System;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using System.Windows;

namespace Mavdown.Desktop.Services
{
    public class PythonBridge : IDisposable
    {
        private Process? _process;
        private StreamWriter? _stdin;
        private readonly string _pythonScriptPath;
        private readonly string _workingDir;
        private bool _isDisposed;

        public event Action<string>? OnLog;
        public event Action<double, string, string, string>? OnProgress; // value, text, speed, eta
        public event Action<JsonObject>? OnInfoData;
        public event Action<string, string>? OnThumbReady; // path, base64
        public event Action? OnDownloadFinish;
        public event Action<string>? OnDownloadError;
        public event Action<JsonArray>? OnHistoryLoaded;
        public event Action<JsonObject>? OnConfigLoaded;
        public event Action? OnEngineReady;
        public event Action<string>? OnInfoTitle;
        public event Action<string>? OnInspectError;
        public event Action? OnInspectComplete;
        public event Action<string>? OnPixivLoginStatus;
        public event Action<bool, string?, string?>? OnPixivLoginComplete;
        public event Action<bool, string>? OnPixivVerifyResult;

        public bool IsReady { get; private set; }

        public PythonBridge(string rootDir)
        {
            _workingDir = rootDir;
            _pythonScriptPath = Path.Combine(rootDir, "mav_core.py");
        }

        public void Start()
        {
            if (_process != null && !_process.HasExited)
                return;

            string exePath = Path.Combine(_workingDir, "mav_core.exe");
            if (!File.Exists(exePath))
            {
                string baseExe = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "mav_core.exe");
                if (File.Exists(baseExe))
                {
                    exePath = baseExe;
                }
            }
            ProcessStartInfo psi;

            if (File.Exists(exePath))
            {
                psi = new ProcessStartInfo
                {
                    FileName = exePath,
                    Arguments = "--daemon",
                    WorkingDirectory = _workingDir,
                    UseShellExecute = false,
                    RedirectStandardInput = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    CreateNoWindow = true,
                    StandardOutputEncoding = System.Text.Encoding.UTF8,
                    StandardInputEncoding = System.Text.Encoding.UTF8
                };
            }
            else
            {
                // Fallback ke python interpreter
                psi = new ProcessStartInfo
                {
                    FileName = "python",
                    Arguments = $"-u \"{_pythonScriptPath}\" --daemon",
                    WorkingDirectory = _workingDir,
                    UseShellExecute = false,
                    RedirectStandardInput = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    CreateNoWindow = true,
                    StandardOutputEncoding = System.Text.Encoding.UTF8,
                    StandardInputEncoding = System.Text.Encoding.UTF8
                };
            }

            // Sanitasi PATH dari untrusted junction points (seperti scoop\apps) dan prioritaskan bin internal
            string? rawPath = Environment.GetEnvironmentVariable("PATH");
            if (!string.IsNullOrEmpty(rawPath))
            {
                var cleanEntries = rawPath.Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries)
                    .Where(p => !p.Contains(@"scoop\apps", StringComparison.OrdinalIgnoreCase))
                    .ToList();

                string binDir = Path.Combine(_workingDir, "bin");
                if (Directory.Exists(binDir) && !cleanEntries.Contains(binDir))
                {
                    cleanEntries.Insert(0, binDir);
                }
                psi.EnvironmentVariables["PATH"] = string.Join(Path.PathSeparator, cleanEntries);
            }

            _process = new Process { StartInfo = psi, EnableRaisingEvents = true };
            _process.OutputDataReceived += (s, e) => HandleIncomingLine(e.Data);
            _process.ErrorDataReceived += (s, e) =>
            {
                if (!string.IsNullOrWhiteSpace(e.Data))
                {
                    Application.Current?.Dispatcher.Invoke(() => OnLog?.Invoke($"[CORE ERR] {e.Data}\n"));
                }
            };

            _process.Start();
            _stdin = _process.StandardInput;
            _process.BeginOutputReadLine();
            _process.BeginErrorReadLine();
        }

        private void HandleIncomingLine(string? line)
        {
            if (string.IsNullOrWhiteSpace(line)) return;

            try
            {
                var doc = JsonNode.Parse(line)?.AsObject();
                if (doc == null) return;

                string eventType = doc["event"]?.ToString() ?? "";

                Application.Current?.Dispatcher.Invoke(() =>
                {
                    switch (eventType)
                    {
                        case "ready":
                            IsReady = true;
                            OnEngineReady?.Invoke();
                            break;

                        case "log":
                            OnLog?.Invoke(doc["text"]?.ToString() ?? "");
                            break;

                        case "progress":
                            double val = doc["value"]?.GetValue<double>() ?? 0.0;
                            string text = doc["text"]?.ToString() ?? "";
                            string speed = doc["speed"]?.ToString() ?? "";
                            string eta = doc["eta"]?.ToString() ?? "";
                            OnProgress?.Invoke(val, text, speed, eta);
                            break;

                        case "info_data":
                            if (doc["data"] is JsonObject dataObj)
                                OnInfoData?.Invoke(dataObj);
                            break;

                        case "info_title":
                            OnInfoTitle?.Invoke(doc["title"]?.ToString() ?? "");
                            break;

                        case "inspect_error":
                            OnInspectError?.Invoke(doc["error"]?.ToString() ?? "Terjadi kesalahan saat inspeksi.");
                            break;

                        case "inspect_complete":
                            OnInspectComplete?.Invoke();
                            break;

                        case "info_thumb":
                            string path = doc["path"]?.ToString() ?? "";
                            string b64 = doc["base64"]?.ToString() ?? "";
                            OnThumbReady?.Invoke(path, b64);
                            break;

                        case "download_finish":
                            OnDownloadFinish?.Invoke();
                            break;

                        case "download_error":
                            OnDownloadError?.Invoke(doc["message"]?.ToString() ?? "Unduhan gagal.");
                            break;

                        case "history_list":
                            if (doc["entries"] is JsonArray arr)
                                OnHistoryLoaded?.Invoke(arr);
                            break;

                        case "config_data":
                            if (doc["config"] is JsonObject cfgObj)
                                OnConfigLoaded?.Invoke(cfgObj);
                            break;

                        case "pixiv_login_status":
                            OnPixivLoginStatus?.Invoke(doc["status"]?.ToString() ?? "");
                            break;

                        case "pixiv_login_complete":
                            bool loginOk = doc["success"]?.GetValue<bool>() ?? false;
                            string? errOrSession = loginOk ? doc["session"]?.ToString() : doc["error"]?.ToString();
                            string? userName = doc["user_name"]?.ToString();
                            OnPixivLoginComplete?.Invoke(loginOk, errOrSession, userName);
                            break;

                        case "pixiv_verify_result":
                            bool verifyValid = doc["valid"]?.GetValue<bool>() ?? false;
                            string verifyMsg = doc["message"]?.ToString() ?? "";
                            OnPixivVerifyResult?.Invoke(verifyValid, verifyMsg);
                            break;
                    }
                });
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"[JSON Parse Error] {ex.Message} -> {line}");
            }
        }

        public async Task SendCommandAsync(object payload)
        {
            if (_stdin == null || _process == null || _process.HasExited)
                return;

            string json = JsonSerializer.Serialize(payload);
            await _stdin.WriteLineAsync(json);
            await _stdin.FlushAsync();
        }

        public async Task InspectUrlAsync(string url, string shareText = "", string cookie = "Tidak Ada")
        {
            await SendCommandAsync(new
            {
                action = "inspect",
                url = url,
                share_text = shareText,
                cookie = cookie,
                id = Guid.NewGuid().ToString("N")[..8]
            });
        }

        public async Task StartDownloadAsync(
            string url,
            string mode = "video",
            string audioFormat = "mp3",
            string res = "best",
            string vcodec = "auto",
            string acodec = "auto",
            string container = "mp4",
            bool downloadSubs = false,
            bool embedSubs = true,
            string subsLang = "id,en",
            bool embedThumb = true,
            bool useAria2 = true,
            bool downloadPlaylist = false,
            string customPath = "",
            string cookie = "Tidak Ada",
            string ugoiraFormat = "mp4")
        {
            await SendCommandAsync(new
            {
                action = "download",
                url = url,
                mode = mode,
                audio_format = audioFormat,
                res = res,
                vcodec = vcodec,
                acodec = acodec,
                container = container,
                download_subs = downloadSubs,
                embed_subs = embedSubs,
                subs_lang = subsLang,
                embed_thumb = embedThumb,
                use_aria2 = useAria2,
                download_playlist = downloadPlaylist,
                custom_path = customPath,
                cookie = cookie,
                ugoira_format = ugoiraFormat,
                id = Guid.NewGuid().ToString("N")[..8]
            });
        }

        public async Task UpdateYtdlpAsync(string channel = "stable")
        {
            await SendCommandAsync(new { action = "update_ytdlp", channel = channel, id = Guid.NewGuid().ToString("N")[..8] });
        }

        public async Task CancelDownloadAsync()
        {
            await SendCommandAsync(new { action = "cancel" });
        }

        public async Task RequestHistoryAsync(string query = "")
        {
            await SendCommandAsync(new { action = "get_history", query = query });
        }

        public async Task RequestConfigAsync()
        {
            await SendCommandAsync(new { action = "get_config" });
        }

        public async Task PixivLoginBrowserAsync()
        {
            await SendCommandAsync(new { action = "pixiv_login_browser", id = Guid.NewGuid().ToString("N")[..8] });
        }

        public async Task VerifyPixivSessionAsync(string session = "")
        {
            await SendCommandAsync(new { action = "verify_pixiv_session", session = session, id = Guid.NewGuid().ToString("N")[..8] });
        }

        public void Dispose()
        {
            if (_isDisposed) return;
            _isDisposed = true;

            try
            {
                if (_stdin != null)
                {
                    _stdin.WriteLine("{\"action\":\"exit\"}");
                    _stdin.Flush();
                }
                if (_process != null && !_process.HasExited)
                {
                    if (!_process.WaitForExit(1000))
                        _process.Kill();
                }
            }
            catch { }
            finally
            {
                _process?.Dispose();
            }
        }
    }
}
