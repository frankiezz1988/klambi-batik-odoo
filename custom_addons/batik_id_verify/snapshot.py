"""Snapshot data bisnis & akuntansi ke CSV deterministik, untuk membandingkan dua lingkungan (sandbox vs Railway/VPS).

Prinsip:
- Read-only (hanya SELECT + pembacaan ORM), aman dijalankan di produksi/demo.
- Kunci baris = kunci alami (nomor dokumen, kode akun, SKU, ...), BUKAN id, sehingga tahan terhadap perbedaan id.
- Urutan baris tetap, angka dibulatkan, tanggal ISO (datetime dalam UTC) -> dua lingkungan dengan data sama menghasilkan berkas identik.
- Tiap dataset berdiri sendiri: bila satu gagal (modul tidak terpasang, kolom beda), dicatat di manifest dan sisanya tetap jalan.
"""
import csv
import datetime as dt
import io
import json
import os
import zipfile
from decimal import Decimal

from odoo import release

ASOF_DEFAULT = "2026-10-17"          # tanggal acuan umur piutang/hutang (akhir data seed)
SNAPSHOT_VERSION = 1

# kode akun (per perusahaan, kolom code_store jsonb) dan nama en_US (jsonb)
ACODE = "(select v from jsonb_each_text(a.code_store) t(k, v) order by k limit 1)"


def N(col):
    return "(%s->>'en_US')" % col


# tabel yang isinya memang berubah sendiri (sesi, cron, bus, cache aset web, ...): hanya diagnostik, tidak dihitung sebagai selisih
VOLATILE_PREFIX = ("bus_", "ir_attachment", "ir_logging", "res_device", "res_users_log", "mail_", "ir_cron", "ir_config_parameter",
                   "res_users_apikeys", "res_users_identitycheck", "ir_actions_todo", "base_import", "ir_profile", "ir_websocket",
                   "ir_demo", "orm_signaling", "website_", "iap_", "snailmail_", "sms_", "ir_mail_server", "auth_totp")


def fmt(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, Decimal):
        s = format(v, "f")
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return "0" if s in ("-0", "") else s
    if isinstance(v, float):
        s = ("%.6f" % v).rstrip("0").rstrip(".")
        return "0" if s in ("-0", "") else s
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat(sep=" ") if isinstance(v, dt.datetime) else v.isoformat()
    if isinstance(v, (list, tuple)):
        return ";".join(fmt(x) for x in v)
    return str(v).replace("\r", " ").replace("\n", " ")


def _table_exists(cr, name):
    cr.execute("select to_regclass(%s)", ("public." + name,))
    return cr.fetchone()[0] is not None


