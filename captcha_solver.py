"""
=====================================
MAP PERTAMINA - CAPTCHA SOLVER (v6 - BAND-RESTRICTED)
=====================================
Diperbaiki berdasarkan analisis gambar CAPTCHA ASLI MAP (Agustus 2026):

  Temuan: puzzle piece hanya berada di SATU BAND VERTIKAL (mis. y=35..92),
  bukan sepanjang tinggi gambar. Metode lama menganalisis SELURUH tinggi →
  tertipu foto latar (danau, kebun teh, langit) → gap meleset jauh
  (terdeteksi x≈180 padahal target asli x≈133).

  Solusi (v6):
    1. Tentukan band vertikal & offset piece DARI ALPHA channel piece PNG.
    2. Batasi seluruh analisis HANYA ke band itu.
    3. Deteksi target dengan 2 metode yang saling cek:
         A. Edge-template  : Canny(band) vs Canny(piece)  [TM_CCOEFF_NORMED]
         C. Alpha↔Frosted  : siluet alpha piece vs peta "frosted"
                             (terang + tak berwarna = overlay puzzle, bukan langit)
                             [TM_CCORR_NORMED]  ← paling andal (conf ~0.95)
    4. Konsensus: jika A & C dekat (≤15px) → rata-rata; else pakai yang conf tinggi.
    5. Jarak drag = target_center - piece_center_offset  (bukan gap_x - 30 buta).

  Divalidasi pada debug_captcha_bg.png asli: center=132.5, drag=103px (benar).

Claude Vision hanya fallback OPSIONAL (mati by default; USE_CLAUDE_FALLBACK=1).

Import:
    from captcha_solver import solve_captcha
"""

import asyncio
import base64
import os
import random
import time

import cv2
import numpy as np

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from playwright.async_api import Page


ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
USE_CLAUDE_FALLBACK = os.getenv("USE_CLAUDE_FALLBACK", "0") == "1"

# Dimensi (dikonfirmasi dari HTML inspect)
CAPTCHA_BG_WIDTH  = 310
CAPTCHA_BG_HEIGHT = 233
PIECE_WIDTH       = 60
MAX_DRAG          = CAPTCHA_BG_WIDTH - 5

# Offset koreksi drag (empiris; band-method sudah akurat → 0)
DRAG_OFFSET_KOREKSI = 0

SEL = {
    "bg_img":    "img.rc-slider-captcha-jigsaw-bg",
    "piece_img": "img.rc-slider-captcha-jigsaw-puzzle",
    "container": ".rc-slider-captcha-jigsaw",
    "handle":    "span.rc-slider-captcha-control-button",
    "handle_alt": "span.rc-slider-captcha-button",
    "control":   ".rc-slider-captcha-control",
    "indicator": ".rc-slider-captcha-control-indicator",
    "refresh":   ".rc-slider-captcha-jigsaw-refresh .rc-slider-captcha-icon",
    "refresh2":  ".mantine-1c66ga",
}


# ═══════════════════════════════════════════════════════
# HELPER: Decode base64 image dari src
# ═══════════════════════════════════════════════════════

async def ambil_gambar_dari_src(page: Page, selector: str):
    try:
        el = page.locator(selector).first
        if await el.count() == 0:
            print(f"   [IMG] Elemen tidak ditemukan: {selector}")
            return None
        src = await el.get_attribute("src")
        if not src or "base64," not in src:
            return None
        img_bytes = base64.b64decode(src.split("base64,", 1)[1])
        arr = np.frombuffer(img_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)  # jaga alpha PNG
        if img is None:
            return None
        print(f"   [IMG] {selector}: shape={img.shape}")
        return img
    except Exception as e:
        print(f"   [IMG] Error ambil gambar: {e}")
        return None


def simpan_debug(img, path: str):
    try:
        cv2.imwrite(path, img)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════
