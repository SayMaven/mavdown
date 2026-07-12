@echo off
echo Memulai proses kompilasi Nuitka...

:: Pastikan nuitka terinstall
:: Menambahkan direktori bin dan assets agar dikompilasi masuk
python -m nuitka ^
    --standalone ^
    --windows-console-mode=disable ^
    --include-data-dir=bin=bin ^
    --include-data-dir=assets=assets ^
    --windows-icon-from-ico=assets/waifu_icon.ico ^
    --enable-plugin=tk-inter ^
    --output-dir=dist ^
    mavdown.py

echo Selesai kompilasi Nuitka.
pause
