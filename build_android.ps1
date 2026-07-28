$ErrorActionPreference = "Stop"

Write-Host "Menyiapkan direktori build bersih..."
$BuildDir = "$env:TEMP\mavdown_clean_build"

# Hapus folder jika sudah ada
if (Test-Path $BuildDir) {
    Remove-Item -Path $BuildDir -Recurse -Force
}
New-Item -ItemType Directory -Path $BuildDir | Out-Null

# Daftar file dan folder yang WAJIB dimasukkan ke dalam APK
$IncludeItems = @(
    "gui.py",
    "downloader.py",
    "config.py",
    "assets",
    "requirements.txt",
    "bin/ffmpeg",
    "mavdown.py"
)

foreach ($item in $IncludeItems) {
    if (Test-Path $item) {
        if ($item -eq "bin/ffmpeg") {
            if (!(Test-Path "$BuildDir\bin")) {
                New-Item -ItemType Directory -Path "$BuildDir\bin" | Out-Null
            }
            Copy-Item -Path $item -Destination "$BuildDir\bin\" -Force
        } else {
            Copy-Item -Path $item -Destination $BuildDir -Recurse -Force
        }
    }
}

Write-Host "Membangun APK dari lingkungan bersih..."
Push-Location $BuildDir

# Jalankan flet build
flet build apk --module-name mavdown --arch arm64-v8a

Pop-Location

# Pindahkan hasil APK kembali ke folder utama
$ApkDir = "$BuildDir\build\apk"
if (Test-Path $ApkDir) {
    $ApkFile = Get-ChildItem -Path $ApkDir -Filter "*.apk" | Select-Object -First 1
    if ($ApkFile) {
        Copy-Item -Path $ApkFile.FullName -Destination ".\mavdown_optimized.apk" -Force
        Write-Host "Selesai! APK berukuran kecil berhasil dibuat: mavdown_optimized.apk" -ForegroundColor Green
    } else {
        Write-Host "Gagal menemukan file APK hasil build di dalam $ApkDir." -ForegroundColor Red
    }
} else {
    Write-Host "Direktori $ApkDir tidak ditemukan." -ForegroundColor Red
}

# Bersihkan direktori sementara
try {
    Remove-Item -Path $BuildDir -Recurse -Force -ErrorAction SilentlyContinue
} catch {
    Write-Host "Peringatan: Beberapa file sementara terkunci oleh Gradle daemon dan tidak dapat dihapus." -ForegroundColor Yellow
}
