"""
=====================================
NIK UTIL — Urai data dari NIK
=====================================
Ringan (tanpa dependensi berat) supaya bisa dipakai UI maupun runner.
"""

import re
from datetime import date as _date

BULAN_ID = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
            "Juli", "Agustus", "September", "Oktober", "November", "Desember"]


def tanggal_lahir_dari_nik(nik: str):
    """
    Urai tanggal lahir dari NIK: digit 7-12 = DDMMYY.
    Perempuan → DD ditambah 40 (dikurangi lagi di sini).
    Abad: pakai 20xx bila hasilnya bikin usia >= 17, selain itu 19xx.
    Return (hari, bulan, tahun) atau None jika tak valid.
    """
    try:
        nik = str(nik).strip()
        dd = int(nik[6:8]); mm = int(nik[8:10]); yy = int(nik[10:12])
        hari = dd - 40 if dd > 40 else dd
        thn_ini = _date.today().year
        tahun = 2000 + yy if (2000 + yy) <= (thn_ini - 17) else 1900 + yy
        if not (1 <= hari <= 31 and 1 <= mm <= 12):
            return None
        return hari, mm, tahun
    except Exception:
        return None


def parse_tanggal_lahir(raw, tempat: str = ""):
    """
    Parse nilai kolom 'Tanggal Lahir' dari Excel.
    Bisa: datetime, string 'd/m/yyyy' atau 'd-m-yyyy', atau 'Mati'.
    Return (tuple(hari,bulan,tahun) atau None, mati: bool).
    """
    if isinstance(tempat, str) and "mati" in tempat.lower():
        return None, True
    if raw is None:
        return None, False
    # datetime dari openpyxl
    if hasattr(raw, "day") and hasattr(raw, "month") and hasattr(raw, "year"):
        try:
            return (int(raw.day), int(raw.month), int(raw.year)), False
        except Exception:
            return None, False
    s = str(raw).strip()
    if not s:
        return None, False
    if "mati" in s.lower():
        return None, True
    m = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})$", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y = 2000 + y if (2000 + y) <= (_date.today().year - 17) else 1900 + y
        if 1 <= d <= 31 and 1 <= mo <= 12:
            return (d, mo, y), False
    return None, False


def fmt_tanggal(tgl):
    """(d,m,y) → 'd Bulan yyyy'. None → '-'."""
    if not tgl:
        return "-"
    d, m, y = tgl
    return f"{d} {BULAN_ID[m] if 1 <= m <= 12 else '??'} {y}"
