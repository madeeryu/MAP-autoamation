"""
=====================================
MAP PERTAMINA — TRANSAKSI OTOMATIS (dashboard core)
=====================================
Alur transaksi 1 NIK di web MAP Pertamina, dipakai oleh core/runner.py.

Basis: map_transaction v5 ("FIXED ALUR" — Jalur A/B, autocomplete NIK,
robust wait_for_selector) + pembacaan stok MAP + CAPTCHA OTOMATIS
(captcha_solver.solve_captcha). Berbeda dari v5 yang manual, di sini CAPTCHA
diselesaikan otomatis oleh solver OpenCV.

ALUR:
  Menu Utama
    → Catat Penjualan
    → Ketik NIK → autocomplete → LANJUTKAN PENJUALAN
    → [Jalur A] pilih RT/UM → LANJUTKAN TRANSAKSI
      [Jalur B] langsung form tabung (NIK hanya RT)
    → set jumlah tabung → CEK PESANAN
    → PROSES PENJUALAN
    → CAPTCHA slider (solve_captcha OTOMATIS)
    → halaman sukses → auto KEMBALI KE HALAMAN UTAMA

Return jalankan_transaksi_tunggal:
    'SUKSES' | 'TOLAK' | 'NIB' | 'STOK_HABIS' | 'GAGAL'

NOTE REKONSTRUKSI (2026): dibangun ulang untuk arsitektur dashboard dengan
menggabungkan file v5 asli + captcha_solver v5. Selector transaksi = verbatim
dari file v5 Anda; selector stok = dari file E: yang sempat terbaca.
"""

import asyncio
import random
from datetime import date as _date

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from captcha_solver import solve_captcha


MAP_URL = "https://subsiditepatlpg.mypertamina.id/merchant-login"

# ── Kelengkapan data pelanggan (kebijakan baru MAP) ──
TEMPAT_LAHIR_DEFAULT = "Cirebon"
from core.nik_util import tanggal_lahir_dari_nik, BULAN_ID as _BULAN_ID


async def _pilih_dropdown(page, placeholder: str, target: str) -> bool:
    """Klik Mantine Select (by placeholder Tgl/Bln/Thn) lalu pilih opsi == target."""
    inp = page.locator(f"input[placeholder='{placeholder}']").first
    if await inp.count() == 0:
        return False
    try:
        await inp.click()
        await asyncio.sleep(0.4)
        opts = page.locator("[role='option']")
        for i in range(await opts.count()):
            o = opts.nth(i)
            t = (await o.inner_text() or "").strip()
            if t == target or t.lstrip("0") == target.lstrip("0"):
                await o.click()
                await asyncio.sleep(0.2)
                return True
        # fallback: ketik lalu pilih opsi pertama
        await inp.fill(target)
        await asyncio.sleep(0.4)
        opts = page.locator("[role='option']")
        if await opts.count() > 0:
            await opts.first.click()
            await asyncio.sleep(0.2)
            return True
    except Exception as e:
        print(f"  [UPDATE] dropdown '{placeholder}' error: {e}")
    return False

# ─────────────────────────────────────────────
# SELECTOR
# ─────────────────────────────────────────────

