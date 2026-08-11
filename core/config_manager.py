"""
=====================================
CONFIG MANAGER — Data Pangkalan & History
=====================================
Menyimpan konfigurasi pangkalan dan history transaksi per bulan ke
data/pangkalan_config.json.

Struktur config:
{
  "pangkalan": [
    {
      "id": "<uuid>",
      "nama": "Addenin",
      "telepon": "0812xxxx",
      "password": "xxxx",
      "excel_path": "Data_NIK_Konsumen_LPG.xlsx",
      "aktif": true,
      "history": {
        "2026-06": {
          "rt_offset": 711,   # stok awal manual (patokan mutlak)
          "um_offset": 92,
          "rt_sesi":   219,   # akumulasi transaksi bot bulan ini
          "um_sesi":   8,
          "rt_sudah":  930,   # = rt_offset + rt_sesi
          "um_sudah":  100,
          "sesi": [ {id, tanggal, stok, rt_dijalankan, um_dijalankan,
                     sukses, tolak, gagal, status}, ... ]
        }
      }
    }
  ]
}

NOTE REKONSTRUKSI (2026): file ini dibangun ulang dari ingatan sesi setelah
E:\automation hilang. Fungsi get_history_bulan_ini / set_offset_awal /
selesaikan_sesi mengikuti sumber asli; load/save/tambah_pangkalan adalah
rekonstruksi setara-fungsional — verifikasi bila menemukan keanehan.
"""

import json
import uuid
from pathlib import Path
from datetime import date


# ─────────────────────────────────────────────
# PATH
# ─────────────────────────────────────────────
import sys

def _data_dir() -> Path:
    """Folder data/ di samping main.py (frozen) atau root project (dev)."""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent.parent
    d = base / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


DATA_DIR    = _data_dir()
CONFIG_PATH = DATA_DIR / "pangkalan_config.json"


# ─────────────────────────────────────────────
# LOAD / SAVE
# ─────────────────────────────────────────────

def load_config() -> dict:
    """Baca config JSON. Jika belum ada, kembalikan struktur kosong."""
    if not CONFIG_PATH.exists():
        return {"pangkalan": []}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if "pangkalan" not in cfg:
            cfg["pangkalan"] = []
        return cfg
    except Exception as e:
        print(f"[Config] ⚠️  Gagal baca config: {e}")
        return {"pangkalan": []}


def save_config(cfg: dict):
    """Tulis config JSON (atomik via file sementara)."""
    tmp = CONFIG_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    tmp.replace(CONFIG_PATH)


# ─────────────────────────────────────────────
# PANGKALAN CRUD
# ─────────────────────────────────────────────

def get_pangkalan_by_id(pangkalan_id: str) -> dict | None:
    for p in load_config()["pangkalan"]:
        if p["id"] == pangkalan_id:
            return p
    return None


def get_semua_pangkalan() -> list:
    return load_config()["pangkalan"]


def tambah_pangkalan(nama: str, telepon: str = "", password: str = "",
                     excel_path: str = "Data_NIK_Konsumen_LPG.xlsx") -> dict:
    """Tambah pangkalan baru dan simpan. Return dict pangkalan baru."""
    cfg = load_config()
    baru = {
        "id":         str(uuid.uuid4()),
        "nama":       nama,
        "telepon":    telepon,
        "password":   password,
        "excel_path": excel_path,
        "aktif":      True,
        "history":    {},
    }
    cfg["pangkalan"].append(baru)
    save_config(cfg)
    print(f"[Config] Pangkalan ditambah: {nama} ({baru['id'][:8]}...)")
    return baru


def update_pangkalan(pangkalan_id: str, **kwargs):
    """Update field pangkalan (nama, telepon, password, excel_path, aktif)."""
    cfg = load_config()
    for p in cfg["pangkalan"]:
        if p["id"] == pangkalan_id:
            for k, v in kwargs.items():
                p[k] = v
            save_config(cfg)
            return
    print(f"[Config] update_pangkalan: {pangkalan_id} tidak ditemukan")


def hapus_pangkalan(pangkalan_id: str):
    cfg = load_config()
    cfg["pangkalan"] = [p for p in cfg["pangkalan"] if p["id"] != pangkalan_id]
    save_config(cfg)


# ─────────────────────────────────────────────
# HISTORY BULANAN
# ─────────────────────────────────────────────

def _bulan_key() -> str:
    """Return key bulan format: '2026-05'"""
    return date.today().strftime("%Y-%m")


