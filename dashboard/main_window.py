"""
=====================================
MAIN WINDOW — Dashboard MAP Automation
=====================================
Jendela utama: daftar kartu pangkalan, tombol tambah/mulai/stop, dan
orkestrasi PangkalanRunner. Tiap runner berjalan di THREAD terpisah
(masing-masing membuka browser sendiri) agar beberapa pangkalan bisa
paralel dan UI tetap responsif. Callback runner (dari worker thread)
diteruskan ke UI lewat sinyal Qt yang thread-safe.

NOTE REKONSTRUKSI (2026): dibangun ulang untuk mencocokkan interface
PangkalanRunner (run_sync + callback on_log/on_progress/on_selesai) dan
PangkalanCard yang sudah direkonstruksi.
"""

import sys
import threading
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QPushButton, QLabel, QSpinBox, QMessageBox,
)
from PyQt6.QtCore import QObject, pyqtSignal, Qt, QTimer

from dashboard import theme as T

from core.config_manager import (
    get_semua_pangkalan, tambah_pangkalan, hapus_pangkalan,
    tambah_sesi, get_history_bulan_ini,
)
from core.session_pool import SessionPool, reset_session_lock
from core.komposisi_helper import hitung_komposisi_sesi
from core.app_paths import resolve_excel
from core.runner import PangkalanRunner

from dashboard.pangkalan_card import PangkalanCard
from dashboard.dialog_pangkalan import DialogPangkalan


