"""Generator data dummy: produk batik, pembelian (+landed cost), penjualan multi-channel, settlement marketplace,
biaya operasional, pajak bulanan, lalu audit rule + user demo. Semua angka fiktif."""
import datetime as dt
import math
import random
from collections import defaultdict

from dateutil.relativedelta import relativedelta

import config as C
from common import Steps, load_registry, save_registry, user_group_field

SEASON = {1: 1.0, 2: 0.95, 3: 1.25, 4: 1.1, 5: 0.95, 6: 0.95, 7: 1.0, 8: 1.05, 9: 1.15, 10: 1.3, 11: 1.1, 12: 1.2}


def rupiah(x):
    return int(round(x))


def pick_field(model, *candidates):
    """Nama field berbeda antar versi Odoo (mis. tax_id vs tax_ids): ambil yang ada."""
    for name in candidates:
        if name in model._fields:
            return name
    return None


def month_end(d):
    return (d.replace(day=1) + relativedelta(months=1)) - dt.timedelta(days=1)


class Seeder:
    def __init__(self, env):
        ctx = dict(env.context, tracking_disable=True, mail_notrack=True, mail_create_nolog=True,
                   mail_auto_subscribe_no_notify=True, skip_sms=True)
        self.env = env(context=ctx)
        self.reg = load_registry(env)
        self.acc = self.reg["acc"]
        self.tax = self.reg["tax"]
        self.jr = self.reg["journal"]
        self.ana = self.reg["analytic"]
        self.rng = random.Random(C.SEED)
        self.today = dt.date.today()
        first = self.today.replace(day=1)
        self.months = [first - relativedelta(months=i) for i in range(C.MONTHS - 1, -1, -1)]
        self.start = self.months[0]
        self.partners, self.products, self.teams = {}, {}, {}
        self.nsfp_seq = 0
        self.onhand = defaultdict(int)
        self.settle = defaultdict(list)   # channel -> [(pay_date, gross, dpp)]
        self.cash_in = defaultdict(int)   # 'YYYY-MM' -> kas toko
        self.orders = []
        self.stats = defaultdict(int)
        self._stock_col = None

    # ------------------------------------------------------------------ master
    def _partner(self, name, company=True, **extra):
        P = self.env["res.partner"]
        p = P.search([("name", "=", name)], limit=1)
        if not p:
            p = P.create({"name": name, "company_type": "company" if company else "person",
                          "country_id": self.env.ref("base.id").id, **extra})
        return p

    def master(self):
        env = self.env
        for name in C.VENDORS:
            self.partners[name] = self._partner(name)
        for key, name in C.SERVICE_PARTNERS.items():
            self.partners[key] = self._partner(name)
        for ch in C.CHANNELS:
            self.partners[ch["code"]] = self._partner(ch["partner"], company=False)
        self.ig_customers = [self._partner(f"Pelanggan IG {i:02d}", company=False) for i in range(1, 41)]

        Team = env["crm.team"]
        for ch in C.CHANNELS:
            t = Team.search([("name", "=", ch["team"])], limit=1) or Team.create({"name": ch["team"]})
            self.teams[ch["code"]] = t

        categ = self.reg["categ"]
        Tmpl = env["product.template"]
        storable = {"is_storable": True} if "is_storable" in Tmpl._fields else {}
        ptype = "consu" if storable else "product"
        for sku, name, cat, cost, price, weight, vendor in C.PRODUCTS:
            tmpl = Tmpl.search([("default_code", "=", sku)], limit=1)
            if not tmpl:
                vals = {
                    "name": name, "default_code": sku, "type": ptype, **storable,
                    "categ_id": categ[cat], "list_price": price, "standard_price": cost,
                    "seller_ids": [(0, 0, {"partner_id": self.partners[vendor].id, "price": cost, "min_qty": 0})],
                }
                sale_tax = pick_field(Tmpl, "taxes_id", "tax_ids", "sale_tax_ids")
                buy_tax = pick_field(Tmpl, "supplier_taxes_id", "purchase_tax_ids")
                if sale_tax:
                    vals[sale_tax] = [(6, 0, [self.tax["ppn_out"]])]
                if buy_tax:
                    vals[buy_tax] = [(6, 0, [self.tax["ppn_in"]])]
                tmpl = Tmpl.create(vals)
            self.products[sku] = {"p": tmpl.product_variant_id, "cost": cost, "price": price,
                                  "weight": weight, "vendor": vendor, "name": name}
        lc_fields = {"landed_cost_ok": True} if "landed_cost_ok" in Tmpl._fields else {}
        self.lc_product = Tmpl.search([("name", "=", "Ongkos Angkut Pembelian")], limit=1) or Tmpl.create(
            {"name": "Ongkos Angkut Pembelian", "type": "service", **lc_fields})
        print(f"Master: {len(self.partners)} partner, {len(self.products)} produk, {len(self.teams)} tim channel")

    # ------------------------------------------------------------------ helpers
    def _pay(self, moves, journal_id, date):
        if date > self.today:
            return
        reg = self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=moves.ids).create(
            {"payment_date": date, "journal_id": journal_id})
        reg._create_payments()

    def _journal_entry(self, jcode, date, ref, lines):
        """lines: (account_id, debit, credit, partner_id|None, analytic_distribution|None)"""
        vals = []
        for acc, dr, cr, partner, dist in lines:
            if not (dr or cr):
                continue
            v = {"account_id": acc, "debit": dr, "credit": cr, "name": ref}
            if partner:
                v["partner_id"] = partner
            if dist:
                v["analytic_distribution"] = dist
            vals.append((0, 0, v))
        assert sum(x[2]["debit"] for x in vals) == sum(x[2]["credit"] for x in vals), f"JE tidak balance: {ref}"
        move = self.env["account.move"].create({
            "move_type": "entry", "journal_id": self.jr[jcode], "date": date, "ref": ref, "line_ids": vals})
        move.action_post()
        return move

    def _redate_stock(self, pickings, when):
        moves = pickings.move_ids
        pickings.write({"date_done": when})
        moves.write({"date": when})
        if "move_line_ids" in moves._fields:
            moves.move_line_ids.write({"date": when})
        d = when.date()
        if self._stock_col is None:
            self.env.cr.execute(
                "SELECT 1 FROM information_schema.columns WHERE table_name='account_move' AND column_name='stock_move_id'")
            self._stock_col = bool(self.env.cr.fetchone())
            if not self._stock_col:
                print("   !! kolom account_move.stock_move_id tidak ada: jurnal valuasi stok tidak di-redate")
        if self._stock_col:
            self.env.cr.execute("UPDATE account_move SET date=%s WHERE stock_move_id = ANY(%s)", (d, moves.ids))
            self.env.cr.execute(
                "UPDATE account_move_line SET date=%s WHERE move_id IN "
                "(SELECT id FROM account_move WHERE stock_move_id = ANY(%s))", (d, moves.ids))
        self.env.invalidate_all()

    def _receive_or_deliver(self, picking, when):
        picking.action_assign()
        for mv in picking.move_ids:
            mv.quantity = mv.product_uom_qty
        picking.with_context(skip_backorder=True, skip_sms=True, skip_immediate=True).button_validate()
        self._redate_stock(picking, when)

    def _nsfp(self, d):
        self.nsfp_seq += 1
        return f"040.000-{d.year % 100:02d}.{self.nsfp_seq:08d}"

    # ------------------------------------------------------------------ opening
    def opening_capital(self):
        d = self.start
        self._journal_entry("SETL", d, "Setoran modal awal (DEMO)", [
            (self.acc["bank_main"], C.OPENING_CAPITAL, 0, None, None),
            (self.acc["capital"], 0, C.OPENING_CAPITAL, None, None),
        ])

    # ------------------------------------------------------------------ orders plan
    def plan_orders(self):
        prods = list(self.products)
        weights = [self.products[s]["weight"] for s in prods]
        ch_w = [c["weight"] for c in C.CHANNELS]
        seq = defaultdict(int)
        for m in self.months:
            last = month_end(m)
            if last >= self.today:
                last = self.today - dt.timedelta(days=1)
                if last < m:  # hari ini tanggal 1: belum ada hari penuh di bulan ini
                    continue
            n = int(C.ORDERS_PER_MONTH * SEASON[m.month] * self.rng.uniform(0.9, 1.1))
            for _ in range(n):
                ch = self.rng.choices(C.CHANNELS, weights=ch_w)[0]
                day = self.rng.randint(1, max(1, last.day))
                d = m.replace(day=day)
                lines = {}
                for sku in set(self.rng.choices(prods, weights=weights, k=self.rng.choice([1, 1, 2, 2, 3]))):
                    lines[sku] = self.rng.choices([1, 2, 3], weights=[80, 15, 5])[0]
                lo, hi = ch["discount"]
                disc = round(self.rng.uniform(lo, hi) / 0.05) * 0.05
                seq[(ch["code"], d)] += 1
                ref = f"{ch['ref_prefix']}{d:%y%m%d}{seq[(ch['code'], d)]:04d}"
                self.orders.append({"date": d, "ch": ch, "lines": lines, "disc": disc, "ref": ref})
        self.orders.sort(key=lambda o: (o["date"], o["ref"]))
        print(f"Rencana order: {len(self.orders)} order, {self.months[0]:%Y-%m} s.d. {self.months[-1]:%Y-%m}")

    # ------------------------------------------------------------------ purchasing
    def purchase_month(self, m):
        env = self.env
        demand = defaultdict(int)
        nxt = m + relativedelta(months=1)
        for o in self.orders:
            if o["date"].replace(day=1) == m:
                for sku, q in o["lines"].items():
                    demand[sku] += q
        by_vendor = defaultdict(list)
        for sku, info in self.products.items():
            need = math.ceil(demand[sku] * 1.2) + 3
            if m == self.start:
                need += math.ceil(demand[sku] * 0.3)
            qty = max(0, need - self.onhand[sku])
            if qty:
                by_vendor[info["vendor"]].append((sku, qty))
        pos, total_qty_value = env["purchase.order"], 0
        day = min(2, max(1, (self.today - m).days))
        pdate = m.replace(day=day)
        for vendor, lines in by_vendor.items():
            order_lines = []
            for sku, qty in lines:
                info = self.products[sku]
                price = rupiah(info["cost"] * self.rng.uniform(0.97, 1.05) / 1000) * 1000
                order_lines.append((0, 0, {
                    "product_id": info["p"].id, "product_qty": qty, "price_unit": price,
                    "date_planned": dt.datetime.combine(pdate, dt.time(9)),
                }))
                self.onhand[sku] += qty
                total_qty_value += qty * price
            po = env["purchase.order"].create({
                "partner_id": self.partners[vendor].id,
                "date_order": dt.datetime.combine(pdate, dt.time(9)), "order_line": order_lines})
            po.button_confirm()
            for pick in po.picking_ids:
                self._receive_or_deliver(pick, dt.datetime.combine(pdate + dt.timedelta(days=1), dt.time(10)))
            po.action_create_invoice()
            bill = po.invoice_ids[:1]
            bdate = min(pdate + dt.timedelta(days=2), self.today)
            bill.write({"invoice_date": bdate, "date": bdate, "ref": f"INV-{po.name}",
                        "btk_nsfp": f"010.000-{bdate.year % 100:02d}.{self.rng.randint(10**7, 10**8 - 1)}"})
            bill.action_post()
            self._pay(bill, self.jr["BCA"], bdate + dt.timedelta(days=14))
            pos |= po
        for sku in self.products:  # konsumsi bulan ini
            self.onhand[sku] -= demand[sku]
        if pos and total_qty_value:
            self._landed_cost(pos, pdate + dt.timedelta(days=1), rupiah(total_qty_value * 0.015))

    def _landed_cost(self, pos, d, amount):
        env = self.env
        try:
            with env.cr.savepoint():
                cat = env["product.category"].browse(self.reg["categ"]["Batik Cap"])
                journal = cat.property_stock_journal
                lc = env["stock.landed.cost"].create({
                    "date": d, "picking_ids": [(6, 0, pos.picking_ids.ids)],
                    "account_journal_id": journal.id,
                    "cost_lines": [(0, 0, {
                        "name": "Ongkos angkut pembelian", "product_id": self.lc_product.product_variant_id.id,
                        "price_unit": amount, "split_method": "by_current_cost_price",
                        "account_id": self.acc["landed_accr"]})],
                })
                lc.compute_landed_cost()
                lc.button_validate()
                self.stats["landed_cost"] += amount
        except Exception as exc:  # noqa: BLE001
            print(f"   (landed cost dilewati: {str(exc)[:120]})")

    # ------------------------------------------------------------------ sales
    def sales_month(self, m):
        env = self.env
        orders = [o for o in self.orders if o["date"].replace(day=1) == m]
        failed = 0
        for o in orders:
            try:
                with env.cr.savepoint():
                    self._one_sale(o)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                if failed <= 3:
                    print(f"   order {o['ref']} gagal: {str(exc)[:200]}")
        print(f"   {len(orders) - failed}/{len(orders)} order sukses")
        if orders and failed > len(orders) / 2:
            raise RuntimeError(f"terlalu banyak order gagal ({failed}/{len(orders)})")

    def _one_sale(self, o):
        env, ch = self.env, o["ch"]
        code = ch["code"]
        when = dt.datetime.combine(o["date"], dt.time(self.rng.randint(8, 21), self.rng.randint(0, 59)))
        partner = self.rng.choice(self.ig_customers) if code == "INSTAGRAM" else self.partners[code]
        dist = {str(self.ana[code]): 100}
        lines = []
        for sku, qty in o["lines"].items():
            info = self.products[sku]
            price = rupiah(info["price"] * (1 - o["disc"]) / 1000) * 1000
            lines.append((0, 0, {
                "product_id": info["p"].id, "product_uom_qty": qty, "price_unit": price,
                "analytic_distribution": dist}))
        so = env["sale.order"].create({
            "partner_id": partner.id, "team_id": self.teams[code].id, "date_order": when,
            "client_order_ref": o["ref"], "order_line": lines})
        so.action_confirm()
        for pick in so.picking_ids:
            self._receive_or_deliver(pick, when)
        inv = so._create_invoices()
        inv.write({"invoice_date": o["date"], "btk_nsfp": self._nsfp(o["date"]),
                   "btk_channel_ref": o["ref"], "btk_kode_transaksi": "04"})
        inv.action_post()
        dpp = inv.amount_untaxed
        gross = inv.amount_total
        self.stats["omzet"] += dpp
        self.stats[f"omzet_{code}"] += dpp
        if code == "STORE" and self.rng.random() < 0.4:
            self._pay(inv, self.jr["KTOK"], o["date"])
            self.cash_in[o["date"].strftime("%Y-%m")] += rupiah(gross)
            return
        jcode = {"STORE": "QRIS", "SHOPEE": "SHPE", "TOKPED": "TKPD", "TIKTOK": "TTOK", "INSTAGRAM": "PGW"}[code]
        lag = 0 if code == "STORE" else C.SETTLEMENT_LAG_DAYS
        pdate = o["date"] + dt.timedelta(days=lag)
        if pdate <= self.today:
            self._pay(inv, self.jr[jcode], pdate)
            self.settle[code].append((pdate, rupiah(gross), rupiah(dpp)))

    # ------------------------------------------------------------------ settlement (fee, PPN masukan fee, PPh 22)
    def settle_channels(self):
        pph22_start = dt.date.fromisoformat(C.PPH22_START)
        platform = {"SHOPEE": "shopee_platform", "TOKPED": "tokped_platform", "TIKTOK": "tiktok_platform",
                    "INSTAGRAM": "gateway", "STORE": "bank"}
        wallet_acc = {c["code"]: self.acc[c["wallet"]] for c in C.CHANNELS}
        count = 0
        for ch in C.CHANNELS:
            code = ch["code"]
            buckets = defaultdict(list)
            for pdate, gross, dpp in self.settle[code]:
                buckets[((pdate - self.start).days // C.SETTLEMENT_BUCKET_DAYS)].append((pdate, gross, dpp))
            for b, items in sorted(buckets.items()):
                sdate = max(i[0] for i in items) + dt.timedelta(days=1)
                if sdate > self.today:
                    continue
                gross = sum(i[1] for i in items)
                dpp = sum(i[2] for i in items)
                dist = {str(self.ana[code]): 100}
                lines = [(wallet_acc[code], 0, gross, None, None)]
                fees_total = 0
                for label, rate, key in ch["fees"]:
                    amt = rupiah(dpp * rate / 100)
                    fees_total += amt
                    lines.append((self.acc[key], amt, 0, None, dist))
                ppn_fee = rupiah(fees_total * C.PPN_EFFECTIVE / 100)
                lines.append((self.acc["ppn_in"], ppn_fee, 0, self.partners[platform[code]].id, None))
                pph22 = rupiah(dpp * C.PPH22_MARKETPLACE_RATE / 100) if (ch["pph22"] and sdate >= pph22_start) else 0
                lines.append((self.acc["pph22_prepaid"], pph22, 0, self.partners[platform[code]].id, None))
                net = gross - fees_total - ppn_fee - pph22
                lines.append((self.acc["bank_main"], net, 0, None, None))
                self._journal_entry("SETL", sdate, f"Settlement {ch['name']} #{b + 1}", lines)
                count += 1
        print(f"Settlement: {count} jurnal settlement (fee + PPN masukan fee + PPh 22 dipungut)")

    # ------------------------------------------------------------------ monthly costs
    def _bill(self, partner_key, d, ref, account, amount, tax_keys, dist=None, nsfp=False, pay_after=10):
        env = self.env
        if d > self.today:
            return None
        line = {"name": ref, "account_id": self.acc[account], "quantity": 1, "price_unit": amount,
                "tax_ids": [(6, 0, [self.tax[k] for k in tax_keys])]}
        if dist:
            line["analytic_distribution"] = dist
        vals = {"move_type": "in_invoice", "partner_id": self.partners[partner_key].id,
                "invoice_date": d, "date": d, "ref": ref, "invoice_line_ids": [(0, 0, line)]}
        if nsfp:
            vals["btk_nsfp"] = f"010.000-{d.year % 100:02d}.{self.rng.randint(10**7, 10**8 - 1)}"
        bill = env["account.move"].create(vals)
        bill.action_post()
        self._pay(bill, self.jr["BCA"], d + dt.timedelta(days=pay_after))
        return bill

    def costs_month(self, m):
        costs = C.MONTHLY_COSTS
        tag = f"{m:%b %Y}"
        cc_toko = {str(self.ana["CC:Toko Yogyakarta"]): 100}
        cc_hq = {str(self.ana["CC:Kantor Pusat"]): 100}
        self._bill("landlord", m.replace(day=3), f"Sewa toko {tag}", "rent", costs["rent"], ["pph42"], cc_toko)
        self._bill("utility", m.replace(day=8), f"Listrik & internet {tag}", "utilities", costs["utilities"], [], cc_hq)
        self._bill("agency", m.replace(day=12), f"Jasa host live TikTok {tag}", "kol", costs["kol_agency"],
                   ["ppn_in", "pph23"], {str(self.ana["TIKTOK"]): 100}, nsfp=True)
        ads_partner = {"INSTAGRAM": "meta", "TIKTOK": "tiktok_ads", "SHOPEE": "shopee_ads", "TOKPED": "tokped_ads"}
        for code, amt in costs["ads"].items():
            jitter = rupiah(amt * self.rng.uniform(0.85, 1.2) / 1000) * 1000
            self._bill(ads_partner[code], m.replace(day=15), f"Iklan {code} {tag}", "ads", jitter,
                       ["ppn_in"], {str(self.ana[code]): 100}, nsfp=True)
        split = {str(self.ana[c]): p for c, p in costs["packaging_split"].items()}
        self._bill("packaging", m.replace(day=6), f"Kemasan {tag}", "packaging", costs["packaging"],
                   ["ppn_in"], split, nsfp=True)
        # gaji + PPh 21
        pay_day = m.replace(day=25)
        if pay_day <= self.today:
            sal = costs["salary"]
            pph21 = rupiah(sal * costs["pph21_rate"] / 100)
            self._journal_entry("PYRL", pay_day, f"Gaji {tag}", [
                (self.acc["salary"], sal, 0, None, cc_hq),
                (self.acc["pph21"], 0, pph21, None, None),
                (self.acc["bank_main"], 0, sal - pph21, None, None)])
        bank_fee = 150_000
        if month_end(m) <= self.today:
            self._journal_entry("SETL", month_end(m), f"Biaya admin bank {tag}", [
                (self.acc["bank_fee"], bank_fee, 0, None, None), (self.acc["bank_main"], 0, bank_fee, None, None)])
        # setoran kas toko ke bank
        cash = self.cash_in.get(m.strftime("%Y-%m"), 0)
        dep_day = min(month_end(m), self.today)
        if cash:
            self._journal_entry("SETL", dep_day, f"Setoran kas toko ke bank {tag}", [
                (self.acc["bank_main"], cash, 0, None, None), (self.acc["cash_store"], 0, cash, None, None)])

    # ------------------------------------------------------------------ monthly tax closing & remittance
    def tax_closing(self):
        env, acc = self.env, self.acc
        keys = ["ppn_out", "ppn_in", "pph21", "pph23", "pph42", "pph22_prepaid", "landed_accr", "rev_goods", "rev_discount"]
        env.cr.execute(
            """SELECT to_char(date_trunc('month', date), 'YYYY-MM'), account_id, SUM(balance)
               FROM account_move_line WHERE parent_state='posted' AND company_id=%s AND account_id = ANY(%s)
               GROUP BY 1, 2""", (env.company.id, [acc[k] for k in keys]))
        data = defaultdict(lambda: defaultdict(int))
        inv = {acc[k]: k for k in keys}
        for ym, aid, bal in env.cr.fetchall():
            data[ym][inv[aid]] = rupiah(bal)
        for m in self.months:
            ym, e = m.strftime("%Y-%m"), month_end(m)
            if e >= self.today:
                continue  # hanya bulan yang sudah tutup
            d, nxt = data[ym], m + relativedelta(months=1)
            # PPN: neto keluaran - masukan
            x, y = -d["ppn_out"], d["ppn_in"]
            net = x - y
            if x or y:
                lines = [(acc["ppn_out"], x, 0, None, None), (acc["ppn_in"], 0, y, None, None)]
                lines.append((acc["ppn_payable"], 0, net, None, None) if net >= 0
                             else (acc["ppn_lebih"], -net, 0, None, None))
                self._journal_entry("PAJAK", e, f"Rekap PPN masa {ym} (keluaran - masukan)", lines)
                if net > 0 and nxt.replace(day=15) <= self.today:
                    self._journal_entry("PAJAK", nxt.replace(day=15), f"Setor PPN masa {ym}", [
                        (acc["ppn_payable"], net, 0, None, None), (acc["bank_main"], 0, net, None, None)])
            # PPh Final UMKM 0,5% omzet bruto
            omzet = -(d["rev_goods"] + d["rev_discount"])
            final = rupiah(omzet * C.PPH_FINAL_UMKM_RATE / 100)
            if final > 0:
                self._journal_entry("PAJAK", e, f"Beban PPh Final UMKM masa {ym}", [
                    (acc["tax_expense"], final, 0, None, None), (acc["pph_final"], 0, final, None, None)])
                credit = min(final, max(0, d["pph22_prepaid"]))
                if nxt.replace(day=15) <= self.today:
                    self._journal_entry("PAJAK", nxt.replace(day=15), f"Setor PPh Final masa {ym} (kredit PPh 22)", [
                        (acc["pph_final"], final, 0, None, None),
                        (acc["pph22_prepaid"], 0, credit, None, None),
                        (acc["bank_main"], 0, final - credit, None, None)])
            # setoran PPh 21 / 23 / 4(2) + pelunasan utang landed cost
            p21, p23, p42, lc = -d["pph21"], -d["pph23"], -d["pph42"], -d["landed_accr"]
            if (p21 or p23 or p42) and nxt.replace(day=10) <= self.today:
                tot = p21 + p23 + p42
                self._journal_entry("PAJAK", nxt.replace(day=10), f"Setor PPh 21/23/4(2) masa {ym}", [
                    (acc["pph21"], p21, 0, None, None), (acc["pph23"], p23, 0, None, None),
                    (acc["pph42"], p42, 0, None, None), (acc["bank_main"], 0, tot, None, None)])
            if lc > 0 and nxt.replace(day=20) <= self.today:
                self._journal_entry("SETL", nxt.replace(day=20), f"Bayar ongkos angkut pembelian {ym}", [
                    (acc["landed_accr"], lc, 0, None, None), (acc["bank_main"], 0, lc, None, None)])
        print("Penutupan pajak bulanan selesai (PPN, PPh Final, setoran PPh 21/23/4(2))")

    # ------------------------------------------------------------------ audit, users, hardening
    def finalize(self):
        env = self.env
        # 1) Audit trail (OCA auditlog) - dipasang SETELAH seeding agar log hanya berisi aktivitas "nyata"
        if "auditlog.rule" in env:
            models = ["account.move", "account.move.line", "account.account", "account.tax", "account.journal",
                      "account.payment", "product.template", "product.category", "res.partner", "stock.picking",
                      "sale.order", "purchase.order"]
            for model in models:
                mid = env["ir.model"].search([("model", "=", model)], limit=1)
                if not mid or env["auditlog.rule"].search([("model_id", "=", mid.id)], limit=1):
                    continue
                rule = env["auditlog.rule"].create({
                    "name": f"Audit {model}", "model_id": mid.id, "log_type": "full",
                    "log_read": False, "log_create": True, "log_write": True, "log_unlink": True})
                rule.subscribe()
            print(f"Audit trail: rule dipasang untuk {len(models)} model")
            # aktivitas contoh agar Audit Log tidak kosong saat demo
            prods = list(self.products.values())[:3]
            for i, info in enumerate(prods):
                info["p"].product_tmpl_id.list_price = info["price"] + (i + 1) * 5000
            self.partners["landlord"].street = "Jl. Malioboro No. 99 (alamat diperbarui)"
            env["account.tax"].browse(self.tax["ppn_out"]).description = "PPN 11% efektif"
        # 2) Hardening: hash chain jurnal penjualan/pembelian (inalterability)
        for j in env["account.journal"].search([("type", "in", ("sale", "purchase"))]):
            if "restrict_mode_hash_table" in j._fields:
                j.restrict_mode_hash_table = True
        # 3) Lock date (opsional)
        if C.DEMO_LOCK and len(self.months) > 2:
            lock = month_end(self.months[-3])
            for f in ("fiscalyear_lock_date", "tax_lock_date"):
                if f in env.company._fields:
                    env.company[f] = lock
            print(f"Lock date s.d. {lock}")
        # 4) User demo (segregation of duties)
        gf = user_group_field(env)
        specs = [
            ("accountant@batik-demo.example", "Akuntan Demo", ["account.group_account_user", "account.group_account_invoice",
                                                              "sales_team.group_sale_manager", "stock.group_stock_user"]),
            ("owner@batik-demo.example", "Owner (Read-only Audit)", ["account.group_account_readonly"]),
            ("kasir@batik-demo.example", "Kasir Toko", ["account.group_account_invoice", "sales_team.group_sale_salesman"]),
        ]
        for login, name, xmlids in specs:
            if env["res.users"].search([("login", "=", login)], limit=1):
                continue
            groups = [env.ref(x, raise_if_not_found=False) for x in xmlids]
            vals = {"name": name, "login": login, "password": "demo1234",
                    gf: [(4, g.id) for g in groups if g], "company_id": env.company.id,
                    "company_ids": [(6, 0, [env.company.id])]}
            env["res.users"].create(vals)
        print("User demo: accountant / owner (read-only) / kasir  (password: demo1234)")

    def trial_check(self):
        self.env.cr.execute("""SELECT COALESCE(SUM(debit),0), COALESCE(SUM(credit),0) FROM account_move_line
                               WHERE parent_state='posted' AND company_id=%s""", (self.env.company.id,))
        dr, cr = self.env.cr.fetchone()
        print(f"Cek neraca saldo: debit={dr:,.0f} credit={cr:,.0f} selisih={dr - cr:,.2f}")
        for k in sorted(self.stats):
            if k.startswith("omzet"):
                print(f"   {k}: Rp {self.stats[k]:,.0f}")


def run(env):
    s = Steps(env)
    sd = Seeder(env)
    with s.step("Master data (partner, produk, tim channel)"):
        sd.master()
    with s.step("Modal awal"):
        sd.opening_capital()
    with s.step("Rencana order dummy"):
        sd.plan_orders()
    for m in sd.months:
        with s.step(f"{m:%Y-%m} pembelian + landed cost"):
            sd.purchase_month(m)
        with s.step(f"{m:%Y-%m} penjualan multi-channel"):
            sd.sales_month(m)
    with s.step("Settlement marketplace/QRIS/gateway"):
        sd.settle_channels()
    for m in sd.months:
        with s.step(f"{m:%Y-%m} biaya operasional"):
            sd.costs_month(m)
    with s.step("Penutupan pajak bulanan"):
        sd.tax_closing()
    with s.step("Audit trail, hardening, user demo"):
        sd.finalize()
    with s.step("Cek keseimbangan jurnal"):
        sd.trial_check()
    return s.summary()
