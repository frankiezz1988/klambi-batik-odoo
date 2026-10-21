from odoo import api, fields, models
from odoo.exceptions import UserError

from .params import BPJS, JP_WAGE_CAP, KES_WAGE_CAP


class PayrollRun(models.Model):
    _name = "btk.payroll.run"
    _description = "Proses Gaji Bulanan"
    _order = "date desc, id desc"

    name = fields.Char(compute="_compute_name", store=True)
    date = fields.Date(string="Tanggal bayar / jurnal", required=True, default=fields.Date.today)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    state = fields.Selection([("draft", "Draft"), ("computed", "Terhitung"), ("posted", "Terposting")],
                             default="draft")
    line_ids = fields.One2many("btk.payroll.line", "run_id")
    move_id = fields.Many2one("account.move", readonly=True, copy=False)
    journal_id = fields.Many2one("account.journal", domain="[('type', '=', 'general')]", required=True,
                                 default=lambda s: s._cfg_id("journal"))
    salary_account_id = fields.Many2one("account.account", required=True, default=lambda s: s._cfg_id("salary"))
    bpjs_expense_account_id = fields.Many2one("account.account", required=True, default=lambda s: s._cfg_id("bpjs_exp"))
    bpjs_payable_account_id = fields.Many2one("account.account", required=True, default=lambda s: s._cfg_id("bpjs_payable"))
    pph21_account_id = fields.Many2one("account.account", required=True, default=lambda s: s._cfg_id("pph21"))
    bank_account_id = fields.Many2one("account.account", required=True, default=lambda s: s._cfg_id("bank"))
    total_gross = fields.Float(compute="_compute_totals")
    total_pph21 = fields.Float(compute="_compute_totals")
    total_bpjs = fields.Float(compute="_compute_totals")
    total_net = fields.Float(compute="_compute_totals")
    warning = fields.Char(compute="_compute_totals")

    @api.model
    def _cfg_id(self, key):
        val = self.env["ir.config_parameter"].sudo().get_param(f"batik.payroll.{key}")
        return int(val) if val and val.isdigit() else False

    @api.depends("date")
    def _compute_name(self):
        for r in self:
            r.name = f"Gaji {r.date:%m/%Y}" if r.date else "Gaji"

    @api.depends("line_ids", "date")
    def _compute_totals(self):
        for r in self:
            r.total_gross = sum(r.line_ids.mapped("gross_salary"))
            r.total_pph21 = sum(r.line_ids.mapped("pph21"))
            r.total_bpjs = sum(r.line_ids.mapped("bpjs_employee")) + sum(r.line_ids.mapped("bpjs_employer"))
            r.total_net = sum(r.line_ids.mapped("net_pay"))
            r.warning = ("Desember: PPh 21 memerlukan rekonsiliasi tahunan (Pasal 17) yang BELUM diimplementasikan; "
                         "nilai TER bulan ini bersifat sementara.") if r.date and r.date.month == 12 else False

    def action_compute(self):
        for run in self:
            if run.state == "posted":
                raise UserError(self.env._("Proses gaji sudah diposting."))
            run.line_ids.unlink()
            vals = [{"run_id": run.id, "employee_id": e.id}
                    for e in self.env["btk.employee"].search([("company_id", "=", run.company_id.id)])
                    if not e.join_date or e.join_date <= run.date]
            self.env["btk.payroll.line"].create(vals)
            run.state = "computed"

    def action_post(self):
        for run in self:
            if run.state != "computed" or not run.line_ids:
                raise UserError(self.env._("Hitung gaji terlebih dahulu."))
            gross = round(sum(run.line_ids.mapped("gross_salary")))
            er = round(sum(run.line_ids.mapped("bpjs_employer")))
            ee = round(sum(run.line_ids.mapped("bpjs_employee")))
            pph = round(sum(run.line_ids.mapped("pph21")))
            net = gross - ee - pph
            name = run.name
            # beban gaji & BPJS dialokasikan per cost center karyawan (analytic)
            by_cc = {}
            for ln in run.line_ids:
                cc = ln.employee_id.analytic_account_id.id or False
                d = by_cc.setdefault(cc, [0.0, 0.0])
                d[0] += ln.gross_salary
                d[1] += ln.bpjs_employer
            lines = []
            for cc, (g, b) in by_cc.items():
                dist = {"analytic_distribution": {str(cc): 100}} if cc else {}
                lines.append((0, 0, {"account_id": run.salary_account_id.id, "name": name, "debit": round(g), "credit": 0, **dist}))
                lines.append((0, 0, {"account_id": run.bpjs_expense_account_id.id, "name": f"{name} - BPJS pemberi kerja", "debit": round(b), "credit": 0, **dist}))
            gross = sum(l[2]["debit"] for l in lines[0::2])
            er = sum(l[2]["debit"] for l in lines[1::2])
            net = gross - ee - pph
            lines += [
                (0, 0, {"account_id": run.pph21_account_id.id, "name": f"{name} - PPh 21", "debit": 0, "credit": pph}),
                (0, 0, {"account_id": run.bpjs_payable_account_id.id, "name": f"{name} - utang BPJS", "debit": 0, "credit": ee + er}),
                (0, 0, {"account_id": run.bank_account_id.id, "name": f"{name} - gaji bersih", "debit": 0, "credit": net}),
            ]
            move = self.env["account.move"].create({
                "move_type": "entry", "journal_id": run.journal_id.id, "date": run.date, "ref": name,
                "line_ids": [ln for ln in lines if ln[2]["debit"] or ln[2]["credit"]],
            })
            move.action_post()
            run.write({"move_id": move.id, "state": "posted"})

    def action_draft(self):
        for run in self:
            if run.move_id:
                run.move_id.button_draft()
                run.move_id.unlink()
            run.state = "draft"