# ---------------------------------------------------------------- dataset berbasis SQL
# (nama, kolom kunci, tabel wajib, sql)   -- sql memakai %(asof)s bila perlu
SQL_DATASETS = [
    ("modules", ["name"], ["ir_module_module"],
     "select name, latest_version from ir_module_module where state = 'installed' order by name"),

    ("company", ["name"], ["res_company"],
     """select c.name, cur.name as currency, p.city, p.zip, p.vat, p.street
        from res_company c join res_currency cur on cur.id = c.currency_id join res_partner p on p.id = c.partner_id
        order by c.name"""),

    ("currencies_active", ["name"], ["res_currency"],
     "select name, active from res_currency where active order by name"),

    ("accounts", ["code"], ["account_account"],
     """select %(ac)s as code, %(nm)s as name, a.account_type, a.reconcile, a.active
        from account_account a order by 1""" % {"ac": ACODE, "nm": N("a.name")}),

    ("journals", ["code"], ["account_journal"],
     """select j.code, %(nm)s as name, j.type, j.active, j.restrict_mode_hash_table as hash_locked
        from account_journal j order by j.code""" % {"nm": N("j.name")}),

    ("taxes", ["key"], ["account_tax"],
     """select t.type_tax_use || '|' || %(nm)s || '#' || row_number() over (partition by t.type_tax_use, %(nm)s order by t.id) as key,
               t.amount_type, t.amount, t.price_include_override as price_include, t.active
        from account_tax t order by 1""" % {"nm": N("t.name")}),

    ("analytic_accounts", ["key"], ["account_analytic_account"],
     """select %(pn)s || '|' || %(nm)s as key, a.code, a.active
        from account_analytic_account a join account_analytic_plan p on p.id = a.plan_id order by 1""" % {"pn": N("p.name"), "nm": N("a.name")}),

    ("partners", ["key"], ["res_partner"],
     """select p.name || '#' || row_number() over (partition by p.name order by p.id) as key,
               p.is_company, p.street, p.city, p.zip, st.name as state, co.code as country, p.vat, p.phone, p.ref, p.active,
               p.customer_rank > 0 as is_customer, p.supplier_rank > 0 as is_vendor
        from res_partner p left join res_country_state st on st.id = p.state_id left join res_country co on co.id = p.country_id
        where p.name is not null order by 1"""),

    ("moves", ["key"], ["account_move"],
     """select m.name || '#' || row_number() over (partition by m.name order by m.id) as key,
               m.date, m.move_type, m.state, j.code as journal, p.name as partner, m.ref, cur.name as currency,
               round(m.amount_untaxed::numeric, 2) as untaxed, round(m.amount_tax::numeric, 2) as tax,
               round(m.amount_total::numeric, 2) as total, round(m.amount_residual::numeric, 2) as residual,
               m.payment_state, m.invoice_date_due as due, (tm.name->>'en_US') as sales_team
        from account_move m join account_journal j on j.id = m.journal_id left join res_partner p on p.id = m.partner_id
        left join res_currency cur on cur.id = m.currency_id left join crm_team tm on tm.id = m.team_id
        order by 1"""),

    ("move_lines", ["key"], ["account_move_line"],
     """select mv.name || '#' || mv.dup || '|' || l.line_no as key,
               l.date, l.parent_state, %(ac)s as account, p.name as partner, l.display_type,
               round(l.debit::numeric, 2) as debit, round(l.credit::numeric, 2) as credit,
               round(l.amount_residual::numeric, 2) as residual, l.reconciled, l.matching_number,
               pp.default_code as product, round(l.quantity::numeric, 4) as qty,
               an.dist as analytic
        from (select l.*, row_number() over (partition by l.move_id order by l.id) as line_no from account_move_line l) l
        join (select m.id, m.name, row_number() over (partition by m.name order by m.id) as dup from account_move m) mv on mv.id = l.move_id
        join account_account a on a.id = l.account_id
        left join res_partner p on p.id = l.partner_id
        left join product_product pp on pp.id = l.product_id
        left join lateral (
            select string_agg(%(an)s || '=' || d.value, ';' order by %(an)s) as dist
            from jsonb_each_text(coalesce(l.analytic_distribution, '{}'::jsonb)) d(key, value)
            join account_analytic_account aa on aa.id = split_part(d.key, ',', 1)::int) an on true
        order by mv.name, mv.dup, l.line_no""" % {"ac": ACODE, "an": N("aa.name")}),

    ("trial_balance", ["account"], ["account_move_line"],
     """select %(ac)s as account, %(nm)s as name,
               round(sum(l.debit)::numeric, 2) as debit, round(sum(l.credit)::numeric, 2) as credit,
               round(sum(l.balance)::numeric, 2) as balance
        from account_move_line l join account_account a on a.id = l.account_id
        where l.parent_state = 'posted' group by 1, 2 having abs(sum(l.debit)) + abs(sum(l.credit)) > 0 order by 1""" % {"ac": ACODE, "nm": N("a.name")}),

    ("trial_balance_monthly", ["key"], ["account_move_line"],
     """select to_char(l.date, 'YYYY-MM') || '|' || %(ac)s as key,
               round(sum(l.debit)::numeric, 2) as debit, round(sum(l.credit)::numeric, 2) as credit
        from account_move_line l join account_account a on a.id = l.account_id
        where l.parent_state = 'posted' group by 1 order by 1""" % {"ac": ACODE}),

    ("pl_by_analytic", ["key"], ["account_move_line"],
     """select to_char(l.date, 'YYYY-MM') || '|' || %(an)s || '|' || a.account_type as key,
               round(sum(-l.balance * d.value::numeric / 100)::numeric, 2) as amount
        from account_move_line l join account_account a on a.id = l.account_id
        cross join lateral jsonb_each_text(coalesce(l.analytic_distribution, '{}'::jsonb)) d(key, value)
        join account_analytic_account aa on aa.id = split_part(d.key, ',', 1)::int
        where l.parent_state = 'posted' and (a.account_type like 'income%%' or a.account_type like 'expense%%')
        group by 1 order by 1""" % {"an": N("aa.name")}),

    ("aging", ["key"], ["account_move_line"],
     """select a.account_type || '|' || p.name as key,
               round(sum(l.amount_residual) filter (where (%(asof)s::date - coalesce(l.date_maturity, l.date)) <= 0)::numeric, 2) as not_due,
               round(sum(l.amount_residual) filter (where (%(asof)s::date - coalesce(l.date_maturity, l.date)) between 1 and 30)::numeric, 2) as d1_30,
               round(sum(l.amount_residual) filter (where (%(asof)s::date - coalesce(l.date_maturity, l.date)) between 31 and 60)::numeric, 2) as d31_60,
               round(sum(l.amount_residual) filter (where (%(asof)s::date - coalesce(l.date_maturity, l.date)) between 61 and 90)::numeric, 2) as d61_90,
               round(sum(l.amount_residual) filter (where (%(asof)s::date - coalesce(l.date_maturity, l.date)) > 90)::numeric, 2) as d90p,
               round(sum(l.amount_residual)::numeric, 2) as total
        from account_move_line l join account_account a on a.id = l.account_id join res_partner p on p.id = l.partner_id
        where l.parent_state = 'posted' and not l.reconciled and l.amount_residual <> 0
          and a.account_type in ('asset_receivable', 'liability_payable')
        group by 1 order by 1"""),

    ("sale_orders", ["name"], ["sale_order"],
     """select so.name, so.state, to_char(so.date_order, 'YYYY-MM-DD HH24:MI:SS') as date_order_utc, p.name as partner, %(tn)s as team, w.name as warehouse,
               so.client_order_ref, round(so.amount_untaxed::numeric, 2) as untaxed, round(so.amount_total::numeric, 2) as total, so.invoice_status
        from sale_order so left join res_partner p on p.id = so.partner_id left join crm_team tm on tm.id = so.team_id
        left join stock_warehouse w on w.id = so.warehouse_id order by so.name""" % {"tn": N("tm.name")}),

    ("sale_lines", ["key"], ["sale_order_line"],
     """select so.name || '|' || row_number() over (partition by sl.order_id order by sl.sequence, sl.id) as key,
               pp.default_code as product, round(sl.product_uom_qty::numeric, 4) as qty, round(sl.price_unit::numeric, 2) as price,
               round(sl.discount::numeric, 2) as discount, round(sl.price_subtotal::numeric, 2) as subtotal,
               round(sl.qty_delivered::numeric, 4) as delivered, round(sl.qty_invoiced::numeric, 4) as invoiced
        from sale_order_line sl join sale_order so on so.id = sl.order_id left join product_product pp on pp.id = sl.product_id
        where sl.display_type is null order by so.name, sl.sequence, sl.id"""),

    ("purchase_orders", ["name"], ["purchase_order"],
     """select po.name, po.state, to_char(po.date_order, 'YYYY-MM-DD HH24:MI:SS') as date_order_utc, p.name as partner,
               po.partner_ref, round(po.amount_untaxed::numeric, 2) as untaxed, round(po.amount_total::numeric, 2) as total, po.invoice_status, po.receipt_status
        from purchase_order po join res_partner p on p.id = po.partner_id order by po.name"""),

    ("purchase_lines", ["key"], ["purchase_order_line"],
     """select po.name || '|' || row_number() over (partition by pl.order_id order by pl.sequence, pl.id) as key,
               pp.default_code as product, round(pl.product_qty::numeric, 4) as qty, round(pl.price_unit::numeric, 2) as price,
               round(pl.price_subtotal::numeric, 2) as subtotal, round(pl.qty_received::numeric, 4) as received, round(pl.qty_invoiced::numeric, 4) as invoiced
        from purchase_order_line pl join purchase_order po on po.id = pl.order_id left join product_product pp on pp.id = pl.product_id
        where pl.display_type is null order by po.name, pl.sequence, pl.id"""),

    ("pickings", ["name"], ["stock_picking"],
     """select sp.name, %(tn)s as picking_type, sp.state, p.name as partner, sp.origin,
               to_char(sp.scheduled_date, 'YYYY-MM-DD HH24:MI:SS') as scheduled_utc, to_char(sp.date_done, 'YYYY-MM-DD HH24:MI:SS') as done_utc,
               ls.complete_name as src, ld.complete_name as dest
        from stock_picking sp join stock_picking_type pt on pt.id = sp.picking_type_id
        left join res_partner p on p.id = sp.partner_id left join stock_location ls on ls.id = sp.location_id left join stock_location ld on ld.id = sp.location_dest_id
        order by sp.name""" % {"tn": N("pt.name")}),

    ("stock_moves", ["key"], ["stock_move"],
     """select coalesce(sm.reference, '') || '|' || pp.default_code || '|' ||
               row_number() over (partition by sm.reference, sm.product_id order by sm.id) as key,
               sm.state, to_char(sm.date, 'YYYY-MM-DD HH24:MI:SS') as date_utc, round(sm.product_uom_qty::numeric, 4) as demand, round(sm.quantity::numeric, 4) as qty_done,
               ls.complete_name as src, ld.complete_name as dest, sm.is_inventory, round(coalesce(sm.value, 0)::numeric, 2) as value
        from stock_move sm join product_product pp on pp.id = sm.product_id
        left join stock_location ls on ls.id = sm.location_id left join stock_location ld on ld.id = sm.location_dest_id
        order by 1"""),

    ("stock_quants", ["key"], ["stock_quant"],
     """select pp.default_code || '|' || l.complete_name as key, round(sum(q.quantity)::numeric, 4) as qty
        from stock_quant q join product_product pp on pp.id = q.product_id join stock_location l on l.id = q.location_id
        where l.usage = 'internal' group by 1 having abs(sum(q.quantity)) > 0.00001 order by 1"""),

    ("mrp_productions", ["name"], ["mrp_production"],
     """select mo.name, pp.default_code as product, round(mo.product_qty::numeric, 4) as qty, mo.state,
               to_char(mo.date_start, 'YYYY-MM-DD HH24:MI:SS') as start_utc, mo.origin, sp.name as subcontractor
        from mrp_production mo join product_product pp on pp.id = mo.product_id left join res_partner sp on sp.id = mo.subcontractor_id order by mo.name"""),

    ("scraps", ["name"], ["stock_scrap"],
     """select s.name, pp.default_code as product, round(s.scrap_qty::numeric, 4) as qty, s.state, to_char(s.date_done, 'YYYY-MM-DD HH24:MI:SS') as done_utc,
               l.complete_name as from_loc, ls.complete_name as scrap_loc
        from stock_scrap s join product_product pp on pp.id = s.product_id left join stock_location l on l.id = s.location_id
        left join stock_location ls on ls.id = s.scrap_location_id order by s.name"""),

    # ---- produksi jahit (addon batik_id_production; dilewati bila addon tidak terpasang)
    ("prod_batches", ["name"], ["btk_prod_batch"],
     """select b.name, pp.default_code as product, tp.name as tailor, po.name as po, b.state,
               to_char(b.date_po, 'YYYY-MM-DD') as date_po, to_char(b.date_handover, 'YYYY-MM-DD') as handover,
               to_char(b.date_last_receipt, 'YYYY-MM-DD') as last_receipt, b.lead_days, b.late_days,
               round(b.qty_ordered::numeric, 2) as qty_ordered, round(b.qty_received::numeric, 2) as qty_received,
               round(b.qty_checked::numeric, 2) as qty_checked, round(b.qty_rework::numeric, 2) as qty_rework,
               round(b.qty_reject::numeric, 2) as qty_reject, round(b.qty_pass::numeric, 2) as qty_pass,
               round(b.qty_sold::numeric, 2) as qty_sold, round(b.material_cost::numeric, 2) as material_cost,
               round(b.waste_cost::numeric, 2) as waste_cost, round(b.service_cost::numeric, 2) as service_cost,
               round(b.service_deduction::numeric, 2) as service_deduction, round(b.net_cost::numeric, 2) as net_cost,
               round(b.unit_cost::numeric, 2) as unit_cost, round(b.planned_unit_cost::numeric, 2) as planned_unit_cost,
               round(b.revenue::numeric, 2) as revenue, round(b.cogs_batch::numeric, 2) as cogs_batch, round(b.margin::numeric, 2) as margin
        from btk_prod_batch b join product_product pp on pp.id = b.product_id join res_partner tp on tp.id = b.tailor_id
        join purchase_order po on po.id = b.purchase_id order by b.name"""),

    ("prod_batch_materials", ["key"], ["btk_prod_batch_material", "btk_prod_batch"],
     """select b.name || '|' || pp.default_code as key, round(m.qty_per_unit::numeric, 4) as qty_per_unit,
               round(m.qty_std::numeric, 2) as qty_std, round(m.qty_sent::numeric, 2) as qty_sent,
               round(m.qty_consumed::numeric, 2) as qty_consumed, round(m.qty_waste::numeric, 2) as qty_waste,
               round(m.qty_balance::numeric, 2) as qty_balance, round(m.cost_consumed::numeric, 2) as cost_consumed,
               round(m.cost_waste::numeric, 2) as cost_waste
        from btk_prod_batch_material m join btk_prod_batch b on b.id = m.batch_id join product_product pp on pp.id = m.product_id order by 1"""),

    ("qc_inspections", ["name"], ["btk_qc_inspection"],
     """select q.name, b.name as batch, sp.name as picking, to_char(q.date, 'YYYY-MM-DD HH24:MI:SS') as date_utc,
               round(q.qty_received::numeric, 2) as qty_received, round(q.qty_checked::numeric, 2) as qty_checked,
               round(q.qty_reject::numeric, 2) as qty_reject, round(q.qty_rework::numeric, 2) as qty_rework,
               round(q.qty_pass::numeric, 2) as qty_pass, q.result, q.state
        from btk_qc_inspection q join btk_prod_batch b on b.id = q.batch_id left join stock_picking sp on sp.id = q.picking_id order by q.name"""),

    ("qc_findings", ["key"], ["btk_qc_inspection_line", "btk_qc_inspection"],
     """select q.name || '|' || d.code || '|' || l.disposition as key, round(sum(l.qty)::numeric, 2) as qty
        from btk_qc_inspection_line l join btk_qc_inspection q on q.id = l.inspection_id join btk_qc_defect d on d.id = l.defect_id
        group by 1 order by 1"""),

    ("payments", ["key"], ["account_payment"],
     """select ap.name || '#' || row_number() over (partition by ap.name order by ap.id) as key,
               ap.date, round(ap.amount::numeric, 2) as amount, ap.payment_type, ap.partner_type, p.name as partner, j.code as journal,
               ap.state, ap.memo, ap.is_reconciled
        from account_payment ap join account_journal j on j.id = ap.journal_id left join res_partner p on p.id = ap.partner_id order by 1"""),

    ("bank_statement_lines", ["key"], ["account_bank_statement_line"],
     """select j.code || '|' || m.date || '|' || coalesce(bl.payment_ref, '') || '|' ||
               row_number() over (partition by j.code, m.date, bl.payment_ref order by bl.id) as key,
               round(bl.amount::numeric, 2) as amount, bl.is_reconciled, p.name as partner
        from account_bank_statement_line bl join account_move m on m.id = bl.move_id
        join account_journal j on j.id = bl.journal_id left join res_partner p on p.id = bl.partner_id order by 1"""),

    ("assets", ["name"], ["account_asset"],
     """select a.name, a.state, a.date_start, round(a.purchase_value::numeric, 2) as purchase_value, round(a.salvage_value::numeric, 2) as salvage,
               round(a.value_depreciated::numeric, 2) as depreciated, round(a.value_residual::numeric, 2) as residual, a.method_number, pr.name as profile
        from account_asset a left join account_asset_profile pr on pr.id = a.profile_id order by a.name"""),

    ("asset_lines", ["key"], ["account_asset_line"],
     """select a.name || '|' || l.line_date || '|' || l.type || '|' ||
               row_number() over (partition by l.asset_id, l.line_date, l.type order by l.id) as key,
               round(l.amount::numeric, 2) as amount, m.name as move, l.move_check, l.init_entry
        from account_asset_line l join account_asset a on a.id = l.asset_id left join account_move m on m.id = l.move_id order by 1"""),

    ("employees", ["name"], ["btk_employee"],
     """select e.name, e.nik, e.ptkp, e.ter_category, e.join_date, round(e.basic_salary::numeric, 2) as basic,
               round(e.allowance::numeric, 2) as allowance, e.active, %(an)s as cost_center
        from btk_employee e left join account_analytic_account aa on aa.id = e.analytic_account_id order by e.name""" % {"an": N("aa.name")}),

    ("payroll_runs", ["name"], ["btk_payroll_run"],
     """select r.name, r.state, r.date, m.name as move from btk_payroll_run r left join account_move m on m.id = r.move_id order by r.name"""),

    ("payroll_lines", ["key"], ["btk_payroll_line"],
     """select r.name || '|' || e.name as key, round(l.gross_salary::numeric, 2) as gross, round(l.bpjs_employee::numeric, 2) as bpjs_ee,
               round(l.bpjs_employer::numeric, 2) as bpjs_er, round(l.pph21::numeric, 2) as pph21, round(l.net_pay::numeric, 2) as net
        from btk_payroll_line l join btk_payroll_run r on r.id = l.run_id join btk_employee e on e.id = l.employee_id order by 1"""),

    ("budget_items", ["key"], ["mis_budget_item"],
     """select b.name || '|' || k.name || '|' || i.date_from as key, round(i.amount::numeric, 2) as amount
        from mis_budget_item i join mis_budget b on b.id = i.budget_id
        join mis_report_kpi_expression e on e.id = i.kpi_expression_id join mis_report_kpi k on k.id = e.kpi_id order by 1"""),

    ("mis_report_kpis", ["key"], ["mis_report_kpi"],
     """select %(rn)s || '|' || k.name as key, k.description
        from mis_report_kpi k join mis_report r on r.id = k.report_id order by 1""" % {"rn": N("r.name")}),

    ("users", ["login"], ["res_users"],
     """select u.login, p.name, u.active,
               (select string_agg(g.module || '.' || g.name, ';' order by g.module, g.name)
                  from res_groups_users_rel rel join ir_model_data g on g.model = 'res.groups' and g.res_id = rel.gid
                  where rel.uid = u.id) as groups
        from res_users u join res_partner p on p.id = u.partner_id order by u.login"""),

    ("auditlog_rules", ["name"], ["auditlog_rule"],
     """select r.name, r.state, r.log_read, r.log_write, r.log_create, r.log_unlink from auditlog_rule r order by r.name"""),

    ("auditlog_summary", ["key"], ["auditlog_log"],
     """select model_model || '|' || method as key, count(*) as n from auditlog_log group by 1 order by 1"""),

    ("init_marks", ["key"], ["ir_config_parameter"],
     """select key from ir_config_parameter where key like 'batik.%' and key not like 'batik.reset%' order by key"""),

    ("config_env", ["key"], ["ir_config_parameter"],
     """select key, value from ir_config_parameter where key in ('web.base.url', 'web.base.url.freeze') order by key"""),

    ("sequences", ["key"], ["ir_sequence"],
     """select code || '|' || coalesce(prefix, '') as key, number_next, padding from ir_sequence where code like 'account%%' or code like 'sale%%' or code like 'purchase%%' order by 1""".replace("%%", "%")),
]


