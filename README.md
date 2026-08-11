# MAP Automation

Aplikasi desktop **PyQt6** untuk otomasi transaksi tabung LPG 3kg di web
**MAP (Merchant Apps Pertamina)** menggunakan **Playwright + Chromium**, dengan
solver CAPTCHA otomatis berbasis **OpenCV**.

> ⚠️ **Data tidak disertakan.** File NIK pelanggan (`Data_NIK_Konsumen_LPG.xlsx`),
> konfigurasi pangkalan (berisi password login), serta cooldown/transaksi
> **sengaja tidak di-upload** demi keamanan (lihat `.gitignore`).

## Fitur
- Dashboard multi-pangkalan (kartu berjejer, tema MyPertamina).
- Komposisi otomatis **90% RT / 10% UM** kumulatif per bulan.
- **Stok awal (patokan)** yang bisa disinkronkan tanpa menggandakan transaksi.
- **Cooldown** per NIK (RT sukses 3 hari, UM 1 hari, tolak/NIB 3 hari).
- **Pengaturan**: batas tabung per pelanggan/bulan + kelola/unlock cooldown.
- Tabel **sisa jatah pelanggan** + indikator ketersediaan NIK.
- CAPTCHA slider diselesaikan otomatis (OpenCV, band-restricted matching).

## Instalasi
```bash
pip install -r requirements.txt
playwright install chromium
```

## Menjalankan
```bash
python main.py
```
Saat pertama jalan: klik **➕ Tambah Pangkalan** (isi nama, nomor HP & password
login MAP, file Excel NIK).

## Struktur
```
main.py                 entry point
captcha_solver.py       CAPTCHA solver (OpenCV)
pelanggan_excel.py      baca NIK dari Excel
core/                   config, komposisi, cooldown, pool, runner, transaksi
dashboard/              UI PyQt6 (main window, kartu, dialog)
```

## Data yang harus disiapkan sendiri
- `Data_NIK_Konsumen_LPG.xlsx` — sheet `Sheet1`, kolom: `No | Nama | NIK KTP | Keterangan`
  (Keterangan: `RT`, `UM`, atau `RT/UM`).
- Data pangkalan diisi lewat UI (tersimpan lokal di `data/pangkalan_config.json`).
