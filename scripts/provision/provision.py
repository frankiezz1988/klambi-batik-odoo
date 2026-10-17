"""Provisioning master data: company, CoA retail overlay, pajak ID, analytic channel, jurnal, kategori produk, MIS."""
import csv
import os

import config as C
from common import Steps, load_registry, save_registry

DATA_DIR = os.environ.get("BATIK_DATA_DIR", "/mnt/data")


# --------------------------------------------------------------------------- company
def setup_company(env):
    """Harus dijalankan SEBELUM modul account/l10n_id agar CoA Indonesia ter-load untuk company ini."""
    idr = env.ref("base.IDR")
    idr.active = True
    company = env.company
    vals = {
        "name": C.COMPANY["name"],
        "street": C.COMPANY["street"],
        "city": C.COMPANY["city"],
        "zip": C.COMPANY["zip"],
        "email": C.COMPANY["email"],
        "phone": C.COMPANY["phone"],
        "country_id": env.ref("base.id").id,
        "currency_id": idr.id,
        "vat": C.COMPANY["vat"],
    }
    company.write(vals)
    partner = company.partner_id
    if "l10n_id_pkp" in partner._fields:  # jika modul l10n_id sudah terpasang
        partner.l10n_id_pkp = True
    admin = env.ref("base.user_admin")
    lang = env["res.lang"].search([("code", "=", "id_ID")], limit=1)
    admin.write({"tz": "Asia/Jakarta", **({"lang": "id_ID"} if lang else {})})
    print(f"Company: {company.name} | {company.country_id.code} | {company.currency_id.name}")


# --------------------------------------------------------------------------- CoA overlay
def load_coa(env):
    company = env.company
    Account = env["account.account"]
    has_policy = "analytic_policy" in Account._fields
    reg = {}
    path = os.path.join(DATA_DIR, "coa_retail_batik.csv")
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            code = row["code"]
            acc = Account.search([("code", "=", code), ("company_ids", "in", company.ids)], limit=1) \
                if "company_ids" in Account._fields else Account.search([("code", "=", code)], limit=1)
            vals = {
                "code": code,
                "name": row["name"],
                "account_type": row["account_type"],
                "reconcile": row["reconcile"] == "1",
            }
            if has_policy and row["analytic_policy"]:
                vals["analytic_policy"] = row["analytic_policy"]
            if acc:
                acc.write({k: v for k, v in vals.items() if k != "code"})
            else:
                acc = Account.create(vals)
            reg[row["key"]] = acc.id
    save_registry(env, {"acc": reg})
    print(f"CoA overlay: {len(reg)} akun retail dimuat/diperbarui")
    return reg


# --------------------------------------------------------------------------- accounting config
def configure_company_accounting(env, acc):
    company = env.company
    company.anglo_saxon_accounting = True  # COGS diposting saat invoice -> ikut analytic channel
    for fname, key in (("income_account_id", "rev_goods"), ("expense_account_id", "cogs")):
        if fname in company._fields:
            company[fname] = acc[key]
    print("Anglo-saxon accounting ON; akun default pendapatan/HPP di-set")


def ensure_journal(env, code, name, jtype, account_id=None, direct=True):
    company = env.company
    j = env["account.journal"].search([("code", "=", code), ("company_id", "=", company.id)], limit=1)
    if not j:
        vals = {"name": name, "code": code, "type": jtype, "company_id": company.id}
        if jtype in ("bank", "cash") and account_id:
            vals["default_account_id"] = account_id
        j = env["account.journal"].create(vals)
    if jtype in ("bank", "cash") and account_id and direct:
        # Demo: payment langsung ke akun jurnal (tanpa outstanding account + bank statement).
        # Produksi: gunakan statement/OCA account-reconcile.
        lines = j.inbound_payment_method_line_ids | j.outbound_payment_method_line_ids
        lines.write({"payment_account_id": account_id})
    return j


