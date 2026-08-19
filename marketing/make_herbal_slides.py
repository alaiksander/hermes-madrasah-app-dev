#!/usr/bin/env python3
"""Generator 4 slide promosi herbal 9:16 (1080x1920) kanggo video TikTok.
Desain: fresh green + amber/honey + cream, Poppins, template GENERIK (tanpa brand/klaim).
Dipanggil: python3 make_herbal_slides.py  →  /tmp/herbal_slide_{1..4}.png
"""
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont
import math, random

W, H = 1080, 1920
GREEN_DEEP = (22, 74, 46)
GREEN = (52, 121, 74)
GREEN_LIGHT = (224, 238, 228)
AMBER = (222, 168, 60)
AMBER_LIGHT = (248, 236, 210)
CREAM = (252, 248, 240)
INK = (34, 48, 40)
WHITE = (255, 255, 255)
GRAY = (120, 128, 122)

FONT_DIR = "/home/ubuntu/scripts/fonts"
NOTO = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
DEJAVU_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
DEJAVU_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def _cmap(p):
    with TTFont(p) as f:
        return set(f.getBestCmap().keys())
_POPB = _cmap(f"{FONT_DIR}/Poppins-Bold.ttf")
_POPR = _cmap(f"{FONT_DIR}/Poppins-Regular.ttf")

def font(sz, bold=True):
    return ImageFont.truetype(f"{FONT_DIR}/Poppins-{'Bold' if bold else 'Regular'}.ttf", sz)

def text_mixed(d, xy, text, fnt, fill, anchor="lm", bold=None):
    if bold is None:
        bold = "Bold" in (getattr(fnt, "path", "") or "")
    alt = ImageFont.truetype(DEJAVU_BOLD if bold else DEJAVU_REG, fnt.size)
    sup = _POPB if bold else _POPR
    runs, cur, cur_ok = [], "", None
    for ch in text:
        ok = ord(ch) in sup
        if cur_ok is None or ok == cur_ok:
            cur += ch
            if cur_ok is None:
                cur_ok = ok
        else:
            runs.append((cur, cur_ok)); cur, cur_ok = ch, ok
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

def emoji_img(em, h):
    f = ImageFont.truetype(NOTO, 109)
    tmp = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    ImageDraw.Draw(tmp).text((20, 20), em, font=f, embedded_color=True)
    bb = tmp.getbbox()
    if not bb:
        return None
    c = tmp.crop(bb)
    return c.resize((max(1, int(h * c.width / c.height)), h), Image.LANCZOS)

def paste_emoji(img, x, y, em, h, anchor="mm"):
    im = emoji_img(em, h)
    if im is None:
        return
    if anchor == "mm":
        x -= im.width // 2
        y -= im.height // 2
    img.paste(im, (int(x), int(y)), im)

