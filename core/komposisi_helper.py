"""
=====================================
KOMPOSISI HELPER — Hitung RT/UM Per Sesi
=====================================
Tanggung jawab:
  - Hitung berapa RT dan UM yang perlu dijalankan di sesi ini
    berdasarkan akumulasi bulan berjalan (90% RT : 10% UM total)
  - Validasi stok tidak melebihi kemampuan data pelanggan
  - Hitung estimasi progress bulan ini

Logika utama:
  Total bulan ini = rt_sudah + um_sudah + stok_baru
  Target RT bulan ini = total * 90%
  Target UM bulan ini = total * 10%

  RT sesi ini = max(0, target_RT - rt_sudah)
  UM sesi ini = max(0, target_UM - um_sudah)

  Jika rt_sesi + um_sesi > stok → normalisasi proporsional
"""

import math
from dataclasses import dataclass


RASIO_RT = 0.90
RASIO_UM = 0.10


@dataclass
class KomposisiSesi:
    """Hasil perhitungan komposisi RT/UM untuk sesi ini."""
    stok:           int      # Stok yang akan dijalankan sesi ini
    rt_sesi:        int      # Jumlah RT yang perlu dijalankan sesi ini
    um_sesi:        int      # Jumlah UM yang perlu dijalankan sesi ini

    # Context bulan ini (setelah sesi ini selesai)
    rt_sudah:       int      # RT yang sudah jalan sebelum sesi ini
    um_sudah:       int      # UM yang sudah jalan sebelum sesi ini
    total_bulan_ini: int     # Total tabung bulan ini setelah sesi ini

    # Keterangan tambahan
    catatan:        str = ""

    @property
    def target_rt_bulan(self) -> int:
        return math.floor(self.total_bulan_ini * RASIO_RT)

    @property
    def target_um_bulan(self) -> int:
        return self.total_bulan_ini - self.target_rt_bulan

    def __str__(self) -> str:
        lines = [
            f"─── Komposisi Sesi ───",
            f"  Stok sesi ini    : {self.stok} tabung",
            f"  RT sesi ini      : {self.rt_sesi} transaksi",
            f"  UM sesi ini      : {self.um_sesi} transaksi",
            f"",
            f"  Total bulan ini  : {self.total_bulan_ini} tabung",
            f"  Target RT bulan  : {self.target_rt_bulan} (90%)",
            f"  Target UM bulan  : {self.target_um_bulan} (10%)",
            f"  RT sudah jalan   : {self.rt_sudah}",
            f"  UM sudah jalan   : {self.um_sudah}",
        ]
        if self.catatan:
            lines.append(f"  ⚠️  {self.catatan}")
        return "\n".join(lines)


def hitung_komposisi_sesi(
    rt_sudah: int,
    um_sudah: int,
    stok_baru: int,
) -> KomposisiSesi:
    """
    Hitung berapa RT dan UM yang harus dijalankan di sesi ini.

    Args:
        rt_sudah   : Jumlah RT yang sudah diinput bulan ini (sebelum sesi ini)
        um_sudah   : Jumlah UM yang sudah diinput bulan ini (sebelum sesi ini)
        stok_baru  : Stok kiriman baru yang akan dijalankan sesi ini

    Returns:
        KomposisiSesi dengan breakdown RT/UM untuk sesi ini

    Contoh:
        rt_sudah=0, um_sudah=0, stok=100
        → total=100, target_RT=90, target_UM=10
        → rt_sesi=90, um_sesi=10

        rt_sudah=630, um_sudah=70, stok=100
        → total=800, target_RT=720, target_UM=80
        → rt_sesi=max(0, 720-630)=90, um_sesi=max(0, 80-70)=10

        rt_sudah=700, um_sudah=0, stok=100
        → total=800, target_RT=720, target_UM=80
        → rt_sesi=max(0, 720-700)=20, um_sesi=max(0, 80-0)=80
        → rt+um=100 = stok ✅

        Kasus over (RT sudah terlalu banyak):
        rt_sudah=750, um_sudah=50, stok=100
        → total=900, target_RT=810, target_UM=90
        → rt_sesi=max(0, 810-750)=60, um_sesi=max(0, 90-50)=40
        → rt+um=100 = stok ✅
    """
    catatan = ""
    total_bulan_ini = rt_sudah + um_sudah + stok_baru

    # Target kumulatif bulan ini
    target_rt = math.floor(total_bulan_ini * RASIO_RT)
    target_um = total_bulan_ini - target_rt

    # Kebutuhan sesi ini
    rt_sesi = max(0, target_rt - rt_sudah)
    um_sesi = max(0, target_um - um_sudah)

    total_perlu = rt_sesi + um_sesi

    # Normalisasi jika total melebihi stok (bisa terjadi karena rounding)
    if total_perlu > stok_baru:
        kelebihan = total_perlu - stok_baru
        # Kurangi RT dulu (UM lebih kritis untuk dikejar)
        rt_sesi = max(0, rt_sesi - kelebihan)
        total_perlu = rt_sesi + um_sesi

        # Jika masih melebihi, kurangi UM juga
        if total_perlu > stok_baru:
            um_sesi = max(0, stok_baru - rt_sesi)

        catatan = f"Normalisasi dilakukan (rt+um melebihi stok)"

    # Kasus total kurang dari stok (bisa terjadi jika sudah sangat kelebihan RT atau UM)
    if rt_sesi + um_sesi < stok_baru:
        sisa = stok_baru - rt_sesi - um_sesi
        # Tambahkan ke RT (lebih aman karena limit 1 tabung)
        rt_sesi += sisa
        if catatan:
            catatan += f"; sisa {sisa} dialokasikan ke RT"
        else:
            catatan = f"Sisa {sisa} dialokasikan ke RT (sudah mencapai target UM)"

    # Pastikan tidak ada nilai negatif
    rt_sesi = max(0, rt_sesi)
    um_sesi = max(0, um_sesi)

    return KomposisiSesi(
        stok=stok_baru,
        rt_sesi=rt_sesi,
        um_sesi=um_sesi,
        rt_sudah=rt_sudah,
        um_sudah=um_sudah,
        total_bulan_ini=total_bulan_ini,
        catatan=catatan,
    )


