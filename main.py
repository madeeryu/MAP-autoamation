"""
=====================================
MAP AUTOMATION — Entry Point
=====================================
Cara menjalankan:
    python main.py

Requirements:
    pip install PyQt6 playwright opencv-python openpyxl python-dotenv anthropic
    playwright install chromium
"""

import os
import sys
from pathlib import Path

# ── Set Playwright browser path SEBELUM import playwright apapun ──────────────
# Frozen (.exe): browser disimpan di folder instalasi (ms-playwright/)
# Dev mode    : JANGAN set env var — biarkan Playwright pakai lokasi default-nya
if getattr(sys, 'frozen', False):
    _base_dir    = Path(sys.executable).parent
    _browsers_dir = _base_dir / "ms-playwright"
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_browsers_dir)
else:
    _browsers_dir = Path.home() / "AppData" / "Local" / "ms-playwright"

# Pastikan folder project ada di path (untuk import modul lokal)
sys.path.insert(0, str(Path(__file__).parent))


# ─────────────────────────────────────────────
# BROWSER CHECK & INSTALL
# ─────────────────────────────────────────────

def _chromium_sudah_ada() -> bool:
    """Cek apakah folder Chromium sudah ada di browsers_dir."""
    if not _browsers_dir.exists():
        return False
    return any(
        p.is_dir() and p.name.startswith("chromium-")
        for p in _browsers_dir.iterdir()
    )


def _cari_playwright_driver() -> list:
    """
    Kembalikan command list untuk menjalankan playwright driver.
    Frozen: [node.exe, cli.js]  atau  [playwright.cmd via cmd]
    Dev   : [playwright_driver_path]
    """
    if getattr(sys, 'frozen', False):
        meipass = Path(getattr(sys, '_MEIPASS', ''))
        driver_dir = meipass / "playwright" / "driver"

        node   = driver_dir / "node.exe"
        script = driver_dir / "package" / "cli.js"
        if node.exists() and script.exists():
            return [str(node), str(script)]

        cmd_file = driver_dir / "playwright.cmd"
        if cmd_file.exists():
            return ["cmd", "/c", str(cmd_file)]

        raise FileNotFoundError(
            f"Playwright driver tidak ditemukan.\n"
            f"Folder: {driver_dir}\n"
            "Coba jalankan ulang build.bat."
        )

    from playwright._impl._driver import compute_driver_executable
    return [str(compute_driver_executable())]


def _install_browser():
    """Download & install Chromium browser (dipanggil dari thread)."""
    import subprocess
    try:
        driver_cmd = _cari_playwright_driver()
    except Exception as e:
        return False, str(e)

    try:
        env = os.environ.copy()
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(_browsers_dir)
        full_cmd = driver_cmd + ["install", "chromium"]
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
            shell=False,
        )
        if result.returncode == 0:
            return True, ""
        else:
            err = result.stderr[-800:] if result.stderr else result.stdout[-800:]
            return False, err or "Unknown error"
    except subprocess.TimeoutExpired:
        return False, "Download timeout (>10 menit). Cek koneksi internet."
    except Exception as e:
        return False, str(e)