def wrap_center(d, text, y, fnt, fill, max_w, spacing=1.4):
    lines = []
    for ln in textwrap_fill(text, max_w):
        lines.append(ln)
    lh = int(fnt.size * spacing)
    yy = y - lh * len(lines) / 2
    for ln in lines:
        text_mixed(d, (W // 2, yy + lh / 2), ln, fnt, fill, anchor="mm")
        yy += lh

def textwrap_fill(text, width):
    import textwrap
    return textwrap.wrap(text, width)

def bg_gradient(c1, c2):
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        col = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
        d.line([(0, y), (W, y)], fill=col)
    return img

def deco_leaves(img):
    """Dekorasi lembut: bunderan ijo/amber transparan + emoji godhong ing pojok."""
    deco = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(deco)
    for (cx, cy, r, col, a) in [
        (W - 60, 160, 240, GREEN, 26),
        (-80, H * 0.45, 260, AMBER, 20),
        (W - 40, H - 300, 200, GREEN, 18),
    ]:
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(ov).ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (a,))
        deco = Image.alpha_composite(deco, ov)
    img = Image.alpha_composite(img.convert("RGBA"), deco)
    paste_emoji(img, 90, 170, "🌿", 110, anchor="mm")
    paste_emoji(img, W - 90, H - 240, "🍯", 130, anchor="mm")
    return img.convert("RGB")

def header(d):
    """Brand row ndhuwur."""
    d.rounded_rectangle([70, 60, 70 + 74, 60 + 74], radius=20, fill=GREEN_DEEP)
    paste_emoji(d._image, 107, 97, "🌿", 52)
    text_mixed(d, (170, 78), "HERBAL ALAMI", font(46, bold=True), INK, anchor="lm")
    text_mixed(d, (170, 126), "Jamu tradisional pilihan", font(28), GRAY, anchor="lm")

def footer(d, label="Tersedia di TikTok Shop"):
    d.line([(70, 1720), (W - 70, 1720)], fill=AMBER, width=3)
    text_mixed(d, (W // 2, 1685), label, font(34), GRAY, anchor="mm")
    d.rounded_rectangle([W // 2 - 260, 1790, W // 2 + 260, 1920], radius=48, fill=GREEN_DEEP)
    text_mixed(d, (W // 2, 1855), "ORDER SEKARANG", font(44, bold=True), WHITE, anchor="mm")

# ===== Slide 1: Hook (pain point) =====
def slide1():
    img = deco_leaves(bg_gradient((250, 246, 236), (240, 234, 218)))
    d = ImageDraw.Draw(img)
    header(d)
    # badge
    d.rounded_rectangle([W // 2 - 230, 330, W // 2 + 230, 396], radius=33, fill=AMBER)
    text_mixed(d, (W // 2, 363), "🌿 HERBAL • NATURAL", font(32, bold=True), WHITE, anchor="mm")
    text_mixed(d, (W // 2, 560), "Asam urat & kolesterol?", font(84, bold=True), INK, anchor="mm")
    text_mixed(d, (W // 2, 668), "Banyak yang beralih ke", font(52), GRAY, anchor="mm")
    text_mixed(d, (W // 2, 738), "jamu herbal alami.", font(52), GRAY, anchor="mm")
    # lingkaran dekoratif tengah
    d.ellipse([W // 2 - 150, 920, W // 2 + 150, 1220], fill=GREEN_LIGHT, outline=AMBER, width=6)
    paste_emoji(img, W // 2, 1070, "🍵", 240)
    text_mixed(d, (W // 2, 1400), "Rempah pilihan,", font(46, bold=True), GREEN_DEEP, anchor="mm")
    text_mixed(d, (W // 2, 1462), "diolah secara tradisional.", font(46, bold=True), GREEN_DEEP, anchor="mm")
    footer(d)
    img.save("/tmp/herbal_slide_1.png", optimize=True)

# ===== Slide 2: Product (bahan alami) =====
def slide2():
    img = deco_leaves(bg_gradient((226, 240, 230), (238, 244, 236)))
    d = ImageDraw.Draw(img)
    header(d)
    text_mixed(d, (W // 2, 420), "100% HERBAL ALAMI", font(72, bold=True), GREEN_DEEP, anchor="mm")
    text_mixed(d, (W // 2, 515), "Tanpa bahan kimia berbahaya", font(38), GRAY, anchor="mm")
    # 3 kartu bahan
    items = [("🍯", "Madu Murni"), ("🌱", "Jahe & Kunyit"), ("🌿", "Sereh & Daun")]
    y0 = 640
    for i, (em, nm) in enumerate(items):
        cy = y0 + i * 210
        d.rounded_rectangle([110, cy, W - 110, cy + 170], radius=30, fill=WHITE,
                            outline=GREEN_LIGHT, width=3)
        paste_emoji(img, 210, cy + 85, em, 96)
        text_mixed(d, (320, cy + 85), nm, font(44, bold=True), INK, anchor="lm")
        text_mixed(d, (W - 130, cy + 85), "✓", font(52, bold=True), GREEN, anchor="mm")
    text_mixed(d, (W // 2, 1390), "Dikemas higienis,", font(44, bold=True), GREEN_DEEP, anchor="mm")
    text_mixed(d, (W // 2, 1452), "praktis diminum setiap hari.", font(44, bold=True), GREEN_DEEP, anchor="mm")
    footer(d)
    img.save("/tmp/herbal_slide_2.png", optimize=True)

# ===== Slide 3: Benefit (generik, tanpa klaim medis) =====
def slide3():
    img = deco_leaves(bg_gradient((252, 248, 240), (246, 238, 224)))
    d = ImageDraw.Draw(img)
    header(d)
    text_mixed(d, (W // 2, 430), "Rutin & Konsisten", font(76, bold=True), INK, anchor="mm")
    text_mixed(d, (W // 2, 530), "kunci menjaga tubuh tetap fit", font(40), GRAY, anchor="mm")
    # 3 poin benefit
    pts = [("1", "Minum rutin tiap pagi"), ("2", "Gaya hidup + pola makan seimbang"), ("3", "Rasakan bedanya tiap minggu")]
    y0 = 700
    for i, (n, t) in enumerate(pts):
        cy = y0 + i * 200
        d.ellipse([W // 2 - 130, cy - 130, W // 2 + 130, cy + 130], fill=GREEN_LIGHT)
        text_mixed(d, (W // 2, cy), n, font(64, bold=True), GREEN_DEEP, anchor="mm")
        text_mixed(d, (W // 2, cy + 150), t, font(42, bold=True), INK, anchor="mm")
    text_mixed(d, (W // 2, 1520), "Herbal bukan pengganti obat —", font(34), GRAY, anchor="mm")
    text_mixed(d, (W // 2, 1570), "baca aturan pakai & konsultasikan bila perlu.", font(34), GRAY, anchor="mm")
    footer(d)
    img.save("/tmp/herbal_slide_3.png", optimize=True)

# ===== Slide 4: CTA =====
def slide4():
    img = bg_gradient(GREEN_DEEP, (18, 60, 38))
    deco = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(deco)
    for (cx, cy, r, col, a) in [(W - 60, 160, 240, AMBER, 40), (-80, H * 0.5, 260, GREEN, 60)]:
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(ov).ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (a,))
        deco = Image.alpha_composite(deco, ov)
    img = Image.alpha_composite(img.convert("RGBA"), deco).convert("RGB")
    d = ImageDraw.Draw(img)
    paste_emoji(img, W // 2, 400, "🌿", 190)
    text_mixed(d, (W // 2, 640), "Siap coba herbal alami?", font(72, bold=True), WHITE, anchor="mm")
    text_mixed(d, (W // 2, 740), "Tersedia di TikTok Shop & Shopee", font(40), (210, 226, 216), anchor="mm")
    d.rounded_rectangle([W // 2 - 340, 950, W // 2 + 340, 950 + 130], radius=65, fill=AMBER)
    text_mixed(d, (W // 2, 1015), "ORDER SEKARANG", font(54, bold=True), GREEN_DEEP, anchor="mm")
    text_mixed(d, (W // 2, 1220), "Klik link di bio", font(44, bold=True), WHITE, anchor="mm")
    text_mixed(d, (W // 2, 1300), "Bisa COD • Pengiriman cepat", font(38), (210, 226, 216), anchor="mm")
    text_mixed(d, (W // 2, 1720), "Herbal alami • Rempah pilihan", font(34), (180, 200, 188), anchor="mm")
    img.save("/tmp/herbal_slide_4.png", optimize=True)

if __name__ == "__main__":
    slide1()
    slide2()
    slide3()
    slide4()
    print("Slides siap: /tmp/herbal_slide_{1..4}.png")
