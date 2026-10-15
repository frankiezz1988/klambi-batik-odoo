#!/usr/bin/env python3
"""Ekspor laporan dari Odoo (XML-RPC, read-only) menjadi situs statis + CSV staging e-Faktur.

Output (--out): index.html, data.json, efaktur_staging.csv, _headers
Dipakai lokal (`make snapshot`) dan di GitHub Actions untuk deploy ke Cloudflare Pages.
"""
import argparse
import collections
import csv
import datetime as dt
import json
import os
import sys
import xmlrpc.client

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "provision"))
import config as C  # noqa: E402

BS_TYPES = ("asset_", "liability_", "equity")


class Odoo:
    def __init__(self, url, db, user, password):
        self.db, self.password = db, password
        self.uid = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common").authenticate(db, user, password, {})
        if not self.uid:
            raise SystemExit("Login Odoo gagal (cek --user/--password/--db)")
        self.models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)

    def call(self, model, method, *args, **kw):
        return self.models.execute_kw(self.db, self.uid, self.password, model, method, list(args), kw)

    def read_all(self, model, domain, fields, page=4000):
        out, offset = [], 0
        while True:
            chunk = self.call(model, "search_read", domain, fields=fields, limit=page, offset=offset, order="id")
            out += chunk
            if len(chunk) < page:
                return out
            offset += page

    def has_model(self, model):
        return bool(self.call("ir.model", "search_count", [("model", "=", model)]))


def m2o_id(v):
    return v[0] if v else None


def m2o_name(v):
    return v[1] if v else ""


def section_of(acc):
    code, typ = acc["code"] or "", acc["account_type"]
    if code.startswith("4") or typ.startswith("income"):
        return "rev"
    if code.startswith("5") or typ == "expense_direct_cost":
        return "cogs"
    if code.startswith("61"):
        return "selling"
    if code.startswith("69"):
        return "tax"
    if typ.startswith("expense"):
        return "ga"
    return None


def cash_category(acc):
    code, typ = acc["code"] or "", acc["account_type"]
    if typ in ("asset_receivable",) or code.startswith("1110"):
        return "Penerimaan dari pelanggan / marketplace"
    if typ == "liability_payable":
        return "Pembayaran ke pemasok"
    if code.startswith("2140"):
        return "Pembayaran ongkos angkut pembelian"
    if code.startswith("113"):
        return "Pembayaran persediaan"
    if code.startswith("114") or code.startswith("213"):
        return "Pajak (PPN / PPh)"
    if code.startswith("6210"):
        return "Gaji"
    if code.startswith("611"):
        return "Biaya marketplace / MDR (dipotong settlement)"
    if code.startswith("3"):
        return "Pendanaan (modal)"
    if code.startswith("6"):
        return "Beban operasional lain"
    return "Lain-lain"


