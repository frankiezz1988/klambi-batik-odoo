from odoo import api, fields, models

from .params import PTKP_CHOICES, TER_CATEGORY


class BtkEmployee(models.Model):
    _name = "btk.employee"
    _description = "Karyawan (payroll ringan)"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)
    nik = fields.Char(string="NIK", size=16)
    npwp = fields.Char(string="NPWP", size=16)
    ptkp = fields.Selection(PTKP_CHOICES, string="Status PTKP", required=True, default="TK0")
    ter_category = fields.Selection([("A", "A"), ("B", "B"), ("C", "C")], compute="_compute_ter", store=True)
    basic_salary = fields.Float(string="Gaji pokok", required=True)
    allowance = fields.Float(string="Tunjangan tetap")
    join_date = fields.Date()

    @api.depends("ptkp")
    def _compute_ter(self):
        for e in self:
            e.ter_category = TER_CATEGORY.get(e.ptkp, "A")
