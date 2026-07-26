@echo off
echo Memulai proses kompilasi Nuitka...

:: Pastikan nuitka terinstall
python -m nuitka ^
    --standalone ^
    --windows-console-mode=disable ^
    --include-data-dir=bin=bin ^
    --include-data-dir=assets=assets ^
    --windows-icon-from-ico=assets/waifu_icon.ico ^
    --enable-plugin=tk-inter ^
    --lto=no ^
    --output-dir=dist ^
    mavdown.py

echo Memindahkan biner pendukung ke folder output...
xcopy /E /I /Y bin dist\mavdown.dist\bin

echo Selesai kompilasi Nuitka.
pause
