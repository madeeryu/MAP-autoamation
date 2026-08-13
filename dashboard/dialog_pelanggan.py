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
    QMessageBox, QFormLayout,
)
from PyQt6.QtGui import QColor, QRegularExpressionValidator
from PyQt6.QtCore import Qt, QRegularExpression

from core.statistik import detail_pelanggan
from core.app_paths import resolve_excel
from pelanggan_excel import tambah_pelanggan_ke_excel
from dashboard import theme as T

WARNA_STATUS = {
    "Siap":            "#2e7d32",
    "Batas tercapai":  "#c62828",
    "Mati":            "#616161",
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
        self.filter_status.addItems(["Semua", "Siap", "Cooldown", "Batas tercapai",
                                     "Mati", "⚠️ Selisih tgl (Excel≠NIK)"])
        self.filter_status.currentTextChanged.connect(self._terapkan_filter)
        row.addWidget(self.filter_status)
        btn_refresh = QPushButton("🔄"); btn_refresh.setFixedWidth(44)
        btn_refresh.clicked.connect(self._muat)
        row.addWidget(btn_refresh)
        btn_tambah = QPushButton("➕ Tambah Pelanggan")
        btn_tambah.clicked.connect(self._tambah_pelanggan)
        row.addWidget(btn_tambah)
        root.addLayout(row)

        # Tabel
        self._kolom = ["Nama", "NIK", "Tempat", "Tgl (Excel)", "Tgl (NIK)", "Cek", "Status"]
        self.tabel = QTableWidget(0, len(self._kolom))
        self.tabel.setHorizontalHeaderLabels(self._kolom)
        self.tabel.verticalHeader().setVisible(False)
        self.tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabel.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        hh = self.tabel.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, len(self._kolom)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
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
        siap  = sum(1 for x in self._data if x["status"] == "Siap")
        cd    = sum(1 for x in self._data if x["status"].startswith("Cooldown"))
        bts   = sum(1 for x in self._data if x["status"] == "Batas tercapai")
        mati  = sum(1 for x in self._data if x.get("mati"))
        beda  = sum(1 for x in self._data if x.get("cocok") is False)
        self.lbl_ringkas.setText(
            f"Total {len(self._data)} — 🟢 Siap {siap}  🔒 Cooldown {cd}  "
            f"🚫 Batas {bts}  ⚰️ Mati {mati}  ⚠️ Selisih tgl {beda}")
        self._terapkan_filter()

    def _terapkan_filter(self):
        q  = self.cari.text().strip().lower()
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
            if fs == "Mati" and not x.get("mati"):
                continue
            if fs.startswith("⚠️") and x.get("cocok") is not False:
                continue
            rows.append(x)

        self.tabel.setRowCount(0)
        for x in rows:
            r = self.tabel.rowCount(); self.tabel.insertRow(r)
            self.tabel.setItem(r, 0, QTableWidgetItem(x["nama"]))
            self.tabel.setItem(r, 1, QTableWidgetItem(x["nik"]))
            self.tabel.setItem(r, 2, QTableWidgetItem(x.get("tempat", "")))
            self.tabel.setItem(r, 3, QTableWidgetItem(x.get("tgl_excel", "-")))
            self.tabel.setItem(r, 4, QTableWidgetItem(x.get("tgl_nik", "-")))
            # Kolom Cek: ✓ cocok, ✗ beda, – belum ada data Excel
            cocok = x.get("cocok")
            if cocok is True:
                cek, ck = "✓", "#2e7d32"
            elif cocok is False:
                cek, ck = "✗ beda", "#c62828"
            else:
                cek, ck = "–", T.MUTED
            it_c = QTableWidgetItem(cek); it_c.setForeground(QColor(ck))
            it_c.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabel.setItem(r, 5, it_c)
            it_st = QTableWidgetItem(x["status"])
            warna = WARNA_STATUS.get(
                x["status"], "#ef6c00" if x["status"].startswith("Cooldown") else T.TEXT)
            it_st.setForeground(QColor(warna))
            self.tabel.setItem(r, 6, it_st)

    def _tambah_pelanggan(self):
        dlg = DialogTambahPelanggan(self)
        if not dlg.exec():
            return
        nik, nama, ket = dlg.get_data()
        try:
            path = resolve_excel(self.excel_path)
            tambah_pelanggan_ke_excel(path, nik, nama, ket)
        except Exception as e:
            QMessageBox.warning(self, "Gagal", str(e))
            return
        QMessageBox.information(
            self, "Berhasil",
            f"Pelanggan ditambahkan:\n{nama} — {nik} ({ket})\n\n"
            f"Tersimpan ke:\n{resolve_excel(self.excel_path)}")
        self.cari.setText(nik)   # langsung tampilkan hasilnya
        self._muat()


class DialogTambahPelanggan(QDialog):
    """Form input pelanggan baru: NIK, Nama, Keterangan."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tambah Pelanggan")
        self.setMinimumWidth(400)
        self.setStyleSheet(f"""
            QDialog {{ background: {T.BG}; }}
            QLabel {{ color: {T.TEXT}; }}
            QLineEdit, QComboBox {{ background: white; border: 1px solid {T.GREEN_BORDER};
                border-radius: 7px; padding: 7px 10px; }}
            QPushButton {{ background: {T.GREEN}; color: white; border: none;
                border-radius: 7px; padding: 8px 16px; font-weight: bold; }}
            QPushButton:hover {{ background: {T.GREEN_DARK}; }}
            QPushButton#batal {{ background: white; color: {T.GREEN_DARK};
                border: 1px solid {T.GREEN_BORDER}; }}
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18); root.setSpacing(10)
        judul = QLabel("Tambah Pelanggan Baru")
        judul.setStyleSheet(f"color:{T.GREEN_DARK};font-size:15px;font-weight:bold;")
        root.addWidget(judul)

        form = QFormLayout(); form.setSpacing(9)
        self.in_nik = QLineEdit(); self.in_nik.setPlaceholderText("16 digit NIK KTP")
        self.in_nik.setMaxLength(16)
        self.in_nik.setValidator(QRegularExpressionValidator(
            QRegularExpression(r"[0-9]{0,16}"), self))
        form.addRow("NIK KTP:", self.in_nik)
        self.in_nama = QLineEdit(); self.in_nama.setPlaceholderText("Nama pelanggan")
        form.addRow("Nama:", self.in_nama)
        self.in_ket = QComboBox(); self.in_ket.addItems(["RT", "UM", "RT/UM"])
        form.addRow("Keterangan:", self.in_ket)
        root.addLayout(form)

        ket = QLabel("RT = Rumah Tangga · UM = Usaha Mikro · RT/UM = keduanya (fleksibel)")
        ket.setStyleSheet(f"color:{T.MUTED};font-size:10px;"); ket.setWordWrap(True)
        root.addWidget(ket)

        row = QHBoxLayout(); row.addStretch()
        b1 = QPushButton("Batal"); b1.setObjectName("batal"); b1.clicked.connect(self.reject)
        b2 = QPushButton("Simpan"); b2.setDefault(True); b2.clicked.connect(self._simpan)
        row.addWidget(b1); row.addWidget(b2)
        root.addLayout(row)

    def _simpan(self):
        nik = self.in_nik.text().strip()
        if len(nik) != 16 or not nik.isdigit():
            QMessageBox.warning(self, "Validasi", "NIK harus tepat 16 digit angka.")
            return
        if not self.in_nama.text().strip():
            QMessageBox.warning(self, "Validasi", "Nama wajib diisi.")
            return
        self.accept()

    def get_data(self):
        return (self.in_nik.text().strip(), self.in_nama.text().strip(),
                self.in_ket.currentText())