# DETEKSI GAP (v6) — band-restricted
# ═══════════════════════════════════════════════════════

def detect_gap_opencv(bg, piece):
    """
    Deteksi target gap CAPTCHA MAP.

    Returns:
        (drag_logical, center_x)  atau  (None, None)
    """
    try:
        if bg is None or piece is None:
            return None, None
        if len(bg.shape) == 2:
            bg = cv2.cvtColor(bg, cv2.COLOR_GRAY2BGR)
        elif bg.shape[2] == 4:
            bg = cv2.cvtColor(bg, cv2.COLOR_BGRA2BGR)

        if piece.shape[2] < 4:
            print("   [OpenCV] Piece tanpa alpha — deteksi kurang andal")
            return None, None

        # 1) Band vertikal & offset piece DARI ALPHA
        alpha = piece[:, :, 3]
        ys, xs = np.where(alpha > 30)
        if len(xs) == 0:
            return None, None
        y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
        pcen = (x0 + x1) / 2.0                 # pusat konten piece dlm sprite
        band = bg[y0:y1 + 1, :]
        pc   = piece[y0:y1 + 1, x0:x1 + 1]     # crop piece ke bbox konten
        pw   = pc.shape[1]

        # 2) Metode A — edge template
        be = cv2.Canny(cv2.GaussianBlur(cv2.cvtColor(band, cv2.COLOR_BGR2GRAY), (3, 3), 0), 50, 150)
        pe = cv2.Canny(cv2.GaussianBlur(cv2.cvtColor(pc[:, :, :3], cv2.COLOR_BGR2GRAY), (3, 3), 0), 50, 150)
        cA = confA = None
        if pe.shape[1] < be.shape[1] and pe.shape[0] <= be.shape[0]:
            rA = cv2.matchTemplate(be, pe, cv2.TM_CCOEFF_NORMED)
            lA = int(np.argmax(rA)); cA = lA + pw / 2.0; confA = float(rA.max())
            print(f"   [M-A EdgeTpl] center={cA:.0f} conf={confA:.3f}")

        # 3) Metode C — siluet alpha vs peta frosted (terang + tak berwarna)
        hsv = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)
        S = hsv[:, :, 1]; V = hsv[:, :, 2]
        frosted = (((V > 150) & (S < 60)).astype(np.uint8)) * 255
        pm = ((pc[:, :, 3] > 30).astype(np.uint8)) * 255
        cC = confC = None
        if pm.shape[1] < frosted.shape[1] and pm.shape[0] <= frosted.shape[0]:
            rC = cv2.matchTemplate(frosted, pm, cv2.TM_CCORR_NORMED)
            lC = int(np.argmax(rC)); cC = lC + pw / 2.0; confC = float(rC.max())
            print(f"   [M-C AlphaFrost] center={cC:.0f} conf={confC:.3f}")

        # 4) Konsensus
        center, src = None, ""
        if cA is not None and cC is not None:
            if abs(cA - cC) <= 15:
                center, src = (cA + cC) / 2.0, "A+C"
            elif (confC or 0) >= 0.6:
                center, src = cC, "C"
            elif (confA or 0) >= 0.35:
                center, src = cA, "A"
            else:
                center, src = cC, "C(low)"
        elif cC is not None:
            center, src = cC, "C"
        elif cA is not None:
            center, src = cA, "A"

        if center is None:
            print("   [OpenCV] ❌ Deteksi gagal")
            return None, None

        drag = float(center) - pcen + DRAG_OFFSET_KOREKSI
        drag = max(5.0, min(float(MAX_DRAG), drag))
        print(f"   [OpenCV] ✅ [{src}] center={center:.0f} | pcen={pcen:.0f} | drag={drag:.0f}px")
        return drag, float(center)
    except Exception as e:
        import traceback; traceback.print_exc()
        return None, None


# ═══════════════════════════════════════════════════════
# Claude Vision (fallback OPSIONAL)
# ═══════════════════════════════════════════════════════