def setup_journals(env, acc):
    specs = [
        ("KTOK", "Kas Toko", "cash", "cash_store"),
        ("BCA", "Bank BCA - Operasional", "bank", "bank_main"),
        ("QRIS", "Settlement QRIS/EDC Toko", "bank", "bank_qris"),
        ("SHPE", "Escrow Shopee", "bank", "wallet_shopee"),
        ("TKPD", "Escrow Tokopedia", "bank", "wallet_tokped"),
        ("TTOK", "Escrow TikTok Shop", "bank", "wallet_tiktok"),
        ("PGW", "Payment Gateway (IG/Web)", "bank", "wallet_gateway"),
    ]
    reg = {}
    for code, name, jtype, key in specs:
        reg[code] = ensure_journal(env, code, name, jtype, acc[key]).id
    # Rekening untuk demo rekonsiliasi bank: payment TIDAK langsung ke akun bank (pakai outstanding account)
    reg["BCA2"] = ensure_journal(env, "BCA2", "Bank BCA - Rekening Rekonsiliasi", "bank", acc["bank_rek"], direct=False).id
    reg["ASET"] = ensure_journal(env, "ASET", "Jurnal Aset Tetap & Penyusutan", "general").id
    reg["SETL"] = ensure_journal(env, "SETL", "Settlement Marketplace & Penyesuaian", "general").id
    reg["PAJAK"] = ensure_journal(env, "PAJAK", "Jurnal Pajak (PPN/PPh)", "general").id
    reg["PYRL"] = ensure_journal(env, "PYRL", "Jurnal Gaji", "general").id
    save_registry(env, {"journal": reg})
    print(f"Jurnal: {', '.join(reg)}")


def ensure_tax(env, name, amount, use, tax_account_id, group_name):
    company = env.company
    tax = env["account.tax"].search(
        [("name", "=", name), ("type_tax_use", "=", use), ("company_id", "=", company.id)], limit=1
    )
    if tax:
        return tax
    group = env["account.tax.group"].search([("name", "=", group_name)], limit=1) \
        or env["account.tax.group"].create({"name": group_name})
    tax = env["account.tax"].create({
        "name": name, "amount": amount, "amount_type": "percent", "type_tax_use": use,
        "tax_group_id": group.id, "company_id": company.id,
    })
    reps = tax.invoice_repartition_line_ids | tax.refund_repartition_line_ids
    reps.filtered(lambda r: r.repartition_type == "tax").write({"account_id": tax_account_id})
    return tax


def setup_taxes(env, acc):
    t = {
        "ppn_out": ensure_tax(env, "PPN Keluaran 12% x DPP 11/12 (efektif 11%)", C.PPN_EFFECTIVE, "sale", acc["ppn_out"], "PPN"),
        "ppn_in": ensure_tax(env, "PPN Masukan 12% x DPP 11/12 (efektif 11%)", C.PPN_EFFECTIVE, "purchase", acc["ppn_in"], "PPN"),
        "pph23": ensure_tax(env, "PPh 23 Jasa 2% (dipotong)", -C.PPH23_RATE, "purchase", acc["pph23"], "PPh"),
        "pph42": ensure_tax(env, "PPh 4(2) Sewa 10% (dipotong)", -C.PPH42_SEWA_RATE, "purchase", acc["pph42"], "PPh"),
    }
    save_registry(env, {"tax": {k: v.id for k, v in t.items()}})
    print("Pajak: " + "; ".join(v.name for v in t.values()))


def setup_analytic(env):
    plan_model = env["account.analytic.plan"]
    acc_model = env["account.analytic.account"]
    plan_ch = plan_model.search([("name", "=", "Channel Penjualan")], limit=1) or plan_model.create({"name": "Channel Penjualan"})
    plan_cc = plan_model.search([("name", "=", "Cost Center")], limit=1) or plan_model.create({"name": "Cost Center"})
    reg = {}
    for ch in C.CHANNELS:
        a = acc_model.search([("name", "=", ch["name"]), ("plan_id", "=", plan_ch.id)], limit=1) \
            or acc_model.create({"name": ch["name"], "code": ch["code"], "plan_id": plan_ch.id})
        reg[ch["code"]] = a.id
    for cc in C.COST_CENTERS:
        a = acc_model.search([("name", "=", cc), ("plan_id", "=", plan_cc.id)], limit=1) \
            or acc_model.create({"name": cc, "plan_id": plan_cc.id})
        reg["CC:" + cc] = a.id
    save_registry(env, {"analytic": reg, "plan_channel": plan_ch.id})
    print(f"Analytic: plan Channel ({len(C.CHANNELS)} akun) + Cost Center ({len(C.COST_CENTERS)})")


