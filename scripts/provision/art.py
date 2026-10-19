"""Generator gambar produk (ilustrasi ORISINAL bergaya motif batik, bukan foto & bukan karya pihak lain).
Menghasilkan JPEG 640x640 per produk: siluet busana terisi pola (parang, kawung, mega mendung, truntum, lasem, sekar jagad)."""
import io
import math
import random

from PIL import Image, ImageDraw, ImageFilter

W = 640
PALETTES = {   # latar, tengah, aksen terang, garis gelap
    "indigo": ((22, 38, 84), (45, 76, 140), (214, 196, 150), (10, 18, 46)),
    "maroon": ((96, 26, 30), (150, 56, 44), (233, 206, 160), (52, 12, 16)),
    "brown": ((80, 50, 28), (134, 88, 48), (238, 214, 170), (42, 26, 14)),
    "teal": ((14, 76, 82), (30, 124, 124), (230, 214, 170), (6, 40, 46)),
    "plum": ((72, 30, 80), (122, 62, 124), (236, 212, 176), (36, 14, 42)),
}


def _pattern(kind, pal, seed):
    bg, mid, acc, dark = pal
    rng = random.Random(seed)
    im = Image.new("RGB", (W, W), bg)
    d = ImageDraw.Draw(im)
    if kind == "parang":
        step = 46
        for k in range(-W, W * 2, step):
            pts = []
            for t in range(0, W + 30, 12):
                x = k + t
                y = t + 14 * math.sin(t / 22.0)
                pts.append((x, y))
            d.line(pts, fill=acc, width=9)
            pts2 = [(x + 20, y + 6) for x, y in pts]
            d.line(pts2, fill=mid, width=7)
        for x in range(0, W, 46):
            for y in range(0, W, 46):
                d.ellipse((x + 18, y + 18, x + 26, y + 26), fill=acc)
    elif kind == "kawung":
        r = 34
        for gy in range(-1, W // r + 2):
            for gx in range(-1, W // r + 2):
                cx, cy = gx * r * 1.55, gy * r * 1.55
                for dx, dy in ((0, -r * 0.58), (0, r * 0.58), (-r * 0.58, 0), (r * 0.58, 0)):
                    d.ellipse((cx + dx - r * 0.5, cy + dy - r * 0.5, cx + dx + r * 0.5, cy + dy + r * 0.5), outline=acc, width=3, fill=mid)
                d.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill=acc)
    elif kind == "megamendung":
        for row in range(0, W + 60, 52):
            for col in range(-40, W + 60, 96):
                x = col + (row // 52 % 2) * 48
                for i in range(5):
                    rr = 40 - i * 7
                    d.arc((x - rr, row - rr, x + rr, row + rr), 180, 360, fill=acc if i % 2 == 0 else mid, width=6)
                d.line((x - 40, row, x + 40, row), fill=acc, width=4)
    elif kind == "truntum":
        for gy in range(0, W, 40):
            for gx in range(0, W, 40):
                ox = 20 if (gy // 40) % 2 else 0
                cx, cy = gx + ox, gy
                for a in range(0, 360, 45):
                    x2, y2 = cx + 9 * math.cos(math.radians(a)), cy + 9 * math.sin(math.radians(a))
                    d.line((cx, cy, x2, y2), fill=acc, width=3)
                d.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), fill=mid)
    elif kind == "lasem":
        for gy in range(0, W + 50, 50):
            for gx in range(0, W + 50, 50):
                ox = 25 if (gy // 50) % 2 else 0
                cx, cy = gx + ox, gy
                for a in range(0, 360, 72):
                    px = cx + 14 * math.cos(math.radians(a)); py = cy + 14 * math.sin(math.radians(a))
                    d.ellipse((px - 9, py - 9, px + 9, py + 9), fill=mid, outline=acc, width=2)
                d.ellipse((cx - 6, cy - 6, cx + 6, cy + 6), fill=acc)
        for k in range(0, W * 2, 100):
            d.line((k, 0, k - W, W), fill=dark, width=2)
    else:  # sekarjagad
        for _ in range(90):
            cx, cy = rng.randint(0, W), rng.randint(0, W)
            r = rng.randint(14, 38)
            kind2 = rng.choice(("circle", "diamond", "flower"))
            col = rng.choice((acc, mid, dark))
            if kind2 == "circle":
                d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=col, width=4)
            elif kind2 == "diamond":
                d.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], outline=col, fill=mid)
            else:
                for a in range(0, 360, 60):
                    px = cx + r * 0.6 * math.cos(math.radians(a)); py = cy + r * 0.6 * math.sin(math.radians(a))
                    d.ellipse((px - r * .35, py - r * .35, px + r * .35, py + r * .35), fill=col)
    return im