SEL = {
    "input_phone":    "input[type='tel'], input[placeholder*='Nomor'], input[name*='phone']",
    "input_password": "input[type='password']",

    # ── MENU UTAMA ──
    "tombol_catat_penjualan": [
        ".styles_leftSection___ZTVp",
        "text=Catat Penjualan",
        ".styles_root__6zS3q",
        "div:has-text('Catat Penjualan')",
    ],
    "indikator_menu_utama": [
        ".styles_leftSection___ZTVp",
        "text=Catat Penjualan",
    ],

    # ── STOK MAP (halaman utama) ──
    "stok_container": ".styles_summaryProductCard__Uv3IK",
    "stok_label":     ".mantine-1v7wwf6",   # teks "Stok"
    "stok_nilai":     ".mantine-1ovr98n",   # teks "100 Tabung"
    "alert_stok_kosong": [
        "text=stok tabung yang dapat dijual kosong",
        ".styles_warning__OM_Pf:has-text('stok tabung')",
        ".styles_alertInfo__WvEN4:has-text('stok')",
    ],

    # ── INPUT NIK ──
    "input_nik": [
        "input[placeholder='Masukkan 16 digit NIK Pelanggan']",
        "input[inputmode='numeric'][maxlength='18']",
        "input.mantine-Autocomplete-input",
        "input[placeholder*='16 digit']",
        "input[placeholder*='NIK']",
    ],
    "tombol_lanjutkan_penjualan": [
        "button[data-testid='btnCheckNik'][type='submit']",
        "button:has-text('LANJUTKAN PENJUALAN')",
        "button:has-text('Lanjutkan Penjualan')",
    ],

    # ── MODAL PELANGGAN (Jalur A) ──
    "radio_rt":  "input[type='radio'][value='Rumah Tangga']",
    "radio_um":  "input[type='radio'][value='Usaha Mikro']",
    "label_rt":  "label.styles_container__Cnm0i:has(input[value='Rumah Tangga'])",
    "label_um":  "label.styles_container__Cnm0i:has(input[value='Usaha Mikro'])",
    "tombol_lanjutkan_transaksi": [
        # Prioritaskan TEKS (class styles_primary__k_AUJ juga dipakai "LENGKAPI NIB")
        "button:has-text('LANJUTKAN TRANSAKSI')",
        "button:has-text('Lanjutkan Transaksi')",
        "button.styles_primary__k_AUJ:has-text('LANJUTKAN')",
        "button:has-text('LANJUTKAN')",
    ],
    "tombol_tutup": [
        "button.styles_lightGreen__flYZ5",
        "button:has-text('TUTUP')",
        "button:has-text('Tutup')",
        "button[data-testid='btnCheckNik'][type='button']",
    ],

    # ── FORM TABUNG ──
    "input_jumlah_tabung":  "input[data-testid='numberInput']",
    "tombol_tambah_tabung": "button[data-testid='actionIcon2']",
    "tombol_kurang_tabung": "button[data-testid='actionIcon1']",
    "tombol_cek_pesanan": [
        "button[data-testid='btnCheckOrder']",
        "button:has-text('CEK PESANAN')",
    ],

    # ── KONFIRMASI ──
    "tombol_proses_penjualan": [
        "button[data-testid='btnPay']",
        "button:has-text('PROSES PENJUALAN')",
    ],

    # ── SUKSES ──
    "tombol_kembali_utama": [
        "a[href='/merchant/app'] button",
        "a[href='/merchant/app']",
        "button:has-text('KEMBALI KE HALAMAN UTAMA')",
        "button:has-text('Kembali ke Halaman Utama')",
        "button:has-text('KEMBALI')",
    ],
    "indikator_sukses": [
        "text=Berhasil", "text=BERHASIL", "text=Transaksi berhasil",
        "a[href='/merchant/app']", "[class*='success']",
    ],

    # ── TEKS PENOLAKAN ──
    "teks_tolak": [
        "melebihi batas kewajaran", "batas kewajaran", "terlalu sering",
        "melebihi batas", "sudah bertransaksi", "tidak dapat", "tidak bisa",
        "kuota habis", "tidak terdaftar", "tidak memenuhi", "belum bisa",
    ],
    # NIB = belum daftar NIB (khusus UM). Diperlakukan terpisah.
    "teks_nib": [
        "belum terdaftar nib", "nib belum", "wajib nib", "nomor induk berusaha",
    ],
}


# ─────────────────────────────────────────────
# UTILITAS
# ─────────────────────────────────────────────

async def ketik_per_karakter(page: Page, selector: str, teks: str, delay_ms: int = 80):
    """Ketik karakter per karakter (field NIK/telp memblokir paste)."""
    await page.click(selector)
    await page.keyboard.press("Control+a")
    await page.keyboard.press("Delete")
    await page.type(selector, teks, delay=delay_ms)


