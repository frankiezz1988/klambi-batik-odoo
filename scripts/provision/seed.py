"""Seed v2 Klambi Bali: mesin kejadian kronologis (1 Jul - 17 Okt 2026, saldo awal 30 Jun).

Semua dokumen dibuat lewat ORM Odoo dengan "jam" yang digeser (freezegun) ke tanggal kejadian, sehingga nomor dokumen,
create_date, tanggal jurnal valuasi stok, payment, penyusutan dsb. otomatis kronologis tanpa redate manual.
Urutan kejadian dihasilkan perencana murni (plan.py = order; supply.py = pembelian/jahit/transfer) lalu dieksekusi di sini.
Semua angka fiktif."""
import datetime as dt
import heapq
import math
import random
import traceback
from collections import defaultdict

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

import config as C
import plan as P
import supply as S
from common import Steps, load_registry, save_registry, user_group_field

PRIO = {"opening": 0, "rm_po": 0, "tailor_po": 0, "bought_po": 0, "recv": 0, "sortase": 0, "transfer": 1, "order": 2,
        "return": 3, "pay": 4, "payout": 4, "deposit": 4, "cost": 5, "monthly": 5, "closing": 8}
LOC_OF = S.LOC_OF


def rp(x):
    return int(round(x))


def month_end(d):
    return (d.replace(day=1) + relativedelta(months=1)) - dt.timedelta(days=1)


def pick_field(model, *names):
    for n in names:
        if n in model._fields:
            return n
    return None


