"""Perencana pasokan (murni Python, tanpa Odoo): dari rencana order -> jadwal pembelian bahan baku, order jahit
(subkontrak), pembelian barang jadi, penerimaan via Sortase -> Stok Utama, serta transfer ke Toko & Marketplace.
Simulasi stok bayangan memastikan penjualan tidak melebihi stok (kekurangan -> qty dipotong = penjualan hilang).

Dijalankan sendiri untuk menyetel:  python supply.py"""
import datetime as dt
import math
import random
from collections import defaultdict

import config as C
import plan as P

LOC_OF = {"STORE": "TKO", "SHOPEE": "MKT", "TOKPED": "MKT", "TIKTOK": "MKT"}      # default: MAIN
MADE = {sku: dict(cat=cat, price=price, cloth=cloth, meters=m, acc=acc, fee=fee)
        for sku, _n, cat, price, _w, (cloth, m), acc, fee, _p, _c in C.MADE}
BOUGHT = {sku: dict(cat=cat, cost=cost, price=price, vendor=v) for sku, _n, cat, cost, price, _w, v, _p, _c in C.BOUGHT}
RAWINFO = {sku: dict(uom=u, cost=cost, vendor=v) for sku, _n, u, cost, v in C.RAW}
TAILOR_CAP = {t[0]: t[3] for t in C.TAILORS}           # pcs / minggu
TAILOR_PREF = {t[0]: t[4] for t in C.TAILORS}

TAILOR_LEAD = 7        # hari dari PO jahit sampai barang jadi diterima di Sortase
RM_LEAD = 3            # hari dari PO bahan baku sampai diterima
SORT_DAYS = 1          # Sortase -> Stok Utama
BOUGHT_LEAD = 5
RM_MIN = {"RM-KAIN-CAP": 50, "RM-KAIN-PRT": 50, "RM-KAIN-RAY": 50, "RM-ACC-SET": 40}
OPEN_DATE = C.START - dt.timedelta(days=1)

# Keterlambatan pemasok (edge case): (awalan sku, mulai PO, selesai PO, hari tambahan, alasan)
SUPPLIER_DELAYS = [
    ("BC-DRS", dt.date(2026, 9, 28), dt.date(2026, 10, 3), 6, "Penjahit kekurangan tenaga saat musim pesanan seragam"),
    ("BC-SRB", dt.date(2026, 9, 28), dt.date(2026, 10, 3), 6, "Penjahit kekurangan tenaga saat musim pesanan seragam"),
]
# Penerimaan parsial: sku awalan -> (tanggal PO terdekat setelah, bagian diterima pertama, hari menunggu sisa)
PARTIAL = [("BC-KMJ-001", dt.date(2026, 8, 3), 0.7, 5), ("BP-DRS", dt.date(2026, 9, 14), 0.6, 6)]


def workday(d):
    return d + dt.timedelta(days=1) if d.weekday() == 6 else d


