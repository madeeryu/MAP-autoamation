"""
=====================================
SESSION POOL — Alokasi NIK per Pangkalan
=====================================
Membaca daftar pelanggan dari Excel, menyaring NIK yang sedang terkunci
(dipakai sesi berjalan) dan yang masih cooldown, lalu membagikannya ke
pangkalan sebagai antrian RT/UM.

Lock antar-sesi disimpan di data/session_lock.json agar 2 pangkalan yang
jalan paralel tidak memakai NIK yang sama. Lock auto-reset saat hari berganti.

NOTE REKONSTRUKSI (2026): dibangun ulang dari ingatan sesi setelah
E:\automation hilang. Method _load dan bagian alokasi RT mengikuti sumber asli;
fungsi lock (lock_nik/get_nik_terkunci/reset_session_lock) dan bagian alokasi UM
adalah rekonstruksi setara-fungsional.
"""

import sys
import json
import random
import threading
from pathlib import Path
from datetime import date

from core.nik_database import get_nik_cooldown_aktif


# ─────────────────────────────────────────────
# PATH & SESSION LOCK
# ─────────────────────────────────────────────

def _data_dir() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent.parent
    d = base / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


DATA_DIR          = _data_dir()
SESSION_LOCK_PATH = DATA_DIR / "session_lock.json"

_lock_io = threading.Lock()


def _baca_lock() -> dict:
    if not SESSION_LOCK_PATH.exists():
        return {"tanggal": date.today().isoformat(), "nik": {}}
    try:
        with open(SESSION_LOCK_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"tanggal": date.today().isoformat(), "nik": {}}