# ---------------------------------------------------------------- dataset berbasis ORM
def ds_products(env, asof):
    P = env["product.product"].with_context(active_test=False)
    env.cr.execute("select res_id, checksum, store_fname from ir_attachment where res_model = 'product.template' and res_field = 'image_1920' and store_fname is not null")
    img = {r[0]: (r[1], r[2]) for r in env.cr.fetchall()}
    header = ["key", "name", "categ", "cost_method", "type", "storable", "list_price", "standard_price", "uom", "barcode", "sale_ok", "purchase_ok",
              "active", "image_checksum", "image_file_exists"]
    rows = []
    for p in P.search([], order="default_code, id"):
        t = p.product_tmpl_id
        chk, fn = img.get(t.id, ("", ""))
        exists = ""
        if fn:
            exists = os.path.exists(env["ir.attachment"]._full_path(fn))
        rows.append([p.default_code or ("(tanpa kode)|%s" % p.name), p.name, p.categ_id.complete_name,
                     p.categ_id.property_cost_method or "", p.type, p.is_storable, round(p.list_price, 2), round(p.standard_price, 2), p.uom_id.name,
                     p.barcode or "", p.sale_ok, p.purchase_ok, p.active, chk, exists])
    return header, rows


def ds_valuation(env, asof):
    P = env["product.product"].search([("is_storable", "=", True)], order="default_code")
    header = ["key", "qty_on_hand", "avg_cost", "total_value"]
    rows = [[p.default_code, round(p.qty_available, 4), round(p.standard_price, 2), round(p.total_value, 2)] for p in P]
    return header, rows


