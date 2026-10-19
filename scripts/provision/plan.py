"""Perencana order (murni Python, tanpa Odoo) -> daftar order harian deterministik.
Dipakai oleh seed.py; bisa dijalankan sendiri untuk menyetel omzet:  python plan.py"""
import datetime as dt
import math
import random
from collections import defaultdict

import config as C

# bobot pilihan produk per persona (awalan SKU atau SKU lengkap -> pengali pada bobot dasar)
PERSONA_PREF = {
    "STORE": {"BT-": 1.8, "BC-SRB": 2.2, "BC-KBY": 1.8, "AK-": 0.8, "BP-KDS": 0.7},
    "SHOPEE": {"BP-": 1.2, "AK-MSK": 0.9, "AK-TAS": 0.9, "BT-": 0.3, "BC-SRB": 0.8, "BC-DRS": 1.2},
    "TOKPED": {"BP-": 1.2, "AK-": 0.9, "BT-": 0.4, "BC-SRB": 0.9},
    "TIKTOK": {"BP-DRS": 1.2, "BC-DRS": 2.0, "BC-BLS": 1.6, "BC-KBY": 1.8, "BC-SRB": 1.4, "BT-": 0.7},
    "INSTAGRAM": {"BT-": 2.6, "BC-DRS": 1.6, "BC-SRB": 2.0, "BC-KBY": 2.0, "BP-KDS": 0.4},
    "RESELLER": {"BP-": 1.3, "BC-KMJ-001": 1.5, "BC-BLS": 1.5, "BC-DRS": 1.4, "AK-": 0.9, "BT-": 0.4},
    "CORPORATE": {"BC-KMJ-003": 6.0, "BC-KMJ-001": 3.0, "BC-BLS-001": 2.5, "BP-KMJ-001": 1.5, "BT-": 0.0, "BC-SRB": 0.0,
                  "AK-": 0.3, "BP-KDS": 0.0, "BP-DRS": 0.5, "BP-OTR": 0.5, "BC-KBY": 0.4},
}
DISC_RANGE = {"STORE": (0.0, 0.08), "SHOPEE": (0.04, 0.15), "TOKPED": (0.03, 0.12), "TIKTOK": (0.08, 0.22),
              "INSTAGRAM": (0.0, 0.10), "RESELLER": (0.22, 0.28), "CORPORATE": (0.08, 0.12)}
POOL = {"STORE": 70, "SHOPEE": 140, "TOKPED": 45, "TIKTOK": 95, "INSTAGRAM": 45}
RETURN_P = {"STORE": 0.01, "SHOPEE": 0.035, "TOKPED": 0.03, "TIKTOK": 0.06, "INSTAGRAM": 0.02, "B2B": 0.01}
CANCEL_P = {"SHOPEE": 0.015, "TOKPED": 0.015, "TIKTOK": 0.02}


def catalog():
    """sku -> {price, weight}"""
    out = {}
    for sku, name, cat, price, w, *_ in C.MADE:
        out[sku] = {"price": price, "weight": w, "name": name}
    for sku, name, cat, cost, price, w, *_ in C.BOUGHT:
        out[sku] = {"price": price, "weight": w, "name": name}
    return out


def _weights(cat, persona):
    pref = PERSONA_PREF.get(persona, {})
    ws = {}
    for sku, info in cat.items():
        m = 1.0
        for k, v in pref.items():
            if sku.startswith(k):
                m = v if k == sku or len(k) >= len(sku) - 4 else v
        # awalan paling panjang menang
        best, mult = 0, 1.0
        for k, v in pref.items():
            if sku.startswith(k) and len(k) > best:
                best, mult = len(k), v
        ws[sku] = info["weight"] * mult
    return ws


def _pareto(rng, n, a=2.0):
    return min(n - 1, int(n * (rng.random() ** a)))


def _basket(rng, cat, persona, wcache):
    ws = wcache[persona]
    skus, w = list(ws), [ws[s] for s in ws]
    if persona == "RESELLER":
        k = rng.choice([2, 3, 3, 4, 4, 5])
        picks = sorted(set(rng.choices(skus, weights=w, k=k + 2)))
        return {s: rng.choice([6, 8, 10, 12, 12, 15, 18, 20, 24]) for s in list(picks)[:k]}
    if persona == "CORPORATE":
        k = rng.choice([1, 2, 2, 3])
        picks = sorted(set(rng.choices(skus, weights=w, k=k + 2)))
        return {s: rng.choice([10, 12, 15, 20, 20, 24, 30, 36, 40, 50]) for s in list(picks)[:k]}
    n_items = {"STORE": [1, 1, 2, 2, 3, 4], "SHOPEE": [1, 1, 1, 2, 2, 3], "TOKPED": [1, 1, 1, 2, 2, 3],
               "TIKTOK": [1, 2, 2, 3, 3, 4], "INSTAGRAM": [1, 2, 2, 3]}[persona]
    k = rng.choice(n_items)
    lines = {}
    for s in sorted(set(rng.choices(skus, weights=w, k=k))):
        qmax = 3 if persona in ("STORE", "INSTAGRAM") else 2
        lines[s] = rng.choices(range(1, qmax + 1), weights=[78, 18, 4][:qmax])[0]
    return lines


def _price(cat, sku, disc):
    return int(round(cat[sku]["price"] * (1 - disc) / 1000.0)) * 1000


def event_mult(d, code):
    m = 1.0
    for a, b, mult, chs, _ in C.EVENTS:
        if a <= d <= b and (chs is None or code in chs):
            m *= mult
    return m


