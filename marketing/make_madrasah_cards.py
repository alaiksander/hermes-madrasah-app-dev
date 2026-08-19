#!/usr/bin/env python3
"""Generator Kartu Marketing /madrasah — desain profesional teal/ivory/gold.
Target: kepala madrasah, operator/TU, guru (BUKAN remaja — beda karo kartu vocab).
Ukuran: 1080x1350 portrait (IG feed / WA status / FB).
Gambar = kartu tok; caption = teks pisah (aturan kang).
Dipanggil: python3 make_madrasah_cards.py  →  3 PNG ing /tmp/kartu_madrasah_*.png
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import qrcode, textwrap, math, random, os
from fontTools.ttLib import TTFont

# ===== Konfigurasi =====
W, H = 1080, 1350
TEAL = (15, 118, 110)
TEAL_DARK = (10, 80, 75)
TEAL_LIGHT = (214, 234, 231)
IVORY = (250, 248, 243)
IVORY2 = (243, 239, 229)
GOLD = (198, 162, 90)
INK = (38, 50, 48)
GRAY = (110, 120, 117)
RED = (198, 38, 42)
WHITE = (255, 255, 255)

FONT_DIR = "/home/ubuntu/scripts/fonts"
NOTO = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
DEJAVU_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
DEJAVU_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
APP_URL = "vps.alaiksander.my.id/madrasah"

def _cmap(path):
    with TTFont(path) as f:
        return set(f.getBestCmap().keys())

_POP_B_CMAP = _cmap(f"{FONT_DIR}/Poppins-Bold.ttf")
_POP_R_CMAP = _cmap(f"{FONT_DIR}/Poppins-Regular.ttf")

def font(size, bold=True):
    return ImageFont.truetype(f"{FONT_DIR}/Poppins-{'Bold' if bold else 'Regular'}.ttf", size)

def font_baloo(size):
    return ImageFont.truetype(f"{FONT_DIR}/Baloo2-Bold.ttf", size)

def text_mixed(d, xy, text, fnt, fill, anchor="lm", bold=None):
    """Draw teks; karakter sing ora didukung Poppins (cth panah →) otomatis
    fallback menyang DejaVu — ora dadi kotak tofu."""
    if bold is None:
        bold = "Bold" in (getattr(fnt, "path", "") or "")
    size = fnt.size
    alt = ImageFont.truetype(DEJAVU_BOLD if bold else DEJAVU_REG, size)
    sup = _POP_B_CMAP if bold else _POP_R_CMAP
    # pisah dadi run: Poppins-supported vs fallback
    runs, cur, cur_ok = [], "", None
    for ch in text:
        ok = ord(ch) in sup
        if cur_ok is None or ok == cur_ok:
            cur += ch
            if cur_ok is None:
                cur_ok = ok
        else:
            runs.append((cur, cur_ok))
            cur, cur_ok = ch, ok
    runs.append((cur, cur_ok))
    total = sum((fnt if ok else alt).getlength(s) for s, ok in runs)
    x, y = xy
    if anchor == "mm":
        x -= total / 2
    elif anchor == "rm":
        x -= total
    for s, ok in runs:
        f = fnt if ok else alt
        d.text((x, y), s, font=f, fill=fill, anchor="lm")
        x += f.getlength(s)

# ===== Background: gradien ivory lembut =====
def gradient_bg():
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        col = tuple(int(IVORY[i] + (IVORY2[i] - IVORY[i]) * t) for i in range(3))
        d.line([(0, y), (W, y)], fill=col)
    return img

def add_deco(img):
    """Dekorasi halus: lingkaran teal/gold sangat transparan."""
    deco = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(deco)
    for (cx, cy, r, col, alpha) in [
        (W - 90, 130, 260, TEAL, 16),
        (-60, H * 0.42, 220, GOLD, 14),
        (W - 40, H - 320, 200, TEAL, 10),
    ]:
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(ov).ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (alpha,))
        deco = Image.alpha_composite(deco, ov)
    return Image.alpha_composite(img.convert("RGBA"), deco).convert("RGB")

def emoji_img(em, h):
    """Render emoji warna (Noto bitmap, native 109px) → crop → resize."""
    f = ImageFont.truetype(NOTO, 109)
    tmp = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    ImageDraw.Draw(tmp).text((20, 20), em, font=f, embedded_color=True)
    bbox = tmp.getbbox()
    if not bbox:
        return None
    cropped = tmp.crop(bbox)
    w0, h0 = cropped.size
    return cropped.resize((max(1, int(h * w0 / h0)), h), Image.LANCZOS)

def draw_emoji(d, x, y, em, h, anchor="mm"):
    im = emoji_img(em, h)
    if im is None:
        return
    if anchor == "mm":
        x -= im.width // 2
        y -= im.height // 2
    d._image.paste(im, (int(x), int(y)), im)

def wrap_center(d, text, y, fnt, fill, max_w, spacing=1.35, anchor_y="mm"):
    lines = textwrap.wrap(text, width=max_w)
    lh = int(fnt.size * spacing)
    total = lh * len(lines)
    yy = y - total / 2 if anchor_y == "mm" else y
    for ln in lines:
        text_mixed(d, (W // 2, yy + lh / 2), ln, fnt, fill, anchor="mm")
        yy += lh
    return total

# ===== Footer standar: QR + CTA + brand =====
def draw_footer(img, qr_url=APP_URL):
    d = ImageDraw.Draw(img)
    # garis emas tipis
    d.line([(70, 1135), (W - 70, 1135)], fill=GOLD, width=3)
    # QR 150px kiri bawah (aturan kang: cilik, ora nindih info)
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data("https://" + qr_url)
    qr.make(fit=True)
    qim = qr.make_image(fill_color=TEAL_DARK, back_color="white").convert("RGB")
    qim = qim.resize((150, 150), Image.LANCZOS)
    img.paste(qim, (70, 1170))
    # teks sebelah QR
    em = emoji_img("📲", 46)
    if em:
        img.paste(em, (250, 1202), em)
        tx = 250 + em.width + 22
    else:
        tx = 250
    d.text((tx, 1202), "Coba gratis", font=font(48, bold=True), fill=TEAL, anchor="lm")
    d.text((250, 1272), APP_URL, font=font(36), fill=GRAY, anchor="lm")
    # (brand "Absensi Madrasah" ora dipasang maneh ing ngisor — wis ana ing brand row ndhuwur;
    #  URL 620px saka x=250 → 870 ora nabrak apa-apa)

def draw_brand_row(d):
    # kotak teal + ceklis putih
    d.rounded_rectangle([70, 56, 70 + 74, 56 + 74], radius=20, fill=TEAL)
    d.line([(92, 88), (106, 104), (126, 76)], fill=WHITE, width=10, joint="curve")
    d.text((166, 74), "ABSENSI MADRASAH", font=font(46, bold=True), fill=INK, anchor="lm")
    d.text((166, 122), "Aplikasi absensi digital untuk madrasah", font=font(28), fill=GRAY, anchor="lm")

def draw_qr_mockup(cx, cy, size=300, seed=7):
    """Mockup QR sederhana ing panel putih rounded (bali RGBA, siap alpha_composite)."""
    r = random.Random(seed)
    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    pd.rounded_rectangle([cx - size // 2, cy - size // 2, cx + size // 2, cy + size // 2],
                         radius=36, fill=(255, 255, 255, 255), outline=TEAL + (255,), width=8)
    n = 21
    cell = (size - 60) // n
    x0, y0 = cx - (n * cell) // 2, cy - (n * cell) // 2
    # finder squares (3)
    for fx, fy in [(0, 0), (n - 7, 0), (0, n - 7)]:
        pd.rectangle([x0 + fx * cell, y0 + fy * cell, x0 + (fx + 7) * cell, y0 + (fy + 7) * cell],
                     fill=TEAL_DARK)
        pd.rectangle([x0 + (fx + 1) * cell, y0 + (fy + 1) * cell,
                      x0 + (fx + 6) * cell, y0 + (fy + 6) * cell], fill=WHITE)
        pd.rectangle([x0 + (fx + 2) * cell, y0 + (fy + 2) * cell,
                      x0 + (fx + 5) * cell, y0 + (fy + 5) * cell], fill=TEAL_DARK)
    # modul acak deterministik
    for i in range(n):
        for j in range(n):
            if (i < 8 and j < 8) or (i < 8 and j >= n - 8) or (i >= n - 8 and j < 8):
                continue
            if r.random() < 0.42:
                pd.rectangle([x0 + i * cell, y0 + j * cell, x0 + (i + 1) * cell, y0 + (j + 1) * cell],
                             fill=TEAL_DARK)
    return panel

# ===== Kartu 1: 17 Agustus (momentum, merah-putih) =====
def card_17an():
    img = add_deco(gradient_bg())
    d = ImageDraw.Draw(img)
    # pita merah tipis + garis emas ing ndhuwur
    d.rectangle([0, 0, W, 14], fill=RED)
    d.rectangle([0, 14, W, 20], fill=GOLD)
    draw_brand_row(d)

    d.text((W // 2, 330), "DIRGAHAYU RI KE-81", font=font(40, bold=True), fill=RED, anchor="mm")
    # angka 17 gedhe (label 330 ora kepotong: 17 di 520, span 355-685)
    d.text((W // 2 + 6, 526), "17", font=font(330, bold=True), fill=(170, 200, 196), anchor="mm")
    d.text((W // 2, 520), "17", font=font(330, bold=True), fill=RED, anchor="mm")
    d.text((W // 2, 740), "A G U S T U S   2 0 2 6", font=font(34), fill=GRAY, anchor="mm")

    d.text((W // 2, 830), "Semangat baru,", font=font(78, bold=True), fill=INK, anchor="mm")
    d.text((W // 2, 920), "data baru.", font=font(78, bold=True), fill=TEAL, anchor="mm")
    wrap_center(d, "Tahun ajaran 2026/2027 dimulai — siapkan kelas baru, naikkan murid, dan catat kehadiran dari awal dengan rapi.",
                1050, font(38), GRAY, 46)

    draw_footer(img)
    img.save("/tmp/kartu_madrasah_17an.png", optimize=True)

# ===== Kartu 2: Naik Kelas (fitur, 3 langkah) =====
def card_naik_kelas():
    img = add_deco(gradient_bg())
    d = ImageDraw.Draw(img)
    draw_brand_row(d)

    d.text((W // 2, 330), "Naik kelas?", font=font(84, bold=True), fill=INK, anchor="mm")
    d.text((W // 2, 424), "3 langkah, beres.", font=font(84, bold=True), fill=TEAL, anchor="mm")

    # panel langkah (py=500 ben catatan emas ora nabrak footer 1135)
    px, py, pw, ph = 90, 500, W - 180, 430
    d.rounded_rectangle([px + 8, py + 8, px + pw + 8, py + ph + 8], radius=40, fill=(228, 222, 210))
    d.rounded_rectangle([px, py, px + pw, py + ph], radius=40, fill=WHITE)
    steps = [
        ("1", "Pilih tahun ajaran baru"),
        ("2", "Centang kelas yang naik"),
        ("3", "Klik \"Naik Kelas\" — murid otomatis pindah"),
    ]
    y = py + 78
    for num, txt in steps:
        d.ellipse([px + 60 - 34, y - 34, px + 60 + 34, y + 34], fill=TEAL)
        d.text((px + 60, y), num, font=font(44, bold=True), fill=WHITE, anchor="mm")
        wrap_center(d, txt, y, font(40), INK, 30)
        y += 118

    # catatan emas (ny=986 → box 986-1106, footer 1135 aman)
    ny = py + ph + 56
    d.rounded_rectangle([90, ny, W - 90, ny + 120], radius=28, fill=(244, 236, 214))
    d.text((W // 2, ny + 60), "Kelas tujuan dibuat otomatis • Data tahun lalu tetap tersimpan",
           font=font(32), fill=(140, 110, 50), anchor="mm")
    d.text((W // 2, ny + 96), "Kelas 9 otomatis ditandai lulus", font=font(30), fill=(140, 110, 50), anchor="mm")

    draw_footer(img)
    img.save("/tmp/kartu_madrasah_naik_kelas.png", optimize=True)

# ===== Kartu 3: Absen QR 3 detik (benefit) =====
def card_qr_3detik():
    img = add_deco(gradient_bg())
    d = ImageDraw.Draw(img)
    draw_brand_row(d)

    d.text((W // 2, 320), "Absen 3 detik,", font=font(80, bold=True), fill=INK, anchor="mm")
    d.text((W // 2, 412), "cukup scan QR.", font=font(80, bold=True), fill=TEAL, anchor="mm")

    # mockup panel QR tengah
    panel = draw_qr_mockup(W // 2, 700, size=330, seed=11)
    img = Image.alpha_composite(img.convert("RGBA"), panel).convert("RGB")
    d = ImageDraw.Draw(img)
    # label scan
    d.text((W // 2, 900), "Guru tampilkan QR  •  Murid scan dari HP", font=font(36, bold=True), fill=INK, anchor="mm")
    wrap_center(d, "Kehadiran tercatat otomatis beserta waktunya. Bisa juga pakai scanner 2D USB untuk mode kiosk di pintu masuk.",
                1010, font(36), GRAY, 44)

    draw_footer(img)
    img.save("/tmp/kartu_madrasah_qr_3detik.png", optimize=True)

# ===== Kartu 4-6: Carousel Kamis 13 Agu — Ekspor Rekap Excel (tips) =====
def draw_excel_table(cx, cy, w=860, h=520):
    """Mockup tabel Excel: header teal + 5 baris data. Bali panel RGBA."""
    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    x0, y0 = cx - w // 2, cy - h // 2
    pd.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=28, fill=(255, 255, 255, 255))
    # header
    hh = 92
    pd.rounded_rectangle([x0, y0, x0 + w, y0 + hh], radius=28, fill=TEAL)
    pd.rectangle([x0, y0 + hh - 28, x0 + w, y0 + hh], fill=TEAL)  # ratakake sudhut ngisor header
    cols = [("NIS", 200), ("NAMA", 360), ("HADIR", 130), ("%", 170)]
    hx = x0
    for name, cw in cols:
        pd.text((hx + cw // 2, y0 + hh // 2), name, font=font(34, bold=True), fill=WHITE, anchor="mm")
        hx += cw
    # baris
    rows = [
        ("12345", "Ahmad F.", "22", "96%"),
        ("12346", "Siti N.", "21", "91%"),
        ("12347", "M. Rizky", "23", "100%"),
        ("12348", "Dewi A.", "20", "87%"),
        ("12349", "Bagus P.", "19", "83%"),
    ]
    ry = y0 + hh
    rh = (h - hh) // len(rows)
    for i, (nis, nama, hadir, pct) in enumerate(rows):
        if i % 2 == 1:
            pd.rectangle([x0, ry, x0 + w, ry + rh], fill=(247, 245, 240))
        pd.line([x0, ry, x0 + w, ry], fill=(232, 228, 218), width=2)
        pd.text((x0 + 100, ry + rh // 2), nis, font=font(30), fill=GRAY, anchor="mm")
        pd.text((x0 + 200 + 180, ry + rh // 2), nama, font=font(32), fill=INK, anchor="mm")
        pd.text((x0 + 200 + 360 + 65, ry + rh // 2), hadir, font=font(30), fill=INK, anchor="mm")
        pd.text((x0 + w - 85, ry + rh // 2), pct, font=font(32, bold=True), fill=TEAL, anchor="mm")
        ry += rh
    pd.line([x0, ry, x0 + w, ry], fill=(232, 228, 218), width=2)
    return panel

def card_excel_slide1():
    img = add_deco(gradient_bg())
    d = ImageDraw.Draw(img)
    draw_brand_row(d)
    # badge tips
    d.rounded_rectangle([W // 2 - 190, 200, W // 2 + 190, 264], radius=32, fill=GOLD)
    d.text((W // 2, 232), "TIPS  •  KAMIS", font=font(32, bold=True), fill=WHITE, anchor="mm")
    d.text((W // 2, 372), "Laporan ke wali murid?", font=font(72, bold=True), fill=INK, anchor="mm")
    d.text((W // 2, 478), "Rekap absensi manual makan waktu…", font=font(38), fill=GRAY, anchor="mm")
    # before/after
    t30 = "30 MENIT"
    f30 = font(100, bold=True)
    d.text((W // 2, 648), t30, font=f30, fill=RED, anchor="mm")
    tw = d.textlength(t30, font=f30)
    d.line([(W // 2 - tw / 2, 648 + 16), (W // 2 + tw / 2, 648 + 16)], fill=RED, width=10)
    text_mixed(d, (W // 2, 790), "→", font(90, bold=True), GOLD, anchor="mm")
    d.text((W // 2, 930), "10 DETIK", font=font(100, bold=True), fill=TEAL, anchor="mm")
    text_mixed(d, (W // 2, 1060), "Buka rekap → pilih tanggal → ekspor. Beres.",
               font(38, bold=True), INK, anchor="mm")
    draw_footer(img)
    img.save("/tmp/kartu_madrasah_excel_1.png", optimize=True)

def card_excel_slide2():
    img = add_deco(gradient_bg())
    d = ImageDraw.Draw(img)
    draw_brand_row(d)
    d.text((W // 2, 340), "Ekspor rekap:", font=font(78, bold=True), fill=INK, anchor="mm")
    d.text((W // 2, 432), "3 klik, jadi.", font=font(78, bold=True), fill=TEAL, anchor="mm")
    px, py, pw, ph = 90, 520, W - 180, 380
    d.rounded_rectangle([px + 8, py + 8, px + pw + 8, py + ph + 8], radius=40, fill=(228, 222, 210))
    d.rounded_rectangle([px, py, px + pw, py + ph], radius=40, fill=WHITE)
    steps = [
        ("1", "Buka menu Rekap"),
        ("2", "Pilih rentang tanggal"),
        ("3", "Ekspor Excel"),
    ]
    y = py + 66
    for num, txt in steps:
        d.ellipse([px + 60 - 34, y - 34, px + 60 + 34, y + 34], fill=TEAL)
        d.text((px + 60, y), num, font=font(44, bold=True), fill=WHITE, anchor="mm")
        d.text((px + 130, y), txt, font=font(42, bold=True), fill=INK, anchor="lm")
        y += 118
    ny = py + ph + 50
    d.rounded_rectangle([90, ny, W - 90, ny + 120], radius=28, fill=(244, 236, 214))
    d.text((W // 2, ny + 60), "File .xlsx langsung rapi — siap kirim ke wali murid.",
           font=font(34), fill=(140, 110, 50), anchor="mm")
    draw_footer(img)
    img.save("/tmp/kartu_madrasah_excel_2.png", optimize=True)

def card_excel_slide3():
    img = add_deco(gradient_bg())
    d = ImageDraw.Draw(img)
    draw_brand_row(d)
    d.text((W // 2, 300), "Rekap siap kirim.", font=font(76, bold=True), fill=INK, anchor="mm")
    panel = draw_excel_table(W // 2, 700)
    img = Image.alpha_composite(img.convert("RGBA"), panel).convert("RGB")
    d = ImageDraw.Draw(img)
    d.text((W // 2, 1030), "Ekspor per hari, per minggu, atau rentang tanggal.",
           font=font(36), fill=GRAY, anchor="mm")
    draw_footer(img)
    img.save("/tmp/kartu_madrasah_excel_3.png", optimize=True)

if __name__ == "__main__":
    card_17an()
    card_naik_kelas()
    card_qr_3detik()
    card_excel_slide1()
    card_excel_slide2()
    card_excel_slide3()
    print("Kartu siap: /tmp/kartu_madrasah_{17an,naik_kelas,qr_3detik,excel_1,excel_2,excel_3}.png")
