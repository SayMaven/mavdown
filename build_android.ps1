$ErrorActionPreference = "Stop"

Write-Host "Menyiapkan direktori build bersih..."
$BuildDir = "$env:TEMP\Mavdown"

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

# Gunakan ikon kustom jika tersedia
if (Test-Path "assets\waifu_icon.png") {
    Copy-Item "assets\waifu_icon.png" -Destination "assets\icon.png" -Force
    Write-Host "Ikon kustom (waifu_icon.png) diterapkan." -ForegroundColor Cyan
}

# Jalankan flet build
flet build apk --module-name mavdown --arch arm64-v8a

Pop-Location

# Pindahkan hasil APK kembali ke folder utama
$ApkDir = "$BuildDir\build\apk"
if (Test-Path $ApkDir) {
    $ApkFile = Get-ChildItem -Path $ApkDir -Filter "*.apk" | Select-Object -First 1
    if ($ApkFile) {
        Copy-Item -Path $ApkFile.FullName -Destination ".\mavdown_optimized.apk" -Force
        
        Write-Host "Mendekompilasi APK untuk mengaktifkan extractNativeLibs (Bypass Android W^X)..." -ForegroundColor Cyan
        if (!(Test-Path "$env:TEMP\apktool.jar")) {
            Invoke-WebRequest -Uri "https://bitbucket.org/iBotPeaches/apktool/downloads/apktool_2.9.3.jar" -OutFile "$env:TEMP\apktool.jar"
        }
        
        # Ekstrak APK dengan apktool (-s agar cepat karena tidak perlu decompile smali)
        $ApkToolDir = "$env:TEMP\mavdown_apk_unpacked"
        if (Test-Path $ApkToolDir) { Remove-Item -Path $ApkToolDir -Recurse -Force }
        java -jar "$env:TEMP\apktool.jar" d -s ".\mavdown_optimized.apk" -o $ApkToolDir -f | Out-Null
        
        Write-Host "Memodifikasi AndroidManifest.xml dan memasukkan FFmpeg..." -ForegroundColor Cyan
        python -c "import xml.etree.ElementTree as ET; ET.register_namespace('android', 'http://schemas.android.com/apk/res/android'); tree = ET.parse(r'$ApkToolDir\AndroidManifest.xml'); root = tree.getroot(); app = root.find('application'); app.set('{http://schemas.android.com/apk/res/android}extractNativeLibs', 'true'); tree.write(r'$ApkToolDir\AndroidManifest.xml', xml_declaration=True, encoding='utf-8')"
        
        $LibDir = "$ApkToolDir\lib\arm64-v8a"
        if (!(Test-Path $LibDir)) { New-Item -ItemType Directory -Path $LibDir -Force | Out-Null }
        Copy-Item -Path "bin\ffmpeg" -Destination "$LibDir\libffmpeg.so" -Force
        
        Write-Host "Membangun kembali APK..." -ForegroundColor Cyan
        java -jar "$env:TEMP\apktool.jar" b $ApkToolDir -o ".\mavdown_optimized.apk" | Out-Null
        
        Write-Host "Menandatangani ulang APK menggunakan uber-apk-signer..." -ForegroundColor Cyan
        if (!(Test-Path "$env:TEMP\uber-apk-signer.jar")) {
            Invoke-WebRequest -Uri "https://github.com/patrickfav/uber-apk-signer/releases/download/v1.3.0/uber-apk-signer-1.3.0.jar" -OutFile "$env:TEMP\uber-apk-signer.jar"
        }
        java -jar "$env:TEMP\uber-apk-signer.jar" -a ".\mavdown_optimized.apk" --allowResign --overwrite | Out-Null
        
        Write-Host "Selesai! APK berhasil dibuat dan disuntik FFmpeg dengan dukungan penuh Android 10+: mavdown_optimized.apk" -ForegroundColor Green
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