def get_history_bulan_ini(pangkalan_id: str) -> dict:
    """
    Ambil history bulan ini untuk pangkalan tertentu.
    Jika bulan baru / belum ada, return dict kosong (otomatis mulai dari 0).

    Struktur return:
      {
        "rt_offset":  int,   # transaksi manual sebelum pakai sistem (tetap)
        "um_offset":  int,
        "rt_sesi":    int,   # akumulasi RT dari sesi-sesi yang sudah jalan
        "um_sesi":    int,
        "rt_sudah":   int,   # total = rt_offset + rt_sesi
        "um_sudah":   int,   # total = um_offset + um_sesi
        "sesi":       list,
      }
    """
    p = get_pangkalan_by_id(pangkalan_id)
    if not p:
        return {"rt_offset": 0, "um_offset": 0, "rt_sesi": 0, "um_sesi": 0,
                "rt_sudah": 0, "um_sudah": 0, "sesi": []}

    bulan  = _bulan_key()
    history = p.get("history", {})

    if bulan not in history:
        return {"rt_offset": 0, "um_offset": 0, "rt_sesi": 0, "um_sesi": 0,
                "rt_sudah": 0, "um_sudah": 0, "sesi": []}

    h = history[bulan]

    # Support format lama (belum ada rt_offset) — migrasi otomatis
    rt_offset = h.get("rt_offset", 0)
    um_offset = h.get("um_offset", 0)
    rt_sesi   = h.get("rt_sesi",   0)
    um_sesi   = h.get("um_sesi",   0)

    # Format lama: rt_sudah berisi gabungan (offset + sesi), tidak ada rt_sesi
    # Deteksi: jika rt_sesi == 0 tapi rt_sudah > 0 dan tidak ada rt_offset tersimpan
    if rt_sesi == 0 and rt_offset == 0 and h.get("rt_sudah", 0) > 0:
        rt_sesi_calc = sum(s.get("rt_dijalankan", 0) for s in h.get("sesi", []))
        um_sesi_calc = sum(s.get("um_dijalankan", 0) for s in h.get("sesi", []))
        rt_offset = max(0, h.get("rt_sudah", 0) - rt_sesi_calc)
        um_offset = max(0, h.get("um_sudah", 0) - um_sesi_calc)
        rt_sesi   = rt_sesi_calc
        um_sesi   = um_sesi_calc

    return {
        "rt_offset": rt_offset,
        "um_offset": um_offset,
        "rt_sesi":   rt_sesi,
        "um_sesi":   um_sesi,
        "rt_sudah":  rt_offset + rt_sesi,
        "um_sudah":  um_offset + um_sesi,
        "sesi":      h.get("sesi", []),
    }


def set_offset_awal(pangkalan_id: str, rt_offset: int, um_offset: int):
    """
    Set jumlah RT dan UM sebagai PATOKAN AWAL (nilai mutlak) bulan berjalan.

    Stok awal di sini diperlakukan sebagai total tabung yang SUDAH terjual
    sampai saat input (sinkronisasi manual). Karena itu akumulasi sesi bot
    (rt_sesi / um_sesi) DIRESET ke 0 — supaya angka yang diinput TIDAK
    ditambahkan lagi dengan transaksi yang sudah terhitung sebelumnya.

    Transaksi bot berikutnya akan menambah dari patokan ini.
    Riwayat sesi (list "sesi") tetap dipertahankan sebagai log historis.
    """
    cfg  = load_config()
    bulan = _bulan_key()
    for p in cfg["pangkalan"]:
        if p["id"] == pangkalan_id:
            if "history" not in p:
                p["history"] = {}
            if bulan not in p["history"]:
                p["history"][bulan] = {
                    "rt_offset": 0, "um_offset": 0,
                    "rt_sesi":   0, "um_sesi":   0,
                    "rt_sudah":  0, "um_sudah":  0,
                    "sesi": []
                }
            h = p["history"][bulan]
            h["rt_offset"] = rt_offset
            h["um_offset"] = um_offset
            # Reset akumulasi sesi: stok awal adalah nilai mutlak/patokan,
            # bukan ditambah dengan transaksi bot yang sudah terhitung sebelumnya.
            h["rt_sesi"]   = 0
            h["um_sesi"]   = 0
            h["rt_sudah"]  = rt_offset
            h["um_sudah"]  = um_offset
            save_config(cfg)
            print(f"[Config] {p['nama']}: stok awal (patokan) RT={rt_offset}, UM={um_offset}")
            return
    print(f"[Config] Pangkalan {pangkalan_id} tidak ditemukan")


# Alias lama agar kode lain yang mungkin pakai set_sudah_diinput tidak pecah
def set_sudah_diinput(pangkalan_id: str, rt_sudah: int, um_sudah: int):
    """Alias ke set_offset_awal (backward compat)."""
    set_offset_awal(pangkalan_id, rt_sudah, um_sudah)


# ─────────────────────────────────────────────
# SESI
# ─────────────────────────────────────────────

