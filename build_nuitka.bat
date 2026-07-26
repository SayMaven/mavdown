@echo off
echo Memulai proses kompilasi Nuitka...

:: Pastikan nuitka terinstall
:: Mencegah C compiler out of heap space (C1002) pada google.genai.types
python -m nuitka ^
    --standalone ^
    --windows-console-mode=disable ^
    --include-data-dir=bin=bin ^
    --include-data-dir=assets=assets ^
    --windows-icon-from-ico=assets/waifu_icon.ico ^
    --enable-plugin=tk-inter ^
    --nofollow-import-to=google.genai.types ^
    --lto=no ^
    --output-dir=dist ^
    mavdown.py

echo Memindahkan biner pendukung ke folder output...
xcopy /E /I /Y bin dist\mavdown.dist\bin

echo Selesai kompilasi Nuitka.
pause