class PayrollLine(models.Model):
    _name = "btk.payroll.line"
    _description = "Baris Gaji"

    run_id = fields.Many2one("btk.payroll.run", required=True, ondelete="cascade", index=True)
    employee_id = fields.Many2one("btk.employee", required=True)
    ter_category = fields.Selection(related="employee_id.ter_category")
    basic = fields.Float(compute="_compute_all", store=True)
    allowance = fields.Float(compute="_compute_all", store=True)
    gross_salary = fields.Float(string="Gaji bruto (tunai)", compute="_compute_all", store=True)
    bpjs_ee_jht = fields.Float(compute="_compute_all", store=True)
    bpjs_ee_jp = fields.Float(compute="_compute_all", store=True)
    bpjs_ee_kes = fields.Float(compute="_compute_all", store=True)
    bpjs_er_jht = fields.Float(compute="_compute_all", store=True)
    bpjs_er_jp = fields.Float(compute="_compute_all", store=True)
    bpjs_er_jkk = fields.Float(compute="_compute_all", store=True)
    bpjs_er_jkm = fields.Float(compute="_compute_all", store=True)
    bpjs_er_kes = fields.Float(compute="_compute_all", store=True)
    bpjs_employee = fields.Float(compute="_compute_all", store=True)
    bpjs_employer = fields.Float(compute="_compute_all", store=True)
    taxable_gross = fields.Float(string="Penghasilan bruto (dasar TER)", compute="_compute_all", store=True,
                                 help="Gaji + premi JKK/JKM/Kesehatan yang dibayar pemberi kerja (PMK 168/2023).")
    ter_rate = fields.Float(string="Tarif TER (%)", compute="_compute_all", store=True)
    pph21 = fields.Float(string="PPh 21", compute="_compute_all", store=True)
    net_pay = fields.Float(string="Gaji bersih", compute="_compute_all", store=True)

    @api.depends("employee_id", "employee_id.basic_salary", "employee_id.allowance", "employee_id.ter_category")
    def _compute_all(self):
        ter = self.env["btk.ter.rate"]
        for ln in self:
            e = ln.employee_id
            gross = e.basic_salary + e.allowance
            jp_base, kes_base = min(gross, JP_WAGE_CAP), min(gross, KES_WAGE_CAP)
            vals = {
                "basic": e.basic_salary, "allowance": e.allowance, "gross_salary": gross,
                "bpjs_ee_jht": round(gross * BPJS["jht_ee"] / 100), "bpjs_ee_jp": round(jp_base * BPJS["jp_ee"] / 100),
                "bpjs_ee_kes": round(kes_base * BPJS["kes_ee"] / 100),
                "bpjs_er_jht": round(gross * BPJS["jht_er"] / 100), "bpjs_er_jp": round(jp_base * BPJS["jp_er"] / 100),
                "bpjs_er_jkk": round(gross * BPJS["jkk_er"] / 100), "bpjs_er_jkm": round(gross * BPJS["jkm_er"] / 100),
                "bpjs_er_kes": round(kes_base * BPJS["kes_er"] / 100),
            }
            vals["bpjs_employee"] = vals["bpjs_ee_jht"] + vals["bpjs_ee_jp"] + vals["bpjs_ee_kes"]
            vals["bpjs_employer"] = (vals["bpjs_er_jht"] + vals["bpjs_er_jp"] + vals["bpjs_er_jkk"]
                                     + vals["bpjs_er_jkm"] + vals["bpjs_er_kes"])
            # Dasar TER: gaji + premi yang ditanggung pemberi kerja untuk JKK, JKM, Kesehatan
            taxable = gross + vals["bpjs_er_jkk"] + vals["bpjs_er_jkm"] + vals["bpjs_er_kes"]
            rate = ter.rate_for(e.ter_category or "A", taxable)
            vals.update({"taxable_gross": taxable, "ter_rate": rate, "pph21": round(taxable * rate / 100)})
            vals["net_pay"] = gross - vals["bpjs_employee"] - vals["pph21"]
            ln.update(vals)