def build(o):
    accs = {a["id"]: a for a in o.read_all("account.account", [], ["code", "name", "account_type"])}
    lines = o.read_all("account.move.line", [("parent_state", "=", "posted")],
                       ["date", "account_id", "debit", "credit", "balance", "move_id", "move_type",
                        "product_id", "quantity", "display_type"])
    moves = {m["id"]: m for m in o.read_all(
        "account.move", [("move_type", "=", "out_invoice"), ("state", "=", "posted")],
        ["name", "invoice_date", "partner_id", "team_id", "amount_untaxed", "amount_tax", "amount_total",
         "btk_nsfp", "btk_channel_ref", "btk_kode_transaksi"])}
    ana = o.read_all("account.analytic.line", [], ["date", "account_id", "amount", "general_account_id"])
    months = sorted({l["date"][:7] for l in lines})
    midx = {m: i for i, m in enumerate(months)}
    n = len(months)

    def acct(l):
        return accs[m2o_id(l["account_id"])]

    # ---- P&L bulanan per akun
    pnl = collections.defaultdict(lambda: [0.0] * n)
    for l in lines:
        a = acct(l)
        sec = section_of(a)
        if sec:
            sign = -1 if sec == "rev" else 1
            pnl[(sec, a["code"], a["name"])][midx[l["date"][:7]]] += sign * l["balance"]
    sections = {}
    for sec in ("rev", "cogs", "selling", "ga", "tax"):
        rows = [{"code": c, "name": nm, "values": v, "total": sum(v)}
                for (s, c, nm), v in sorted(pnl.items()) if s == sec]
        sections[sec] = {"rows": rows, "total": [sum(r["values"][i] for r in rows) for i in range(n)]}
    tot = lambda k: sections[k]["total"]  # noqa: E731
    gross = [tot("rev")[i] - tot("cogs")[i] for i in range(n)]
    opinc = [gross[i] - tot("selling")[i] - tot("ga")[i] for i in range(n)]
    net = [opinc[i] - tot("tax")[i] for i in range(n)]

    # ---- Neraca saldo & neraca kumulatif per akhir bulan
    cum = [collections.defaultdict(lambda: [0.0, 0.0]) for _ in range(n)]  # akun -> [debit, credit] kumulatif
    for l in lines:
        i = midx[l["date"][:7]]
        for j in range(i, n):
            cum[j][m2o_id(l["account_id"])][0] += l["debit"]
            cum[j][m2o_id(l["account_id"])][1] += l["credit"]
    tb = []
    bs = []
    for j in range(n):
        rows_tb, groups = [], {"asset": [], "liability": [], "equity": []}
        earn = 0.0
        for aid, (d, c) in sorted(cum[j].items(), key=lambda kv: accs[kv[0]]["code"] or ""):
            a = accs[aid]
            rows_tb.append({"code": a["code"], "name": a["name"], "type": a["account_type"], "debit": d, "credit": c,
                            "balance": d - c})
            t = a["account_type"]
            if t.startswith("asset_"):
                groups["asset"].append({"code": a["code"], "name": a["name"], "value": d - c})
            elif t.startswith("liability_"):
                groups["liability"].append({"code": a["code"], "name": a["name"], "value": c - d})
            elif t.startswith("equity"):
                groups["equity"].append({"code": a["code"], "name": a["name"], "value": c - d})
            elif section_of(a):
                earn += c - d
        groups["equity"].append({"code": "", "name": "Laba (Rugi) Berjalan", "value": earn})
        tb.append({"month": months[j], "rows": rows_tb,
                   "totals": {"debit": sum(r["debit"] for r in rows_tb), "credit": sum(r["credit"] for r in rows_tb)}})
        bs.append({"month": months[j], **groups,
                   "total_asset": sum(x["value"] for x in groups["asset"]),
                   "total_le": sum(x["value"] for x in groups["liability"] + groups["equity"])})

    # ---- Arus kas (metode langsung, berdasar lawan akun dari jurnal yang menyentuh akun kas/bank)
    by_move = collections.defaultdict(list)
    for l in lines:
        by_move[m2o_id(l["move_id"])].append(l)
    cats = collections.defaultdict(lambda: [0.0] * n)
    cash_open_close = [0.0] * n
    for mid, ls in by_move.items():
        cash = [x for x in ls if acct(x)["account_type"] == "asset_cash"]
        if not cash:
            continue
        i = midx[cash[0]["date"][:7]]
        cash_open_close[i] += sum(x["balance"] for x in cash)
        for x in ls:
            if acct(x)["account_type"] != "asset_cash":
                cats[cash_category(acct(x))][i] += -x["balance"]
    ending, run = [], 0.0
    for i in range(n):
        run += cash_open_close[i]
        ending.append(run)
    cashflow = {"categories": [{"name": k, "values": v, "total": sum(v)} for k, v in sorted(cats.items())],
                "net": cash_open_close, "ending": ending}

    # ---- Profitabilitas per channel
    team_to_code = {c["team"]: c["code"] for c in C.CHANNELS}
    name_to_code = {c["name"]: c["code"] for c in C.CHANNELS}
    ch = {c["code"]: {"code": c["code"], "name": c["name"], "orders": 0, "revenue": 0.0, "cogs": 0.0, "fees": {}}
          for c in C.CHANNELS}
    for m in moves.values():
        code = team_to_code.get(m2o_name(m["team_id"]))
        if code:
            ch[code]["orders"] += 1
    for l in lines:
        if l["move_type"] != "out_invoice":
            continue
        code = team_to_code.get(m2o_name(moves.get(m2o_id(l["move_id"]), {}).get("team_id")))
        if not code:
            continue
        a = acct(l)
        if a["account_type"].startswith("income"):
            ch[code]["revenue"] += -l["balance"]
        elif a["account_type"] == "expense_direct_cost":
            ch[code]["cogs"] += l["balance"]
    for r in ana:
        code = name_to_code.get(m2o_name(r["account_id"]))
        g = accs.get(m2o_id(r["general_account_id"]))
        if code and g and g["account_type"] == "expense" and (g["code"] or "").startswith("61"):
            ch[code]["fees"][g["name"]] = ch[code]["fees"].get(g["name"], 0.0) - r["amount"]
    channels = []
    for c in ch.values():
        fees = sum(c["fees"].values())
        gp = c["revenue"] - c["cogs"]
        contrib = gp - fees
        channels.append({**c, "gross_profit": gp, "channel_costs": fees, "contribution": contrib,
                         "gm_pct": gp / c["revenue"] * 100 if c["revenue"] else 0,
                         "contrib_pct": contrib / c["revenue"] * 100 if c["revenue"] else 0,
                         "aov": c["revenue"] / c["orders"] if c["orders"] else 0})

    # ---- HPP & margin per produk
    prod = collections.defaultdict(lambda: {"qty": 0.0, "revenue": 0.0, "cogs": 0.0})
    for l in lines:
        if l["move_type"] != "out_invoice" or not l["product_id"]:
            continue
        a = acct(l)
        p = prod[m2o_name(l["product_id"])]
        if a["account_type"].startswith("income"):
            p["revenue"] += -l["balance"]
            p["qty"] += l["quantity"]
        elif a["account_type"] == "expense_direct_cost":
            p["cogs"] += l["balance"]
    products = sorted(
        [{"name": k, **v, "gm_pct": (v["revenue"] - v["cogs"]) / v["revenue"] * 100 if v["revenue"] else 0,
          "hpp_unit": v["cogs"] / v["qty"] if v["qty"] else 0} for k, v in prod.items()],
        key=lambda x: -x["revenue"])

    # ---- Ringkasan pajak per bulan
    def monthly(code_prefix, sign):
        v = [0.0] * n
        for l in lines:
            if (acct(l)["code"] or "").startswith(code_prefix):
                v[midx[l["date"][:7]]] += sign * l["balance"]
        return v

    taxes = {
        "PPN Keluaran (kredit)": monthly("2130101", -1), "PPN Masukan (debit)": monthly("1140101", 1),
        "PPh 22 dipungut marketplace": monthly("1140201", 1), "Beban PPh Final UMKM": monthly("6910101", 1),
        "PPh 21 terutang": monthly("2130201", -1), "PPh 23 dipotong": monthly("2130202", -1),
        "PPh 4(2) sewa dipotong": monthly("2130203", -1),
    }

    # ---- e-Faktur staging
    efaktur = []
    for m in moves.values():
        efaktur.append([m["invoice_date"], m["btk_nsfp"] or "", m["btk_kode_transaksi"] or "", m["name"],
                        m["btk_channel_ref"] or "", m2o_name(m["partner_id"]), round(m["amount_untaxed"]),
                        round(m["amount_untaxed"] * 11 / 12), round(m["amount_tax"]), round(m["amount_total"])])
    efaktur.sort()

    audit = []
    if o.has_model("auditlog.log"):
        for r in o.call("auditlog.log", "search_read", [], fields=["create_date", "model_id", "res_id", "method", "user_id", "name"],
                        limit=40, order="id desc"):
            audit.append({"at": r["create_date"], "model": m2o_name(r["model_id"]), "record": r["name"],
                          "method": r["method"], "user": m2o_name(r["user_id"])})

    return {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "company": C.COMPANY["name"], "months": months,
        "pnl": {"sections": sections, "gross": gross, "operating": opinc, "net": net},
        "tb": tb, "bs": bs, "cashflow": cashflow, "channels": channels, "products": products,
        "taxes": taxes, "audit": audit, "efaktur_count": len(efaktur),
        "kpi": {"revenue": sum(tot("rev")), "gross": sum(gross), "net": sum(net),
                "orders": sum(c["orders"] for c in channels), "cash": ending[-1] if ending else 0},
    }, efaktur


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("ODOO_URL", "http://localhost:8069"))
    ap.add_argument("--db", default=os.environ.get("ODOO_DB", "batik_demo"))
    ap.add_argument("--user", default=os.environ.get("ODOO_USER", "admin"))
    ap.add_argument("--password", default=os.environ.get("ODOO_PASSWORD", "admin"))
    ap.add_argument("--out", default="site")
    a = ap.parse_args()
    data, efaktur = build(Odoo(a.url, a.db, a.user, a.password))
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(HERE, "template.html"), encoding="utf-8") as fh:
        html = fh.read().replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False))
    with open(os.path.join(a.out, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(html)
    with open(os.path.join(a.out, "data.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(a.out, "efaktur_staging.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["tanggal_faktur", "nsfp", "kode_transaksi", "no_invoice", "ref_order_channel", "pembeli",
                    "harga_jual_dpp_umum", "dpp_nilai_lain_11_12", "ppn", "total"])
        w.writerows(efaktur)
    with open(os.path.join(a.out, "_headers"), "w") as fh:
        fh.write("/*\n  X-Robots-Tag: noindex\n  Referrer-Policy: no-referrer\n")
    print(f"Snapshot tertulis di {a.out}/ ({len(data['months'])} bulan, {data['efaktur_count']} invoice)")


if __name__ == "__main__":
    main()
