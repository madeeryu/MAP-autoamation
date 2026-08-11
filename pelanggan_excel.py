"""
=====================================
MAP PERTAMINA - MANAJEMEN PELANGGAN DARI EXCEL
=====================================
Membaca data NIK pelanggan dari file Excel.

Kolom Excel (Sheet1): No. | Nama | NIK KTP | Keterangan | ...
Keterangan: 'RT', 'UM', atau 'RT/UM'.

Dipakai oleh core/session_pool.py:
    from pelanggan_excel import PelangganManager
    mgr = PelangganManager(excel_path=...)
    mgr.semua_pelanggan  # → [{nik, nama, keterangan}, ...]
"""

import json
import os
import random
from datetime import datetime, date
from pathlib import Path

from openpyxl import load_workbook

EXCEL_PATH = "Data_NIK_Konsumen_LPG.xlsx"
LOG_PATH   = "log_transaksi_harian.json"

TABUNG_RT = 1
TABUNG_UM = 3


class PelangganManager:
    """Mengelola data pelanggan dari Excel."""

    def __init__(self, excel_path: str = EXCEL_PATH, sheet_name: str = "Sheet1"):
        self.excel_path = excel_path
        self.sheet_name = sheet_name
        self.semua_pelanggan: list[dict] = []
        self.log_hari_ini: dict = {}
        self._load_excel()
        self._load_log()

    # ── LOAD ──
    def _load_excel(self):
        if not Path(self.excel_path).exists():
            raise FileNotFoundError(
                f"File Excel tidak ditemukan: {self.excel_path}\n"
                f"Letakkan file di folder: {os.getcwd()}"
            )

        print(f"  [Excel] Membaca data dari: {self.excel_path}")
        wb = load_workbook(self.excel_path, read_only=True)
        # Pakai sheet yang diminta, fallback ke sheet aktif
        ws = wb[self.sheet_name] if self.sheet_name in wb.sheetnames else wb.active

        self.semua_pelanggan = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            # Kolom: No. | Nama | NIK KTP | Keterangan | ...
            if not row or len(row) < 3 or not row[2]:
                continue

            nik        = str(row[2]).strip()
            nama       = str(row[1]).strip().rstrip("/") if row[1] else ""
            keterangan = str(row[3]).strip().upper() if len(row) > 3 and row[3] else "RT"

            if len(nik) != 16 or not nik.isdigit():
                continue

            if keterangan not in ("RT", "UM", "RT/UM"):
                keterangan = "RT"

            self.semua_pelanggan.append({
                "nik":        nik,
                "nama":       nama,
                "keterangan": keterangan,
            })

        wb.close()
        print(f"  [Excel] {len(self.semua_pelanggan)} pelanggan berhasil dimuat")

        rt    = sum(1 for p in self.semua_pelanggan if p["keterangan"] == "RT")
        um    = sum(1 for p in self.semua_pelanggan if p["keterangan"] == "UM")
        rt_um = sum(1 for p in self.semua_pelanggan if p["keterangan"] == "RT/UM")
        print(f"  [Excel] RT: {rt} | UM: {um} | RT/UM (fleksibel): {rt_um}")

    def _load_log(self):
        hari_ini = date.today().isoformat()
        if Path(LOG_PATH).exists():
            try:
                with open(LOG_PATH, "r", encoding="utf-8") as f:
                    semua = json.load(f)
                self.log_hari_ini = semua.get(hari_ini, {})
            except Exception:
                self.log_hari_ini = {}
        else:
            self.log_hari_ini = {}

    def _simpan_log(self):
        hari_ini = date.today().isoformat()
        semua = {}
        if Path(LOG_PATH).exists():
            try:
                with open(LOG_PATH, "r", encoding="utf-8") as f:
                    semua = json.load(f)
            except Exception:
                pass
        semua[hari_ini] = self.log_hari_ini
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(semua, f, indent=2, ensure_ascii=False)

    # ── UTIL (opsional, dari versi standalone) ──
    def catat_hasil(self, nik, nama, kategori, jumlah_tabung, status):
        self.log_hari_ini[nik] = {
            "nama": nama, "kategori": kategori, "jumlah_tabung": jumlah_tabung,
            "status": status, "waktu": datetime.now().strftime("%H:%M:%S"),
        }
        self._simpan_log()


if __name__ == "__main__":
    try:
        mgr = PelangganManager()
        print(f"Total: {len(mgr.semua_pelanggan)} pelanggan")
    except FileNotFoundError as e:
        print(f"❌ {e}")