def ds_boms(env, asof):
    header = ["key", "type", "product_qty", "subcontractors"]
    rows = []
    for b in env["mrp.bom"].search([], order="id"):
        subs = ",".join(sorted(b.subcontractor_ids.mapped("name"))) if "subcontractor_ids" in b._fields else ""
        for ln in b.bom_line_ids:
            rows.append(["%s|%s" % (b.product_tmpl_id.default_code or b.product_tmpl_id.name, ln.product_id.default_code or ln.product_id.name),
                         b.type, round(ln.product_qty, 4), subs])
    rows.sort(key=lambda r: r[0])
    return header, rows


def ds_filestore(env, asof):
    """Integritas filestore: berapa lampiran bertipe berkas yang tidak ada di disk (selain aset web yang dibangun ulang otomatis)."""
    env.cr.execute("select id, store_fname, res_model from ir_attachment where store_fname is not null and url is null")
    tot = miss = 0
    by = {}
    for aid, fn, rm in env.cr.fetchall():
        tot += 1
        if not os.path.exists(env["ir.attachment"]._full_path(fn)):
            miss += 1
            by[rm] = by.get(rm, 0) + 1
    rows = [["total_files", tot], ["missing_files", miss]] + [["missing:%s" % k, v] for k, v in sorted(by.items())]
    return ["key", "value"], rows