async def detect_gap_claude(bg_path: str):
    """Returns (drag_logical, center) atau (None, None)."""
    if not USE_CLAUDE_FALLBACK or not ANTHROPIC_API_KEY:
        return None, None
    try:
        import anthropic
        with open(bg_path, "rb") as f:
            img_data = base64.standard_b64encode(f.read()).decode("utf-8")
        media = "image/png" if bg_path.lower().endswith(".png") else "image/jpeg"
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model="claude-sonnet-4-20250514", max_tokens=50,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media, "data": img_data}},
                {"type": "text", "text": (
                    f"Gambar CAPTCHA slider {CAPTCHA_BG_WIDTH}x{CAPTCHA_BG_HEIGHT}px. Ada satu lubang "
                    f"puzzle (siluet putih frosted). Berapa X pusat lubang itu (pixel dari kiri)? "
                    f"Jawab HANYA satu angka.")},
            ]}],
        )
        angka = "".join(filter(str.isdigit, resp.content[0].text.strip()))
        if angka:
            center = int(angka)
            drag = max(5.0, min(float(MAX_DRAG), center - PIECE_WIDTH / 2.0))
            print(f"   [Claude API] center={center} drag={drag:.0f}")
            return drag, float(center)
        return None, None
    except Exception as e:
        print(f"   [Claude API] Error: {e}")
        return None, None


# ═══════════════════════════════════════════════════════
# DRAG MANUSIAWI
# ═══════════════════════════════════════════════════════

async def drag_manusiawi(page: Page, handle_box: dict, jarak_px: float):
    cx = handle_box["x"] + handle_box["width"] / 2
    cy = handle_box["y"] + handle_box["height"] / 2
    print(f"   [Slider] Start ({cx:.0f},{cy:.0f}) → +{jarak_px:.0f}px")

    await page.mouse.move(cx - random.uniform(2, 8), cy + random.uniform(-3, 3))
    await asyncio.sleep(random.uniform(0.1, 0.2))
    await page.mouse.move(cx, cy)
    await asyncio.sleep(random.uniform(0.08, 0.15))
    await page.mouse.down()
    await asyncio.sleep(random.uniform(0.05, 0.12))

    steps = random.randint(35, 50)
    for i in range(1, steps + 1):
        t = i / steps
        ease = 4 * t**3 if t < 0.5 else 1 - (-2 * t + 2)**3 / 2
        noise = 1.0 if (0.2 < t < 0.8) else 0.3
        nx = random.gauss(0, 0.8 * noise); ny = random.gauss(0, 0.4 * noise)
        target_x = cx + jarak_px * ease
        if 0.3 < t < 0.7 and random.random() < 0.06:
            target_x -= random.uniform(1.5, 4.0)
        await page.mouse.move(target_x + nx, cy + ny)
        if t < 0.1 or t > 0.9:
            await asyncio.sleep(random.uniform(0.020, 0.040))
        elif t < 0.2 or t > 0.8:
            await asyncio.sleep(random.uniform(0.012, 0.025))
        else:
            await asyncio.sleep(random.uniform(0.005, 0.013))

    await asyncio.sleep(random.uniform(0.08, 0.2))
    await page.mouse.up()
    print(f"   [Slider] Selesai di x≈{cx + jarak_px:.0f}")


# ═══════════════════════════════════════════════════════
# CEK SUKSES
# ═══════════════════════════════════════════════════════