async def klik_pertama(page: Page, selector_list, label: str = "") -> bool:
    for sel in selector_list:
        try:
            el = page.locator(sel).first
            if await el.count() > 0 and await el.is_visible():
                await el.click()
                if label:
                    print(f"      ✅ {label}: '{sel}'")
                return True
        except Exception:
            continue
    return False


async def cek_tolak(page: Page) -> tuple[bool, str]:
    try:
        konten = (await page.content()).lower()
        for teks in SEL["teks_tolak"]:
            if teks in konten:
                return True, teks
    except Exception:
        pass
    return False, ""


async def cek_nib(page: Page) -> bool:
    try:
        konten = (await page.content()).lower()
        return any(t in konten for t in SEL["teks_nib"])
    except Exception:
        return False


async def tutup_modal(page: Page):
    await klik_pertama(page, SEL["tombol_tutup"])
    await asyncio.sleep(0.4)


async def tunggu_menu_utama(page: Page, timeout: int = 8_000) -> bool:
    for sel in SEL["indikator_menu_utama"]:
        try:
            await page.wait_for_selector(sel, timeout=timeout)
            return True
        except Exception:
            continue
    return False


MENU_URL = "https://subsiditepatlpg.mypertamina.id/merchant/app"


async def di_menu_utama(page: Page) -> bool:
    """True jika tombol/menu 'Catat Penjualan' benar-benar tampak."""
    for sel in SEL["indikator_menu_utama"]:
        try:
            el = page.locator(sel).first
            if await el.count() > 0 and await el.is_visible():
                return True
        except Exception:
            pass
    return False


async def pastikan_di_menu(page: Page) -> bool:
    """
    Pastikan halaman berada di menu utama sebelum transaksi.
    Setelah transaksi gagal (mis. CAPTCHA gagal), halaman bisa nyangkut di
    halaman pembayaran/konfirmasi — di sini kita paksa kembali ke menu.
    """
    if await di_menu_utama(page):
        return True
    # Coba klik tombol "Kembali ke Halaman Utama" bila ada
    for sel in SEL["tombol_kembali_utama"]:
        try:
            el = page.locator(sel).first
            if await el.count() > 0 and await el.is_visible():
                await el.click()
                if await tunggu_menu_utama(page, timeout=8_000):
                    return True
        except Exception:
            pass
    # Paksa navigasi ke menu utama
    try:
        await page.goto(MENU_URL, wait_until="domcontentloaded", timeout=20_000)
        await asyncio.sleep(0.8)
    except Exception:
        pass
    return await tunggu_menu_utama(page, timeout=10_000)


async def sesi_masih_aktif(page: Page) -> bool:
    try:
        for sel in SEL["indikator_menu_utama"]:
            if await page.locator(sel).count() > 0:
                return True
        if "/merchant" in page.url and "login" not in page.url:
            return True
    except Exception:
        pass
    return False


# ─────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────