def setup_categories(env, acc):
    Cat = env["product.category"]
    # xmlid product.product_category_all tidak ada di Odoo 19 -> cari kategori induk (tanpa parent), buat "All" bila tak ada
    root = env.ref("product.product_category_all", raise_if_not_found=False) \
        or Cat.search([("parent_id", "=", False)], order="id", limit=1) \
        or Cat.create({"name": "All"})
    reg = {}
    for c in C.CATEGORIES:
        vals = {
            "name": c["name"], "parent_id": root.id,
            "property_cost_method": c["cost_method"],   # FIFO utk Batik Tulis, AVCO lainnya
            "property_valuation": "real_time",
            "property_account_income_categ_id": acc["rev_goods"],
            "property_account_expense_categ_id": acc["cogs"],
            "property_stock_valuation_account_id": acc["inventory"],
            "property_stock_account_input_categ_id": acc["stock_in"],
            "property_stock_account_output_categ_id": acc["stock_out"],
        }
        cat = Cat.search([("name", "=", c["name"])], limit=1)
        if cat:
            cat.write(vals)
        else:
            cat = Cat.create(vals)
        reg[c["name"]] = cat.id
    save_registry(env, {"categ": reg})
    print("Kategori produk: costing FIFO (Batik Tulis) & AVCO (lainnya), valuation real-time")


# --------------------------------------------------------------------------- MIS Builder templates (P&L, Neraca)
def setup_mis(env):
    Report, Kpi = env["mis.report"], env["mis.report.kpi"]
    if Report.search([("name", "=", "Laba Rugi - Retail Batik")], limit=1):
        print("MIS template sudah ada")
        return
    pl = Report.create({"name": "Laba Rugi - Retail Batik"})
    rows = [
        ("pendapatan", "Penjualan Bersih", "-balp[4%]"),
        ("hpp", "Harga Pokok Penjualan", "balp[5%]"),
        ("laba_kotor", "Laba Kotor", "pendapatan - hpp"),
        ("beban_channel", "Beban Channel (komisi, MDR, iklan, KOL, kemasan)", "balp[611%] + balp[612%] + balp[613%]"),
        ("beban_umum", "Beban Umum & Administrasi", "balp[62%]"),
        ("laba_usaha", "Laba Usaha", "laba_kotor - beban_channel - beban_umum"),
        ("beban_pajak", "Beban PPh Final", "balp[69%]"),
        ("laba_bersih", "Laba Bersih", "laba_usaha - beban_pajak"),
    ]
    for i, (name, desc, expr) in enumerate(rows):
        Kpi.create({"report_id": pl.id, "sequence": i * 10, "name": name, "description": desc, "expression": expr})
    bs = Report.create({"name": "Neraca - Retail Batik"})
    rows = [
        ("kas_bank", "Kas, Bank & Saldo Escrow", "bale[111%]"),
        ("persediaan", "Persediaan", "bale[113%]"),
        ("pajak_dimuka", "Pajak Dibayar Dimuka", "bale[114%]"),
        ("aset_lain", "Aset Lain", "bale[115%] + bale[121%]"),
        ("total_aset", "Total Aset", "kas_bank + persediaan + pajak_dimuka + aset_lain"),
        ("liabilitas", "Total Liabilitas (utang usaha, pajak, interim)", "-bale[2%]"),
        ("modal", "Modal Disetor", "-bale[3%]"),
        ("laba_berjalan", "Laba Berjalan", "-(bale[4%] + bale[5%] + bale[6%])"),
        ("total_pasiva", "Total Liabilitas + Ekuitas", "liabilitas + modal + laba_berjalan"),
    ]
    for i, (name, desc, expr) in enumerate(rows):
        Kpi.create({"report_id": bs.id, "sequence": i * 10, "name": name, "description": desc, "expression": expr})
    for rep, title in ((pl, "Laba Rugi Bulanan"), (bs, "Neraca Bulanan")):
        periods = [
            (0, {"name": f"M-{i}" if i else "Bulan ini", "mode": "relative", "type": "m", "offset": -i, "duration": 1})
            for i in range(5, -1, -1)
        ]
        env["mis.report.instance"].create({
            "name": title, "report_id": rep.id, "company_id": env.company.id,
            "period_ids": periods,
        })
    print("MIS Builder: template + instance Laba Rugi & Neraca dibuat")