async def cek_sukses(page: Page) -> bool:
    await asyncio.sleep(1.2)
    try:
        if await page.locator(SEL["container"]).count() == 0:
            print("   [CAPTCHA] Container hilang → Sukses")
            return True
        control = page.locator(SEL["control"]).first
        if await control.count() > 0:
            style = await control.get_attribute("style") or ""
            if style and "235, 241, 225" not in style:
                print("   [CAPTCHA] Warna control berubah → Sukses")
                return True
        indicator = page.locator(SEL["indicator"]).first
        if await indicator.count() > 0:
            style = await indicator.get_attribute("style") or ""
            if style and "188, 203, 160" not in style:
                print("   [CAPTCHA] Indicator berubah → Sukses")
                return True
        for sel in [".rc-slider-captcha-success", "[class*='success']", "text=Berhasil"]:
            if await page.locator(sel).count() > 0:
                print(f"   [CAPTCHA] Sukses via '{sel}'")
                return True
        for hsel in (SEL["handle"], SEL["handle_alt"]):
            h = page.locator(hsel).first
            if await h.count() > 0 and await h.get_attribute("disabled") is not None:
                print("   [CAPTCHA] Handle disabled → Sukses")
                return True
        return False
    except Exception as e:
        print(f"   [CAPTCHA] Error cek sukses: {e}")
        return False


# ═══════════════════════════════════════════════════════
# REFRESH
# ═══════════════════════════════════════════════════════