async def login(page: Page, phone: str, password: str) -> bool:
    print("\n  [LOGIN] Membuka MAP...")
    await page.goto(MAP_URL, wait_until="domcontentloaded", timeout=30_000)
    await asyncio.sleep(1.0)

    # Sudah login? (redirect ke /merchant/app atau menu sudah tampil)
    if await sesi_masih_aktif(page):
        print("  [LOGIN] ✅ Sudah login (sesi aktif) — lewati form")
        await tunggu_menu_utama(page, timeout=8_000)
        return True

    for sel in ["text=Masuk", "a:has-text('Masuk')", "button:has-text('Masuk')"]:
        el = page.locator(sel).first
        if await el.count() > 0:
            await el.click()
            await asyncio.sleep(0.8)
            break

    field_phone = None
    for sel in ["input[type='tel']", "input[placeholder*='Nomor']", "input[name*='phone']"]:
        try:
            await page.wait_for_selector(sel, timeout=5_000)
            field_phone = sel
            break
        except Exception:
            continue
    if not field_phone:
        print("  [LOGIN] ❌ Field HP tidak ditemukan")
        return False

    await ketik_per_karakter(page, field_phone, phone, delay_ms=60)
    await asyncio.sleep(0.2)
    await ketik_per_karakter(page, "input[type='password']", password, delay_ms=60)
    await asyncio.sleep(0.2)

    for sel in ["button[type='submit']", "button:has-text('Masuk')"]:
        el = page.locator(sel).first
        if await el.count() > 0:
            await el.click()
            break

    try:
        await page.wait_for_load_state("networkidle", timeout=20_000)
        await asyncio.sleep(0.5)
        # Tunggu menu utama benar-benar siap sebelum lanjut transaksi
        if await tunggu_menu_utama(page, timeout=12_000):
            print("  [LOGIN] ✅ Berhasil (menu utama siap)")
        else:
            print("  [LOGIN] ✅ Login submit — menu utama belum terdeteksi, lanjut hati-hati")
        return True
    except PlaywrightTimeoutError:
        print("  [LOGIN] ❌ Timeout")
        return False


# ─────────────────────────────────────────────
# BACA STOK MAP
# ─────────────────────────────────────────────

async def baca_stok_map(page: Page) -> int:
    """Baca jumlah stok tabung di halaman utama MAP. -1 jika tak ditemukan."""
    try:
        containers = page.locator(SEL["stok_container"])
        n = await containers.count()
        for i in range(n):
            card = containers.nth(i)
            labels = card.locator(SEL["stok_label"])
            for j in range(await labels.count()):
                teks = (await labels.nth(j).inner_text() or "").strip().lower()
                if teks == "stok":
                    nilai_els = card.locator(SEL["stok_nilai"])
                    if await nilai_els.count() > 0:
                        raw = await nilai_els.first.inner_text()
                        angka = "".join(filter(str.isdigit, raw or ""))
                        if angka:
                            stok = int(angka)
                            print(f"  [STOK] MAP: {stok} tabung tersisa")
                            return stok
        print("  [STOK] ⚠️  Elemen stok tidak ditemukan")
        return -1
    except Exception as e:
        print(f"  [STOK] Error baca stok: {e}")
        return -1


async def cek_stok_kosong(page: Page) -> bool:
    """True jika muncul alert stok MAP habis (setelah input NIK)."""
    try:
        for sel in SEL["alert_stok_kosong"]:
            if await page.locator(sel).count() > 0:
                print("  [STOK] 🚫 Alert stok kosong terdeteksi — stok MAP = 0!")
                return True
    except Exception:
        pass
    return False


# ─────────────────────────────────────────────
# STEP-STEP TRANSAKSI
# ─────────────────────────────────────────────

async def _input_nik_terbuka(page: Page) -> bool:
    """True jika field input NIK sedang terlihat (modal 'Masukkan NIK' terbuka)."""
    for sel in SEL["input_nik"]:
        try:
            el = page.locator(sel).first
            if await el.count() > 0 and await el.is_visible():
                return True
        except Exception:
            pass
    return False


async def klik_catat_penjualan(page: Page) -> bool:
    # KASUS PENTING: setelah transaksi DITOLAK, sering ada modal sisa yang masih
    # terbuka (mis. "Masukkan NIK / pendaftaran"). Kalau dibiarkan, tombol
    # "Catat Penjualan" tertutup modal → bot nge-scroll & macet.
    # (User konfirmasi: menutup modal dulu bikin bot lanjut normal.)
    # Jadi TUTUP dulu modal sisa sebelum klik Catat Penjualan.
    for _ in range(3):
        if not await _input_nik_terbuka(page):
            break
        print("  [STEP 1] Ada modal sisa — menutup dulu")
        await tutup_modal(page)
        if await _input_nik_terbuka(page):
            try:
                await page.keyboard.press("Escape")   # fallback kalau TUTUP gagal
            except Exception:
                pass
        await asyncio.sleep(0.6)

    # Pastikan menu utama benar-benar ready dulu (hindari klik saat halaman
    # belum selesai render setelah login/kembali).
    await tunggu_menu_utama(page, timeout=15_000)
    if not await klik_pertama(page, SEL["tombol_catat_penjualan"], "Catat Penjualan"):
        print("  [STEP 1] ❌ Tombol Catat Penjualan tidak ditemukan")
        await page.screenshot(path="debug_menu.png")
        return False
    for sel in SEL["input_nik"]:
        try:
            await page.wait_for_selector(sel, timeout=5_000)
            return True
        except Exception:
            continue
    await asyncio.sleep(0.7)
    return True