# --------------------------------------------------------------------------- payroll params, aset tetap, anggaran
def setup_payroll_params(env, acc):
    jr = load_registry(env)["journal"]
    params = {"journal": jr["PYRL"], "salary": acc["salary"], "bpjs_exp": acc["bpjs_exp"],
              "bpjs_payable": acc["bpjs_payable"], "pph21": acc["pph21"], "bank": acc["bank_main"]}
    icp = env["ir.config_parameter"].sudo()
    for k, v in params.items():
        icp.set_param(f"batik.payroll.{k}", str(v))
    print("Parameter akun payroll disimpan (batik.payroll.*)")


def setup_asset_profile(env, acc):
    """OCA account_asset_management: profil penyusutan garis lurus 4 tahun (peralatan toko)."""
    Profile = env["account.asset.profile"]
    jr = load_registry(env)["journal"]
    prof = Profile.search([("name", "=", "Peralatan Toko & Kantor (4 th, garis lurus)")], limit=1)
    if not prof:
        prof = Profile.create({
            "name": "Peralatan Toko & Kantor (4 th, garis lurus)",
            "account_asset_id": acc["equipment"],
            "account_depreciation_id": acc["accum_depr"],
            "account_expense_depreciation_id": acc["depreciation"],
            "journal_id": jr["ASET"],
            "method": "linear", "method_time": "year", "method_number": 4, "method_period": "month",
        })
    save_registry(env, {"asset_profile": prof.id})
    print("Profil aset tetap dibuat:", prof.name)


def setup_budget(env):
    """OCA mis_builder_budget: anggaran bulanan untuk KPI template Laba Rugi."""
    Budget, Item = env["mis.budget"], env["mis.budget.item"]
    report = env["mis.report"].search([("name", "=", "Laba Rugi - Retail Batik")], limit=1)
    if not report or Budget.search([("name", "=", "Anggaran Operasional (DEMO)")], limit=1):
        return
    import datetime as dt
    from dateutil.relativedelta import relativedelta
    first = dt.date.today().replace(day=1)
    start = first - relativedelta(months=C.MONTHS - 1)
    budget = Budget.create({"name": "Anggaran Operasional (DEMO)", "report_id": report.id,
                            "date_from": start, "date_to": first + relativedelta(months=1, days=-1)})
    plan = {"pendapatan": 75_000_000, "hpp": 35_000_000, "beban_channel": 22_000_000, "beban_umum": 48_000_000}
    kpis = {k.name: k for k in report.kpi_ids}
    for i in range(C.MONTHS):
        m0 = start + relativedelta(months=i)
        m1 = m0 + relativedelta(months=1, days=-1)
        for name, amount in plan.items():
            kpi = kpis.get(name)
            if kpi and kpi.expression_ids:
                Item.create({"budget_id": budget.id, "kpi_expression_id": kpi.expression_ids[0].id,
                             "date_from": m0, "date_to": m1, "amount": amount})
    print("Anggaran MIS dibuat dengan", C.MONTHS, "bulan x", len(plan), "KPI")


# --------------------------------------------------------------------------- orchestrator
def run(env):
    s = Steps(env)
    acc = {}
    with s.step("CoA retail overlay (CSV)"):
        acc = load_coa(env)
    acc = acc or load_registry(env).get("acc", {})
    with s.step("Setup accounting company (anglo-saxon, default akun)"):
        configure_company_accounting(env, acc)
    with s.step("Jurnal (kas, bank, escrow marketplace, settlement, pajak, gaji)"):
        setup_journals(env, acc)
    with s.step("Pajak Indonesia (PPN masukan/keluaran, PPh 23, PPh 4(2))"):
        setup_taxes(env, acc)
    with s.step("Analytic: plan Channel + Cost Center"):
        setup_analytic(env)
    with s.step("Kategori produk + costing method + valuation"):
        setup_categories(env, acc)
    with s.step("MIS Builder: template Laba Rugi & Neraca"):
        setup_mis(env)
    with s.step("Parameter akun payroll (batik_id_payroll)"):
        setup_payroll_params(env, acc)
    with s.step("Profil aset tetap (OCA account_asset_management)"):
        setup_asset_profile(env, acc)
    with s.step("Anggaran MIS (OCA mis_builder_budget)"):
        setup_budget(env)
    return s.summary()