async def tunggu_gambar_baru(page: Page, src_lama: str, timeout: float = 6.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        bg = page.locator(SEL["bg_img"]).first
        if await bg.count() > 0:
            s = await bg.get_attribute("src") or ""
            if s and s != src_lama:
                return True
        await asyncio.sleep(0.3)
    return False


async def _refresh(page: Page):
    for sel in [SEL["refresh2"], SEL["refresh"],
                ".rc-slider-captcha-jigsaw-refresh", ".mantine-1c66ga > *"]:
        el = page.locator(sel).first
        if await el.count() > 0:
            try:
                await el.scroll_into_view_if_needed()
                await asyncio.sleep(0.3)
                await el.click()
                print(f"   [CAPTCHA] Refresh via '{sel}'")
                await asyncio.sleep(random.uniform(1.5, 2.5))
                return
            except Exception:
                continue
    await asyncio.sleep(2)


# ═══════════════════════════════════════════════════════
# FUNGSI UTAMA
# ═══════════════════════════════════════════════════════

async def solve_captcha(page: Page) -> bool:
    MAX = 3
    stat = {"opencv": 0, "claude": 0}

    for percobaan in range(1, MAX + 1):
        print(f"\n   {'═'*50}\n   [CAPTCHA] Percobaan {percobaan}/{MAX}\n   {'═'*50}")
        try:
            try:
                await page.wait_for_selector(SEL["container"], timeout=12_000)
            except Exception:
                print("   [CAPTCHA] ❌ Container tidak muncul")
                await page.screenshot(path=f"debug_captcha_fail_{percobaan}.png")
                continue

            await asyncio.sleep(2.0)

            bg_el = page.locator(SEL["bg_img"]).first
            src_lama = (await bg_el.get_attribute("src") or "") if await bg_el.count() > 0 else ""

            bg_img    = await ambil_gambar_dari_src(page, SEL["bg_img"])
            piece_img = await ambil_gambar_dari_src(page, SEL["piece_img"])

            if bg_img is not None:
                simpan_debug(bg_img, "debug_captcha_bg.png")
            if piece_img is not None:
                simpan_debug(piece_img, "debug_captcha_piece.png")

            drag_logical, center = detect_gap_opencv(bg_img, piece_img)
            if drag_logical is not None:
                stat["opencv"] += 1
            else:
                drag_logical, center = await detect_gap_claude("debug_captcha_bg.png")
                if drag_logical is not None:
                    stat["claude"] += 1

            if drag_logical is None:
                print("   [CAPTCHA] ❌ Gap tak terdeteksi, refresh...")
                await _refresh(page)
                await tunggu_gambar_baru(page, src_lama)
                continue

            # Handle + skala layar
            handle_box = None
            for sel in [SEL["handle"], SEL["handle_alt"], ".rc-slider-captcha-control > span"]:
                el = page.locator(sel).first
                if await el.count() > 0:
                    box = await el.bounding_box()
                    if box:
                        handle_box = box
                        break
            if not handle_box:
                print("   [CAPTCHA] ❌ Handle tidak ditemukan")
                await page.screenshot(path=f"debug_captcha_fail_{percobaan}.png")
                continue

            # Konversi drag (px gambar 0..310) → gerak HANDLE (px layar).
            # Handle bergerak di TRACK yang bisa lebih lebar dari gambar, jadi
            # tidak 1:1. Rasio: piece menempuh (310-60)=250 px gambar saat handle
            # menempuh (track_width - handle_width) px layar.
            track_w = None
            ctrl = page.locator(SEL["control"]).first
            if await ctrl.count() > 0:
                cb = await ctrl.bounding_box()
                if cb and cb["width"] > 0:
                    track_w = cb["width"]
            if track_w is None:
                cont_el = page.locator(SEL["container"]).first
                cbx = await cont_el.bounding_box() if await cont_el.count() > 0 else None
                track_w = cbx["width"] if (cbx and cbx["width"] > 0) else CAPTCHA_BG_WIDTH

            handle_w = handle_box.get("width", 0) or 0
            max_handle_travel = max(1.0, track_w - handle_w)
            max_piece_travel  = float(CAPTCHA_BG_WIDTH - PIECE_WIDTH)   # 250 px gambar
            frac = min(1.0, drag_logical / max_piece_travel)
            jarak_layar = frac * max_handle_travel
            print(f"   [CAPTCHA] drag_img={drag_logical:.0f} track={track_w:.0f} "
                  f"handle_w={handle_w:.0f} frac={frac:.3f} → layar={jarak_layar:.0f}px")

            await drag_manusiawi(page, handle_box, jarak_layar)

            await asyncio.sleep(2.0)
            if await cek_sukses(page):
                print(f"   ✅ CAPTCHA BERHASIL! (OpenCV={stat['opencv']}x Claude={stat['claude']}x)")
                return True

            print("   ❌ Verifikasi gagal, refresh...")
            await page.screenshot(path=f"debug_captcha_fail_{percobaan}.png")
            await _refresh(page)
            await tunggu_gambar_baru(page, src_lama)

        except Exception as e:
            import traceback
            print(f"   [CAPTCHA] Error tak terduga: {e}")
            traceback.print_exc()
            await asyncio.sleep(2)

    print(f"\n   ❌ Gagal setelah {MAX}x (OpenCV={stat['opencv']}x Claude={stat['claude']}x)")
    return False


# ═══════════════════════════════════════════════════════
# TEST OFFLINE
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    bg_path    = sys.argv[1] if len(sys.argv) > 1 else "debug_captcha_bg.png"
    piece_path = sys.argv[2] if len(sys.argv) > 2 else "debug_captcha_piece.png"
    if not os.path.exists(bg_path):
        print(f"❌ File tidak ada: {bg_path}")
        sys.exit(1)
    bg = cv2.imread(bg_path, cv2.IMREAD_UNCHANGED)
    piece = cv2.imread(piece_path, cv2.IMREAD_UNCHANGED) if os.path.exists(piece_path) else None
    drag, center = detect_gap_opencv(bg, piece)
    if drag is not None:
        print(f"\n✅ center={center:.0f}px | drag={drag:.0f}px")
        vis = bg.copy()
        if len(vis.shape) == 2: vis = cv2.cvtColor(vis, cv2.COLOR_GRAY2BGR)
        elif vis.shape[2] == 4: vis = cv2.cvtColor(vis, cv2.COLOR_BGRA2BGR)
        cv2.line(vis, (int(center), 0), (int(center), vis.shape[0]-1), (0, 0, 255), 2)
        cv2.imwrite("debug_captcha_result.png", vis)
        print("   Hasil: debug_captcha_result.png")
    else:
        print("\n❌ Gagal deteksi")