class Seeder:
    def __init__(self, env):
        ctx = dict(env.context, tracking_disable=True, mail_notrack=True, mail_create_nolog=True,
                   mail_auto_subscribe_no_notify=True, skip_sms=True, lang="id_ID")
        self.env = env(context=ctx)
        self.reg = load_registry(env)
        r = self.reg
        self.acc, self.tax, self.jr, self.ana = r["acc"], r["tax"], r["journal"], r["analytic"]
        self.W, self.PRD, self.RAW = r["wh"], r["m_products"], r["m_raw"]
        self.PT = r["m_partners"]
        self.pool = r["m_pool"]
        self.rng = random.Random(C.SEED + 77)
        self.q, self._seq = [], 0
        self.f = None
        self.cur = C.START
        self.meta = {}                                   # ref order -> info (untuk retur)
        self.settle = defaultdict(list)                  # channel -> [[tgl bayar, bruto, dpp, sudah]]
        self.cash_pending = []                           # [(tgl, jumlah)] kas toko belum disetor
        self.stats = defaultdict(float)
        self.errors = defaultdict(int)
        self.nsfp_seq = 0
        self.bill_seq = 0
        self.dpp_month = defaultdict(lambda: defaultdict(float))   # 'YYYY-MM' -> channel -> DPP
        self.reseller_map = {n: (c, s, d, t, k) for n, c, s, d, t, k in C.RESELLERS}
        self.loc_ids = {"MAIN": self.W["main_stock"], "TKO": self.W["tko_stock"], "MKT": self.W["mkt_loc"]}
        self.btk = "btk_nsfp" in self.env["account.move"]._fields

    # ------------------------------------------------------------------ waktu & antrean
    def at(self, d, h=10, m=0):
        """Geser jam sistem ke tanggal d pukul h:m WITA (disimpan UTC = h-8)."""
        t = dt.datetime.combine(d, dt.time(0)) + dt.timedelta(hours=h - 8, minutes=m)
        self.cur = d
        if self.f is None:
            self._fz = freeze_time(t, tick=False)
            self.f = self._fz.start()
        else:
            self.f.move_to(t)

    def push(self, d, _k, h=None, minute=0, **kw):
        if d > C.END:
            return
        self._seq += 1
        heapq.heappush(self.q, (d, PRIO[_k], self._seq, _k, h, minute, kw))

    def run_queue(self):
        done = 0
        while self.q:
            d, prio, seq, kind, h, minute, kw = heapq.heappop(self.q)
            self.at(d, h if h is not None else {"opening": 8, "transfer": 9, "pay": 14, "payout": 15, "cost": 11,
                                                 "monthly": 11, "closing": 19, "deposit": 16}.get(kind, 10), minute)
            try:
                with self.env.cr.savepoint():
                    getattr(self, "h_" + kind)(**kw)
            except Exception as exc:  # noqa: BLE001
                self.errors[kind] += 1
                if self.errors[kind] <= 3:
                    print(f"   !! [{kind}] {d} gagal: {str(exc)[:240]}")
                    if self.errors[kind] == 1:
                        traceback.print_exc()
                self.env.invalidate_all()
            done += 1
            if done % 40 == 0:
                self.env.cr.commit()
            if done % 200 == 0:
                self.env.invalidate_all()
                print(f"   ... {done} kejadian diproses, sekarang {d}")
        self.env.cr.commit()
        print(f"Kejadian diproses: {done}; gagal per jenis: {dict(self.errors) or '-'}")

    # ------------------------------------------------------------------ util
    def partner(self, key):
        return self.PT[key]

    def pterm(self, days):
        name = {0: "Kontan", 14: "15 Hari", 15: "15 Hari", 21: "21 Hari", 30: "30 Hari", 45: "45 Hari"}.get(days, "30 Hari")
        t = self.env["account.payment.term"].search([("name", "=", name)], limit=1)
        return t.id

    def je(self, jcode, date, ref, lines):
        """lines: (account_id, debit, credit, partner_id|None, analytic|None)"""
        vals, td, tc = [], 0, 0
        for a, dr, cr, pid, dist in lines:
            dr, cr = rp(dr), rp(cr)
            if not (dr or cr):
                continue
            v = {"account_id": a, "debit": dr, "credit": cr, "name": ref}
            if pid:
                v["partner_id"] = pid
            if dist:
                v["analytic_distribution"] = dist
            vals.append((0, 0, v))
            td += dr
            tc += cr
        assert td == tc, f"JE tidak balance {ref}: {td} vs {tc}"
        mv = self.env["account.move"].create({"move_type": "entry", "journal_id": self.jr[jcode], "date": date,
                                              "ref": ref, "line_ids": vals})
        mv.action_post()
        return mv

    def validate(self, picking, backorder=True, no_backorder_ids=None):
        ctx = dict(skip_backorder=backorder, skip_sms=True, skip_immediate=True)
        if no_backorder_ids:
            ctx["picking_ids_not_to_backorder"] = no_backorder_ids
        return picking.with_context(**ctx).button_validate()

    def fill(self, picking, qtys=None):
        picking.action_assign()
        for mv in picking.move_ids:
            want = mv.product_uom_qty if qtys is None else qtys.get(mv.product_id.id, 0)
            mv.quantity = want

    def nsfp(self, d, vendor=False):
        self.nsfp_seq += 1
        return (f"010.000-{d.year % 100:02d}.{self.rng.randint(10 ** 7, 10 ** 8 - 1)}" if vendor
                else f"040.000-{d.year % 100:02d}.{self.nsfp_seq:08d}")

    def post_bill(self, bill, d, ref, vendor_pkp=False, pay=True, partial=None, slow=0):
        vals = {"invoice_date": d, "date": d, "ref": ref}
        if self.btk and vendor_pkp:
            vals["btk_nsfp"] = self.nsfp(d, True)
        bill.write(vals)
        bill.action_post()
        if pay:
            due = bill.invoice_date_due or d
            delay = slow + self.rng.choice([0, 0, 1, 2, 3, 5, 7])
            if partial:
                first = rp(bill.amount_total * partial[0])
                self.push(due + dt.timedelta(days=delay), "pay", move=bill.id, journal="BCA", amount=first)
                self.push(due + dt.timedelta(days=delay + partial[1]), "pay", move=bill.id, journal="BCA", amount=None)
            else:
                self.push(due + dt.timedelta(days=delay), "pay", move=bill.id, journal="BCA", amount=None)
        return bill

    # ------------------------------------------------------------------ pembayaran
    def pay_now(self, move, jcode, amount=None, date=None):
        move = move.exists()
        if not move or move.payment_state in ("paid", "in_payment") or move.state != "posted":
            return None
        ctx = dict(active_model="account.move", active_ids=move.ids)
        vals = {"payment_date": date or self.cur, "journal_id": self.jr[jcode]}
        if amount:
            vals["amount"] = amount
        wiz = self.env["account.payment.register"].with_context(**ctx).create(vals)
        wiz._create_payments()
        return True

    # ------------------------------------------------------------------ saldo awal
    def h_opening(self, fg, rm):
        env, acc = self.env, self.acc
        loc_inv = env["stock.location"].search([("usage", "=", "inventory"), ("company_id", "in", (env.company.id, False))], limit=1)
        old_acc = loc_inv.valuation_account_id.id
        loc_inv.valuation_account_id = acc["capital"]          # penyesuaian stok awal -> Modal Disetor (saldo awal)
        Q = env["stock.quant"].with_context(inventory_mode=True)
        n = 0
        for (loc, sku), q in fg.items():
            if q > 0:
                Q.create({"product_id": self.PRD[sku], "location_id": self.loc_ids[loc], "inventory_quantity": q}).action_apply_inventory()
                n += 1
        for sku, q in rm.items():
            Q.create({"product_id": self.RAW[sku], "location_id": self.loc_ids["MAIN"], "inventory_quantity": q}).action_apply_inventory()
        loc_inv.valuation_account_id = old_acc
        # kas, bank, aset tetap, piutang & hutang awal
        d = self.cur
        rani = self.partner("RES:Butik Kebaya Denpasar Rani")
        ap = self.partner("CV Tekstil Pekalongan Mulia")
        P_ = env["res.partner"]
        ar_acc = P_.browse(rani).property_account_receivable_id.id
        ap_acc = P_.browse(ap).property_account_payable_id.id
        assets = [("Rak Display Toko", 18_000_000, "CC:Toko Denpasar"), ("Manekin & Perlengkapan Display", 7_500_000, "CC:Toko Denpasar"),
                  ("Laptop & Perangkat POS", 14_000_000, "CC:Kantor Pusat"), ("Printer Label & Scanner Barcode", 4_000_000, "CC:Gudang & Produksi")]
        bank, cash = C.OPENING["bank"], C.OPENING["cash"]
        ar, apv = C.OPENING["ar"][0][1], C.OPENING["ap"][0][1]
        equip = sum(a[1] for a in assets)
        lines = [(acc["bank_main"], bank, 0, None, None), (acc["cash_store"], cash, 0, None, None),
                 (ar_acc, ar, 0, rani, None), (ap_acc, 0, apv, ap, None)]
        for nm, val, cc in assets:
            lines.append((acc["equipment"], val, 0, None, {str(self.ana[cc]): 100}))
        lines.append((acc["capital"], 0, bank + cash + ar + equip - apv, None, None))
        mv = self.je("SETL", d, "Saldo awal 30 Jun 2026 (kas, bank, aset tetap, piutang, hutang, modal)", lines)
        # aset tetap (OCA): draft otomatis dari baris jurnal -> sesuaikan & validasi
        Asset = env["account.asset"]
        drafts = Asset.search([("state", "=", "draft")])
        spec = {a[1]: a for a in assets}
        for a in drafts:
            sp = spec.get(a.purchase_value)
            vals = {"date_start": C.START}
            if sp:
                vals.update({"name": sp[0], "analytic_distribution": {str(self.ana[sp[2]]): 100}})
            a.write(vals)
            a.validate()
        print(f"Saldo awal: {n} baris stok FG + {len(rm)} bahan baku, kas/bank Rp {bank + cash:,}, aset {len(drafts)}")
        # penerimaan piutang & pelunasan hutang awal
        self.push(dt.date(2026, 7, 15), "pay", move=-1, journal="BCA", amount=None, _open="ar")
        self.push(dt.date(2026, 7, 16), "pay", move=-2, journal="BCA", amount=None, _open="ap")

    # ------------------------------------------------------------------ pembelian bahan baku / barang beli jadi
    def _po(self, partner_key, lines, d, days, pkp):
        env = self.env
        tfield = pick_field(env["purchase.order.line"], "tax_ids", "taxes_id")
        vals_lines = []
        for sku_id, qty, price, taxed in lines:
            lv = {"product_id": sku_id, "product_qty": qty, "price_unit": price,
                  "date_planned": dt.datetime.combine(d, dt.time(2))}
            lv[tfield] = [(6, 0, [self.tax["ppn_in"]] if (pkp and taxed) else [])]
            vals_lines.append((0, 0, lv))
        po = env["purchase.order"].create({"partner_id": self.partner(partner_key), "date_order": dt.datetime.combine(d, dt.time(2)),
                                           "payment_term_id": self.pterm(days), "order_line": vals_lines})
        po.button_confirm()
        return po

    def h_rm_po(self, vendor, lines, recv, date=None):
        d = self.cur
        pkp, term = C.SUPPLIER_PKP.get(vendor, (True, 30))
        rise = 1 + (C.CLOTH_PRICE_RISE["pct"] / 100.0 if d >= C.CLOTH_PRICE_RISE["from"] else 0)
        pl = []
        for sku, q in lines:
            cost = next(r[3] for r in C.RAW if r[0] == sku)
            pl.append((self.RAW[sku], q, rp(cost * (rise if sku.startswith("RM-KAIN") else 1.0)), True))
        po = self._po(vendor, pl, d, term, pkp)
        self.stats["po_rm"] += 1
        self.push(recv, "recv", po=po.id, kind="rm", vendor=vendor, pkp=pkp, rej=None)

    def h_bought_po(self, vendor, lines, recv):
        d = self.cur
        pkp, term = C.SUPPLIER_PKP.get(vendor, (False, 14))
        cost = {b[0]: b[3] for b in C.BOUGHT}
        pl = [(self.PRD[sku], q, cost[sku], True) for sku, q in lines]
        po = self._po(vendor, pl, d, term, pkp)
        self.stats["po_bought"] += 1
        self.push(recv, "recv", po=po.id, kind="bought", vendor=vendor, pkp=pkp, rej=None)

    def h_tailor_po(self, tailor, lines, recv, note=None):
        d = self.cur
        pkp = next(t[2] for t in C.TAILORS if t[0] == tailor)
        env = self.env
        tfield = pick_field(env["purchase.order.line"], "tax_ids", "taxes_id")
        vl = []
        for sku, q in lines:
            fee = next(m[7] for m in C.MADE if m[0] == sku) * (1.04 if tailor == "CV Garment Dewata" else 1.0)
            lv = {"product_id": self.PRD[sku], "product_qty": q, "price_unit": rp(fee),
                  "date_planned": dt.datetime.combine(d + dt.timedelta(days=S.TAILOR_LEAD), dt.time(2))}
            lv[tfield] = [(6, 0, ([self.tax["ppn_in"]] if pkp else []) + [self.tax["pph23"]])]
            vl.append((0, 0, lv))
        po = env["purchase.order"].create({"partner_id": self.partner(tailor), "date_order": dt.datetime.combine(d, dt.time(2)),
                                           "payment_term_id": self.pterm(0 if not pkp else 15), "order_line": vl,
                                           **({"origin": note[:60]} if note else {})})
        po.button_confirm()
        # kirim bahan baku ke penjahit (resupply subkontraktor)
        for pk in env["stock.picking"].search([("origin", "ilike", po.name), ("picking_type_id.name", "ilike", "Resupply"), ("state", "not in", ("done", "cancel"))]):
            self.fill(pk)
            self.validate(pk)
        self.stats["po_tailor"] += 1
        for rd, rl in recv.items():
            self.push(rd, "recv", po=po.id, kind="tailor", vendor=tailor, pkp=pkp, rows=rl, note=note)

    # ------------------------------------------------------------------ penerimaan di Sortase -> Stok Utama
    def h_recv(self, po, kind, vendor, pkp, rows=None, rej=None, note=None):
        env = self.env
        po = env["purchase.order"].browse(po)
        picks = po.picking_ids.filtered(lambda p: p.state not in ("done", "cancel") and p.picking_type_code == "incoming")[:1]
        if not picks:
            return
        qmap = None
        if kind == "tailor":
            qmap = defaultdict(float)
            for sku, q, rj in rows:
                qmap[self.PRD[sku]] += q
        self.fill(picks, dict(qmap) if qmap else None)
        self.validate(picks)
        # tagihan pemasok (menurut qty diterima)
        po.action_create_invoice()
        bill = po.invoice_ids.filtered(lambda b: b.state == "draft")[:1]
        partial = None
        slow = 0
        if kind == "rm" and self.cur.month == 8 and vendor.startswith("CV Tekstil") and "partial_done" not in self.stats:
            partial, self.stats["partial_done"] = (0.6, 14), 1          # edge: dibayar sebagian lalu dilunasi 14 hari kemudian
        if kind == "rm" and self.cur.month == 9 and vendor.startswith("PT Kain") and "late_done" not in self.stats:
            slow, self.stats["late_done"] = 18, 1                        # edge: pembayaran terlambat 18 hari
        self.post_bill(bill, self.cur, f"INV-{vendor.split()[0][:4].upper()}-{self.cur:%y%m%d}-{po.id}", pkp, partial=partial, slow=slow)
        # Sortase (QC) -> Stok Utama, hari kerja berikutnya
        rjs = defaultdict(float)
        for sku, q, rj in (rows or []):
            if rj:
                rjs[self.PRD[sku]] += rj
        self.push(S.workday(self.cur + dt.timedelta(days=1)), "sortase", picks=picks.ids, rejects=dict(rjs))

    def h_sortase(self, picks, rejects):
        env = self.env
        P_ = env["stock.picking"].browse(picks)
        stor = P_.move_ids.move_dest_ids.picking_id.filtered(lambda p: p.state not in ("done", "cancel"))
        for pid, q in rejects.items():
            sc = env["stock.scrap"].create({"product_id": pid, "scrap_qty": q, "location_id": self.W["main_input"],
                                            "origin": "Reject QC Sortase (jahitan cacat)"})
            sc.action_validate()
            self.stats["reject_pcs"] += q
        for p in stor:
            p.action_assign()
            for mv in p.move_ids:
                mv.quantity = mv.quantity or 0
            self.validate(p, no_backorder_ids=p.ids)

    # ------------------------------------------------------------------ transfer ke toko / marketplace
    def h_transfer(self, loc, lines):
        env = self.env
        pt = env["stock.warehouse"].browse(self.W["main"]).int_type_id
        dst = self.loc_ids[loc]
        pk = env["stock.picking"].create({
            "picking_type_id": pt.id, "location_id": self.W["main_stock"], "location_dest_id": dst,
            "origin": "Replenishment " + ("Toko Denpasar" if loc == "TKO" else "Gudang Marketplace"),
            "move_ids": [(0, 0, {"product_id": self.PRD[s], "product_uom_qty": q,
                                 "location_id": self.W["main_stock"], "location_dest_id": dst}) for s, q in lines]})
        pk.action_confirm()
        self.fill(pk)
        self.validate(pk)
        self.stats["transfer"] += 1

    # ------------------------------------------------------------------ penjualan
    def _customer(self, o):
        code, persona = o["ch"], o["persona"]
        if persona == "RESELLER":
            name = self.rng.choice(list(self.reseller_map))
            self.cur_terms = self.reseller_map[name][3]
            return self.partner("RES:" + name), name
        if persona == "CORPORATE":
            name = self.rng.choice([c[0] for c in C.CORPORATES])
            self.cur_terms = 15
            return self.partner("COR:" + name), name
        ids = self.pool[code]
        return ids[min(o["cust"], len(ids) - 1)], None

    def h_order(self, o):
        env = self.env
        o = self.orders_by_ref[o]
        if o.get("void"):
            return
        code, persona, d = o["ch"], o["persona"], o["date"]
        partner, bname = self._customer(o)
        team = self.teams[code]
        dist = {str(self.ana[code]): 100}
        lines = [(0, 0, {"product_id": self.PRD[s], "product_uom_qty": q, "price_unit": self.catalog[s]["price"],
                         "discount": round(o["disc"] * 100, 2), "analytic_distribution": dist}) for s, q, _p in o["lines"]]
        vals = {"partner_id": partner, "team_id": team, "date_order": dt.datetime.combine(d, dt.time(0)) + dt.timedelta(hours=max(o["time"][0], 8) - 8, minutes=o["time"][1]),
                "client_order_ref": o["ref"], "warehouse_id": self.W["tko"] if code == "STORE" else self.W["main"], "order_line": lines}
        if persona in ("RESELLER", "CORPORATE"):
            vals["payment_term_id"] = self.pterm(self.cur_terms)
        so = env["sale.order"].create(vals)
        so.action_confirm()
        if o.get("cancel"):
            so._action_cancel()
            self.stats["so_cancel"] += 1
            return
        loc = LOC_OF.get(code, "MAIN")
        for pk in so.picking_ids:
            if loc == "MKT":
                pk.do_unreserve()
                pk.move_ids.write({"location_id": self.loc_ids["MKT"]})
                pk.write({"location_id": self.loc_ids["MKT"]})
            self.fill(pk)
            self.validate(pk)
        inv = so._create_invoices()
        v = {"invoice_date": d}
        if self.btk:
            v.update({"btk_nsfp": self.nsfp(d), "btk_channel_ref": o["ref"], "btk_kode_transaksi": "04"})
        inv.write(v)
        inv.action_post()
        dpp, gross = rp(inv.amount_untaxed), rp(inv.amount_total)
        self.stats["omzet"] += dpp
        self.dpp_month[d.strftime("%Y-%m")][code] += dpp
        meta = {"so": so.id, "inv": inv.id, "o": o, "gross": gross, "dpp": dpp, "wallet": None}
        self.meta[o["ref"]] = meta
        ch = self.chan[code]
        if code == "STORE":
            r = o["u"]
            if r < 0.36:
                self.pay_now(inv, "KTOK", None, d)
                self.cash_pending.append((d, gross))
                meta["wallet"] = "KTOK"
            else:
                self.pay_now(inv, "QRIS", None, d)
                self.settle["STORE"].append([d, gross, dpp, False])
                meta["wallet"] = "QRIS"
        elif code == "B2B":
            slow = persona == "RESELLER" and bname in ("Lapak Batik Jakarta Selatan", "Toko Sandang Jaya Makassar")
            due = inv.invoice_date_due or d
            delay = (25 if slow else 0) + self.rng.choice([0, 1, 2, 3, 5, 8])
            if persona == "RESELLER" and d.month == 8 and d.day >= 5 and "stuck_ar" not in self.stats:
                self.stats["stuck_ar"] = 1                # edge: piutang reseller macet (follow-up penagihan, >30 hari lewat jatuh tempo)
                meta["wallet"] = "BCA"
            else:
                self.push(due + dt.timedelta(days=delay), "pay", move=inv.id, journal="BCA", amount=None)
                meta["wallet"] = "BCA"
        else:
            lag = C.SETTLEMENT_LAG_DAYS
            meta["wallet"] = ch["journal"]
            self.push(d + dt.timedelta(days=lag), "pay", move=inv.id, journal=ch["journal"], amount=None, _wallet=(code, gross, dpp))

    def h_pay(self, move, journal, amount, _open=None, _wallet=None):   # noqa: F811 - versi lengkap
        env = self.env
        if _open:
            self._pay_open(_open, journal)
            return
        mv = env["account.move"].browse(move)
        if self.pay_now(mv, journal, amount) and _wallet:
            code, gross, dpp = _wallet
            self.settle[code].append([self.cur, gross, dpp, False])

    def _pay_open(self, which, journal):
        env = self.env
        if which == "ar":
            partner = self.partner("RES:Butik Kebaya Denpasar Rani")
            pay_type, ptype = "inbound", "customer"
        else:
            partner = self.partner("CV Tekstil Pekalongan Mulia")
            pay_type, ptype = "outbound", "supplier"
        acct_type = "asset_receivable" if which == "ar" else "liability_payable"
        lines = env["account.move.line"].search([("partner_id", "=", partner), ("account_id.account_type", "=", acct_type),
                                                 ("parent_state", "=", "posted"), ("reconciled", "=", False),
                                                 ("move_id.ref", "ilike", "Saldo awal")])
        if not lines:
            return
        wiz = env["account.payment.register"].with_context(active_model="account.move.line", active_ids=lines.ids).create(
            {"payment_date": self.cur, "journal_id": self.jr[journal]})
        wiz._create_payments()

    # ------------------------------------------------------------------ retur penjualan
    def h_return(self, order):
        env = self.env
        meta = self.meta.get(order)
        if not meta:
            return
        o = self.orders_by_ref[order]
        code = o["ch"]
        so, inv = env["sale.order"].browse(meta["so"]), env["account.move"].browse(meta["inv"])
        pick = so.picking_ids.filtered(lambda p: p.state == "done" and p.picking_type_code == "outgoing")[:1]
        wiz = env["stock.return.picking"].with_context(active_id=pick.id, active_ids=pick.ids, active_model="stock.picking").create({})
        for ln in wiz.product_return_moves:
            ln.quantity = ln.move_id.product_uom_qty
        res = wiz.action_create_returns()
        ret = env["stock.picking"].browse(res["res_id"])
        dest = self.loc_ids[o.get("loc", "MAIN")]
        ret.write({"location_dest_id": dest})
        ret.move_ids.write({"location_dest_id": dest})
        self.fill(ret)
        self.validate(ret)
        if not o.get("ret_restock", True):          # barang cacat -> reject (scrap)
            for mv in ret.move_ids:
                loc = mv.location_dest_id.id
                sc = env["stock.scrap"].create({"product_id": mv.product_id.id, "scrap_qty": mv.quantity, "location_id": loc,
                                                "origin": f"Retur {order} - barang cacat"})
                sc.action_validate()
            self.stats["return_reject"] += 1
        rev = env["account.move.reversal"].with_context(active_model="account.move", active_ids=inv.ids).create(
            {"journal_id": inv.journal_id.id, "date": self.cur, "reason": "Retur pelanggan"})
        (getattr(rev, "reverse_moves", None) or rev.refund_moves)()
        cn = inv.reversal_move_ids[-1:]
        if cn.state == "draft":
            cn.action_post()
        w = meta["wallet"]
        if w and w != "BCA":
            if self.pay_now(cn, w, None):
                if w == "KTOK":
                    self.cash_pending.append((self.cur, -meta["gross"]))
                else:
                    self.settle[code].append([self.cur, -meta["gross"], -meta["dpp"], False])
        self.stats["retur"] += meta["dpp"]

    # ------------------------------------------------------------------ pencairan escrow / settlement
    def h_payout(self, code):
        ch = self.chan[code]
        d = self.cur
        items = [i for i in self.settle[code] if not i[3] and i[0] <= d - dt.timedelta(days=1)]
        if not items:
            return
        gross, dpp = sum(i[1] for i in items), sum(i[2] for i in items)
        if gross <= 0 or dpp <= 0:
            return
        for i in items:
            i[3] = True
        acc = self.acc
        dist = {str(self.ana[code]): 100}
        platform = {"SHOPEE": "shopee_platform", "TOKPED": "tokped_platform", "TIKTOK": "tiktok_platform",
                    "INSTAGRAM": "gateway", "STORE": "bank"}[code]
        wallet = acc[ch["wallet"]]
        lines = [(wallet, 0, gross, None, None)]
        fees = 0
        for label, rate, key in ch["fees"]:
            amt = rp(dpp * rate / 100)
            fees += amt
            lines.append((acc[key], amt, 0, None, dist))
        # edge: denda keterlambatan kirim Shopee & koreksi komisi afiliasi TikTok
        extra = 0
        if code == "SHOPEE" and dt.date(2026, 9, 7) <= d < dt.date(2026, 9, 14) and "pen1" not in self.stats:
            self.stats["pen1"] = 1
            extra = 175_000
            lines.append((acc["fee_penalty"], extra, 0, None, dist))
        if code == "TIKTOK" and dt.date(2026, 10, 5) <= d < dt.date(2026, 10, 12) and "pen2" not in self.stats:
            self.stats["pen2"] = 1
            extra = 420_000
            lines.append((acc["fee_penalty"], extra, 0, None, dist))
        ppn_fee = rp(fees * C.PPN_EFFECTIVE / 100)
        lines.append((acc["ppn_in"], ppn_fee, 0, self.partner(platform), None))
        pph22 = rp(dpp * C.PPH22_MARKETPLACE_RATE / 100) if (ch["pph22"] and d >= dt.date.fromisoformat(C.PPH22_START)) else 0
        lines.append((acc["pph22_prepaid"], pph22, 0, self.partner(platform), None))
        net = gross - fees - ppn_fee - pph22 - extra
        lines.append((acc["bank_main"], net, 0, None, None))
        self.je("SETL", d, f"Pencairan {ch['name']} ({len(items)} transaksi)", lines)
        self.stats["payouts"] += 1

    def h_deposit(self):
        d = self.cur
        items = [x for x in self.cash_pending if x[0] <= d - dt.timedelta(days=1)]
        if not items:
            return
        self.cash_pending = [x for x in self.cash_pending if x not in items]
        amt = sum(x[1] for x in items)
        if amt <= 0:
            return
        diff = 0
        if self.rng.random() < 0.2:
            diff = self.rng.choice([20_000, 35_000, 50_000, 75_000])
        acc = self.acc
        lines = [(acc["bank_main"], amt - diff, 0, None, None), (acc["cash_store"], 0, amt, None, None)]
        if diff:
            lines.append((acc["cash_diff"], diff, 0, None, {str(self.ana["CC:Toko Denpasar"]): 100}))
            self.stats["cash_diff"] += diff
        self.je("SETL", d, f"Setoran kas toko ke bank (s.d. {d - dt.timedelta(days=1):%d %b})", lines)

    # ------------------------------------------------------------------ biaya operasional bulanan
    def bill(self, pkey, ref, account, amount, taxes, dist, d=None, nsfp=False, pay_slow=0, partial=None):
        env = self.env
        d = d or self.cur
        taxf = pick_field(env["account.move.line"], "tax_ids")
        total = rp(amount)
        # alokasi ke beberapa analytic dipecah menjadi satu baris tagihan per akun analitik (100% masing-masing), sehingga
        # laporan per channel (filter analytic) menghitung porsi yang benar, bukan seluruh baris
        parts = [(k, v) for k, v in (dist or {}).items()]
        if len(parts) > 1:
            tp = sum(v for _k, v in parts) or 1
            amts, acc_amt = [], 0
            for i, (k, v) in enumerate(parts):
                a_ = total - acc_amt if i == len(parts) - 1 else rp(total * v / tp)
                acc_amt += a_
                amts.append((k, a_))
        else:
            amts = [(parts[0][0], total)] if parts else [(None, total)]
        vals_lines = []
        for k, a_ in amts:
            line = {"name": ref, "account_id": self.acc[account], "quantity": 1, "price_unit": a_,
                    taxf: [(6, 0, [self.tax[x] for x in taxes])]}
            if k:
                line["analytic_distribution"] = {k: 100}
            vals_lines.append((0, 0, line))
        term = self.pterm(15 if pkey not in ("landlord_toko", "landlord_gudang") else 0)
        b = env["account.move"].create({"move_type": "in_invoice", "partner_id": self.partner(pkey), "invoice_date": d, "date": d,
                                        "ref": ref, "invoice_payment_term_id": term, "invoice_line_ids": vals_lines})
        return self.post_bill(b, d, ref, nsfp, slow=pay_slow, partial=partial)

    def h_cost(self, what, m, spec=None):
        if what == "__je":
            return self._je_spec(spec)
        C_ = C.MONTHLY_COSTS
        mi = (m.year - 2026) * 12 + m.month - 7            # 0 = Juli
        tag = f"{m:%b %Y}"
        cc = lambda n: {str(self.ana["CC:" + n]): 100}
        d = self.cur
        if what == "rent_toko":
            self.bill("landlord_toko", f"Sewa toko {tag}", "rent", C_["rent_toko"], ["pph42"], cc("Toko Denpasar"))
        elif what == "rent_gudang":
            self.bill("landlord_gudang", f"Sewa gudang {tag}", "rent_wh", C_["rent_gudang"], ["pph42"], cc("Gudang & Produksi"))
        elif what == "utilities":
            amt = C_["utilities"] * self.rng.uniform(0.94, 1.08)
            self.bill("utility", f"Listrik & internet {tag}", "utilities", amt, [],
                      {str(self.ana["CC:Kantor Pusat"]): 40, str(self.ana["CC:Toko Denpasar"]): 35, str(self.ana["CC:Gudang & Produksi"]): 25})
        elif what == "agency" and C_["kol_agency"][mi]:
            self.bill("agency", f"Jasa host live TikTok {tag}", "kol", C_["kol_agency"][mi], ["ppn_in", "pph23"], {str(self.ana["TIKTOK"]): 100}, nsfp=True)
        elif what == "ads":
            who = {"INSTAGRAM": "meta", "TIKTOK": "tiktok_ads", "SHOPEE": "shopee_ads", "TOKPED": "tokped_ads"}
            for code, amt in C_["ads"].items():
                base = amt[mi] if isinstance(amt, list) else amt
                if base:
                    self.bill(who[code], f"Iklan {code.title()} {tag}", "ads", rp(base * self.rng.uniform(0.9, 1.12) / 1000) * 1000,
                              ["ppn_in"], {str(self.ana[code]): 100}, nsfp=True)
        elif what == "maint":
            self.bill("maint", f"Servis & perawatan {tag}", "maint", C_["maintenance"], ["pph23"],
                      {str(self.ana["CC:Gudang & Produksi"]): 60, str(self.ana["CC:Toko Denpasar"]): 40}, nsfp=True)
        elif what == "packaging":
            base = sum(v for c, v in self.dpp_month[m.strftime("%Y-%m")].items() if c != "STORE")
            tot = base * C_["packaging_pct"] / 100.0
            share = {c: v for c, v in self.dpp_month[m.strftime("%Y-%m")].items() if c != "STORE" and v}
            s = sum(share.values()) or 1
            dist = {str(self.ana[c]): round(v / s * 100, 2) for c, v in share.items()}
            self.bill("packaging", f"Kemasan & bubble wrap {tag}", "packaging", tot, ["ppn_in"], dist, nsfp=True)
        elif what == "shipping":
            share = {c: v for c, v in self.dpp_month[m.strftime("%Y-%m")].items() if c in ("B2B", "INSTAGRAM") and v}
            s = sum(share.values())
            if s:
                dist = {str(self.ana[c]): round(v / s * 100, 2) for c, v in share.items()}
                self.bill("ekspedisi", f"Ongkos kirim ditanggung penjual {tag}", "shipping", s * C_["shipping_pct"] / 100.0, ["ppn_in"], dist, nsfp=True)
        elif what == "bank_fee":
            self.je("SETL", d, f"Biaya admin bank {tag}", [(self.acc["bank_fee"], C_["bank_fee"], 0, None, {str(self.ana["CC:Kantor Pusat"]): 100}),
                                                         (self.acc["bank_main"], 0, C_["bank_fee"], None, None)])
        elif what == "entertain":     # jamuan klien: PPN pada struk TIDAK dapat dikreditkan -> masuk beban
            amt = {8: 640_000, 9: 1_110_000, 10: 888_000}[m.month]
            self.bill("resto", f"Jamuan klien reseller {tag} (struk incl. PPN)", "entertain", amt, [], {str(self.ana["CC:Kantor Pusat"]): 100}, pay_slow=0)
        elif what == "camera":
            self.camera_purchase()

    def camera_purchase(self):
        env = self.env
        taxf = pick_field(env["account.move.line"], "tax_ids")
        prof = self.reg["asset_profile"]
        line = {"name": "Kamera mirrorless & lighting live TikTok", "account_id": self.acc["equipment"], "quantity": 1,
                "price_unit": 22_000_000, taxf: [(6, 0, [self.tax["ppn_in"]])],
                "analytic_distribution": {str(self.ana["TIKTOK"]): 100}}
        if "asset_profile_id" in env["account.move.line"]._fields:
            line["asset_profile_id"] = prof
        b = env["account.move"].create({"move_type": "in_invoice", "partner_id": self.partner("camera"), "invoice_date": self.cur,
                                        "date": self.cur, "ref": "Pembelian peralatan live", "invoice_payment_term_id": self.pterm(0),
                                        "invoice_line_ids": [(0, 0, line)]})
        self.post_bill(b, self.cur, "KW-DWT-0831", True)
        for a in env["account.asset"].search([("state", "=", "draft")]):
            a.write({"name": "Kamera & Lighting Live TikTok", "date_start": self.cur, "analytic_distribution": {str(self.ana["TIKTOK"]): 100}})
            a.validate()

    def h_monthly(self, what, m):
        env = self.env
        d = self.cur
        tag = f"{m:%b %Y}"
        if what == "payroll":
            run = env["btk.payroll.run"].create({"date": d})
            run.action_compute()
            run.action_post()
        elif what == "accrual":      # akrual gaji Oktober s.d. 17 Okt (belum jatuh tempo)
            full = 0
            for e in env["btk.employee"].search([]):
                full += e.basic_salary + e.allowance
            part = rp(full * 17 / 31.0)
            self.je("SETL", d, f"Akrual gaji & tunjangan 1-17 Okt 2026", [
                (self.acc["salary"], part, 0, None, {str(self.ana["CC:Kantor Pusat"]): 100}),
                (self.acc["accrued"], 0, part, None, None)])
        elif what == "depreciation":
            env["account.asset.compute"].create({"date_end": month_end(m)}).asset_compute()
            drafts = env["account.move"].search([("journal_id", "=", self.jr["ASET"]), ("state", "=", "draft")])
            if drafts:
                drafts.action_post()
        elif what == "opname":
            self.stock_opname()

    def stock_opname(self):
        """Stock opname Stok Utama 30 Sep: beberapa SKU selisih (hilang / lebih)."""
        env = self.env
        Q = env["stock.quant"].with_context(inventory_mode=True)
        n = 0
        for sku, delta in (("BC-KMJ-001", -2), ("BP-KMJ-001", -3), ("AK-SCF-001", +1), ("BT-DRS-001", -1)):
            q = env["stock.quant"].search([("product_id", "=", self.PRD[sku]), ("location_id", "=", self.W["main_stock"])], limit=1)
            if q and q.quantity + delta >= 0:
                q.with_context(inventory_mode=True).write({"inventory_quantity": q.quantity + delta})
                q.action_apply_inventory()
                n += 1
        print(f"Opname 30 Sep: {n} SKU disesuaikan")

    def h_closing(self, m):
        """Penutupan pajak masa m (PPN rekap, PPh Final UMKM) + jadwalkan setoran."""
        env, acc = self.env, self.acc
        keys = ["ppn_out", "ppn_in", "pph21", "pph23", "pph42", "pph22_prepaid", "landed_accr", "rev_goods", "rev_discount", "bpjs_payable"]
        env.cr.execute("""SELECT account_id, SUM(balance) FROM account_move_line WHERE parent_state='posted' AND company_id=%s
                          AND account_id = ANY(%s) AND date >= %s AND date <= %s GROUP BY 1""",
                       (env.company.id, [acc[k] for k in keys], m, month_end(m)))
        inv = {acc[k]: k for k in keys}
        d_ = defaultdict(int)
        for aid, bal in env.cr.fetchall():
            d_[inv[aid]] = rp(bal)
        ym, e, nxt = m.strftime("%Y-%m"), month_end(m), m + relativedelta(months=1)
        x, y = -d_["ppn_out"], d_["ppn_in"]
        net = x - y
        if x or y:
            lines = [(acc["ppn_out"], x, 0, None, None), (acc["ppn_in"], 0, y, None, None)]
            lines.append((acc["ppn_payable"], 0, net, None, None) if net >= 0 else (acc["ppn_lebih"], -net, 0, None, None))
            self.je("PAJAK", e, f"Rekap PPN masa {ym} (keluaran - masukan)", lines)
            if net > 0:
                self.push(nxt.replace(day=15), "cost", what="__je", spec=("PAJAK", f"Setor PPN masa {ym}", [(acc["ppn_payable"], net, 0), (acc["bank_main"], 0, net)]), m=m)
        omzet = -(d_["rev_goods"] + d_["rev_discount"])
        final = rp(omzet * C.PPH_FINAL_UMKM_RATE / 100)
        if final > 0:
            self.je("PAJAK", e, f"Beban PPh Final UMKM masa {ym}", [(acc["tax_expense"], final, 0, None, {str(self.ana["CC:Kantor Pusat"]): 100}),
                                                                (acc["pph_final"], 0, final, None, None)])
            self.push(nxt.replace(day=15), "cost", what="__je", spec=("PAJAK", f"Setor PPh Final masa {ym}", [(acc["pph_final"], final, 0), (acc["bank_main"], 0, final)]), m=m)
        p21, p23, p42 = -d_["pph21"], -d_["pph23"], -d_["pph42"]
        if p21 or p23 or p42:
            self.push(nxt.replace(day=10), "cost", what="__je", spec=("PAJAK", f"Setor PPh 21/23/4(2) masa {ym}",
                      [(acc["pph21"], p21, 0), (acc["pph23"], p23, 0), (acc["pph42"], p42, 0), (acc["bank_main"], 0, p21 + p23 + p42)]), m=m)
        bp = -d_["bpjs_payable"]
        if bp > 0:
            self.push(nxt.replace(day=15), "cost", what="__je", spec=("PAJAK", f"Bayar iuran BPJS {ym}", [(acc["bpjs_payable"], bp, 0), (acc["bank_main"], 0, bp)]), m=m)

    # penyederhanaan: setoran dijadwalkan lewat jenis 'cost' dengan what='__je'
    def _je_spec(self, spec):
        j, ref, lines = spec
        self.je(j, self.cur, ref, [(a, dr, cr, None, None) for a, dr, cr in lines])

    # ------------------------------------------------------------------ demo rekonsiliasi bank
    def bank_rec_demo(self):
        env = self.env
        if "account.bank.statement.line" not in env:
            return
        base = C.END - dt.timedelta(days=10)
        for i, (name, amt, acc_key) in enumerate([("Jasa kebersihan toko", 650_000, "maint"), ("Servis AC gudang", 1_200_000, "maint"),
                                                    ("Cetak banner promo 10.10", 2_300_000, "packaging")]):
            d = base + dt.timedelta(days=i * 3)
            b = env["account.move"].create({"move_type": "in_invoice", "partner_id": self.partner("maint"), "invoice_date": d, "date": d, "ref": name,
                                            "invoice_line_ids": [(0, 0, {"name": name, "account_id": self.acc[acc_key], "quantity": 1, "price_unit": amt,
                                                                         "analytic_distribution": {str(self.ana["CC:Kantor Pusat"]): 100}})]})
            b.action_post()
            self.at(d + dt.timedelta(days=1), 11)
            self.pay_now(b, "BCA2", None, d + dt.timedelta(days=1))
            env["account.bank.statement.line"].create({"journal_id": self.jr["BCA2"], "date": d + dt.timedelta(days=1),
                                                       "payment_ref": f"TRF {name.upper()}", "amount": -amt, "partner_id": self.partner("maint")})
        for j, (ref, amt) in enumerate([("BIAYA ADM BANK", -150_000), ("BUNGA TABUNGAN", 42_000)]):
            env["account.bank.statement.line"].create({"journal_id": self.jr["BCA2"], "date": C.END - dt.timedelta(days=2 + j), "payment_ref": ref, "amount": amt})

    # ------------------------------------------------------------------ penyiapan
    def prepare(self):
        env = self.env
        Team = env["crm.team"]
        self.teams = {}
        for ch in C.CHANNELS:
            t = Team.search([("name", "=", ch["team"])], limit=1) or Team.create({"name": ch["team"]})
            self.teams[ch["code"]] = t.id
        self.chan = {c["code"]: c for c in C.CHANNELS}
        # riwayat harga produk (product.value) dibuat saat master (tanggal nyata) -> mundurkan ke sebelum saldo awal agar
        # rata-rata biaya (AVCO) bisa bergerak mengikuti penerimaan barang berharga baru
        self.env.cr.execute("UPDATE product_value SET date = %s WHERE date > %s", (dt.datetime(2026, 6, 1), dt.datetime(2026, 6, 1)))
        self.env.invalidate_all()
        self.catalog = P.catalog()
        orders = P.build()
        res = S.build(orders)
        self.sup = res
        self.orders = res["orders"]
        self.orders_by_ref = {o["ref"]: o for o in self.orders}
        print("Perencana:", {k: int(v) for k, v in res["stats"].items() if not k.startswith("_")})

    def schedule(self):
        res = self.sup
        for e in res["events"]:
            k = e["kind"]
            payload = {kk: vv for kk, vv in e.items() if kk not in ("date", "kind")}
            if k == "return":
                continue          # retur dijadwalkan dari order
            self.push(e["date"], k, **payload)
        for o in self.orders:
            if o.get("void"):
                continue
            self.push(o["date"], "order", h=max(o["time"][0], 8), minute=o["time"][1], o=o["ref"])
            if o.get("ret_date") and not o.get("cancel"):
                self.push(o["ret_date"], "return", order=o["ref"])
        # pencairan escrow & setoran kas
        d = C.START
        while d <= C.END:
            if d.weekday() == 0:
                for code in ("SHOPEE", "TOKPED", "TIKTOK"):
                    self.push(d, "payout", code=code)
                self.push(d, "deposit")
            if d.weekday() in (0, 3):
                self.push(d, "payout", code="STORE")
                self.push(d, "payout", code="INSTAGRAM")
            if d.weekday() == 3:
                self.push(d, "deposit")
            d += dt.timedelta(days=1)
        # biaya & rutinitas bulanan
        for i in range(4):
            m = C.START.replace(day=1) + relativedelta(months=i)
            for what, day in (("rent_toko", 3), ("rent_gudang", 3), ("utilities", 8), ("agency", 12), ("ads", 15), ("maint", 20)):
                self.push(m.replace(day=day), "cost", what=what, m=m)
            for what in ("packaging", "shipping"):
                self.push(min(month_end(m), C.END), "cost", what=what, m=m, h=18)
            self.push(min(month_end(m), C.END), "cost", what="bank_fee", m=m, h=17)
            if m.month >= 8:
                self.push(m.replace(day={8: 28, 9: 12, 10: 9}[m.month]), "cost", what="entertain", m=m)
            if month_end(m) < C.END:
                self.push(m.replace(day=25), "monthly", what="payroll", m=m)
                self.push(month_end(m), "monthly", what="depreciation", m=m, h=18)
                self.push(month_end(m), "closing", m=m)
        self.push(dt.date(2026, 8, 3), "cost", what="camera", m=dt.date(2026, 8, 1))
        self.push(dt.date(2026, 9, 30), "monthly", what="opname", m=dt.date(2026, 9, 1), h=17)
        self.push(C.END, "monthly", what="accrual", m=dt.date(2026, 10, 1), h=17)

    # ------------------------------------------------------------------ audit, pengguna, keras
    def finalize(self):
        env = self.env
        self.at(C.END, 17, 30)
        if "auditlog.rule" in env:
            models = ["account.move", "account.move.line", "account.account", "account.tax", "account.journal", "account.payment",
                      "product.template", "product.category", "res.partner", "stock.picking", "sale.order", "purchase.order"]
            for model in models:
                mid = env["ir.model"].search([("model", "=", model)], limit=1)
                if not mid or env["auditlog.rule"].search([("model_id", "=", mid.id)], limit=1):
                    continue
                rule = env["auditlog.rule"].create({"name": f"Audit {model}", "model_id": mid.id, "log_type": "full", "log_read": False,
                                                    "log_create": True, "log_write": True, "log_unlink": True})
                for meth in ("set_to_confirmed", "subscribe", "action_subscribe"):
                    if hasattr(rule, meth):
                        getattr(rule, meth)()
                        break
            # aktivitas contoh agar Audit Log berisi saat demo (harga naik 1 Okt, alamat pemasok diperbarui)
            for sku, newp in (("BC-DRS-001", 389_000), ("BC-SRB-001", 619_000)):
                tmpl = env["product.product"].browse(self.PRD[sku]).product_tmpl_id
                tmpl.list_price = newp
            env["res.partner"].browse(self.partner("landlord_toko")).street = "Jl. Raya Sesetan No. 90 (alamat diperbarui)"
            print("Audit trail aktif; contoh perubahan harga & alamat dicatat")
        for j in env["account.journal"].search([("type", "in", ("sale", "purchase"))]):
            if "restrict_mode_hash_table" in j._fields:
                j.restrict_mode_hash_table = True
        gf = user_group_field(env)
        specs = [("accountant@batik-demo.example", "Akuntan Demo", ["account.group_account_manager", "account.group_account_user", "account.group_account_invoice",
                                                                    "sales_team.group_sale_manager", "stock.group_stock_user"]),
                 ("owner@batik-demo.example", "Owner (Read-only Audit)", ["account.group_account_readonly"]),
                 ("kasir@batik-demo.example", "Kasir Toko", ["account.group_account_invoice", "sales_team.group_sale_salesman", "point_of_sale.group_pos_user"])]
        for login, name, xmlids in specs:
            if env["res.users"].search([("login", "=", login)], limit=1):
                continue
            groups = [env.ref(x, raise_if_not_found=False) for x in xmlids]
            env["res.users"].create({"name": name, "login": login, "password": "demo1234", "tz": C.COMPANY["tz"],
                                     gf: [(4, g.id) for g in groups if g], "company_id": env.company.id, "company_ids": [(6, 0, [env.company.id])]})
        adm, full = env.ref("base.user_admin", raise_if_not_found=False), env.ref("account.group_account_user", raise_if_not_found=False)
        if adm and full:
            adm.write({gf: [(4, full.id)]})
        # produk tampil di POS
        T = env["product.template"].search([("sale_ok", "=", True), ("default_code", "!=", False)])
        if "available_in_pos" in T._fields:
            T.write({"available_in_pos": True})
        # scrap/reject & selisih opname (jurnal valuasi otomatis) -> beban gudang: beri analytic cost center Gudang & Produksi
        ga = self.ana.get("CC:Gudang & Produksi")
        if ga:
            L = env["account.move.line"].search([("parent_state", "=", "posted"), ("account_id", "=", self.acc["cogs_adjust"]),
                                                 ("analytic_distribution", "=", False)])
            if L:
                L.write({"analytic_distribution": {str(ga): 100}})
            print(f"Analytic Gudang & Produksi pada {len(L)} baris scrap/selisih opname")
        print("User demo (login = email): accountant@ / owner@ / kasir@batik-demo.example  (password: demo1234)")

    def trial_check(self):
        env = self.env
        env.cr.execute("SELECT COALESCE(SUM(debit),0), COALESCE(SUM(credit),0) FROM account_move_line WHERE parent_state='posted' AND company_id=%s", (env.company.id,))
        dr, cr = env.cr.fetchone()
        print(f"Cek neraca saldo: debit={dr:,.0f} credit={cr:,.0f} selisih={dr - cr:,.2f}")
        print("Omzet (DPP) per channel:")
        tot = defaultdict(float)
        for ym, v in sorted(self.dpp_month.items()):
            print(f"   {ym}: Rp {sum(v.values()):,.0f}  " + ", ".join(f"{c}={x / 1e6:.1f}jt" for c, x in sorted(v.items())))
        print({k: (round(v) if isinstance(v, float) else v) for k, v in self.stats.items()})


def run(env):
    s = Steps(env)
    sd = Seeder(env)
    with s.step("Persiapan: rencana order & pasokan"):
        sd.prepare()
        sd.schedule()
    env.cr.commit()
    # Eksekusi kejadian melakukan commit berkala sendiri -> tidak boleh dibungkus savepoint Steps.step
    try:
        sd.run_queue()
        sd.bank_rec_demo()
        env.cr.commit()
        s.results.append(("Eksekusi kejadian kronologis (30 Jun - 17 Okt)", "OK", ""))
        print("[OK]   Eksekusi kejadian kronologis (30 Jun - 17 Okt)")
    except Exception as exc:  # noqa: BLE001
        env.cr.rollback()
        s.results.append(("Eksekusi kejadian kronologis (30 Jun - 17 Okt)", "FAIL", str(exc)[:300]))
        print(f"[FAIL] Eksekusi kejadian: {exc}")
        traceback.print_exc()
    with s.step("Audit trail, hardening, user demo"):
        sd.finalize()
    with s.step("Cek keseimbangan jurnal"):
        sd.trial_check()
    try:
        sd._fz.stop()
    except Exception:  # noqa: BLE001
        pass
    return s.summary()
