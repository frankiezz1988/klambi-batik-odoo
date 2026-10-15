from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    btk_goods_code = fields.Char(
        string="Kode Barang/Jasa Coretax", size=6,
        help="Kode 6 digit dari referensi (REF) template DJP. Wajib untuk ekspor Coretax.",
    )
    btk_unit_code = fields.Char(
        string="Kode Satuan Coretax", help="Contoh format: UM.0021. Cek daftar UM.xxxx pada REF template DJP.",
    )
