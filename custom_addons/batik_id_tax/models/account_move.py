from odoo import api, fields, models
from odoo.exceptions import ValidationError

# PMK 131/2024: BKP/JKP non-mewah -> PPN = 12% x DPP nilai lain (11/12 x harga jual) = efektif 11%.
DPP_LAIN_NUM, DPP_LAIN_DEN = 11, 12


class AccountMove(models.Model):
    _inherit = "account.move"

    btk_nsfp = fields.Char(
        string="NSFP / Nomor Faktur",
        help="Untuk invoice pelanggan = nomor faktur pajak keluaran (di Coretax diterbitkan sistem saat faktur "
             "ditandatangani; isi via 'Impor NSFP'). Untuk vendor bill = nomor faktur pajak masukan dari penjual.",
        copy=False, index=True, tracking=True,
    )
    btk_kode_transaksi = fields.Selection(
        [
            ("01", "01 - Penyerahan BKP/JKP umum (DPP = harga jual)"),
            ("04", "04 - DPP Nilai Lain (11/12 x harga jual)"),
            ("07", "07 - Penyerahan dengan fasilitas PPN"),
            ("08", "08 - Penyerahan dibebaskan PPN"),
        ],
        string="Kode Transaksi", default="04", tracking=True,
    )
    btk_channel_ref = fields.Char(
        string="No. Order Channel",
        help="Nomor pesanan marketplace / live / toko (untuk rekonsiliasi settlement).",
        copy=False, index=True,
    )
    btk_efaktur_exported = fields.Boolean(string="Sudah diekspor ke Coretax", copy=False)
    btk_ppn_rate = fields.Float(string="Tarif PPN Faktur (%)", default=12.0,
                                help="Tarif pada faktur. Beban efektif non-mewah = 12% x 11/12 = 11%.")
    btk_dpp_nilai_lain = fields.Monetary(string="DPP Nilai Lain", compute="_compute_btk_dpp",
                                         currency_field="currency_id")
    btk_ppn_faktur = fields.Monetary(string="PPN menurut faktur", compute="_compute_btk_dpp",
                                     currency_field="currency_id")
    btk_ppn_selisih = fields.Monetary(string="Selisih vs PPN pembukuan", compute="_compute_btk_dpp",
                                      currency_field="currency_id",
                                      help="PPN pembukuan (pajak efektif 11%) dikurangi PPN faktur. Selisih kecil = pembulatan.")
    btk_buyer_tin = fields.Char(string="NPWP/NIK Pembeli", compute="_compute_btk_buyer_tin")

    @api.depends("amount_untaxed", "amount_tax", "btk_kode_transaksi", "btk_ppn_rate", "currency_id")
    def _compute_btk_dpp(self):
        for move in self:
            base = move.amount_untaxed
            dpp = base * DPP_LAIN_NUM / DPP_LAIN_DEN if move.btk_kode_transaksi == "04" else base
            rnd = move.currency_id.round if move.currency_id else (lambda x: x)
            dpp = rnd(dpp)
            ppn = rnd(dpp * move.btk_ppn_rate / 100.0)
            move.btk_dpp_nilai_lain = dpp
            move.btk_ppn_faktur = ppn
            move.btk_ppn_selisih = move.amount_tax - ppn

    @api.depends("partner_id.btk_tin")
    def _compute_btk_buyer_tin(self):
        for move in self:
            move.btk_buyer_tin = move.partner_id.btk_tin or "0000000000000000"

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
                raise ValidationError(self.env._("NSFP %s sudah dipakai oleh dokumen lain.", move.btk_nsfp))
