from odoo import fields, models


class TerRate(models.Model):
    _name = "btk.ter.rate"
    _description = "Tarif Efektif Rata-rata PPh 21 (TER) bulanan"
    _order = "category, upper_bound"

    category = fields.Selection([("A", "TER A"), ("B", "TER B"), ("C", "TER C")], required=True, index=True)
    upper_bound = fields.Float(string="Penghasilan bruto s.d. (Rp/bulan)", required=True)
    rate = fields.Float(string="Tarif (%)", required=True)

    def rate_for(self, category, gross):
        rec = self.search([("category", "=", category), ("upper_bound", ">=", gross)], order="upper_bound", limit=1)
        return rec.rate if rec else 0.0