def month_pos(d):
    """posisi bulan 0..3 (Jul..Okt) dan interpolasi harian target (naik mulus di dalam bulan)"""
    return d.month - 7


def daily_target(ch, d):
    """target DPP harian channel pada hari d (juta -> rupiah). Interpolasi antar bulan agar tidak melompat."""
    rev = ch["rev"]
    dim = (dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1) - dt.timedelta(days=1)).day
    i = month_pos(d)
    pos = i + (d.day - 15.5) / dim            # jangkar = pertengahan bulan; interpolasi linear antar bulan
    pos = min(max(pos, 0.0), len(rev) - 1)
    lo = int(math.floor(pos)); hi = min(lo + 1, len(rev) - 1)
    level = rev[lo] + (rev[hi] - rev[lo]) * (pos - lo)
    return level * 1_000_000 / dim


def build(rng=None):
    rng = rng or random.Random(C.SEED)
    cat = catalog()
    wcache = {p: _weights(cat, p) for p in PERSONA_PREF}
    # kalibrasi rata-rata DPP per basket tiap persona
    calib = {}
    probe = random.Random(7)
    for persona in PERSONA_PREF:
        lo, hi = DISC_RANGE[persona]
        tot = 0
        for _ in range(1500):
            b = _basket(probe, cat, persona, wcache)
            disc = (lo + hi) / 2
            tot += sum(q * _price(cat, s, disc) for s, q in b.items())
        calib[persona] = tot / 1500
    orders, seq = [], defaultdict(int)
    accum = defaultdict(float)
    d = C.START
    while d <= C.END:
        for ch in C.CHANNELS:
            code = ch["code"]
            if code == "TIKTOK" and d < dt.date(2026, 7, 1):
                continue
            wk = C.WEEKDAY[code][d.weekday()] / (sum(C.WEEKDAY[code]) / 7.0)
            tgt = daily_target(ch, d) * wk * event_mult(d, code) * C.SCALE
            if code == "B2B":
                # dua jenis: 78% omzet reseller, 22% korporat; Hari Batik Nasional memicu pesanan korporat
                parts = [("RESELLER", 0.78), ("CORPORATE", 0.22 * (3.0 if dt.date(2026, 9, 24) <= d <= dt.date(2026, 10, 3) else 1.0))]
            else:
                parts = [(code, 1.0)]
            for persona, share in parts:
                mean_basket = calib[persona]
                lam = tgt * share / mean_basket
                if code == "B2B":      # pesanan grosir/korporat lumpy tapi terdistribusi: akumulator + jitter
                    accum[persona] += lam
                    n = 0
                    while accum[persona] >= rng.uniform(0.7, 1.3):
                        accum[persona] -= 1.0
                        n += 1
                else:
                    n = _poisson(rng, lam)
                for _ in range(n):
                    lo, hi = DISC_RANGE[persona]
                    disc = rng.uniform(lo, hi)
                    if event_mult(d, code) > 1.3 and persona in ("SHOPEE", "TOKPED", "TIKTOK"):
                        disc = min(0.40, disc + 0.06)
                    disc = round(disc / 0.01) * 0.01
                    lines = _basket(rng, cat, persona, wcache)
                    seq[(code, d)] += 1
                    hour = {"STORE": rng.randint(10, 20), "B2B": rng.randint(9, 16), "TIKTOK": rng.choice([13, 19, 20, 21, 22]),
                            "INSTAGRAM": rng.randint(8, 22)}.get(code, rng.randint(7, 22))
                    o = {"date": d, "time": (hour, rng.randint(0, 59)), "ch": code, "persona": persona, "disc": disc,
                         "lines": [(s, q, _price(cat, s, disc)) for s, q in lines.items()],
                         "ref": f"{ch['ref']}-{d:%y%m%d}-{seq[(code, d)]:03d}",
                         "cust": _pareto(rng, POOL.get(code, 1)) if code in POOL else None,
                         "ret": rng.random() < RETURN_P.get(code, 0.0),
                         "cancel": rng.random() < CANCEL_P.get(code, 0.0),
                         "u": rng.random()}
                    orders.append(o)
        d += dt.timedelta(days=1)
    orders.sort(key=lambda o: (o["date"], o["time"], o["ref"]))
    return orders


def _poisson(rng, lam):
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= L:
            return k - 1


if __name__ == "__main__":
    orders = build()
    by = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))
    for o in orders:
        dpp = sum(q * p for _, q, p in o["lines"])
        qty = sum(q for _, q, _ in o["lines"])
        r = by[o["date"].strftime("%Y-%m")][o["ch"] if o["ch"] != "B2B" else o["persona"]]
        r[0] += 1; r[1] += dpp; r[2] += qty
    tot_all = 0
    for ym in sorted(by):
        tt = [0, 0, 0]
        print(ym)
        for ch, (n, dpp, q) in sorted(by[ym].items()):
            print(f"   {ch:10s} orders={n:4d} DPP={dpp/1e6:7.1f}jt  qty={q:5d}  aov={dpp/max(n,1)/1e3:7.0f}rb")
            tt = [tt[0] + n, tt[1] + dpp, tt[2] + q]
        print(f"   TOTAL      orders={tt[0]:4d} DPP={tt[1]/1e6:7.1f}jt  qty={tt[2]:5d}")
        tot_all += tt[1]
    print("total DPP", round(tot_all / 1e6, 1), "jt; orders", len(orders))
