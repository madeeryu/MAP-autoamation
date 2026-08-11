"""
=====================================
STATISTIK — Ketersediaan & Sisa Jatah Pelanggan
=====================================
Gabungkan data Excel + cooldown + pemakaian bulan ini + batas untuk
menghitung status tiap NIK dan ringkasan ketersediaan.
"""

from core.config_manager import get_settings
from core.nik_database import (
    get_nik_cooldown_aktif, get_pemakaian_bulan_ini, get_info_cooldown,
)


def _baca_pelanggan(excel_path: str) -> list:
    from core.app_paths import resolve_excel
    from pelanggan_excel import PelangganManager
    return PelangganManager(excel_path=resolve_excel(excel_path)).semua_pelanggan


def detail_pelanggan(excel_path: str) -> list:
    """
    Status tiap NIK: [{nik, nama, keterangan, terpakai, sisa, status}]
      status: "Siap" | "Cooldown s/d <tgl>" | "Batas tercapai"
      sisa  : batas - terpakai  (None jika tanpa batas)
    """
    semua = _baca_pelanggan(excel_path)
    cd    = get_nik_cooldown_aktif()
    pakai = get_pemakaian_bulan_ini()
    batas = int(get_settings().get("batas_tabung_per_pelanggan", 0) or 0)

    out = []
    for p in semua:
        nik = p["nik"]
        t   = pakai.get(nik, 0)
        sisa = (batas - t) if batas > 0 else None
        if nik in cd:
            info = get_info_cooldown(nik)
            status = f"Cooldown s/d {info['aktif_lagi'] if info else '-'}"
        elif batas > 0 and t >= batas:
            status = "Batas tercapai"
        else:
            status = "Siap"
        out.append({
            "nik": nik, "nama": p["nama"], "keterangan": p["keterangan"],
            "terpakai": t, "sisa": sisa, "status": status,
        })
    return out


def ringkas_ketersediaan(excel_path: str) -> dict:
    """Ringkasan jumlah: {total, siap, cooldown, batas}."""
    d = detail_pelanggan(excel_path)
    return {
        "total":    len(d),
        "siap":     sum(1 for x in d if x["status"] == "Siap"),
        "cooldown": sum(1 for x in d if x["status"].startswith("Cooldown")),
        "batas":    sum(1 for x in d if x["status"] == "Batas tercapai"),
    }