def _tulis_lock(data: dict):
    with open(SESSION_LOCK_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _auto_reset_jika_hari_baru():
    """Reset lock jika tanggal tersimpan bukan hari ini (mis. app jalan lewat tengah malam)."""
    with _lock_io:
        data = _baca_lock()
        if data.get("tanggal") != date.today().isoformat():
            _tulis_lock({"tanggal": date.today().isoformat(), "nik": {}})


def get_nik_terkunci() -> set:
    """Set NIK yang sedang di-lock sesi berjalan."""
    with _lock_io:
        return set(_baca_lock().get("nik", {}).keys())


def lock_nik(nik: str, pangkalan_id: str) -> bool:
    """
    Coba kunci NIK untuk pangkalan tertentu.
    Return True jika berhasil (belum dikunci pihak lain), False jika sudah terkunci.
    """
    with _lock_io:
        data = _baca_lock()
        terkunci = data.setdefault("nik", {})
        if nik in terkunci:
            return False
        terkunci[nik] = pangkalan_id
        _tulis_lock(data)
        return True


def unlock_nik(nik: str):
    with _lock_io:
        data = _baca_lock()
        data.get("nik", {}).pop(nik, None)
        _tulis_lock(data)


def reset_session_lock():
    """Kosongkan seluruh lock (dipanggil saat mulai sesi baru)."""
    with _lock_io:
        _tulis_lock({"tanggal": date.today().isoformat(), "nik": {}})


# ─────────────────────────────────────────────
# SESSION POOL
# ─────────────────────────────────────────────

class SessionPool:
    def __init__(self, excel_path: str = "Data_NIK_Konsumen_LPG.xlsx"):
        self.excel_path = excel_path
        self._semua: list[dict] = []       # Semua pelanggan dari Excel
        self._pool_rt: list[dict] = []     # Kandidat RT belum terpakai
        self._pool_um: list[dict] = []     # Kandidat UM belum terpakai
        self._lock = threading.Lock()      # Thread-safe akses pool
        self._load()

    def _load(self):
        """Load dan siapkan pool pelanggan dari Excel."""
        # Auto-reset lock file jika app berjalan melewati tengah malam
        _auto_reset_jika_hari_baru()

        try:
            import os
            if getattr(sys, 'frozen', False):
                project_root = str(Path(sys.executable).parent)
            else:
                project_root = str(Path(__file__).parent.parent)
            if project_root not in sys.path:
                sys.path.insert(0, project_root)

            cwd = os.getcwd()
            if cwd not in sys.path:
                sys.path.insert(0, cwd)

            from pelanggan_excel import PelangganManager

            # Resolve path Excel: absolute → project_root → cwd
            excel_path = self.excel_path
            if not Path(excel_path).is_absolute():
                for base in [project_root, cwd]:
                    candidate = Path(base) / excel_path
                    if candidate.exists():
                        excel_path = str(candidate)
                        break
            elif not Path(excel_path).exists():
                # Path absolut tapi tidak ada (mis. dipindah ke laptop lain) →
                # cari file dengan nama sama di folder exe / cwd.
                nama = Path(excel_path).name
                for base in [project_root, cwd]:
                    candidate = Path(base) / nama
                    if candidate.exists():
                        print(f"[Pool] Path absolut tak ada, pakai: {candidate}")
                        excel_path = str(candidate)
                        break

            print(f"[Pool] Membaca Excel: {excel_path}")
            mgr = PelangganManager(excel_path=excel_path)
            self._semua = mgr.semua_pelanggan

            # Filter 1: singkirkan yang sedang di-lock sesi ini
            sudah_terkunci = get_nik_terkunci()
            # Filter 2: singkirkan NIK yang masih cooldown
            nik_cooldown = get_nik_cooldown_aktif()
            total_cooldown = len(nik_cooldown)
            if total_cooldown > 0:
                print(f"[Pool] {total_cooldown} NIK dalam cooldown — dilewati")

            tersedia = [
                p for p in self._semua
                if p["nik"] not in sudah_terkunci
                and p["nik"] not in nik_cooldown
            ]

            # Filter 3: batas tabung per pelanggan / bulan (0 = tanpa batas)
            try:
                from core.config_manager import get_settings
                batas = int(get_settings().get("batas_tabung_per_pelanggan", 0) or 0)
            except Exception:
                batas = 0
            if batas > 0:
                from core.nik_database import get_pemakaian_bulan_ini
                pakai = get_pemakaian_bulan_ini()
                sebelum = len(tersedia)
                tersedia = [p for p in tersedia if pakai.get(p["nik"], 0) < batas]
                terpotong = sebelum - len(tersedia)
                if terpotong > 0:
                    print(f"[Pool] {terpotong} NIK dilewati (sudah capai batas {batas} tabung/bulan)")

            # Pisahkan ke pool RT dan UM
            self._pool_rt = [
                p for p in tersedia
                if p["keterangan"] in ("RT", "RT/UM")
            ]
            self._pool_um = [
                p for p in tersedia
                if p["keterangan"] in ("UM", "RT/UM")
            ]

            # Acak urutan agar distribusi tidak terpola
            random.shuffle(self._pool_rt)
            random.shuffle(self._pool_um)

            print(f"[Pool] Load selesai: {len(self._semua)} total, "
                  f"tersedia RT={len(self._pool_rt)} UM={len(self._pool_um)}")

        except Exception as e:
            print(f"[Pool] ❌ Gagal load Excel: {e}")
            self._semua = []
            self._pool_rt = []
            self._pool_um = []

    def alokasi_untuk_pangkalan(
        self,
        pangkalan_id: str,
        jumlah_rt: int,
        jumlah_um: int,
    ) -> list[dict]:
        """
        Ambil dan lock sejumlah NIK untuk pangkalan tertentu.

        Returns:
            list of dict: [{nik, nama, keterangan_asli, kategori_dipakai, jumlah_tabung}]
            Urutan: semua RT dulu, baru UM (runner akan iterasi urut)
        """
        hasil = []
        tidak_bisa_lock = []

        with self._lock:
            # ── Ambil RT ──
            rt_diambil = 0
            sisa_pool_rt = []
            for p in self._pool_rt:
                if rt_diambil >= jumlah_rt:
                    sisa_pool_rt.append(p)
                    continue
                if lock_nik(p["nik"], pangkalan_id):
                    hasil.append({
                        "nik":              p["nik"],
                        "nama":             p["nama"],
                        "keterangan_asli":  p["keterangan"],
                        "kategori_dipakai": "RT",
                        "jumlah_tabung":    1,
                    })
                    rt_diambil += 1
                else:
                    tidak_bisa_lock.append(p["nik"])
            self._pool_rt = sisa_pool_rt

            # ── Ambil UM (skip yang sudah masuk RT) ──
            nik_sudah = {x["nik"] for x in hasil}
            um_diambil = 0
            sisa_pool_um = []
            for p in self._pool_um:
                if um_diambil >= jumlah_um:
                    sisa_pool_um.append(p)
                    continue
                if p["nik"] in nik_sudah:
                    continue  # RT/UM yang sudah jadi RT, skip
                if lock_nik(p["nik"], pangkalan_id):
                    hasil.append({
                        "nik":              p["nik"],
                        "nama":             p["nama"],
                        "keterangan_asli":  p["keterangan"],
                        "kategori_dipakai": "UM",
                        "jumlah_tabung":    1,
                    })
                    um_diambil += 1
                else:
                    tidak_bisa_lock.append(p["nik"])
            self._pool_um = sisa_pool_um

        if tidak_bisa_lock:
            print(f"[Pool] {len(tidak_bisa_lock)} NIK gagal di-lock (dipakai pihak lain)")
        print(f"[Pool] Alokasi {pangkalan_id[:8]}: RT={rt_diambil} UM={um_diambil} "
              f"(diminta RT={jumlah_rt} UM={jumlah_um})")
        return hasil


# ─────────────────────────────────────────────
# TEST
# ─────────────────────────────────────────────

if __name__ == "__main__":
    pool = SessionPool(excel_path="Data_NIK_Konsumen_LPG.xlsx")
    antrian = pool.alokasi_untuk_pangkalan("test-id", 5, 1)
    print(f"Antrian: {len(antrian)} NIK")
    for a in antrian:
        print("  ", a["nik"], a["kategori_dipakai"], a["nama"])