def build(orders=None, seed=None):
    rng = random.Random((seed or C.SEED) + 5)
    orders = orders if orders is not None else P.build()
    end = C.END
    days = [C.START + dt.timedelta(days=i) for i in range((end - C.START).days + 1)]
    # permintaan harian per (lokasi, sku) dari rencana
    dem = defaultdict(lambda: defaultdict(int))
    for o in orders:
        loc = LOC_OF.get(o["ch"], "MAIN")
        for sku, q, _ in o["lines"]:
            dem[o["date"]][(loc, sku)] += q
    skus = list(MADE) + list(BOUGHT)
    # pesanan B2B (reseller/korporat) dikonfirmasi 2-4 minggu sebelum kirim -> perencana melihat ke depan 28 hari
    dem_b2b = defaultdict(lambda: defaultdict(int))
    for o in orders:
        if o["ch"] == "B2B":
            for sku, q, _ in o["lines"]:
                dem_b2b[o["date"]][sku] += q

    def _raw_need(sku, a, b, loc=None):
        t = 0
        d = a
        while d <= min(b, end):
            for (l, s), q in dem.get(d, {}).items():
                if s == sku and (loc is None or l == loc):
                    t += q
            d += dt.timedelta(days=1)
        return t

    def need(sku, a, b, loc=None):
        t = _raw_need(sku, a, b, loc)
        if b > end:      # asumsi permintaan setelah 17 Okt = rata-rata 14 hari terakhir
            avg = _raw_need(sku, end - dt.timedelta(days=13), end, loc) / 14.0
            t += avg * (b - max(a - dt.timedelta(days=1), end)).days
        return t

    def need_b2b(sku, a, b):
        t, d = 0, a
        while d <= min(b, end):
            t += dem_b2b.get(d, {}).get(sku, 0)
            d += dt.timedelta(days=1)
        return t

    need.b2b = need_b2b

    stock = {loc: defaultdict(float) for loc in ("MAIN", "TKO", "MKT")}
    raw = defaultdict(float)
    incoming = []          # (tgl tiba di MAIN (bisa dipakai), sku, qty)  FG
    rm_incoming = []       # (tgl tiba, rm_sku, qty)
    events = []
    ev = lambda d, kind, **kw: events.append({"date": d, "kind": kind, **kw})
    stats = defaultdict(float)

    # ---- saldo awal (30 Jun)
    h = C.START + dt.timedelta(days=15)
    opening = {"fg": {}, "rm": {}}
    for sku in skus:
        for loc, mult, plus in (("TKO", 1.25, 2), ("MKT", 1.25, 2), ("MAIN", 1.10, 3)):
            q = math.ceil(need(sku, C.START, h, loc) * mult) + plus
            stock[loc][sku] = q
            opening["fg"][(loc, sku)] = q
    for r, q in (("RM-KAIN-CAP", 140), ("RM-KAIN-PRT", 90), ("RM-KAIN-RAY", 60), ("RM-ACC-SET", 120)):
        raw[r] = q
        opening["rm"][r] = q
    ev(OPEN_DATE, "opening", fg=opening["fg"], rm=opening["rm"])

    pending_tailor = []   # PO jahit terjadwal (dipakai untuk menghitung "incoming")
    for d in days:
        # 1) kedatangan
        for a in [x for x in incoming if x[0] == d]:
            stock["MAIN"][a[1]] += a[2]
        incoming = [x for x in incoming if x[0] > d]
        for a in [x for x in rm_incoming if x[0] == d]:
            raw[a[1]] += a[2]
        rm_incoming = [x for x in rm_incoming if x[0] > d]
        # 2) tanggal pemesanan ulang (Senin) -> perencanaan
        if d.weekday() == 0 or d == C.START:
            plan_week(d, skus, stock, raw, incoming, rm_incoming, dem, need, ev, rng, stats)
        # 3) transfer Senin & Kamis (Stok Utama -> Toko / Marketplace)
        if d.weekday() in (0, 3):
            span = 3 if d.weekday() == 0 else 4
            for loc in ("TKO", "MKT"):
                lines = []
                for sku in skus:
                    want = math.ceil(need(sku, d, d + dt.timedelta(days=span - 1), loc) * 1.2) + (3 if loc == "TKO" else 2)
                    short = max(0, want - stock[loc][sku])
                    reserve = need(sku, d, d + dt.timedelta(days=span - 1), "MAIN")
                    q = int(min(short, max(0, stock["MAIN"][sku] - reserve)))
                    if q >= 1:
                        lines.append((sku, q))
                        stock["MAIN"][sku] -= q
                        stock[loc][sku] += q
                if lines:
                    ev(d, "transfer", loc=loc, lines=lines)
        # 4) penjualan hari ini (urut waktu)
        for o in [x for x in orders if x["date"] == d]:
            loc = LOC_OF.get(o["ch"], "MAIN")
            new = []
            for sku, q, p in o["lines"]:
                have = int(stock[loc][sku])
                got = min(q, have)
                if got < q:
                    stats["short_lines"] += 1
                    stats["short_qty"] += q - got
                    stats["short_dpp"] += (q - got) * p
                if got > 0:
                    stock[loc][sku] -= got
                    new.append((sku, got, p))
                stats["want_qty"] += q
            o["lines"] = new
            o["loc"] = loc
            if not new:
                o["void"] = True
        # 5) retur: 70% restock, 30% reject (barang rusak/cacat)
        for o in [x for x in orders if x["date"] == d - dt.timedelta(days=5)]:
            if o.get("ret") and not o.get("void") and not o.get("cancel"):
                o["ret_restock"] = rng.random() < 0.7
                o["ret_date"] = d
                if o["ret_restock"]:
                    for sku, q, _ in o["lines"]:
                        stock[o["loc"]][sku] += q
    # jadwalkan retur sebagai event setelah simulasi
    for o in orders:
        if o.get("ret_date"):
            ev(o["ret_date"], "return", order=o["ref"])
    stats["orders_void"] = sum(1 for o in orders if o.get("void"))
    events.sort(key=lambda e: e["date"])
    return {"events": events, "orders": orders, "stats": stats, "opening": opening, "final_stock": stock, "raw": raw}


