"""
=====================================
NIK DATABASE — Cooldown & Log Transaksi
=====================================
Menyimpan status cooldown NIK ke data/nik_cooldown.csv dan log transaksi
ke data/nik_transaksi.csv.

Aturan cooldown:
  - RT beli sukses      → 3 hari (tidak boleh beli lagi < 3 hari)
  - UM beli sukses      → 1 hari (tidak boleh dipakai lagi di hari yang sama)
  - TOLAK / NIB / gagal → 3 hari

Cara cek: NIK dianggap masih cooldown jika  aktif_lagi > tanggal_hari_ini.
(Pada tanggal aktif_lagi itu sendiri, NIK sudah bebas.)

NOTE REKONSTRUKSI (2026): dibangun ulang dari ingatan sesi setelah
E:\automation hilang. Konstanta cooldown, is_cooldown, get_nik_cooldown_aktif,
get_info_cooldown mengikuti sumber asli; _baca_csv/_tulis_csv/catat_transaksi
adalah rekonstruksi setara-fungsional.
"""

import csv
import sys
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Optional


# ─────────────────────────────────────────────
# PATH
# ─────────────────────────────────────────────

def _data_dir() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent.parent
    d = base / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


DATA_DIR       = _data_dir()
COOLDOWN_PATH  = DATA_DIR / "nik_cooldown.csv"
TRANSAKSI_PATH = DATA_DIR / "nik_transaksi.csv"

# ── Aturan cooldown (hari) ──
COOLDOWN_HARI           = 3  # default / backward compat
COOLDOWN_HARI_TOLAK     = 3  # TOLAK / NIB → 3 hari
COOLDOWN_HARI_RT_SUKSES = 3  # RT beli sukses → minimal 3 hari sebelum beli lagi
COOLDOWN_HARI_UM_SUKSES = 1  # UM beli sukses → tidak boleh dipakai lagi hari yang sama

COOLDOWN_FIELDS = [
    "nik",
    "pangkalan_id",
    "alasan",
    "tanggal",       # tanggal transaksi terakhir (kena cooldown)
    "aktif_lagi",    # tanggal NIK bebas kembali (ISO date)
]

TRANSAKSI_FIELDS = [
    "nik",
    "pangkalan_id",
    "status",         # sukses / tolak / nib / gagal
    "kategori",       # RT / UM
    "jumlah_tabung",  # untuk hitung batas per pelanggan/bulan
    "alasan",
    "waktu",
]


# ─────────────────────────────────────────────
# CSV HELPER
# ─────────────────────────────────────────────

def _baca_csv(path: Path, fields: list) -> list:
    if not path.exists():
        return []
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _tulis_csv(path: Path, fields: list, rows: list):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            # hanya tulis field yang dikenal
            w.writerow({k: r.get(k, "") for k in fields})


def init_db():
    """Pastikan file CSV ada beserta header."""
    if not COOLDOWN_PATH.exists():
        _tulis_csv(COOLDOWN_PATH, COOLDOWN_FIELDS, [])
    if not TRANSAKSI_PATH.exists():
        _tulis_csv(TRANSAKSI_PATH, TRANSAKSI_FIELDS, [])


# ─────────────────────────────────────────────
# LOG TRANSAKSI + SET COOLDOWN
# ─────────────────────────────────────────────

def catat_transaksi(nik: str, pangkalan_id: str, status: str,
                    kategori: str = "", alasan: str = "", jumlah_tabung: int = 1):
    """
    Catat hasil transaksi 1 NIK dan pasang cooldown sesuai hasilnya.

    status        : "sukses" / "tolak" / "nib" / "gagal"
    kategori      : "RT" / "UM"  (relevan saat sukses untuk lama cooldown)
    jumlah_tabung : jumlah tabung transaksi (untuk batas per pelanggan/bulan)
    """
    # 1. Log transaksi
    rows = _baca_csv(TRANSAKSI_PATH, TRANSAKSI_FIELDS)
    rows.append({
        "nik":           nik,
        "pangkalan_id":  pangkalan_id,
        "status":        status,
        "kategori":      kategori,
        "jumlah_tabung": jumlah_tabung,
        "alasan":        alasan,
        "waktu":         datetime.now().isoformat(timespec="seconds"),
    })
    _tulis_csv(TRANSAKSI_PATH, TRANSAKSI_FIELDS, rows)

    # 2. Pasang cooldown
    if status == "sukses":
        if kategori == "RT":
            set_cooldown(nik, pangkalan_id, "sukses_rt", hari=COOLDOWN_HARI_RT_SUKSES)
        elif kategori == "UM":
            set_cooldown(nik, pangkalan_id, "sukses_um", hari=COOLDOWN_HARI_UM_SUKSES)
        else:
            set_cooldown(nik, pangkalan_id, "sukses", hari=COOLDOWN_HARI)
    else:
        # tolak / nib / gagal
        set_cooldown(nik, pangkalan_id, alasan or status, hari=COOLDOWN_HARI_TOLAK)


# ─────────────────────────────────────────────
# COOLDOWN NIK
# ─────────────────────────────────────────────

