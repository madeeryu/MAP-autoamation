"""
=====================================
PANGKALAN RUNNER — Mesin Sesi per Pangkalan
=====================================
Menjalankan satu sesi transaksi untuk satu pangkalan: login ke MAP, iterasi
antrian NIK, jalankan transaksi (CAPTCHA otomatis), catat hasil + cooldown,
cari pengganti saat TOLAK/cooldown, relogin bila perlu, berhenti bila stok
MAP habis.

Dipakai dari dashboard/main_window.py:
    runner = PangkalanRunner(pangkalan_id, nama, phone, password,
                             antrian, stok, sesi_id, pool,
                             on_log=..., on_progress=..., on_selesai=...)
    runner.run_sync()          # blocking (panggil dari QThread)
    runner.stop()              # minta berhenti

NOTE REKONSTRUKSI (2026): dibangun ulang untuk arsitektur dashboard,
menggabungkan pola loop map_runner.py + interface PangkalanRunner yang
sempat terbaca dari E:. Verifikasi callback saat mengintegrasikan main_window.
"""

import asyncio

from playwright.async_api import async_playwright

from core.nik_database import init_db, catat_transaksi, is_cooldown
from core.session_pool import unlock_nik
from core.config_manager import selesaikan_sesi

MAX_GAGAL_BERUNTUN = 5

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0.0.0 Safari/537.36")

TABUNG_UM_DEFAULT = 3   # UM default 3 tabung (maks 5)


