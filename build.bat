@echo off
REM =====================================================
REM  BUILD MAP Automation menjadi .exe (folder self-contained)
REM  Hasil: dist\MAP_Automation\MAP_Automation.exe
REM  Sudah termasuk Python runtime + Playwright driver + browser Chromium.
REM =====================================================

REM Ganti PY kalau lokasi Python venv Anda berbeda:
set "PY=D:\miniconda3\envs\automation\python.exe"

echo.
echo [1/3] Build exe dengan PyInstaller...
"%PY%" -m PyInstaller --noconfirm --clean ^
  --name MAP_Automation ^
  --collect-all playwright ^
  --collect-all cv2 ^
  --collect-submodules PyQt6 ^
  main.py
if errorlevel 1 goto :err

echo.
echo [2/3] Menyalin browser Chromium ke dalam paket...
set "MSPW=%LOCALAPPDATA%\ms-playwright"
set "DEST=dist\MAP_Automation\ms-playwright"
mkdir "%DEST%" 2>nul
REM Salin semua build chromium headed (bukan headless_shell) + pendukung
for /d %%D in ("%MSPW%\chromium-*") do xcopy /E /I /Y "%%D" "%DEST%\%%~nxD" >nul
for /d %%D in ("%MSPW%\ffmpeg-*")   do xcopy /E /I /Y "%%D" "%DEST%\%%~nxD" >nul
for /d %%D in ("%MSPW%\winldd-*")   do xcopy /E /I /Y "%%D" "%DEST%\%%~nxD" >nul

echo.
echo [3/3] SELESAI!
echo Hasil: dist\MAP_Automation\MAP_Automation.exe
echo.
echo Cara pakai di laptop lain:
echo   1. Copy SELURUH folder dist\MAP_Automation ke laptop tujuan.
echo   2. Taruh Data_NIK_Konsumen_LPG.xlsx di sebelah MAP_Automation.exe.
echo   3. Jalankan MAP_Automation.exe, lalu Tambah Pangkalan lewat aplikasi.
goto :eof

:err
echo.
echo GAGAL build. Periksa pesan error di atas.
exit /b 1