def _delay(sku, d):
    for pref, a, b, extra, why in SUPPLIER_DELAYS:
        if sku.startswith(pref) and a <= d <= b:
            return extra, why
    return 0, None


def plan_week(d, skus, stock, raw, incoming, rm_incoming, dem, need, ev, rng, stats):
    H_MADE = 4 + TAILOR_LEAD + SORT_DAYS + 7          # t_po(+4) + jahit + sortase + cover 7 hari
    tailor_lines = defaultdict(list)                  # tailor -> [(sku, qty)]
    # --- barang jadi buatan sendiri
    loads = defaultdict(float)
    cand = []
    for sku in MADE:
        horizon = d + dt.timedelta(days=H_MADE)
        dsum = need(sku, d, horizon) + need.b2b(sku, horizon + dt.timedelta(days=1), d + dt.timedelta(days=28))
        have = sum(stock[l][sku] for l in stock) + sum(q for t, s, q in incoming if s == sku)
        short = dsum * 1.10 + 3 - have
        if short >= 6:
            qty = int(math.ceil(short / 6.0) * 6)
            cand.append((sku, qty))
    cand.sort(key=lambda x: -x[1])
    for sku, qty in cand:
        prim = [t for t, pr in TAILOR_PREF.items() if any(sku.startswith(p) for p in pr)] or list(TAILOR_PREF)
        order = prim + [t for t in TAILOR_PREF if t not in prim]
        remaining = qty
        for t in order:
            free = TAILOR_CAP[t] * 1.15 - loads[t]
            if free >= 12:
                take = int(min(remaining, math.floor(free / 6.0) * 6)) if free < remaining else remaining
                if take >= 6:
                    tailor_lines[t].append((sku, take))
                    loads[t] += take
                    remaining -= take
            if remaining <= 0:
                break
        if remaining > 0:
            t = order[0]
            tailor_lines[t].append((sku, remaining))
            loads[t] += remaining
            stats["tailor_overload_pcs"] += remaining
    # --- bahan baku untuk PO jahit minggu ini
    t_po = workday(d + dt.timedelta(days=4))
    need_rm = defaultdict(float)
    for t, lines in tailor_lines.items():
        for sku, q in lines:
            m = MADE[sku]
            need_rm[m["cloth"]] += m["meters"] * q
            need_rm["RM-ACC-SET"] += m["acc"] * q
    rm_by_vendor = defaultdict(list)
    for r, req in need_rm.items():
        arriving = sum(q for t, s, q in rm_incoming if s == r)
        short = req * 1.04 - (raw[r] + arriving)
        if short > 0:
            q = int(math.ceil(short / RM_MIN[r]) * RM_MIN[r])
            rm_by_vendor[RAWINFO[r]["vendor"]].append((r, q))
            rm_incoming.append((workday(d + dt.timedelta(days=RM_LEAD + 1)), r, q))
        raw[r] -= req            # dipakai (diproyeksikan) saat PO jahit
    for v, lines in rm_by_vendor.items():
        ev(d, "rm_po", vendor=v, lines=lines, recv=workday(d + dt.timedelta(days=RM_LEAD)))
        stats["rm_po"] += 1
    # raw[] sudah dikurangi lebih awal (proyeksi); tambahkan kembali kedatangan agar tidak dobel (kedatangan diproses harian)
    # --- jahit: peristiwa
    for t, lines in tailor_lines.items():
        sched = []
        for sku, q in lines:
            extra, why = _delay(sku, t_po)
            sched.append((sku, q, extra, why))
        # penerimaan: tiap SKU diterima pada t_po + TAILOR_LEAD + keterlambatan; bagi menjadi 1-2 pengiriman
        recv_lines = defaultdict(list)       # tanggal -> [(sku, qty, reject)]
        partial_note = None
        for sku, q, extra, why in sched:
            base = workday(t_po + dt.timedelta(days=TAILOR_LEAD + extra))
            part = None
            for p in PARTIAL:
                key = ("p", p[0], p[1])
                if sku.startswith(p[0]) and t_po >= p[1] and key not in _USED:
                    _USED.add(key)
                    part = p
                    break
            rej_total = int(round(q * rng.choice([0, 0, 0.01, 0.02, 0.03]))) if q >= 12 else 0
            if part:
                first = int(round(q * part[2]))
                recv_lines[base].append((sku, first, 0))
                recv_lines[workday(base + dt.timedelta(days=part[3]))].append((sku, q - first, rej_total))
                partial_note = "Penerimaan parsial"
            else:
                recv_lines[base].append((sku, q, rej_total))
            if extra:
                stats["delayed_po"] += 1
        po_lines = [(sku, q) for sku, q, _e, _w in sched]
        delay_note = next((w for _s, _q, e, w in sched if e), None)
        ev(t_po, "tailor_po", tailor=t, lines=po_lines, recv=dict(recv_lines), note=delay_note or partial_note)
        stats["tailor_po"] += 1
        stats["tailor_pcs"] += sum(q for _s, q in po_lines)
        for rd, rl in recv_lines.items():
            for sku, q, rej in rl:
                incoming.append((workday(rd + dt.timedelta(days=SORT_DAYS)), sku, q - rej))
    # --- barang jadi beli jadi
    by_vendor = defaultdict(list)
    for sku in BOUGHT:
        horizon = d + dt.timedelta(days=BOUGHT_LEAD + 12)
        dsum = need(sku, d, horizon) + need.b2b(sku, horizon + dt.timedelta(days=1), d + dt.timedelta(days=21))
        have = sum(stock[l][sku] for l in stock) + sum(q for t, s, q in incoming if s == sku)
        short = dsum * 1.12 + 2 - have
        if short >= 3:
            q = int(math.ceil(short / 3.0) * 3)
            by_vendor[BOUGHT[sku]["vendor"]].append((sku, q))
            incoming.append((workday(d + dt.timedelta(days=BOUGHT_LEAD + SORT_DAYS)), sku, q))
    for v, lines in by_vendor.items():
        ev(d, "bought_po", vendor=v, lines=lines, recv=workday(d + dt.timedelta(days=BOUGHT_LEAD)))
        stats["bought_po"] += 1


