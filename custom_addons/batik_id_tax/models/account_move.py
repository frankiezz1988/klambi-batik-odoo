from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = "account.move"

    btk_nsfp = fields.Char(
        string="NSFP",
        help="Nomor Seri Faktur Pajak. Untuk invoice pelanggan = faktur keluaran; "
             "untuk vendor bill = nomor faktur pajak masukan dari penjual.",
        copy=False,
        index=True,
        tracking=True,
    )
    btk_kode_transaksi = fields.Selection(
        [
            ("01", "01 - Penyerahan BKP/JKP umum (DPP = harga jual)"),
            ("04", "04 - DPP Nilai Lain (11/12 x harga jual)"),
            ("07", "07 - Penyerahan dengan fasilitas PPN"),
            ("08", "08 - Penyerahan dibebaskan PPN"),
        ],
        string="Kode Transaksi",
        default="04",
        tracking=True,
    )
    btk_channel_ref = fields.Char(
        string="No. Order Channel",
        help="Nomor pesanan marketplace / live / toko (untuk rekonsiliasi settlement).",
        copy=False,
        index=True,
    )
    btk_efaktur_exported = fields.Boolean(string="Sudah di-export ke Coretax", copy=False)

    @api.constrains("btk_nsfp", "company_id", "move_type")
    def _check_btk_nsfp_unique(self):
        for move in self.filtered(lambda m: m.btk_nsfp and m.move_type in ("out_invoice", "out_refund")):
            dup = self.search_count([
                ("id", "!=", move.id),
                ("company_id", "=", move.company_id.id),
                ("btk_nsfp", "=", move.btk_nsfp),
                ("move_type", "in", ("out_invoice", "out_refund")),
            ])
            if dup:
                raise ValidationError(
                    self.env._("NSFP %s sudah dipakai oleh dokumen lain.", move.btk_nsfp)
                )
