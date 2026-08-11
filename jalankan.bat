@echo off
REM =====================================================
REM  Jalankan MAP Automation dari SOURCE (kode terbaru)
REM  Untuk dipakai/tes cepat di laptop dev tanpa build exe.
REM  Console tampil supaya log [Pool]/[CAPTCHA]/[STEP] kelihatan.
REM =====================================================
cd /d "%~dp0"

set "PY=D:\miniconda3\envs\automation\python.exe"
if not exist "%PY%" (
  echo Python venv tidak ditemukan di %PY%
  echo Edit jalankan.bat dan sesuaikan path PY, atau pakai: python main.py
  pause
  exit /b 1
)

"%PY%" main.py
echo.
echo === Aplikasi ditutup ===
pause