def _cek_dan_install_browser():
    """Cek browser, jika belum ada tawarkan download. Dipanggil SETELAH QApplication dibuat."""
    if _chromium_sudah_ada():
        return

    from PyQt6.QtWidgets import QMessageBox, QProgressDialog
    from PyQt6.QtCore import Qt
    import threading

    reply = QMessageBox.question(
        None,
        "Setup Browser",
        "Browser Chromium belum terinstall.\n\n"
        "Aplikasi membutuhkan Chromium untuk otomasi transaksi MAP.\n"
        "Download sekarang? (±150 MB, butuh koneksi internet)\n\n"
        "Pilih Tidak untuk lewati — browser bisa diinstall nanti.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    )

    if reply != QMessageBox.StandardButton.Yes:
        return

    from PyQt6.QtWidgets import QApplication
    app_q = QApplication.instance()

    dlg = QProgressDialog(
        "Mengunduh dan menginstall Chromium browser...\n\n"
        "Proses ini membutuhkan beberapa menit.\n"
        "Jangan tutup aplikasi.",
        None, 0, 0,
    )
    dlg.setWindowTitle("Instalasi Browser")
    dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    dlg.setMinimumWidth(420)
    dlg.setCancelButton(None)
    dlg.show()
    app_q.processEvents()

    result_holder = {"ok": False, "error": "", "done": False}

    def run_install():
        ok, err = _install_browser()
        result_holder["ok"] = ok
        result_holder["error"] = err
        result_holder["done"] = True

    t = threading.Thread(target=run_install, daemon=True)
    t.start()

    while not result_holder["done"]:
        app_q.processEvents()
        threading.Event().wait(0.15)

    dlg.close()

    if result_holder["ok"]:
        QMessageBox.information(
            None, "Selesai",
            "✅ Chromium berhasil diinstall!\n\nAplikasi siap digunakan."
        )
    else:
        QMessageBox.warning(
            None, "Gagal Install Browser",
            f"Gagal menginstall Chromium.\n\n"
            f"Error:\n{result_holder['error']}\n\n"
            "Periksa koneksi internet dan coba buka aplikasi lagi."
        )


# ─────────────────────────────────────────────
# DEPENDENCY CHECK (mode dev)
# ─────────────────────────────────────────────

def cek_dependencies():
    """Cek library yang dibutuhkan (hanya relevan saat mode dev/script)."""
    deps = {
        "PyQt6":      "PyQt6",
        "playwright": "playwright",
        "cv2":        "opencv-python",
        "openpyxl":   "openpyxl",
    }
    kurang = []
    for modul, paket in deps.items():
        try:
            __import__(modul)
        except ImportError:
            kurang.append(paket)
    return kurang


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    # ── Log ke file saat frozen/windowed (console disembunyikan) ──
    # Semua print (pool, runner, captcha) + error terekam ke MAP_Automation.log
    # di sebelah exe, supaya masalah tetap bisa didiagnosa tanpa console.
    if getattr(sys, 'frozen', False):
        try:
            from datetime import datetime
            _logf = open(Path(sys.executable).parent / "MAP_Automation.log",
                         "a", encoding="utf-8", buffering=1)
            sys.stdout = _logf
            sys.stderr = _logf
            print(f"\n{'='*55}\n=== START {datetime.now():%Y-%m-%d %H:%M:%S} ===\n{'='*55}")
        except Exception:
            pass

    if not getattr(sys, 'frozen', False):
        kurang = cek_dependencies()
        if kurang:
            print("❌ Library berikut belum terinstall:")
            for lib in kurang:
                print(f"   pip install {lib}")
            print("\nJalankan perintah di atas, lalu coba lagi.")
            sys.exit(1)

    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QFont, QPalette, QColor, QIcon

    app = QApplication(sys.argv)
    app.setApplicationName("MAP Automation")
    app.setApplicationVersion("1.0.0")

    # Ikon aplikasi (frozen: dari _MEIPASS, dev: dari folder script)
    _icon_base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    _icon_path = _icon_base / "icon.ico"
    if _icon_path.exists():
        app.setWindowIcon(QIcon(str(_icon_path)))

    # Paksa tema TERANG (abaikan dark mode Windows) agar background tidak hitam
    app.setStyle("Fusion")
    _pal = QPalette()
    _pal.setColor(QPalette.ColorRole.Window,        QColor("#eef1f4"))
    _pal.setColor(QPalette.ColorRole.WindowText,    QColor("#3a4a55"))
    _pal.setColor(QPalette.ColorRole.Base,          QColor("#ffffff"))
    _pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#f3f6f9"))
    _pal.setColor(QPalette.ColorRole.Text,          QColor("#3a4a55"))
    _pal.setColor(QPalette.ColorRole.Button,        QColor("#ffffff"))
    _pal.setColor(QPalette.ColorRole.ButtonText,    QColor("#3a4a55"))
    _pal.setColor(QPalette.ColorRole.ToolTipBase,   QColor("#ffffff"))
    _pal.setColor(QPalette.ColorRole.ToolTipText,   QColor("#3a4a55"))
    app.setPalette(_pal)

    font = QFont("Segoe UI", 10)
    app.setFont(font)

    _cek_dan_install_browser()

    from dashboard.main_window import MainWindow

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