def ds_kpi(env, asof):
    """Angka kontrol ringkas (yang biasanya ditanyakan saat demo). Dihitung dari SQL agar tidak bergantung ORM."""
    cr = env.cr
    out = []

    def one(key, sql, params=None):
        cr.execute(sql, params)
        out.append([key, fmt(cr.fetchone()[0])])

    def many(prefix, sql, params=None):
        cr.execute(sql, params)
        for k, v in cr.fetchall():
            out.append(["%s|%s" % (prefix, k), fmt(v)])

    one("jurnal_debit_total", "select round(coalesce(sum(debit),0)::numeric,2) from account_move_line where parent_state='posted'")
    one("jurnal_credit_total", "select round(coalesce(sum(credit),0)::numeric,2) from account_move_line where parent_state='posted'")
    many("dokumen_akunting", "select move_type || '/' || state, count(*) from account_move group by 1 order by 1")
    many("omzet_dpp_per_bulan", "select to_char((date_order at time zone 'UTC') at time zone 'Asia/Makassar','YYYY-MM'), round(sum(amount_untaxed)::numeric,2) from sale_order where state='sale' group by 1 order by 1")
    many("omzet_dpp_per_bulan_channel",
         "select to_char((so.date_order at time zone 'UTC') at time zone 'Asia/Makassar','YYYY-MM') || '|' || (tm.name->>'en_US'), round(sum(so.amount_untaxed)::numeric,2) "
         "from sale_order so left join crm_team tm on tm.id=so.team_id where so.state='sale' group by 1 order by 1")
    many("jumlah_order_per_bulan", "select to_char((date_order at time zone 'UTC') at time zone 'Asia/Makassar','YYYY-MM'), count(*) from sale_order where state='sale' group by 1 order by 1")
    many("laba_rugi_per_bulan",
         "select to_char(l.date,'YYYY-MM') || '|' || "
         "case when a.account_type like 'income%' then '1.pendapatan' when a.account_type='expense_direct_cost' then '2.hpp' "
         "when a.account_type='expense_depreciation' then '4.penyusutan' else '3.biaya_operasional' end, round(sum(-l.balance)::numeric,2) "
         "from account_move_line l join account_account a on a.id=l.account_id where l.parent_state='posted' and (a.account_type like 'income%' or a.account_type like 'expense%') group by 1 order by 1")
    many("neraca_per_tipe_akun",
         "select a.account_type, round(sum(l.balance)::numeric,2) from account_move_line l join account_account a on a.id=l.account_id "
         "where l.parent_state='posted' and a.account_type not like 'income%' and a.account_type not like 'expense%' group by 1 order by 1")
    one("laba_rugi_kumulatif",
        "select round(sum(-l.balance)::numeric,2) from account_move_line l join account_account a on a.id=l.account_id "
        "where l.parent_state='posted' and (a.account_type like 'income%' or a.account_type like 'expense%')")
    one("kas_bank_total", "select round(coalesce(sum(l.balance),0)::numeric,2) from account_move_line l join account_account a on a.id=l.account_id where l.parent_state='posted' and a.account_type='asset_cash'")
    one("piutang_usaha_total", "select round(coalesce(sum(l.amount_residual),0)::numeric,2) from account_move_line l join account_account a on a.id=l.account_id where l.parent_state='posted' and not l.reconciled and a.account_type='asset_receivable'")
    one("hutang_usaha_total", "select round(coalesce(sum(l.amount_residual),0)::numeric,2) from account_move_line l join account_account a on a.id=l.account_id where l.parent_state='posted' and not l.reconciled and a.account_type='liability_payable'")
    one("persediaan_gl_1130101",
        "select round(coalesce(sum(l.balance),0)::numeric,2) from account_move_line l join account_account a on a.id=l.account_id where l.parent_state='posted' and (select v from jsonb_each_text(a.code_store) t(k,v) order by k limit 1)='1130101'")
    one("qty_stok_internal_total", "select round(coalesce(sum(q.quantity),0)::numeric,2) from stock_quant q join stock_location l on l.id=q.location_id where l.usage='internal'")
    many("stok_negatif_per_lokasi", "select l.complete_name, count(*) from stock_quant q join stock_location l on l.id=q.location_id where l.usage='internal' and q.quantity<0 group by 1 order by 1")
    many("jumlah_dokumen", "select 'sale_order/' || state, count(*) from sale_order group by 1 union all select 'purchase_order/' || state, count(*) from purchase_order group by 1 "
         "union all select 'picking/' || state, count(*) from stock_picking group by 1 union all select 'mo/' || state, count(*) from mrp_production group by 1 order by 1")
    return ["key", "value"], out


