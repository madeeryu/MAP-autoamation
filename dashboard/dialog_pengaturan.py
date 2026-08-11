"""
=====================================
DIALOG PENGATURAN
=====================================
1. Batas tabung per pelanggan / bulan (0 = tanpa batas).
2. Kelola cooldown: lihat per tanggal, buka sebagian/semua saat mendesak.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox,
    QFrame, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt

from core.config_manager import get_settings, set_setting
from core.nik_database import (
    ringkas_cooldown_per_tanggal, unlock_cooldown_tanggal,
    unlock_cooldown_terdekat, unlock_semua_cooldown, list_cooldown_aktif,
    get_pemakaian_bulan_ini,
)
from dashboard import theme as T


class DialogPengaturan(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pengaturan")
        self.setMinimumSize(560, 640)
        self.setStyleSheet(self._qss())
        self._build()
        self._refresh_cooldown()

    def _qss(self) -> str:
        return f"""
            QDialog {{ background: {T.BG}; }}
            QLabel {{ color: {T.TEXT}; }}
            QLabel#judul {{ color: {T.GREEN_DARK}; font-size: 16px; font-weight: bold; }}
            QLabel#sub {{ color: {T.MUTED}; font-size: 11px; }}
            QFrame#kartu {{ background: white; border: 1px solid {T.GREEN_BORDER};
                border-radius: 12px; }}
            QSpinBox {{ background: white; color: {T.TEXT_DARK};
                border: 1px solid {T.GREEN_BORDER}; border-radius: 6px; padding: 4px 8px; }}
            QPushButton#primer {{ background: {T.GREEN}; color: white; border: none;
                border-radius: 7px; padding: 7px 14px; font-weight: bold; }}
            QPushButton#primer:hover {{ background: {T.GREEN_DARK}; }}
            QPushButton#ghost {{ background: white; color: {T.GREEN_DARK};
                border: 1px solid {T.GREEN_BORDER}; border-radius: 7px; padding: 6px 12px; }}
            QPushButton#ghost:hover {{ background: {T.GREEN_LIGHT}; }}
            QPushButton#bahaya {{ background: #c62828; color: white; border: none;
                border-radius: 7px; padding: 7px 14px; font-weight: bold; }}
            QPushButton#mini {{ background: {T.GREEN}; color: white; border: none;
                border-radius: 5px; padding: 3px 10px; }}
            QPushButton#mini:hover {{ background: {T.GREEN_DARK}; }}
            QTableWidget {{ background: white; border: 1px solid {T.DIVIDER};
                border-radius: 8px; gridline-color: {T.DIVIDER}; }}
            QHeaderView::section {{ background: {T.GREEN_LIGHT}; color: {T.GREEN_DARK};
                border: none; padding: 6px; font-weight: bold; }}
        """

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        judul = QLabel("Pengaturan"); judul.setObjectName("judul")
        root.addWidget(judul)

        # ── Bagian 1: Batas tabung per pelanggan ──
        kartu1 = QFrame(); kartu1.setObjectName("kartu")
        k1 = QVBoxLayout(kartu1); k1.setContentsMargins(16, 14, 16, 14); k1.setSpacing(8)
        t1 = QLabel("Batas Tabung per Pelanggan"); t1.setObjectName("judul")
        t1.setStyleSheet(f"color:{T.GREEN_DARK};font-size:14px;font-weight:bold;")
        k1.addWidget(t1)
        s1 = QLabel("Maksimum tabung yang boleh dibeli tiap NIK dalam satu bulan. "
                    "NIK yang sudah mencapai batas otomatis dilewati.\n0 = tanpa batas.")
        s1.setObjectName("sub"); s1.setWordWrap(True); k1.addWidget(s1)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Batas per bulan:"))
        self.spin_batas = QSpinBox(); self.spin_batas.setRange(0, 99)
        self.spin_batas.setSuffix(" tabung")
        self.spin_batas.setValue(int(get_settings().get("batas_tabung_per_pelanggan", 3)))
        row1.addWidget(self.spin_batas)
        btn_simpan = QPushButton("Simpan"); btn_simpan.setObjectName("primer")
        btn_simpan.clicked.connect(self._simpan_batas)
        row1.addWidget(btn_simpan)
        row1.addStretch()
        btn_lihat = QPushButton("👥 Lihat Sisa Jatah Pelanggan")
        btn_lihat.setObjectName("ghost")
        btn_lihat.clicked.connect(self._lihat_pelanggan)
        row1.addWidget(btn_lihat)
        k1.addLayout(row1)
        root.addWidget(kartu1)

        # ── Bagian 2: Kelola cooldown ──
        kartu2 = QFrame(); kartu2.setObjectName("kartu")
        k2 = QVBoxLayout(kartu2); k2.setContentsMargins(16, 14, 16, 14); k2.setSpacing(8)
        t2 = QLabel("Kelola Cooldown Pelanggan")
        t2.setStyleSheet(f"color:{T.GREEN_DARK};font-size:14px;font-weight:bold;")
        k2.addWidget(t2)
        self.lbl_info_cd = QLabel(""); self.lbl_info_cd.setObjectName("sub")
        self.lbl_info_cd.setWordWrap(True); k2.addWidget(self.lbl_info_cd)

        self.tabel = QTableWidget(0, 3)
        self.tabel.setHorizontalHeaderLabels(["Tanggal bebas", "Jumlah NIK", "Aksi"])
        self.tabel.verticalHeader().setVisible(False)
        self.tabel.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabel.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        hh = self.tabel.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tabel.setFixedHeight(230)
        k2.addWidget(self.tabel)

        # Buka N terdekat
        row_n = QHBoxLayout()
        row_n.addWidget(QLabel("Buka"))
        self.spin_n = QSpinBox(); self.spin_n.setRange(1, 99999); self.spin_n.setValue(100)
        row_n.addWidget(self.spin_n)
        row_n.addWidget(QLabel("NIK dari tanggal terdekat"))
        btn_n = QPushButton("Buka"); btn_n.setObjectName("ghost")
        btn_n.clicked.connect(self._buka_terdekat)
        row_n.addWidget(btn_n)
        row_n.addStretch()
        k2.addLayout(row_n)

        # Buka semua + refresh
        row_all = QHBoxLayout()
        btn_refresh = QPushButton("🔄 Segarkan"); btn_refresh.setObjectName("ghost")
        btn_refresh.clicked.connect(self._refresh_cooldown)
        row_all.addWidget(btn_refresh)
        row_all.addStretch()
        btn_all = QPushButton("Buka SEMUA Cooldown"); btn_all.setObjectName("bahaya")
        btn_all.clicked.connect(self._buka_semua)
        row_all.addWidget(btn_all)
        k2.addLayout(row_all)

        root.addWidget(kartu2)
        root.addStretch()

        # Tutup
        row_close = QHBoxLayout(); row_close.addStretch()
        btn_tutup = QPushButton("Tutup"); btn_tutup.setObjectName("primer")
        btn_tutup.clicked.connect(self.accept)
        row_close.addWidget(btn_tutup)
        root.addLayout(row_close)

    # ─────────────────────────────────────────
    def _simpan_batas(self):
        set_setting("batas_tabung_per_pelanggan", self.spin_batas.value())
        v = self.spin_batas.value()
        pesan = ("Batas dinonaktifkan (tanpa batas)." if v == 0
                 else f"Batas disimpan: {v} tabung per pelanggan/bulan.")
        QMessageBox.information(self, "Tersimpan", pesan)

    def _lihat_pelanggan(self):
        from dashboard.dialog_pelanggan import DialogPelanggan
        from core.config_manager import get_semua_pangkalan
        pks = get_semua_pangkalan()
        excel = pks[0].get("excel_path", "Data_NIK_Konsumen_LPG.xlsx") if pks \
            else "Data_NIK_Konsumen_LPG.xlsx"
        DialogPelanggan(excel, self).exec()

    def _refresh_cooldown(self):
        ringkas = ringkas_cooldown_per_tanggal()
        total = sum(j for _, j in ringkas)
        n_pelanggan = len(get_pemakaian_bulan_ini())
        self.lbl_info_cd.setText(
            f"Total {total} NIK sedang cooldown. "
            f"{n_pelanggan} NIK sudah bertransaksi bulan ini.\n"
            f"Buka cooldown hanya saat mendesak (mis. banyak stok tapi semua NIK terkunci)."
        )
        self.tabel.setRowCount(0)
        for tanggal, jumlah in ringkas:
            r = self.tabel.rowCount(); self.tabel.insertRow(r)
            self.tabel.setItem(r, 0, QTableWidgetItem(tanggal))
            it = QTableWidgetItem(str(jumlah)); it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabel.setItem(r, 1, it)
            btn = QPushButton("Buka"); btn.setObjectName("mini")
            btn.clicked.connect(lambda _, t=tanggal: self._buka_tanggal(t))
            self.tabel.setCellWidget(r, 2, btn)

    def _buka_tanggal(self, tanggal: str):
        n = unlock_cooldown_tanggal(tanggal)
        self._refresh_cooldown()
        QMessageBox.information(self, "Cooldown dibuka",
                                f"{n} NIK (tanggal {tanggal}) dibebaskan.")

    def _buka_terdekat(self):
        n = unlock_cooldown_terdekat(self.spin_n.value())
        self._refresh_cooldown()
        QMessageBox.information(self, "Cooldown dibuka",
                                f"{n} NIK dari tanggal terdekat dibebaskan.")

    def _buka_semua(self):
        total = sum(j for _, j in ringkas_cooldown_per_tanggal())
        if total == 0:
            QMessageBox.information(self, "Info", "Tidak ada cooldown aktif.")
            return
        jawab = QMessageBox.question(
            self, "Konfirmasi",
            f"Buka SEMUA cooldown ({total} NIK)?\n\n"
            f"Ini melanggar aturan jeda 3 hari — lakukan hanya saat mendesak.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if jawab != QMessageBox.StandardButton.Yes:
            return
        n = unlock_semua_cooldown()
        self._refresh_cooldown()
        QMessageBox.information(self, "Selesai", f"{n} NIK dibebaskan dari cooldown.")