class PangkalanRunner:
    def __init__(
        self,
        pangkalan_id: str,
        nama: str,
        phone: str,
        password: str,
        antrian: list,
        stok: int,
        sesi_id: str,
        pool=None,
        on_log=None,
        on_progress=None,
        on_selesai=None,
    ):
        self.pangkalan_id = pangkalan_id
        self.nama         = nama
        self.phone        = phone
        self.password     = password
        self.antrian      = list(antrian)
        self.stok         = stok
        self.sesi_id      = sesi_id
        self.pool         = pool

        self._on_log      = on_log
        self._on_progress = on_progress
        self._on_selesai  = on_selesai

        self._berhenti = False

        # Statistik sesi
        self.sukses = 0
        self.tolak  = 0
        self.gagal  = 0
        self.rt_dijalankan = 0
        self.um_dijalankan = 0
        self.relogin = 0

    # ── kontrol ──
    def stop(self):
        self._berhenti = True
        self._log("⏹ Stop diminta", "warning")

    def _log(self, pesan: str, level: str = "info"):
        print(f"[{self.nama}] {pesan}")
        if self._on_log:
            try:
                self._on_log(self.pangkalan_id, pesan, level)
            except Exception:
                pass

    def _progress(self):
        if self._on_progress:
            try:
                self._on_progress(
                    self.pangkalan_id, self.sukses, self.tolak, self.gagal,
                    self.sukses + self.tolak + self.gagal, len(self.antrian),
                    self.rt_dijalankan, self.um_dijalankan,
                )
            except Exception:
                pass

    # ── pengganti dari pool ──
    def _ambil_pengganti(self, kategori: str):
        if not self.pool:
            return None
        try:
            if kategori.upper() in ("UM", "MIKRO", "USAHA MIKRO"):
                baru = self.pool.alokasi_untuk_pangkalan(self.pangkalan_id, 0, 1)
            else:
                baru = self.pool.alokasi_untuk_pangkalan(self.pangkalan_id, 1, 0)
            return baru[0] if baru else None
        except Exception:
            return None

    # ── entry point sinkron (untuk QThread) ──
    def run_sync(self):
        return asyncio.run(self.run())

    async def run(self):
        init_db()
        self._log(f"🚀 Sesi dimulai — {len(self.antrian)} NIK antrian")

        if not self.antrian:
            self._log("⚠️  Antrian kosong! Cek file Excel dan stok > 0", "warning")
            self._finalisasi()
            return self._hasil()

        from core.map_transaction import (
            login, jalankan_transaksi_tunggal, sesi_masih_aktif,
        )

        gagal_beruntun = 0

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                slow_mo=0,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=USER_AGENT,
            )
            page = await context.new_page()

            self._log("Login ke MAP...")
            if not await login(page, self.phone, self.password):
                self._log("❌ Login gagal", "error")
                await browser.close()
                self._finalisasi()
                return self._hasil()

            idx = 0
            while idx < len(self.antrian) and not self._berhenti:
                item     = self.antrian[idx]
                nik      = item["nik"]
                kategori = item.get("kategori_dipakai", "RT")
                jumlah   = item.get("jumlah_tabung", 1)
                if kategori.upper() in ("UM", "MIKRO", "USAHA MIKRO") and jumlah < 1:
                    jumlah = TABUNG_UM_DEFAULT

                # Skip NIK yang sudah cooldown → cari pengganti
                if is_cooldown(nik):
                    self._log(f"⏭️  Skip {nik[:8]}*** (cooldown) — cari pengganti", "warning")
                    unlock_nik(nik)
                    pengganti = self._ambil_pengganti(kategori)
                    if pengganti:
                        self.antrian[idx] = pengganti
                        continue
                    idx += 1
                    continue

                # Pastikan sesi masih aktif
                if not await sesi_masih_aktif(page):
                    self._log("⚠️  Sesi expired, login ulang...", "warning")
                    self.relogin += 1
                    if not await login(page, self.phone, self.password):
                        self._log("❌ Login ulang gagal — sesi dihentikan", "error")
                        break
                    gagal_beruntun = 0

                self._log(f"📋 [{idx+1}/{len(self.antrian)}] {item.get('nama','')[:20]} "
                          f"| {kategori} | {nik[:8]}***")

                hasil = await jalankan_transaksi_tunggal(
                    page, nik, kategori, jumlah,
                    tempat_lahir=item.get("tempat_lahir", ""),
                    tgl_lahir=item.get("tgl_lahir"),
                )

                # ── STOK MAP habis: hentikan seluruh sesi ──
                if hasil == "STOK_HABIS":
                    self._log("🚫 STOK MAP HABIS — sesi dihentikan", "error")
                    catat_transaksi(nik, self.pangkalan_id, "gagal", kategori, "stok_habis")
                    break

                # ── SUKSES ──
                if hasil == "SUKSES":
                    self.sukses += 1
                    gagal_beruntun = 0
                    is_um = kategori.upper() in ("UM", "MIKRO", "USAHA MIKRO")
                    kat_norm = "UM" if is_um else "RT"
                    if is_um:
                        self.um_dijalankan += 1
                    else:
                        self.rt_dijalankan += 1
                    catat_transaksi(nik, self.pangkalan_id, "sukses", kat_norm,
                                    jumlah_tabung=jumlah)
                    self._progress()
                    idx += 1

                # ── TOLAK / NIB: cooldown + cari pengganti (tidak maju index) ──
                elif hasil in ("TOLAK", "NIB"):
                    self.tolak += 1
                    catat_transaksi(nik, self.pangkalan_id,
                                    "tolak" if hasil == "TOLAK" else "nib",
                                    kategori, hasil.lower())
                    self._log(f"⚠️  {hasil} — cari pengganti", "warning")
                    self._progress()
                    pengganti = self._ambil_pengganti("UM" if hasil == "NIB" else kategori)
                    if pengganti:
                        self.antrian[idx] = pengganti
                        continue
                    idx += 1

                # ── GAGAL teknis: retry 1x lalu maju ──
                else:
                    self.gagal += 1
                    gagal_beruntun += 1
                    self._log("❌ GAGAL (teknis)", "warning")
                    self._progress()
                    idx += 1

                # Relogin jika gagal beruntun
                if gagal_beruntun >= MAX_GAGAL_BERUNTUN:
                    self._log(f"⚠️  {MAX_GAGAL_BERUNTUN}x gagal beruntun — login ulang", "warning")
                    self.relogin += 1
                    if await login(page, self.phone, self.password):
                        gagal_beruntun = 0
                    else:
                        self._log("❌ Login ulang gagal — sesi dihentikan", "error")
                        break

            await browser.close()

        self._finalisasi()
        return self._hasil()

    # ── akhir sesi ──
    def _finalisasi(self):
        try:
            selesaikan_sesi(
                self.pangkalan_id, self.sesi_id,
                sukses=self.sukses, tolak=self.tolak, gagal=self.gagal,
                rt_dijalankan=self.rt_dijalankan, um_dijalankan=self.um_dijalankan,
            )
        except Exception as e:
            self._log(f"⚠️  Gagal simpan hasil sesi: {e}", "warning")

        self._log(
            f"🏁 Selesai — Sukses:{self.sukses} Tolak:{self.tolak} "
            f"Gagal:{self.gagal} Relogin:{self.relogin}x "
            f"(RT:{self.rt_dijalankan} UM:{self.um_dijalankan})",
            "success",
        )
        if self._on_selesai:
            try:
                self._on_selesai(self.pangkalan_id, self._hasil())
            except Exception:
                pass

    def _hasil(self) -> dict:
        return {
            "pangkalan_id": self.pangkalan_id,
            "sukses": self.sukses, "tolak": self.tolak, "gagal": self.gagal,
            "rt_dijalankan": self.rt_dijalankan, "um_dijalankan": self.um_dijalankan,
            "relogin": self.relogin,
        }


# ─────────────────────────────────────────────
# JALANKAN BEBERAPA RUNNER PARALEL
# ─────────────────────────────────────────────

def jalankan_semua_paralel(runners: list, jeda_detik: int = 0):
    """
    Jalankan beberapa PangkalanRunner. Karena tiap runner memakai
    asyncio.run + browser sendiri, dijalankan berurutan dengan jeda
    (paralel penuh butuh thread terpisah — diatur di main_window).
    """
    import time
    hasil = []
    for i, r in enumerate(runners):
        hasil.append(r.run_sync())
        if jeda_detik and i < len(runners) - 1:
            time.sleep(jeda_detik)
    return hasil