def tambah_sesi(pangkalan_id: str, stok: int) -> str:
    """
    Daftarkan sesi baru (stok kiriman baru dari agen).

    Returns:
        sesi_id (UUID string)
    """
    cfg   = load_config()
    bulan = _bulan_key()
    sesi_id = str(uuid.uuid4())
    for p in cfg["pangkalan"]:
        if p["id"] == pangkalan_id:
            if "history" not in p:
                p["history"] = {}
            if bulan not in p["history"]:
                p["history"][bulan] = {
                    "rt_offset": 0, "um_offset": 0,
                    "rt_sesi":   0, "um_sesi":   0,
                    "rt_sudah":  0, "um_sudah":  0,
                    "sesi": []
                }
            p["history"][bulan]["sesi"].append({
                "id":            sesi_id,
                "tanggal":       date.today().isoformat(),
                "stok":          stok,
                "rt_dijalankan": 0,
                "um_dijalankan": 0,
                "sukses":        0,
                "tolak":         0,
                "gagal":         0,
                "status":        "berjalan",
            })
            save_config(cfg)
            return sesi_id
    print(f"[Config] tambah_sesi: pangkalan {pangkalan_id} tidak ditemukan")
    return sesi_id


def update_sesi(pangkalan_id: str, sesi_id: str, **kwargs):
    """
    Update field dalam sesi (sukses, tolak, gagal, status, dll).

    Contoh: update_sesi(pid, sid, sukses=5, rt_dijalankan=5)
    """
    cfg = load_config()
    bulan = _bulan_key()
    for p in cfg["pangkalan"]:
        if p["id"] == pangkalan_id:
            for sesi in p.get("history", {}).get(bulan, {}).get("sesi", []):
                if sesi["id"] == sesi_id:
                    for k, v in kwargs.items():
                        sesi[k] = v
                    save_config(cfg)
                    return
    print(f"[Config] update_sesi: sesi {sesi_id} tidak ditemukan")


def selesaikan_sesi(pangkalan_id: str, sesi_id: str,
                    sukses: int, tolak: int, gagal: int,
                    rt_dijalankan: int, um_dijalankan: int):
    """
    Tandai sesi selesai dan update akumulasi rt_sudah + um_sudah bulan ini.
    Dipanggil setelah runner selesai.
    """
    cfg = load_config()
    bulan = _bulan_key()
    for p in cfg["pangkalan"]:
        if p["id"] == pangkalan_id:
            h = p.get("history", {}).get(bulan, {})

            # Update sesi
            for sesi in h.get("sesi", []):
                if sesi["id"] == sesi_id:
                    sesi["sukses"]         = sukses
                    sesi["tolak"]          = tolak
                    sesi["gagal"]          = gagal
                    sesi["rt_dijalankan"]  = rt_dijalankan
                    sesi["um_dijalankan"]  = um_dijalankan
                    sesi["status"]         = "selesai"
                    break

            # Akumulasi sesi ke rt_sesi / um_sesi (TERPISAH dari offset manual)
            h["rt_sesi"] = h.get("rt_sesi", 0) + rt_dijalankan
            h["um_sesi"] = h.get("um_sesi", 0) + um_dijalankan
            # rt_sudah / um_sudah = offset + sesi
            h["rt_sudah"] = h.get("rt_offset", 0) + h["rt_sesi"]
            h["um_sudah"] = h.get("um_offset", 0) + h["um_sesi"]

            save_config(cfg)
            print(f"[Config] Sesi selesai: {p['nama']} "
                  f"sukses={sukses} RT={rt_dijalankan} UM={um_dijalankan}")
            return


# ─────────────────────────────────────────────
# PENGATURAN APLIKASI
# ─────────────────────────────────────────────

DEFAULT_SETTINGS = {
    "batas_tabung_per_pelanggan": 3,   # 0 = tanpa batas
}


def get_settings() -> dict:
    """Ambil pengaturan aplikasi (digabung dengan default)."""
    cfg = load_config()
    s = cfg.get("settings", {})
    return {**DEFAULT_SETTINGS, **s}


def set_setting(key: str, value):
    """Simpan satu pengaturan aplikasi."""
    cfg = load_config()
    cfg.setdefault("settings", {})[key] = value
    save_config(cfg)
    print(f"[Config] Setting '{key}' = {value}")


# ─────────────────────────────────────────────
# TEST
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("  TEST CONFIG MANAGER")
    print("=" * 50)
    p1 = tambah_pangkalan("Test Pangkalan", "081234567890", "pass123")
    print("Dibuat:", p1["nama"], p1["id"][:8])
    set_offset_awal(p1["id"], 100, 10)
    print("History:", get_history_bulan_ini(p1["id"]))
    hapus_pangkalan(p1["id"])
    print("Dihapus (test selesai).")