async def input_nik(page: Page, nik: str) -> str:
    """Returns 'LANJUT' | 'TOLAK' | 'STOK_HABIS' | 'ERROR'."""
    print(f"  [STEP 2] NIK {nik[:8]}***")
    field_nik = None
    for sel in SEL["input_nik"]:
        try:
            await page.wait_for_selector(sel, timeout=4_000)
            field_nik = sel
            break
        except Exception:
            continue
    if not field_nik:
        print("  [STEP 2] ❌ Field NIK tidak ditemukan")
        await page.screenshot(path="debug_nik.png")
        return "ERROR"

    await ketik_per_karakter(page, field_nik, nik, delay_ms=80)
    await asyncio.sleep(0.5)

    for sel_item in ["[role='option']", ".mantine-Autocomplete-item", "li[role='option']"]:
        try:
            item = page.locator(sel_item).first
            await item.wait_for(state="visible", timeout=1_500)
            await item.click()
            await asyncio.sleep(0.3)
            break
        except Exception:
            continue

    if not await klik_pertama(page, SEL["tombol_lanjutkan_penjualan"], "LANJUTKAN PENJUALAN"):
        await page.keyboard.press("Enter")

    await asyncio.sleep(1.5)

    if await cek_stok_kosong(page):
        return "STOK_HABIS"

    ada_tolak, alasan = await cek_tolak(page)
    if ada_tolak:
        print(f"  [STEP 2] ⚠️  TOLAK: '{alasan}'")
        await tutup_modal(page)
        return "TOLAK"
    return "LANJUT"


async def lewati_nib_reminder(page: Page) -> bool:
    """
    Modal reminder NIB (khusus Usaha Mikro): "Segera Lengkapi NIB..." dengan
    tombol "LENGKAPI NIB" dan "NANTI SAJA, LANJUT TRANSAKSI".

    Ini BUKAN penolakan — bisa dilewati. Klik "NANTI SAJA, LANJUT TRANSAKSI"
    (berbasis TEKS, bukan class, karena class-nya sama dengan tombol lain) agar
    transaksi tetap lanjut. Return True jika modal dilewati.
    """
    for sel in [
        "button:has-text('NANTI SAJA')",
        "button:has-text('LANJUT TRANSAKSI')",
        "button:has-text('Nanti Saja')",
    ]:
        try:
            el = page.locator(sel).first
            if await el.count() > 0 and await el.is_visible():
                await el.click()
                print("  [NIB] Reminder NIB dilewati → NANTI SAJA, LANJUT TRANSAKSI")
                await asyncio.sleep(0.8)
                return True
        except Exception:
            pass
    return False