class RunnerSignals(QObject):
    """Jembatan thread-safe dari worker thread → UI."""
    log      = pyqtSignal(str, str, str)                       # pid, pesan, level
    progress = pyqtSignal(str, int, int, int, int, int, int, int)  # pid,sukses,tolak,gagal,selesai,total,rt,um
    selesai  = pyqtSignal(str, dict)                           # pid, hasil


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MAP Automation — Dashboard")
        self.resize(1100, 760)

        self._cards: dict[str, PangkalanCard] = {}
        self._runners: dict[str, PangkalanRunner] = {}
        self._threads: dict[str, threading.Thread] = {}

        self._signals = RunnerSignals()
        self._signals.log.connect(self._on_log)
        self._signals.progress.connect(self._on_progress)
        self._signals.selesai.connect(self._on_selesai)

        self._build()
        self._muat_kartu()

    # ─────────────────────────────────────────
    def _build(self):
        self.setStyleSheet(T.app_qss())

        pusat = QWidget(); pusat.setObjectName("pusat")
        self.setCentralWidget(pusat)
        root = QVBoxLayout(pusat)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)

        # ── Toolbar ──
        bar = QHBoxLayout()
        judul = QLabel("MAP Automation")
        judul.setStyleSheet(f"font-size: 21px; font-weight: bold; color: {T.GREEN_DARK};")
        sub = QLabel("Merchant Apps Pertamina — Otomasi")
        sub.setStyleSheet(f"color: {T.MUTED}; font-size: 11px;")
        kolom_judul = QVBoxLayout(); kolom_judul.setSpacing(0)
        kolom_judul.addWidget(judul); kolom_judul.addWidget(sub)
        bar.addLayout(kolom_judul)
        bar.addStretch()

        lbl_jeda = QLabel("Jeda (dtk):"); lbl_jeda.setStyleSheet(f"color:{T.MUTED};")
        bar.addWidget(lbl_jeda)
        self.spin_jeda = QSpinBox(); self.spin_jeda.setRange(0, 120); self.spin_jeda.setValue(3)
        bar.addWidget(self.spin_jeda)

        btn_pengaturan = QPushButton("⚙ Pengaturan")
        btn_pengaturan.setObjectName("btn_toolbar_ghost")
        btn_pengaturan.clicked.connect(self._buka_pengaturan)
        bar.addWidget(btn_pengaturan)

        btn_tambah = QPushButton("➕ Tambah Pangkalan")
        btn_tambah.setObjectName("btn_toolbar_ghost")
        btn_tambah.clicked.connect(self._tambah_pangkalan)
        bar.addWidget(btn_tambah)

        self.btn_mulai_semua = QPushButton("▶▶ Mulai Semua")
        self.btn_mulai_semua.setObjectName("btn_toolbar")
        self.btn_mulai_semua.clicked.connect(self._mulai_semua)
        bar.addWidget(self.btn_mulai_semua)

        self.btn_stop_semua = QPushButton("⏹ Stop Semua")
        self.btn_stop_semua.setObjectName("btn_toolbar_stop")
        self.btn_stop_semua.clicked.connect(self._stop_semua)
        self.btn_stop_semua.setVisible(False)
        bar.addWidget(self.btn_stop_semua)

        root.addLayout(bar)

        # ── Area kartu: scroll HORIZONTAL, kartu berjejer ke kanan ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._row_host = QWidget()
        self._row = QHBoxLayout(self._row_host)
        self._row.setSpacing(16)
        self._row.setContentsMargins(4, 8, 4, 8)
        self._row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self._row_host)
        root.addWidget(scroll)

        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Siap. Tambah pangkalan atau mulai sesi.")

    def _muat_kartu(self):
        # Bersihkan row
        while self._row.count():
            item = self._row.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._cards.clear()

        pangkalan = get_semua_pangkalan()
        if not pangkalan:
            kosong = QLabel("Belum ada pangkalan. Klik '➕ Tambah Pangkalan'.")
            kosong.setAlignment(Qt.AlignmentFlag.AlignCenter)
            kosong.setStyleSheet(f"color: {T.MUTED}; padding: 40px; font-size: 13px;")
            self._row.addWidget(kosong)
            return

        for p in pangkalan:
            card = PangkalanCard(p)
            card.mulai_diminta.connect(self._mulai_satu)
            card.stop_diminta.connect(self._stop_satu)
            self._cards[p["id"]] = card
            self._row.addWidget(card, alignment=Qt.AlignmentFlag.AlignTop)
        self._row.addStretch()
        # Hitung ketersediaan setelah window tampil (baca Excel — jangan blok UI)
        QTimer.singleShot(60, self._refresh_semua_ketersediaan)

    def _refresh_semua_ketersediaan(self):
        for c in self._cards.values():
            c.refresh_ketersediaan()

    # ─────────────────────────────────────────
    def _buka_pengaturan(self):
        from dashboard.dialog_pengaturan import DialogPengaturan
        DialogPengaturan(self).exec()
        # Batas/cooldown mungkin berubah → segarkan indikator kartu
        self._refresh_semua_ketersediaan()

    def _tambah_pangkalan(self):
        dlg = DialogPangkalan(self)
        if dlg.exec():
            d = dlg.get_data()
            tambah_pangkalan(d["nama"], d["telepon"], d["password"], d["excel_path"])
            self._muat_kartu()
            self.status_bar.showMessage(f"Pangkalan '{d['nama']}' ditambahkan.")

    # ── build & jalankan runner ──
    def _buat_runner(self, card: PangkalanCard, antrian: list, sesi_id: str, pool) -> PangkalanRunner:
        p = card.pangkalan
        sig = self._signals
        pid = p["id"]

        runner = PangkalanRunner(
            pangkalan_id=pid,
            nama=p.get("nama", "Pangkalan"),
            phone=p.get("telepon", ""),
            password=p.get("password", ""),
            antrian=antrian,
            stok=card.spin_stok.value(),
            sesi_id=sesi_id,
            pool=pool,
            on_log=lambda pid, msg, lvl: sig.log.emit(pid, msg, lvl),
            on_progress=lambda pid, s, t, g, sel, tot, rt, um: sig.progress.emit(pid, s, t, g, sel, tot, rt, um),
            on_selesai=lambda pid, hasil: sig.selesai.emit(pid, hasil),
        )
        return runner

    def _jalankan_runner_thread(self, runner: PangkalanRunner):
        pid = runner.pangkalan_id
        self._runners[pid] = runner
        t = threading.Thread(target=runner.run_sync, daemon=True)
        self._threads[pid] = t
        t.start()

    def _mulai_satu(self, pangkalan_id: str, stok: int, rt_sudah: int, um_sudah: int):
        card = self._cards.get(pangkalan_id)
        if not card:
            return
        reset_session_lock()

        excel_abs = resolve_excel(card.pangkalan.get("excel_path", "Data_NIK_Konsumen_LPG.xlsx"))
        pool = SessionPool(excel_path=excel_abs)

        k = hitung_komposisi_sesi(rt_sudah, um_sudah, stok)
        sesi_id = tambah_sesi(pangkalan_id, stok)
        antrian = pool.alokasi_untuk_pangkalan(pangkalan_id, k.rt_sesi, k.um_sesi)

        runner = self._buat_runner(card, antrian, sesi_id, pool)
        card.set_status("berjalan")
        self._jalankan_runner_thread(runner)
        self.status_bar.showMessage(
            f"▶ {card.pangkalan['nama']}: stok={stok} RT={k.rt_sesi} UM={k.um_sesi}"
        )

    def _mulai_semua(self):
        cards_aktif = [c for c in self._cards.values() if c.spin_stok.value() > 0]
        if not cards_aktif:
            QMessageBox.information(self, "Info", "Isi jumlah stok minimal 1 pangkalan dulu.")
            return
        konfirmasi = QMessageBox.question(
            self, "Mulai Semua",
            f"Mulai sesi untuk {len(cards_aktif)} pangkalan?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if konfirmasi != QMessageBox.StandardButton.Yes:
            return

        reset_session_lock()
        excel_abs = resolve_excel(cards_aktif[0].pangkalan.get("excel_path", "Data_NIK_Konsumen_LPG.xlsx"))
        pool = SessionPool(excel_path=excel_abs)

        for card in cards_aktif:
            pid    = card.pangkalan["id"]
            stok   = card.spin_stok.value()
            h      = get_history_bulan_ini(pid)
            k      = hitung_komposisi_sesi(h.get("rt_sudah", 0), h.get("um_sudah", 0), stok)
            sesi_id = tambah_sesi(pid, stok)
            antrian = pool.alokasi_untuk_pangkalan(pid, k.rt_sesi, k.um_sesi)
            runner  = self._buat_runner(card, antrian, sesi_id, pool)
            card.set_status("berjalan")
            self._jalankan_runner_thread(runner)

        self.btn_mulai_semua.setVisible(False)
        self.btn_stop_semua.setVisible(True)
        self.status_bar.showMessage(f"🚀 Mulai semua: {len(cards_aktif)} pangkalan")

    def _stop_satu(self, pangkalan_id: str):
        r = self._runners.get(pangkalan_id)
        if r:
            r.stop()

    def _stop_semua(self):
        for r in self._runners.values():
            r.stop()
        self.status_bar.showMessage("⏹ Stop semua diminta")

    # ── slot sinyal (di UI thread) ──
    def _on_log(self, pid: str, pesan: str, level: str):
        card = self._cards.get(pid)
        if card:
            card.tambah_log(pesan, level)

    def _on_progress(self, pid, sukses, tolak, gagal, selesai, total, rt, um):
        card = self._cards.get(pid)
        if card:
            card.lbl_komposisi.setText(
                f"✅{sukses} ⚠️{tolak} ❌{gagal}  ({selesai}/{total})"
            )

    def _on_selesai(self, pid: str, hasil: dict):
        card = self._cards.get(pid)
        if card:
            card.set_status("selesai")
            card._refresh_history()
            card.refresh_ketersediaan()
        self._runners.pop(pid, None)
        self._threads.pop(pid, None)
        if not self._runners:
            self.btn_mulai_semua.setVisible(True)
            self.btn_stop_semua.setVisible(False)
            self.status_bar.showMessage("Semua sesi selesai.")