PY_DATASETS = [
    ("products", ["key"], ds_products, False),
    ("valuation", ["key"], ds_valuation, False),
    ("boms", ["key"], ds_boms, False),
    ("filestore_integrity", ["key"], ds_filestore, False),
    ("kpi", ["key"], ds_kpi, False),
]


def _count_tables(env, volatile):
    cr = env.cr
    cr.execute("select model from ir_model where transient")
    transient = {m.replace(".", "_") for (m,) in cr.fetchall()}
    cr.execute("select tablename from pg_tables where schemaname = 'public' order by 1")
    rows = []
    for (t,) in cr.fetchall():
        is_vol = t.startswith(VOLATILE_PREFIX) or t in transient
        if is_vol != volatile:
            continue
        cr.execute('select count(*) from "%s"' % t)
        rows.append([t, cr.fetchone()[0]])
    return ["key", "rows"], rows


def collect(env, asof=None):
    """Hasilkan (daftar dataset, manifest). Dataset = dict(name, key, header, rows, volatile)."""
    asof = asof or ASOF_DEFAULT
    cr = env.cr
    datasets, errors = [], {}

    def run(name, key, volatile, fn):
        try:
            with cr.savepoint():
                header, rows = fn()
            datasets.append({"name": name, "key": key, "header": header, "rows": rows, "volatile": volatile})
        except Exception as exc:  # noqa: BLE001 - satu dataset gagal tidak boleh menghentikan yang lain
            errors[name] = "%s: %s" % (type(exc).__name__, str(exc).strip().splitlines()[0][:300] if str(exc).strip() else "")

    for name, key, tables, sql in SQL_DATASETS:
        if not all(_table_exists(cr, t) for t in tables):
            errors[name] = "dilewati: tabel %s tidak ada" % ",".join(t for t in tables if not _table_exists(cr, t))
            continue

        def fn(sql=sql):
            cr.execute(sql, {"asof": asof}) if "%(asof)s" in sql else cr.execute(sql)
            return [d.name for d in cr.description], [list(r) for r in cr.fetchall()]
        volatile = name in ("config_env",)
        run(name, key, volatile, fn)
    for name, key, fn, volatile in PY_DATASETS:
        run(name, key, volatile, lambda fn=fn: fn(env, asof))
    run("table_counts", ["key"], False, lambda: _count_tables(env, False))
    run("table_counts_volatile", ["key"], True, lambda: _count_tables(env, True))
    cr.execute("select current_database()")
    manifest = {
        "snapshot_version": SNAPSHOT_VERSION,
        "database": cr.fetchone()[0],
        "odoo_version": release.version,
        "generated_utc": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "asof": asof,
        "errors": errors,
    }
    return datasets, manifest