async def handle_modal_pelanggan(page: Page, kategori: str, nik: str = "",
                                 tempat_lahir: str = "", tgl_lahir=None) -> str:
    """
    Tangani modal setelah input NIK, sebagai STATE-MACHINE (urutan bisa beragam):
      - Pilih kategori RT/UM (Pelanggan Terdaftar)
      - Pernyataan Persetujuan (centang → SELANJUTNYA)
      - Reminder NIB (NANTI SAJA, LANJUT TRANSAKSI)
      - "Data Pelanggan belum lengkap" → UPDATE DATA PELANGGAN
      - Form update: Tempat Lahir + Tgl/Bln/Thn (dari NIK) → SELANJUTNYA
      - Konfirmasi "Pastikan data benar" → YA, Perbarui
    Selesai saat form tabung muncul.

    Returns 'FORM_TABUNG' | 'TOLAK' | 'ERROR'.
    """
    print(f"  [STEP 3] Modal pelanggan (target: {kategori})...")

    # Sumber data update: UTAMAKAN Excel, fallback ke urai NIK / default.
    tgl_nik = tanggal_lahir_dari_nik(nik) if nik else None
    tgl = tgl_lahir or tgl_nik
    tempat = (tempat_lahir or "").strip() or TEMPAT_LAHIR_DEFAULT
    if tgl_lahir and tgl_nik and tgl_lahir != tgl_nik:
        print(f"  [UPDATE] ⚠️  Beda tgl Excel {tgl_lahir} vs NIK {tgl_nik} — pakai Excel")
    if tgl:
        print(f"  [UPDATE] Data: Tempat={tempat}, Tgl={tgl[0]} {_BULAN_ID[tgl[1]]} {tgl[2]}")

    kategori_dipilih = False

    for _ in range(45):  # ~ cukup untuk banyak langkah
        # 0) Form tabung → SELESAI
        if await page.locator(SEL["input_jumlah_tabung"]).count() > 0:
            print("  [STEP 3] ✅ Form tabung siap")
            return "FORM_TABUNG"

        # 1) Penolakan
        ada_tolak, alasan = await cek_tolak(page)
        if ada_tolak:
            print(f"  [STEP 3] ⚠️  TOLAK: '{alasan}'")
            await tutup_modal(page)
            return "TOLAK"

        # 2) Reminder NIB (UM) → NANTI SAJA, LANJUT TRANSAKSI
        if await lewati_nib_reminder(page):
            continue

        # 3) Pernyataan Persetujuan → centang semua checkbox → SELANJUTNYA
        if await page.locator("text=Pernyataan Persetujuan").count() > 0:
            cb = page.locator("input[type='checkbox']")
            for i in range(await cb.count()):
                try:
                    if not await cb.nth(i).is_checked():
                        await cb.nth(i).check()
                except Exception:
                    pass
            print("  [UPDATE] Persetujuan dicentang → SELANJUTNYA")
            await klik_pertama(page, ["button:has-text('SELANJUTNYA')"], "Persetujuan")
            await asyncio.sleep(1.0)
            continue

        # 4) "Data Pelanggan belum lengkap" → UPDATE DATA PELANGGAN
        if await page.locator("text=Data Pelanggan belum lengkap").count() > 0:
            print("  [UPDATE] Data belum lengkap → UPDATE DATA PELANGGAN")
            await klik_pertama(page, ["button:has-text('UPDATE DATA PELANGGAN')"], "UPDATE DATA")
            await asyncio.sleep(1.0)
            continue

        # 5) Form update: Tempat Lahir + Tgl/Bln/Thn → SELANJUTNYA
        tl = page.locator(
            "input[placeholder*='tempat lahir'], input[placeholder*='Tempat Lahir']").first
        if await tl.count() > 0 and await tl.is_visible():
            print(f"  [UPDATE] Isi form: Tempat={tempat}, Tgl={tgl}")
            try:
                await tl.click()
                await tl.fill(tempat)
            except Exception:
                pass
            if tgl:
                await _pilih_dropdown(page, "Tgl", str(tgl[0]))
                await _pilih_dropdown(page, "Bln", _BULAN_ID[tgl[1]])
                await _pilih_dropdown(page, "Thn", str(tgl[2]))
            await asyncio.sleep(0.3)
            await klik_pertama(page, ["button[data-testid='btnSubmitUpdate']",
                                      "button:has-text('SELANJUTNYA')"], "Submit update")
            await asyncio.sleep(1.2)
            continue

        # 6) Konfirmasi "Pastikan data benar" → YA, Perbarui
        if await page.locator("text=Pastikan semua data").count() > 0:
            print("  [UPDATE] Konfirmasi → YA, Perbarui DATA PELANGGAN")
            await klik_pertama(page, ["button:has-text('YA, Perbarui')",
                                      "button:has-text('Perbarui DATA')"], "YA Perbarui")
            await asyncio.sleep(1.5)
            continue

        # 7) Pilih kategori RT/UM (jika ada radio) → LANJUTKAN TRANSAKSI
        ada_radio = (
            await page.locator(SEL["radio_rt"]).count() > 0 or
            await page.locator(SEL["radio_um"]).count() > 0 or
            await page.locator(SEL["label_rt"]).count() > 0
        )
        if ada_radio and not kategori_dipilih:
            print("  [STEP 3] ✅ Jalur A — pilih kategori")
            if kategori.upper() in ("RT", "RUMAH TANGGA"):
                await klik_pertama(page, [SEL["label_rt"], SEL["radio_rt"]], "RT dipilih")
            else:
                await klik_pertama(page, [SEL["label_um"], SEL["radio_um"]], "UM dipilih")
            await asyncio.sleep(0.3)
            await klik_pertama(page, SEL["tombol_lanjutkan_transaksi"], "LANJUTKAN TRANSAKSI")
            kategori_dipilih = True
            await asyncio.sleep(1.0)
            continue

        # 8) Modal "Pelanggan Terdaftar" tanpa radio (Jalur B) → LANJUTKAN
        if (not kategori_dipilih and
                await page.locator("text=Pelanggan Terdaftar").count() > 0):
            print("  [STEP 3] ✅ Jalur B — tanpa radio")
            await klik_pertama(
                page,
                SEL["tombol_lanjutkan_transaksi"] + ["button:has-text('LANJUTKAN PENJUALAN')"],
                "Lanjut (Jalur B)")
            kategori_dipilih = True
            await asyncio.sleep(1.0)
            continue

        await asyncio.sleep(0.5)

    print("  [STEP 3] ❌ Timeout menangani modal pelanggan")
    await page.screenshot(path="debug_step3.png")
    return "ERROR"


