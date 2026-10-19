"""Master data v2: mitra (pemasok, penjahit, pelanggan lokal Bali + luar Bali), produk + foto, BoM subkontrak,
gudang & lokasi, price list, POS, karyawan. Idempoten (cari dulu, buat bila belum ada)."""
import base64
import random

import art
import config as C
from common import Steps, load_registry, save_registry


def _pick_field(model, *cands):
    for n in cands:
        if n in model._fields:
            return n
    return None


class Master:
    def __init__(self, env):
        ctx = dict(env.context, tracking_disable=True, mail_notrack=True, mail_create_nolog=True)
        self.env = env(context=ctx)
        self.reg = load_registry(env)
        self.rng = random.Random(C.SEED + 11)
        self.P = self.env["res.partner"]
        self.country = self.env.ref("base.id")
        self.states = {s.code: s.id for s in self.env["res.country.state"].search([("country_id", "=", self.country.id)])}
        self.npwp_seq = 0
        self.out = {"partners": {}, "pool": {}, "products": {}, "tailors": [], "raw": {}}

    # ------------------------------------------------------------------ helpers
    def _npwp(self):
        self.npwp_seq += 1
        return f"09{self.npwp_seq:014d}"

    def partner(self, name, city=None, state="BA", zipc=None, street=None, pkp=None, company=True, **extra):
        p = self.P.search([("name", "=", name)], limit=1)
        if p:
            return p
        vals = {"name": name, "company_type": "company" if company else "person", "country_id": self.country.id,
                "tz": "Asia/Makassar", **extra}
        if city:
            vals["city"] = city
        if state and state in self.states:
            vals["state_id"] = self.states[state]
        if zipc:
            vals["zip"] = zipc
        if street:
            vals["street"] = street
        if company and pkp is not None and "btk_npwp" in self.P._fields:
            vals.update({"btk_npwp": self._npwp(), "btk_is_pkp": bool(pkp)})
        return self.P.create(vals)

    def _bali_addr(self, rng):
        city = rng.choices(list(C.BALI_CITY_W), weights=list(C.BALI_CITY_W.values()))[0]
        area, zipc = rng.choice(C.BALI_AREAS[city])
        return city, "BA", zipc, f"{rng.choice(C.STREETS)} {rng.choice(['', 'Gg. '])}{rng.choice(['Mawar', 'Pura', 'Teratai', 'Sari', 'Dharma', 'Wangaya'])} No. {rng.randint(1, 99)}, {area}"

    def _out_addr(self, rng):
        city, st, zipc, _w = rng.choices(C.OUT_OF_BALI, weights=[x[3] for x in C.OUT_OF_BALI])[0]
        return city, st, str(int(zipc) + rng.randint(0, 40)), f"{rng.choice(C.STREETS)} No. {rng.randint(1, 120)}"

    def _person_name(self, rng, bali):
        if bali:
            a, b = rng.choice(C.FIRST_BALI), rng.choice(C.LAST_BALI)
            return f"{a} {b}"
        return f"{rng.choice(C.FIRST_ID)} {rng.choice(C.LAST_ID)}"

    def _phone(self, rng):
        return f"08{rng.choice(['12', '13', '21', '38', '52', '57', '77', '81'])}-{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}"

    # ------------------------------------------------------------------ mitra
    def partners(self):
        rng = random.Random(C.SEED + 21)
        env = self.env
        # pemasok bahan / pengrajin / penjahit
        locs = {"CV Tekstil Pekalongan Mulia": ("Pekalongan", "JT", "51111"), "PT Kain Printing Bandung Sejahtera": ("Bandung", "JB", "40285"),
                "UD Aksesori Jahit Denpasar": ("Denpasar", "BA", "80119"), "Pengrajin Batik Tulis Solo": ("Solo", "JT", "57148"),
                "Pengrajin Batik Tulis Cirebon": ("Cirebon", "JB", "45153"), "Pengrajin Batik Tulis Yogya": ("Yogyakarta", "YO", "55151"),
                "Pengrajin Batik Pekalongan": ("Pekalongan", "JT", "51117")}
        for name, (pkp, term) in C.SUPPLIER_PKP.items():
            city, st, z = locs[name]
            p = self.partner(name, city, st, z, f"Jl. Sentra Kerajinan No. {rng.randint(3, 80)}", pkp=pkp)
            self.out["partners"][name] = p.id
        for name, city, pkp, cap, prefs in C.TAILORS:
            area = rng.choice(C.BALI_AREAS[city])
            p = self.partner(name, city, "BA", area[1], f"Jl. Raya {area[0]} No. {rng.randint(2, 70)}", pkp=pkp)
            self.out["partners"][name] = p.id
            self.out["tailors"].append(p.id)
        for key, (name, city) in C.SERVICE_PARTNERS.items():
            st = "BA" if city in C.BALI_AREAS else "JK"
            p = self.partner(name, city, st, None, None, pkp=True if key not in ("landlord_gudang",) else False)
            self.out["partners"][key] = p.id
        # reseller & korporat
        rl = self._ensure_pricelist("Reseller (diskon grosir 30%)", 30.0)
        cl = self._ensure_pricelist("Korporat (diskon 12%)", 12.0)
        for name, city, st, disc, term, pkp in C.RESELLERS:
            z = (C.BALI_AREAS.get(city) or [("", "80000")])[0][1] if city in C.BALI_AREAS else "10110"
            p = self.partner(name, city, st, z, f"{rng.choice(C.STREETS)} No. {rng.randint(1, 150)}", pkp=pkp,
                             phone=self._phone(rng), property_product_pricelist=rl.id)
            self.out["partners"]["RES:" + name] = p.id
        for name, city, kind, pkp in C.CORPORATES:
            z = C.BALI_AREAS[city][0][1]
            p = self.partner(name, city, "BA", z, f"{rng.choice(C.STREETS)} No. {rng.randint(1, 150)}", pkp=pkp,
                             phone=self._phone(rng), property_product_pricelist=cl.id)
            self.out["partners"]["COR:" + name] = p.id
        # kumpulan pelanggan perorangan per channel
        bali_share = {"STORE": 0.85, "SHOPEE": 0.25, "TOKPED": 0.20, "TIKTOK": 0.30, "INSTAGRAM": 0.70}
        from plan import POOL
        for code, n in POOL.items():
            ids = []
            seen = set()
            while len(ids) < n:
                bali = rng.random() < bali_share[code]
                name = self._person_name(rng, bali)
                if code == "TIKTOK" and rng.random() < 0.4:
                    name = f"{name.split()[0]} ***{rng.randint(10, 99)}"      # username tersamar khas live commerce
                if name in seen:
                    name = f"{name} {rng.choice('ABCDEFGHJKLMNPRSTW')}."
                if name in seen:
                    continue
                seen.add(name)
                city, st, z, street = self._bali_addr(rng) if bali else self._out_addr(rng)
                p = self.partner(name, city, st, z, street, company=False, phone=self._phone(rng),
                                 ref=f"{code[:3]}{len(ids) + 1:03d}")
                ids.append(p.id)
            self.out["pool"][code] = ids
        print(f"Mitra: {len(self.out['partners'])} badan/mitra, pelanggan perorangan {sum(len(v) for v in self.out['pool'].values())}")

    def _ensure_pricelist(self, name, pct):
        PL = self.env["product.pricelist"]
        pl = PL.search([("name", "=", name)], limit=1)
        if not pl:
            pl = PL.create({"name": name, "item_ids": [(0, 0, {"applied_on": "3_global", "compute_price": "percentage", "percent_price": pct})]})
        return pl

    # ------------------------------------------------------------------ produk
    def products(self):
        env = self.env
        Tmpl, categ, tax = env["product.template"], self.reg["categ"], self.reg["tax"]
        sale_tax = _pick_field(Tmpl, "taxes_id", "tax_ids", "sale_tax_ids")
        route = env.ref("mrp_subcontracting.route_resupply_subcontractor_mto", raise_if_not_found=False)
        meter = env.ref("uom.product_uom_meter", raise_if_not_found=False) or env["uom.uom"].search([("name", "=", "m")], limit=1)
        unit = env.ref("uom.product_uom_unit")
        partners = self.out["partners"]
        raw_cost = {}
        for sku, name, uom, cost, vendor in C.RAW:
            t = Tmpl.search([("default_code", "=", sku)], limit=1)
            if not t:
                vals = {"name": name, "default_code": sku, "type": "consu", "is_storable": True, "categ_id": categ["Bahan Baku"],
                        "list_price": 0, "standard_price": cost, "sale_ok": False, "purchase_ok": True,
                        "uom_id": (meter if uom == "m" else unit).id,
                        "seller_ids": [(0, 0, {"partner_id": partners[vendor], "price": cost, "min_qty": 0})]}
                if route:
                    vals["route_ids"] = [(4, route.id)]
                t = Tmpl.create(vals)
            self.out["raw"][sku] = t.product_variant_id.id
            raw_cost[sku] = cost
        n_img = 0
        made_cost = {}
        # barang jadi buatan sendiri
        for i, (sku, name, cat, price, w, (cloth, meters), acc_sets, jahit, pat, col) in enumerate(C.MADE):
            cost = round(raw_cost[cloth] * meters + raw_cost["RM-ACC-SET"] * acc_sets + jahit)
            made_cost[sku] = cost
            t = Tmpl.search([("default_code", "=", sku)], limit=1)
            if not t:
                vals = {"name": name, "default_code": sku, "type": "consu", "is_storable": True, "categ_id": categ[cat],
                        "list_price": price, "standard_price": cost, "sale_ok": True, "purchase_ok": True,
                        "seller_ids": [(0, 0, {"partner_id": tid, "price": round(jahit * (1.0 if k else 1.0) * (1.04 if k == 3 else 1.0)), "min_qty": 0})
                                       for k, tid in enumerate(self.out["tailors"])]}
                if sale_tax:
                    vals[sale_tax] = [(6, 0, [tax["ppn_out"]])]
                t = Tmpl.create(vals)
                env["mrp.bom"].create({
                    "product_tmpl_id": t.id, "product_qty": 1, "type": "subcontract",
                    "subcontractor_ids": [(6, 0, self.out["tailors"])],
                    "bom_line_ids": [(0, 0, {"product_id": self.out["raw"][cloth], "product_qty": meters}),
                                     (0, 0, {"product_id": self.out["raw"]["RM-ACC-SET"], "product_qty": acc_sets})]})
            self.out["products"][sku] = t.product_variant_id.id
            n_img += self._image(t, sku, name, pat, col, i)
        # barang jadi beli jadi
        for j, (sku, name, cat, cost, price, w, vendor, pat, col) in enumerate(C.BOUGHT):
            t = Tmpl.search([("default_code", "=", sku)], limit=1)
            if not t:
                vals = {"name": name, "default_code": sku, "type": "consu", "is_storable": True, "categ_id": categ[cat],
                        "list_price": price, "standard_price": cost, "sale_ok": True, "purchase_ok": True,
                        "seller_ids": [(0, 0, {"partner_id": partners[vendor], "price": cost, "min_qty": 0})]}
                if sale_tax:
                    vals[sale_tax] = [(6, 0, [tax["ppn_out"]])]
                t = Tmpl.create(vals)
            self.out["products"][sku] = t.product_variant_id.id
            n_img += self._image(t, sku, name, pat, col, 100 + j)
        # produk jasa / non-stok
        lc = Tmpl.search([("name", "=", "Ongkos Angkut Pembelian")], limit=1)
        lc_vals = {"landed_cost_ok": True} if "landed_cost_ok" in Tmpl._fields else {}
        if lc:
            lc.write({"list_price": 0, "sale_ok": False, **lc_vals})
        else:
            lc = Tmpl.create({"name": "Ongkos Angkut Pembelian", "type": "service", "list_price": 0, "sale_ok": False, **lc_vals})
        self.out["lc_product"] = lc.product_variant_id.id
        self.out["made_cost"] = made_cost
        print(f"Produk: {len(C.RAW)} bahan baku, {len(C.MADE)} buatan sendiri (BoM subkontrak), {len(C.BOUGHT)} beli jadi; {n_img} foto dibuat")

    def _image(self, tmpl, sku, name, pat, col, seed):
        if tmpl.image_1920:
            return 0
        data = art.render(art.shape_for(sku, name), pat, col, seed=seed + 3)
        tmpl.image_1920 = base64.b64encode(data)
        return 1

    # ------------------------------------------------------------------ karyawan
    def employees(self):
        env = self.env
        if "btk.employee" not in env:
            return
        ana = {a.name: a.id for a in env["account.analytic.account"].search([])}
        T, G, K = ana.get("Toko Denpasar"), ana.get("Gudang & Produksi"), ana.get("Kantor Pusat")
        staff = [("Siti Rahayu (Manajer Toko)", "K1", 6_500_000, 700_000, "2024-02-01", T),
                 ("Putu Ayu Lestari (Kasir)", "TK0", 3_600_000, 300_000, "2025-03-10", T),
                 ("Komang Adi Pratama (Kasir)", "K0", 3_600_000, 300_000, "2025-06-02", T),
                 ("Made Dewi Sartika (Admin Online)", "TK0", 4_000_000, 300_000, "2024-09-15", K),
                 ("Kadek Surya Atmaja (Admin & CS)", "TK0", 3_800_000, 300_000, "2025-01-20", K),
                 ("Dewi Lestari (Host Live)", "TK0", 3_800_000, 700_000, "2026-07-01", K),
                 ("Ayu Mahesa (Host Live 2)", "TK0", 3_600_000, 700_000, "2026-08-01", K),
                 ("Agus Pratama (Gudang)", "K2", 3_800_000, 300_000, "2024-05-06", G),
                 ("Wayan Sudana (Gudang & QC)", "K1", 3_800_000, 300_000, "2025-04-14", G)]
        for nm, ptkp, basic, allow, join, cc in staff:
            if not env["btk.employee"].search([("name", "=", nm)], limit=1):
                env["btk.employee"].create({"name": nm, "ptkp": ptkp, "basic_salary": basic, "allowance": allow,
                                            "join_date": join, "analytic_account_id": cc})
        print(f"Karyawan: {len(staff)}")


def run(env):
    s = Steps(env)
    m = Master(env)
    with s.step("Master: mitra (pemasok, penjahit, reseller, korporat, pelanggan Bali & luar Bali)"):
        m.partners()
        save_registry(env, {"m_partners": m.out["partners"], "m_pool": m.out["pool"], "m_tailors": m.out["tailors"]})
    with s.step("Master: produk, foto, BoM subkontrak"):
        m.out["partners"] = load_registry(env).get("m_partners", m.out["partners"])
        m.out["tailors"] = load_registry(env).get("m_tailors", m.out["tailors"])
        m.products()
        save_registry(env, {"m_products": m.out["products"], "m_raw": m.out["raw"], "m_lc": m.out["lc_product"],
                            "m_made_cost": m.out["made_cost"]})
    with s.step("Master: karyawan payroll"):
        m.employees()
    return s.summary()