def hitung_persentase_saat_ini(rt_sudah: int, um_sudah: int) -> dict:
    """
    Hitung persentase RT/UM dari yang sudah berjalan bulan ini.
    Berguna untuk ditampilkan di dashboard.

    Returns:
        dict: {total, persen_rt, persen_um, status}
    """
    total = rt_sudah + um_sudah
    if total == 0:
        return {
            "total":     0,
            "persen_rt": 0.0,
            "persen_um": 0.0,
            "status":    "Belum ada transaksi bulan ini",
        }

    persen_rt = (rt_sudah / total) * 100
    persen_um = (um_sudah / total) * 100

    # Evaluasi kondisi
    if abs(persen_rt - 90) <= 2:
        status = "✅ Komposisi ideal (90/10)"
    elif persen_rt > 92:
        status = f"⚠️  RT terlalu banyak ({persen_rt:.1f}%), sesi berikutnya perlu lebih banyak UM"
    elif persen_rt < 88:
        status = f"⚠️  UM terlalu banyak ({persen_um:.1f}%), sesi berikutnya perlu lebih banyak RT"
    else:
        status = f"🔄 Komposisi: RT {persen_rt:.1f}% / UM {persen_um:.1f}%"

    return {
        "total":     total,
        "persen_rt": persen_rt,
        "persen_um": persen_um,
        "status":    status,
    }


# ─────────────────────────────────────────────
# TEST
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  TEST KOMPOSISI HELPER")
    print("=" * 55)

    kasus = [
        # (label, rt_sudah, um_sudah, stok)
        ("Skenario 1: Awal bulan (0/0), stok 100",          0,   0,   100),
        ("Skenario 2: Di tengah bulan (630/70), stok 100",  630, 70,  100),
        ("Skenario 3: RT terlalu banyak (700/0), stok 100", 700, 0,   100),
        ("Skenario 4: UM sudah kejar (750/50), stok 100",   750, 50,  100),
        ("Skenario 5: Stok besar 140",                       0,   0,   140),
        ("Skenario 6: Stok ganjil 160",                      100, 10,  160),
    ]

    for label, rt, um, stok in kasus:
        print(f"\n{'─'*55}")
        print(f"  {label}")
        k = hitung_komposisi_sesi(rt, um, stok)
        print(k)

        # Verifikasi
        total_sesi = k.rt_sesi + k.um_sesi
        assert total_sesi == stok, f"ERROR: rt_sesi+um_sesi={total_sesi} ≠ stok={stok}"
        assert k.rt_sesi >= 0 and k.um_sesi >= 0, "ERROR: nilai negatif!"
        print(f"  ✅ Verifikasi: rt+um={total_sesi} = stok={stok}")

    print("\n✅ Semua skenario berhasil!")