async def set_tabung_dan_cek_pesanan(page: Page, kategori: str, jumlah_tabung: int) -> bool:
    print(f"  [STEP 4] Form tabung — {jumlah_tabung} tabung ({kategori})")
    try:
        await page.wait_for_selector(SEL["input_jumlah_tabung"], timeout=5_000)
    except PlaywrightTimeoutError:
        print("  [STEP 4] ⚠️  Form tabung belum muncul (5s)")

    ada_tolak, alasan = await cek_tolak(page)
    if ada_tolak:
        print(f"  [STEP 4] ⚠️  TOLAK: '{alasan}'")
        return False

    if kategori.upper() in ("MIKRO", "UM", "USAHA MIKRO") and jumlah_tabung > 1:
        plus = page.locator(SEL["tombol_tambah_tabung"]).first
        for i in range(jumlah_tabung - 1):
            if await plus.count() > 0 and await plus.is_enabled():
                await plus.click()
                await asyncio.sleep(0.2)
            else:
                print(f"  [STEP 4] ⚠️  Tombol + tidak aktif (iterasi {i+1})")
                break

    if not await klik_pertama(page, SEL["tombol_cek_pesanan"], "CEK PESANAN"):
        print("  [STEP 4] ❌ Tombol CEK PESANAN tidak ditemukan")
        await page.screenshot(path="debug_tabung.png")
        return False

    for sel in SEL["tombol_proses_penjualan"]:
        try:
            await page.wait_for_selector(sel, timeout=6_000)
            return True
        except Exception:
            continue
    await asyncio.sleep(0.8)
    return True


async def klik_proses_penjualan(page: Page) -> bool:
    print("  [STEP 5] PROSES PENJUALAN")
    if not await klik_pertama(page, SEL["tombol_proses_penjualan"], "PROSES PENJUALAN"):
        print("  [STEP 5] ❌ Tombol tidak ditemukan")
        await page.screenshot(path="debug_konfirmasi.png")
        return False
    await asyncio.sleep(0.5)
    return True


