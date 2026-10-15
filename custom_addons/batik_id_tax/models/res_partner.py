import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    btk_npwp = fields.Char(string="NPWP (15/16 digit)", size=16, help="Hanya angka, tanpa titik/strip.")
    btk_nik = fields.Char(string="NIK (16 digit)", size=16)
    btk_is_pkp = fields.Boolean(string="PKP")
    btk_tku_id = fields.Char(string="ID TKU", compute="_compute_btk_tin",
                             help="NPWP 16 digit + 6 digit kode TKU (000000 = pusat).")
    btk_tin = fields.Char(string="TIN (NPWP/NIK)", compute="_compute_btk_tin")

    @api.depends("btk_npwp", "btk_nik")
    def _compute_btk_tin(self):
        for p in self:
            npwp = (p.btk_npwp or "").strip()
            p.btk_tin = npwp or (p.btk_nik or "").strip() or False
            p.btk_tku_id = (npwp.zfill(16) + "000000") if npwp else False

    @api.constrains("btk_npwp", "btk_nik")
    def _check_btk_ids(self):
        for p in self:
            if p.btk_npwp and not re.fullmatch(r"\d{15,16}", p.btk_npwp):
                raise ValidationError(self.env._("NPWP harus 15 atau 16 digit angka."))
            if p.btk_nik and not re.fullmatch(r"\d{16}", p.btk_nik):
                raise ValidationError(self.env._("NIK harus 16 digit angka."))
