"""
=====================================
PANGKALAN CARD — Kartu Kontrol per Pangkalan (tema MyPertamina)
=====================================
Kartu vertikal berjejer horizontal: header hijau + avatar inisial, lalu body
putih berisi statistik bulan ini, stok MAP, input stok kiriman, stok awal
(patokan), tombol mulai/stop, dan log mini.

Sinyal:
    mulai_diminta(pangkalan_id, stok, rt_sudah, um_sudah)
    stop_diminta(pangkalan_id)
"""

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QTextEdit, QMessageBox, QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QColor

from core.config_manager import get_history_bulan_ini, set_offset_awal
from core.komposisi_helper import hitung_komposisi_sesi
from dashboard import theme as T

CARD_WIDTH = 320


class PangkalanCard(QFrame):
    mulai_diminta = pyqtSignal(str, int, int, int)
    stop_diminta  = pyqtSignal(str)

    def __init__(self, pangkalan: dict, parent=None):
        super().__init__(parent)
        self.pangkalan = pangkalan
        self.setObjectName("card")
        self.setFixedWidth(CARD_WIDTH)
        self.setStyleSheet(self._qss())
        self._shadow()
        self._build()
        self._refresh_history()

    # ─────────────────────────────────────────
    def _shadow(self):
        eff = QGraphicsDropShadowEffect(self)
        eff.setBlurRadius(24)
        eff.setXOffset(0); eff.setYOffset(6)
        eff.setColor(QColor(60, 90, 30, 45))
        self.setGraphicsEffect(eff)

    def _qss(self) -> str:
        return f"""
            QFrame#card {{ background: {T.CARD}; border-radius: 16px; }}
            QFrame#header {{
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 {T.GREEN_GRAD_TOP}, stop:1 {T.GREEN_GRAD_BOT});
                border-top-left-radius: 16px; border-top-right-radius: 16px;
            }}
            QLabel#avatar {{ background: white; border-radius: 26px;
                color: {T.GREEN_DARK}; font-size: 20px; font-weight: bold; }}
            QLabel#nama {{ color: white; font-size: 15px; font-weight: bold; }}
            QLabel#statmini {{ color: {T.TEXT_DARK}; font-size: 13px; font-weight: bold; }}
            QLabel#statlbl {{ color: {T.MUTED}; font-size: 10px; }}
            QFrame#panelstat {{ background: {T.GREEN_LIGHT}; border-radius: 10px; }}
            QTextEdit#log_box {{ background: #10161d; color: #c8d6c0; border: none;
                border-radius: 8px; font-size: 10px; padding: 4px; }}
            QPushButton#btn_mulai {{ background: {T.GREEN}; color: white; border: none;
                border-radius: 8px; font-weight: bold; }}
            QPushButton#btn_mulai:hover {{ background: {T.GREEN_DARK}; }}
            QPushButton#btn_stop {{ background: #c62828; color: white; border: none;
                border-radius: 8px; font-weight: bold; }}
            QPushButton#btn_kecil {{ background: {T.GREEN}; color: white; border: none;
                border-radius: 6px; }}
            QPushButton#btn_kecil:hover {{ background: {T.GREEN_DARK}; }}
            QPushButton#btn_kecil:disabled {{ background: #cfd8cc; color: #90a4ae; }}
        """

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header hijau ──
        header = QFrame(); header.setObjectName("header")
        header.setFixedHeight(112)
        h = QVBoxLayout(header)
        h.setContentsMargins(12, 12, 12, 12); h.setSpacing(4)

        top = QHBoxLayout()
        nama = self.pangkalan.get("nama", "Pangkalan")
        inisial = "".join([w[0] for w in nama.split()[:2]]).upper() or "P"
        self.avatar = QLabel(inisial); self.avatar.setObjectName("avatar")
        self.avatar.setFixedSize(52, 52)
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addWidget(self.avatar)
        top.addStretch()
        self.lbl_status = QLabel(); top.addWidget(self.lbl_status,
                                                  alignment=Qt.AlignmentFlag.AlignTop)
        h.addLayout(top)

        self.lbl_nama = QLabel(nama); self.lbl_nama.setObjectName("nama")
        h.addWidget(self.lbl_nama)
        h.addStretch()
        root.addWidget(header)
        self._set_badge("idle")

        # ── Body putih ──
        body = QWidgetBody()
        b = QVBoxLayout(body)
        b.setContentsMargins(14, 12, 14, 14); b.setSpacing(9)

        # Panel statistik bulan ini
        panel = QFrame(); panel.setObjectName("panelstat")
        pl = QHBoxLayout(panel); pl.setContentsMargins(12, 8, 12, 8)
        self.stat_rt = self._stat("RT bln ini", "0")
        self.stat_um = self._stat("UM bln ini", "0")
        self.stat_map = self._stat("Stok MAP", "—")
        for s in (self.stat_rt, self.stat_um, self.stat_map):
            pl.addLayout(s["lay"]); pl.addStretch()
        b.addWidget(panel)

        # Indikator ketersediaan NIK
        self.lbl_ketersediaan = QLabel("")
        self.lbl_ketersediaan.setStyleSheet(f"color:{T.TEXT};font-size:10px;")
        b.addWidget(self.lbl_ketersediaan)

        # Stok kiriman
        row_stok = QHBoxLayout()
        l1 = QLabel("Stok kiriman:"); l1.setStyleSheet(f"color:{T.MUTED};font-size:11px;")
        row_stok.addWidget(l1)
        self.spin_stok = QSpinBox(); self.spin_stok.setRange(0, 9999)
        self.spin_stok.setToolTip("Jumlah tabung kiriman agen hari ini")
        row_stok.addWidget(self.spin_stok); row_stok.addStretch()
        b.addLayout(row_stok)

        self.lbl_komposisi = QLabel("")
        self.lbl_komposisi.setStyleSheet(f"color:{T.GREEN_DARK};font-size:10px;")
        b.addWidget(self.lbl_komposisi)

        # Stok awal (offset)
        row_off = QHBoxLayout(); row_off.setSpacing(4)
        l2 = QLabel("Awal:"); l2.setStyleSheet(f"color:{T.MUTED};font-size:11px;")
        l2.setToolTip("Stok awal = total tabung terjual sampai kini (patokan mutlak). "
                      "Update untuk sinkronisasi; TIDAK ditambah transaksi sebelumnya.")
        row_off.addWidget(l2)
        self.spin_rt_sudah = QSpinBox(); self.spin_rt_sudah.setRange(0, 99999)
        self.spin_rt_sudah.setPrefix("RT "); row_off.addWidget(self.spin_rt_sudah)
        self.spin_um_sudah = QSpinBox(); self.spin_um_sudah.setRange(0, 99999)
        self.spin_um_sudah.setPrefix("UM "); row_off.addWidget(self.spin_um_sudah)

        self.btn_unlock_awal = QPushButton("🔒"); self.btn_unlock_awal.setObjectName("btn_kecil")
        self.btn_unlock_awal.setFixedSize(28, 28)
        self.btn_unlock_awal.setToolTip("Klik untuk edit stok awal")
        self.btn_unlock_awal.clicked.connect(self._buka_kunci_offset)
        row_off.addWidget(self.btn_unlock_awal)
        self.btn_simpan_awal = QPushButton("💾"); self.btn_simpan_awal.setObjectName("btn_kecil")
        self.btn_simpan_awal.setFixedSize(28, 28)
        self.btn_simpan_awal.setToolTip("Simpan/sinkronkan stok awal (patokan mutlak)")
        self.btn_simpan_awal.clicked.connect(self._simpan_offset_awal)
        self.btn_simpan_awal.setVisible(False)
        row_off.addWidget(self.btn_simpan_awal)
        row_off.addStretch()
        b.addLayout(row_off)

        # Tombol mulai/stop
        self.btn_mulai = QPushButton("▶  Mulai Sesi"); self.btn_mulai.setObjectName("btn_mulai")
        self.btn_mulai.setFixedHeight(36); self.btn_mulai.clicked.connect(self._klik_mulai)
        b.addWidget(self.btn_mulai)
        self.btn_stop = QPushButton("⏹  Stop"); self.btn_stop.setObjectName("btn_stop")
        self.btn_stop.setFixedHeight(36)
        self.btn_stop.clicked.connect(lambda: self.stop_diminta.emit(self.pangkalan["id"]))
        self.btn_stop.setVisible(False)
        b.addWidget(self.btn_stop)

        # Log
        self.log_box = QTextEdit(); self.log_box.setObjectName("log_box")
        self.log_box.setReadOnly(True); self.log_box.setFixedHeight(96)
        b.addWidget(self.log_box)

        root.addWidget(body)

        self.spin_stok.valueChanged.connect(self._update_komposisi_preview)
        self.spin_rt_sudah.valueChanged.connect(self._update_komposisi_preview)
        self.spin_um_sudah.valueChanged.connect(self._update_komposisi_preview)

    def _stat(self, label: str, value: str) -> dict:
        lay = QVBoxLayout(); lay.setSpacing(0)
        lbl = QLabel(label); lbl.setObjectName("statlbl")
        val = QLabel(value); val.setObjectName("statmini")
        lay.addWidget(lbl); lay.addWidget(val)
        return {"lay": lay, "lbl": lbl, "val": val}

    # ─────────────────────────────────────────
    def _set_badge(self, status: str):
        warna = T.STATUS.get(status, T.STATUS["idle"])
        teks = {"idle": "IDLE", "berjalan": "BERJALAN", "selesai": "SELESAI",
                "error": "ERROR", "warning": "PERINGATAN"}.get(status, status.upper())
        self.lbl_status.setText(teks)
        self.lbl_status.setStyleSheet(
            f"background:{warna};color:white;border-radius:9px;"
            f"padding:2px 9px;font-size:10px;font-weight:bold;")

    def set_status(self, status: str):
        self._set_badge(status)
        berjalan = (status == "berjalan")
        self.btn_mulai.setVisible(not berjalan)
        self.btn_stop.setVisible(berjalan)
        self.spin_stok.setEnabled(not berjalan)
        self.btn_simpan_awal.setEnabled(not berjalan)
        self.btn_unlock_awal.setEnabled(not berjalan)

    def set_stok_map(self, stok: int):
        self.stat_map["val"].setText(str(stok) if stok >= 0 else "—")

    def refresh_ketersediaan(self):
        """Hitung & tampilkan ringkasan ketersediaan NIK (baca Excel + cooldown + batas)."""
        try:
            from core.statistik import ringkas_ketersediaan
            r = ringkas_ketersediaan(self.pangkalan.get("excel_path",
                                                        "Data_NIK_Konsumen_LPG.xlsx"))
            self.lbl_ketersediaan.setText(
                f"🟢 Siap {r['siap']}   🔒 Cooldown {r['cooldown']}   🚫 Batas {r['batas']}")
        except Exception as e:
            self.lbl_ketersediaan.setText(f"<i>ketersediaan: {e}</i>")

    def tambah_log(self, pesan: str, level: str = "info"):
        warna = {"success": "#8bc34a", "warning": "#ffb74d",
                 "error": "#ef5350"}.get(level, "#c8d6c0")
        self.log_box.append(f'<span style="color:{warna}">{pesan}</span>')
        sb = self.log_box.verticalScrollBar(); sb.setValue(sb.maximum())

    # ─────────────────────────────────────────
    def _update_komposisi_preview(self):
        stok = self.spin_stok.value()
        if stok <= 0:
            self.lbl_komposisi.setText(""); return
        k = hitung_komposisi_sesi(self.spin_rt_sudah.value(),
                                  self.spin_um_sudah.value(), stok)
        self.lbl_komposisi.setText(f"Sesi ini: RT {k.rt_sesi} + UM {k.um_sesi} = {stok}")

    def _klik_mulai(self):
        stok = self.spin_stok.value()
        if stok <= 0:
            self.tambah_log("⚠️ Isi jumlah stok terlebih dahulu!", "warning"); return
        h = get_history_bulan_ini(self.pangkalan["id"])
        self.mulai_diminta.emit(self.pangkalan["id"], stok,
                                h.get("rt_sudah", 0), h.get("um_sudah", 0))

    def _kunci_offset(self):
        self.spin_rt_sudah.setReadOnly(True); self.spin_um_sudah.setReadOnly(True)
        self.spin_rt_sudah.setStyleSheet(f"QSpinBox{{color:{T.MUTED};}}")
        self.spin_um_sudah.setStyleSheet(f"QSpinBox{{color:{T.MUTED};}}")
        self.btn_unlock_awal.setVisible(True); self.btn_simpan_awal.setVisible(False)

    def _buka_kunci_offset(self):
        self.spin_rt_sudah.setReadOnly(False); self.spin_um_sudah.setReadOnly(False)
        self.spin_rt_sudah.setStyleSheet(""); self.spin_um_sudah.setStyleSheet("")
        self.btn_unlock_awal.setVisible(False); self.btn_simpan_awal.setVisible(True)

    def _refresh_history(self):
        h = get_history_bulan_ini(self.pangkalan["id"])
        rt = h.get("rt_sudah", 0); um = h.get("um_sudah", 0)
        rt_o = h.get("rt_offset", 0); um_o = h.get("um_offset", 0)
        total = rt + um
        if total > 0:
            self.stat_rt["val"].setText(f"{rt} ({rt/total*100:.0f}%)")
            self.stat_um["val"].setText(f"{um} ({um/total*100:.0f}%)")
        else:
            self.stat_rt["val"].setText("0"); self.stat_um["val"].setText("0")
        self.spin_rt_sudah.setValue(rt_o); self.spin_um_sudah.setValue(um_o)
        if rt_o > 0 or um_o > 0:
            self._kunci_offset()
        else:
            self._buka_kunci_offset()

    def _simpan_offset_awal(self):
        rt_o = self.spin_rt_sudah.value(); um_o = self.spin_um_sudah.value()
        h = get_history_bulan_ini(self.pangkalan["id"])
        rt_lama = h.get("rt_offset", 0); um_lama = h.get("um_offset", 0)
        if (rt_lama > 0 or um_lama > 0) and (rt_o != rt_lama or um_o != um_lama):
            jawab = QMessageBox.question(
                self, "Konfirmasi Ubah Stok Awal",
                f"Stok awal (patokan) akan disinkronkan:\n"
                f"  RT lama = {rt_lama} → RT baru = {rt_o}\n"
                f"  UM lama = {um_lama} → UM baru = {um_o}\n\n"
                f"Nilai baru menjadi total acuan (tidak ditambah transaksi\n"
                f"sebelumnya). Lanjutkan?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if jawab != QMessageBox.StandardButton.Yes:
                return
        set_offset_awal(self.pangkalan["id"], rt_o, um_o)
        self.tambah_log(f"💾 Stok awal disimpan: RT={rt_o} UM={um_o}", "success")
        self._refresh_history(); self._update_komposisi_preview()


class QWidgetBody(QFrame):
    """Body putih dengan sudut bawah membulat.

    PENTING: pakai selector #cardbody agar 'background' TIDAK mewarisi ke
    anak-anaknya (kalau tanpa selector, tombol & log ikut jadi putih → hilang).
    """
    def __init__(self):
        super().__init__()
        self.setObjectName("cardbody")
        self.setStyleSheet(
            f"QFrame#cardbody {{ background:{T.CARD};"
            f"border-bottom-left-radius:16px; border-bottom-right-radius:16px; }}")