async def selesaikan_setelah_captcha(page: Page) -> bool:
    """Setelah CAPTCHA sukses: auto klik KEMBALI KE HALAMAN UTAMA, tunggu menu ready."""
    print("  [STEP 7] Menunggu halaman sukses...")
    for _ in range(20):  # ~10 detik
        for sel in SEL["tombol_kembali_utama"]:
            el = page.locator(sel).first
            try:
                if await el.count() > 0 and await el.is_visible():
                    await el.click()
                    print("  [STEP 7] ✅ Auto KEMBALI KE HALAMAN UTAMA")
                    if await tunggu_menu_utama(page, timeout=8_000):
                        print("  [STEP 7] ✅ Menu utama siap")
                    else:
                        await asyncio.sleep(1.0)
                    return True
            except Exception:
                pass
        await asyncio.sleep(0.5)

    # Fallback: cek indikator sukses lain
    for sel in SEL["indikator_sukses"]:
        if await page.locator(sel).count() > 0:
            print(f"  [STEP 7] ✅ Sukses terdeteksi via '{sel}'")
            await tunggu_menu_utama(page, timeout=5_000)
            return True

    await page.screenshot(path="debug_setelah_captcha.png")
    print("  [STEP 7] ⚠️  Indikator sukses tidak terdeteksi")
    return False


# ─────────────────────────────────────────────
# FUNGSI UTAMA: SATU TRANSAKSI
# ─────────────────────────────────────────────

async def jalankan_transaksi_tunggal(
    page: Page,
    nik: str,
    kategori: str = "RT",
    jumlah_tabung: int = 1,
    tempat_lahir: str = "",
    tgl_lahir=None,
) -> str:
    """
    Satu siklus transaksi lengkap dengan CAPTCHA OTOMATIS.

    Returns: 'SUKSES' | 'TOLAK' | 'NIB' | 'STOK_HABIS' | 'GAGAL'
    """
    print(f"\n{'─'*55}\n  {nik[:8]}*** | {kategori} | {jumlah_tabung} tabung\n{'─'*55}")
    try:
        # Recovery: pastikan mulai dari menu utama bersih (halaman bisa nyangkut
        # di halaman pembayaran setelah transaksi sebelumnya gagal).
        if not await pastikan_di_menu(page):
            print("  [RECOVERY] ⚠️  Tidak bisa kembali ke menu utama")
            return "GAGAL"

        if not await klik_catat_penjualan(page):
            return "GAGAL"

        hasil_nik = await input_nik(page, nik)
        if hasil_nik in ("TOLAK", "STOK_HABIS"):
            return hasil_nik
        if hasil_nik == "ERROR":
            return "GAGAL"

        hasil_modal = await handle_modal_pelanggan(page, kategori, nik,
                                                   tempat_lahir, tgl_lahir)
        if hasil_modal in ("TOLAK", "NIB"):
            return hasil_modal
        if hasil_modal == "ERROR":
            return "GAGAL"

        if not await set_tabung_dan_cek_pesanan(page, kategori, jumlah_tabung):
            return "GAGAL"

        if not await klik_proses_penjualan(page):
            return "GAGAL"

        # CAPTCHA OTOMATIS
        print("  [STEP 6] Menyelesaikan CAPTCHA (otomatis)...")
        if not await solve_captcha(page):
            print("  → GAGAL (CAPTCHA)")
            return "GAGAL"

        if await selesaikan_setelah_captcha(page):
            print("  → ✅ SUKSES")
            return "SUKSES"
        return "GAGAL"

    except PlaywrightTimeoutError as e:
        print(f"  [ERROR] Timeout: {e}")
        await page.screenshot(path="debug_timeout.png")
        return "GAGAL"
    except Exception as e:
        print(f"  [ERROR] {type(e).__name__}: {e}")
        await page.screenshot(path="debug_error.png")
        return "GAGAL"
