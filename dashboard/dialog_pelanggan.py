"""
=====================================
DIALOG SISA JATAH PELANGGAN
=====================================
Tabel status tiap NIK: pemakaian bulan ini, sisa jatah, dan status
(Siap / Cooldown / Batas tercapai). Dengan kotak pencarian.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QPushButton,
)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt

from core.statistik import detail_pelanggan
from dashboard import theme as T

WARNA_STATUS = {
    "Siap":            "#2e7d32",
    "Batas tercapai":  "#c62828",
}


class DialogPelanggan(QDialog):
    def __init__(self, excel_path: str, parent=None):
        super().__init__(parent)
        self.excel_path = excel_path
        self.setWindowTitle("Sisa Jatah Pelanggan")
        self.setMinimumSize(680, 620)
        self.setStyleSheet(f"""
            QDialog {{ background: {T.BG}; }}
            QLabel {{ color: {T.TEXT}; }}
            QLineEdit, QComboBox {{ background: white; border: 1px solid {T.GREEN_BORDER};
                border-radius: 7px; padding: 6px 10px; }}
            QTableWidget {{ background: white; border: 1px solid {T.DIVIDER};
                border-radius: 8px; gridline-color: {T.DIVIDER}; }}
            QHeaderView::section {{ background: {T.GREEN_LIGHT}; color: {T.GREEN_DARK};
                border: none; padding: 6px; font-weight: bold; }}
            QPushButton {{ background: {T.GREEN}; color: white; border: none;
                border-radius: 7px; padding: 7px 14px; font-weight: bold; }}
            QPushButton:hover {{ background: {T.GREEN_DARK}; }}
        """)
        self._data = []
        self._build()
        self._muat()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16); root.setSpacing(10)

        judul = QLabel("Sisa Jatah Pelanggan")
        judul.setStyleSheet(f"color:{T.GREEN_DARK};font-size:16px;font-weight:bold;")
        root.addWidget(judul)

        self.lbl_ringkas = QLabel(""); self.lbl_ringkas.setStyleSheet(f"color:{T.MUTED};font-size:11px;")
        root.addWidget(self.lbl_ringkas)

        # Baris pencarian + filter
        row = QHBoxLayout()
        self.cari = QLineEdit(); self.cari.setPlaceholderText("Cari nama atau NIK...")
        self.cari.textChanged.connect(self._terapkan_filter)
        row.addWidget(self.cari, 1)
        self.filter_status = QComboBox()
        self.filter_status.addItems(["Semua", "Siap", "Cooldown", "Batas tercapai"])
        self.filter_status.currentTextChanged.connect(self._terapkan_filter)
        row.addWidget(self.filter_status)
        btn_refresh = QPushButton("🔄"); btn_refresh.setFixedWidth(44)
        btn_refresh.clicked.connect(self._muat)
        row.addWidget(btn_refresh)
        root.addLayout(row)

        # Tabel
        self.tabel = QTableWidget(0, 5)
        self.tabel.setHorizontalHeaderLabels(["Nama", "NIK", "Terpakai", "Sisa", "Status"])
        self.tabel.verticalHeader().setVisible(False)
        self.tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        hh = self.tabel.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self.tabel)

        row_close = QHBoxLayout(); row_close.addStretch()
        btn = QPushButton("Tutup"); btn.clicked.connect(self.accept)
        row_close.addWidget(btn)
        root.addLayout(row_close)

    def _muat(self):
        try:
            self._data = detail_pelanggan(self.excel_path)
        except Exception as e:
            self.lbl_ringkas.setText(f"Gagal baca data: {e}")
            self._data = []
        siap = sum(1 for x in self._data if x["status"] == "Siap")
        cd   = sum(1 for x in self._data if x["status"].startswith("Cooldown"))
        bts  = sum(1 for x in self._data if x["status"] == "Batas tercapai")
        self.lbl_ringkas.setText(
            f"Total {len(self._data)} NIK — 🟢 Siap {siap}  🔒 Cooldown {cd}  🚫 Batas {bts}")
        self._terapkan_filter()

    def _terapkan_filter(self):
        q = self.cari.text().strip().lower()
        fs = self.filter_status.currentText()
        rows = []
        for x in self._data:
            if q and q not in x["nama"].lower() and q not in x["nik"]:
                continue
            if fs == "Siap" and x["status"] != "Siap":
                continue
            if fs == "Cooldown" and not x["status"].startswith("Cooldown"):
                continue
            if fs == "Batas tercapai" and x["status"] != "Batas tercapai":
                continue
            rows.append(x)

        self.tabel.setRowCount(0)
        for x in rows:
            r = self.tabel.rowCount(); self.tabel.insertRow(r)
            self.tabel.setItem(r, 0, QTableWidgetItem(x["nama"]))
            self.tabel.setItem(r, 1, QTableWidgetItem(x["nik"]))
            it_t = QTableWidgetItem(str(x["terpakai"]))
            it_t.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabel.setItem(r, 2, it_t)
            sisa = "∞" if x["sisa"] is None else str(x["sisa"])
            it_s = QTableWidgetItem(sisa); it_s.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabel.setItem(r, 3, it_s)
            it_st = QTableWidgetItem(x["status"])
            warna = WARNA_STATUS.get(x["status"], "#ef6c00" if x["status"].startswith("Cooldown") else T.TEXT)
            it_st.setForeground(QColor(warna))
            self.tabel.setItem(r, 4, it_st)