def write_dir(env, outdir, label="", asof=None):
    os.makedirs(outdir, exist_ok=True)
    datasets, manifest = collect(env, asof)
    manifest["label"] = label
    manifest["datasets"] = {}
    for d in datasets:
        path = os.path.join(outdir, d["name"] + ".csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(d["header"])
            for r in d["rows"]:
                w.writerow([fmt(v) for v in r])
        manifest["datasets"][d["name"]] = {"key": d["key"], "rows": len(d["rows"]), "volatile": d["volatile"], "header": d["header"]}
    with open(os.path.join(outdir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False, sort_keys=True)
    return manifest


def build_zip(env, label="", asof=None):
    datasets, manifest = collect(env, asof)
    manifest["label"] = label
    manifest["datasets"] = {}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for d in datasets:
            s = io.StringIO()
            w = csv.writer(s, lineterminator="\n")
            w.writerow(d["header"])
            for r in d["rows"]:
                w.writerow([fmt(v) for v in r])
            z.writestr(d["name"] + ".csv", s.getvalue())
            manifest["datasets"][d["name"]] = {"key": d["key"], "rows": len(d["rows"]), "volatile": d["volatile"], "header": d["header"]}
        z.writestr("manifest.json", json.dumps(manifest, indent=1, ensure_ascii=False, sort_keys=True))
    return buf.getvalue()
