"""
=====================================
THEME — Palet warna ala MyPertamina (MAP)
=====================================
Hijau olive + putih, sesuai tampilan web MAP Pertamina.
"""

# Hijau utama
GREEN            = "#5a8f22"
GREEN_DARK       = "#3f6e18"
GREEN_GRAD_TOP   = "#6fa834"
GREEN_GRAD_BOT   = "#4d7d1c"
GREEN_LIGHT      = "#eef4e2"   # panel hijau muda
GREEN_BORDER     = "#cfe0b0"

# Netral
BG               = "#eef1f4"   # latar aplikasi
CARD             = "#ffffff"
TEXT_DARK        = "#31460f"   # judul hijau gelap
TEXT             = "#3a4a55"
MUTED            = "#8a9aa5"
DIVIDER          = "#e3e8ee"

# Status
STATUS = {
    "idle":     "#90a4ae",
    "berjalan": "#2e7d32",
    "selesai":  "#1b5e20",
    "error":    "#c62828",
    "warning":  "#ef6c00",
}


def app_qss() -> str:
    """Stylesheet global aplikasi."""
    return f"""
        QMainWindow, QWidget#pusat {{ background: {BG}; }}
        QLabel {{ color: {TEXT}; }}
        QScrollArea {{ border: none; background: transparent; }}
        QScrollBar:horizontal {{ height: 12px; background: {DIVIDER};
            border-radius: 6px; margin: 0; }}
        QScrollBar::handle:horizontal {{ background: {GREEN}; border-radius: 6px;
            min-width: 40px; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        QScrollBar:vertical {{ width: 10px; background: {DIVIDER}; border-radius: 5px; }}
        QScrollBar::handle:vertical {{ background: {GREEN}; border-radius: 5px; min-height: 30px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

        QPushButton#btn_toolbar {{ background: {GREEN}; color: white;
            border: none; border-radius: 8px; padding: 8px 16px; font-weight: bold; }}
        QPushButton#btn_toolbar:hover {{ background: {GREEN_DARK}; }}
        QPushButton#btn_toolbar_stop {{ background: #c62828; color: white;
            border: none; border-radius: 8px; padding: 8px 16px; font-weight: bold; }}
        QPushButton#btn_toolbar_ghost {{ background: white; color: {GREEN_DARK};
            border: 1px solid {GREEN_BORDER}; border-radius: 8px; padding: 8px 16px; font-weight: bold; }}
        QPushButton#btn_toolbar_ghost:hover {{ background: {GREEN_LIGHT}; }}

        QSpinBox {{ background: white; color: {TEXT_DARK}; border: 1px solid {GREEN_BORDER};
            border-radius: 6px; padding: 3px 6px; }}
        QSpinBox:focus {{ border: 1px solid {GREEN}; }}
    """