def shape_for(sku, name):
    """Pilih siluet busana dari kode/nama produk."""
    n = (name or "").lower()
    if "sarimbit" in n or "couple" in n:
        return "couple"
    if "kebaya" in n:
        return "kebaya"
    if "dress" in n:
        return "dress"
    if "blouse" in n:
        return "blouse"
    if "anak" in n:
        return "kids"
    if "outer" in n or "cardigan" in n:
        return "outer"
    return "shirt"


def _silhouette(shape):
    """Poligon siluet pada kanvas WxW (koordinat 0..640)."""
    c = W // 2
    if shape == "dress":
        return [[(c - 70, 90), (c - 40, 70), (c + 40, 70), (c + 70, 90), (c + 55, 250), (c + 150, 560), (c - 150, 560), (c - 55, 250)]]
    if shape == "blouse":
        return [[(c - 120, 120), (c - 50, 90), (c + 50, 90), (c + 120, 120), (c + 170, 250), (c + 120, 270), (c + 100, 230), (c + 95, 500), (c - 95, 500), (c - 100, 230), (c - 120, 270), (c - 170, 250)]]
    if shape == "kebaya":
        return [[(c - 110, 110), (c - 40, 90), (c, 150), (c + 40, 90), (c + 110, 110), (c + 150, 330), (c + 120, 540), (c - 120, 540), (c - 150, 330)]]
    if shape == "outer":
        return [[(c - 130, 110), (c - 55, 90), (c, 130), (c + 55, 90), (c + 130, 110), (c + 195, 400), (c + 150, 420), (c + 118, 250), (c + 105, 540), (c - 105, 540), (c - 118, 250), (c - 150, 420), (c - 195, 400)]]
    if shape == "kids":
        return [[(c - 90, 190), (c - 35, 170), (c + 35, 170), (c + 90, 190), (c + 125, 290), (c + 90, 305), (c + 75, 275), (c + 70, 460), (c - 70, 460), (c - 75, 275), (c - 90, 305), (c - 125, 290)]]
    if shape == "couple":
        return [[(80, 130), (130, 110), (200, 110), (250, 130), (285, 250), (255, 262), (240, 235), (235, 470), (95, 470), (90, 235), (75, 262), (45, 250)],
                [(390, 100), (430, 80), (500, 80), (540, 100), (560, 250), (520, 560), (410, 560), (370, 250)]]
    return [[(c - 130, 110), (c - 55, 90), (c, 135), (c + 55, 90), (c + 130, 110), (c + 190, 290), (c + 142, 310), (c + 112, 230), (c + 105, 520), (c - 105, 520), (c - 112, 230), (c - 142, 310), (c - 190, 290)]]


def render(shape, pattern, palette, seed=0):
    """Hasilkan bytes JPEG: latar krem bergradasi + siluet terisi pola."""
    pal = PALETTES.get(palette, PALETTES["indigo"])
    tex = _pattern(pattern, pal, seed)
    bg = Image.new("RGB", (W, W), (244, 238, 226))
    bd = ImageDraw.Draw(bg)
    for y in range(W):
        t = y / W
        bd.line((0, y, W, y), fill=(int(246 - 14 * t), int(240 - 16 * t), int(228 - 22 * t)))
    mask = Image.new("L", (W, W), 0)
    md = ImageDraw.Draw(mask)
    for poly in _silhouette(shape):
        md.polygon(poly, fill=255)
    shadow = mask.filter(ImageFilter.GaussianBlur(10)).point(lambda v: int(v * 0.35))
    bg.paste((60, 50, 40), (8, 14), shadow)
    bg.paste(tex, (0, 0), mask)
    edge = ImageDraw.Draw(bg)
    for poly in _silhouette(shape):
        edge.line(poly + [poly[0]], fill=pal[3], width=3)
    buf = io.BytesIO()
    bg.save(buf, "JPEG", quality=82)
    return buf.getvalue()