_USED = set()


if __name__ == "__main__":
    _USED.clear()
    res = build()
    s = res["stats"]
    kinds = defaultdict(int)
    for e in res["events"]:
        kinds[e["kind"]] += 1
    print(dict(kinds))
    want, short = s["want_qty"], s["short_qty"]
    print(f"permintaan {want:.0f} pcs, kekurangan {short:.0f} pcs ({short / want * 100:.1f}%), nilai hilang {s['short_dpp'] / 1e6:.1f} jt")
    print({k: v for k, v in s.items() if k not in ("_used",)})
    tot_pcs = defaultdict(int)
    for e in res["events"]:
        if e["kind"] == "tailor_po":
            tot_pcs[e["date"].strftime("%Y-%m")] += sum(q for _s, q in e["lines"])
    print("pcs jahit per bulan:", dict(tot_pcs))
    sold = defaultdict(int)
    for o in res["orders"]:
        sold[o["date"].strftime("%Y-%m")] += sum(q for _s, q, _p in o["lines"])
    print("pcs terjual per bulan:", dict(sold))
    print("stok akhir total pcs:", {l: int(sum(v.values())) for l, v in res["final_stock"].items()})
    print("stok akhir bahan baku:", {k: round(v) for k, v in res["raw"].items()})
    zero = [(l, k) for l, v in res["final_stock"].items() for k, q in v.items() if q <= 0]
    print("SKU kosong di akhir:", zero[:12])