def set_cooldown(nik: str, pangkalan_id: str, alasan: str, hari: int = None):
    """Pasang / perbarui cooldown untuk 1 NIK."""
    if hari is None:
        hari = COOLDOWN_HARI_TOLAK

    today      = date.today()
    aktif_lagi = (today + timedelta(days=hari)).isoformat()

    rows = _baca_csv(COOLDOWN_PATH, COOLDOWN_FIELDS)

    # Update kalau NIK sudah ada, append kalau baru
    ketemu = False
    for r in rows:
        if r["nik"] == nik:
            r["pangkalan_id"] = pangkalan_id
            r["alasan"]       = alasan
            r["tanggal"]      = today.isoformat()
            r["aktif_lagi"]   = aktif_lagi
            ketemu = True
            break
    if not ketemu:
        rows.append({
            "nik":          nik,
            "pangkalan_id": pangkalan_id,
            "alasan":       alasan,
            "tanggal":      today.isoformat(),
            "aktif_lagi":   aktif_lagi,
        })

    _tulis_csv(COOLDOWN_PATH, COOLDOWN_FIELDS, rows)


def is_cooldown(nik: str) -> bool:
    today = date.today().isoformat()
    rows  = _baca_csv(COOLDOWN_PATH, COOLDOWN_FIELDS)
    return any(r["nik"] == nik and r["aktif_lagi"] > today for r in rows)


def get_nik_cooldown_aktif() -> set:
    today = date.today().isoformat()
    rows  = _baca_csv(COOLDOWN_PATH, COOLDOWN_FIELDS)
    return {r["nik"] for r in rows if r["aktif_lagi"] > today}


def get_info_cooldown(nik: str) -> Optional[dict]:
    rows = _baca_csv(COOLDOWN_PATH, COOLDOWN_FIELDS)
    for r in rows:
        if r["nik"] == nik:
            return r
    return None


def bersihkan_cooldown_kadaluarsa():
    """Hapus baris cooldown yang sudah lewat (opsional housekeeping)."""
    today = date.today().isoformat()
    rows  = _baca_csv(COOLDOWN_PATH, COOLDOWN_FIELDS)
    aktif = [r for r in rows if r["aktif_lagi"] > today]
    _tulis_csv(COOLDOWN_PATH, COOLDOWN_FIELDS, aktif)


# ─────────────────────────────────────────────
# BATAS PEMAKAIAN PER PELANGGAN / BULAN
# ─────────────────────────────────────────────

def get_pemakaian_bulan_ini() -> dict:
    """
    Jumlah tabung SUKSES per NIK pada bulan berjalan.
    Returns: {nik: total_tabung}
    """
    bulan = date.today().strftime("%Y-%m")
    hasil: dict = {}
    for r in _baca_csv(TRANSAKSI_PATH, TRANSAKSI_FIELDS):
        if r.get("status") != "sukses":
            continue
        if not (r.get("waktu", "").startswith(bulan)):
            continue
        try:
            jt = int(r.get("jumlah_tabung") or 1)
        except (ValueError, TypeError):
            jt = 1
        nik = r.get("nik", "")
        hasil[nik] = hasil.get(nik, 0) + jt
    return hasil


def batas_tercapai(nik: str, batas: int) -> bool:
    """True jika NIK sudah mencapai/melewati batas tabung bulan ini (batas>0)."""
    if not batas or batas <= 0:
        return False
    return get_pemakaian_bulan_ini().get(nik, 0) >= batas


# ─────────────────────────────────────────────
# KELOLA COOLDOWN (untuk UI Pengaturan)
# ─────────────────────────────────────────────

def list_cooldown_aktif() -> list:
    """Daftar cooldown yang masih aktif, urut tanggal bebas terdekat."""
    today = date.today().isoformat()
    rows = [r for r in _baca_csv(COOLDOWN_PATH, COOLDOWN_FIELDS)
            if r.get("aktif_lagi", "") > today]
    rows.sort(key=lambda r: r.get("aktif_lagi", ""))
    return rows


def ringkas_cooldown_per_tanggal() -> list:
    """Ringkasan jumlah NIK cooldown per tanggal bebas. [(tanggal, jumlah), ...]"""
    from collections import Counter
    c = Counter(r["aktif_lagi"] for r in list_cooldown_aktif())
    return sorted(c.items())


def unlock_cooldown_niks(niks) -> int:
    """Buka cooldown untuk sekumpulan NIK. Return jumlah yang dihapus."""
    niks = set(niks)
    rows = _baca_csv(COOLDOWN_PATH, COOLDOWN_FIELDS)
    sisa = [r for r in rows if r.get("nik") not in niks]
    dihapus = len(rows) - len(sisa)
    if dihapus:
        _tulis_csv(COOLDOWN_PATH, COOLDOWN_FIELDS, sisa)
    return dihapus


def unlock_cooldown_tanggal(tanggal: str) -> int:
    """Buka semua cooldown yang bebasnya pada tanggal tertentu."""
    rows = _baca_csv(COOLDOWN_PATH, COOLDOWN_FIELDS)
    sisa = [r for r in rows if r.get("aktif_lagi") != tanggal]
    dihapus = len(rows) - len(sisa)
    if dihapus:
        _tulis_csv(COOLDOWN_PATH, COOLDOWN_FIELDS, sisa)
    return dihapus


def unlock_cooldown_terdekat(jumlah: int) -> int:
    """Buka `jumlah` NIK cooldown dari tanggal bebas TERDEKAT dulu."""
    aktif = list_cooldown_aktif()          # sudah urut terdekat
    target = {r["nik"] for r in aktif[:max(0, jumlah)]}
    return unlock_cooldown_niks(target)


def unlock_semua_cooldown() -> int:
    """Kosongkan seluruh cooldown. Return jumlah yang dihapus."""
    rows = _baca_csv(COOLDOWN_PATH, COOLDOWN_FIELDS)
    _tulis_csv(COOLDOWN_PATH, COOLDOWN_FIELDS, [])
    return len(rows)


# ─────────────────────────────────────────────
# TEST
# ─────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    print("Cooldown aktif:", len(get_nik_cooldown_aktif()))
