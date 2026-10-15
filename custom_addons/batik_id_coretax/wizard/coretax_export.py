"""Ekspor Faktur Pajak Keluaran.

PENTING: skema XML resmi DJP tidak dipublikasikan sebagai XSD yang bisa diverifikasi saat modul ini ditulis.
- CSV 'Faktur' + 'DetailFaktur' mengikuti KONSEP kolom template Excel DJP (aturan: DPP = qty x harga - diskon,
  DPP nilai lain = 11/12 x DPP, PPN = tarif x DPP nilai lain). Pindahkan ke template resmi (cek sheet REF).
- XML bersifat EKSPERIMENTAL: nama elemen dikumpulkan dari sumber sekunder. Bandingkan dengan keluaran converter
  resmi DJP sebelum dipakai; ubah pemetaan pada XML_TAGS bila berbeda.
- NSFP tidak dikirim: diterbitkan Coretax saat faktur ditandatangani (gunakan wizard Impor NSFP).
"""
import base64
import csv
import io
import xml.etree.ElementTree as ET

from odoo import api, fields, models

FAKTUR_HEADER = [
    "Baris", "Tanggal Faktur", "Jenis Faktur", "Kode Transaksi", "Keterangan Tambahan", "Dokumen Pendukung",
    "Referensi", "Cap Fasilitas", "ID TKU Penjual", "NPWP/NIK Pembeli", "Jenis ID Pembeli", "Negara Pembeli",
    "Nomor Dokumen Pembeli", "Nama Pembeli", "Alamat Pembeli", "Email Pembeli", "ID TKU Pembeli",
]
DETAIL_HEADER = [
    "Baris", "Barang/Jasa", "Kode Barang Jasa", "Nama Barang/Jasa", "Nama Satuan Ukur", "Harga Satuan",
    "Jumlah Barang Jasa", "Total Diskon", "DPP", "DPP Nilai Lain", "Tarif PPN", "PPN", "Tarif PPnBM", "PPnBM",
]
# Pemetaan nama elemen XML (EKSPERIMENTAL) - satu tempat agar mudah dikoreksi.
XML_TAGS = {
    "root": "TaxInvoiceBulk", "seller_tin": "TIN", "list": "ListOfTaxInvoice", "invoice": "TaxInvoice",
    "date": "TaxInvoiceDate", "opt": "TaxInvoiceOpt", "trx": "TrxCode", "ref": "RefDesc",
    "seller_tku": "SellerIDTKU", "buyer_tin": "BuyerTin", "buyer_doc": "BuyerDocument",
    "buyer_country": "BuyerCountry", "buyer_docnum": "BuyerDocumentNumber", "buyer_name": "BuyerName",
    "buyer_addr": "BuyerAdress", "buyer_email": "BuyerEmail", "buyer_tku": "BuyerIDTKU",
    "goods": "ListOfGoodService", "good": "GoodService", "g_opt": "Opt", "g_code": "Code", "g_name": "Name",
    "g_unit": "Unit", "g_price": "Price", "g_qty": "Qty", "g_disc": "TotalDiscount", "g_base": "TaxBase",
    "g_base_other": "OtherTaxBase", "g_rate": "VATRate", "g_vat": "VAT", "g_stlg_rate": "STLGRate", "g_stlg": "STLG",
}


def _num(x):
    return ("%.2f" % x).rstrip("0").rstrip(".") if x else "0"


class CoretaxExport(models.TransientModel):
    _name = "btk.coretax.export"
    _description = "Ekspor Faktur Keluaran Coretax (staging)"

    date_from = fields.Date(required=True, default=lambda s: fields.Date.today().replace(day=1))
    date_to = fields.Date(required=True, default=fields.Date.today)
    only_pending = fields.Boolean(string="Hanya yang belum diekspor", default=True)
    mark_exported = fields.Boolean(string="Tandai sebagai sudah diekspor", default=False)
    default_unit = fields.Char(string="Kode satuan bawaan", default="UM.0021",
                               help="Dipakai bila produk belum punya kode satuan. VERIFIKASI pada REF template DJP.")
    state = fields.Selection([("draft", "Draft"), ("done", "Selesai")], default="draft")
    invoice_count = fields.Integer(readonly=True)
    warnings = fields.Text(readonly=True)
    faktur_file = fields.Binary(string="Faktur (CSV)", readonly=True, attachment=False)
    faktur_name = fields.Char(readonly=True)
    detail_file = fields.Binary(string="DetailFaktur (CSV)", readonly=True, attachment=False)
    detail_name = fields.Char(readonly=True)
    xml_file = fields.Binary(string="XML (EKSPERIMENTAL)", readonly=True, attachment=False)
    xml_name = fields.Char(readonly=True)

    def _domain(self):
        dom = [("move_type", "=", "out_invoice"), ("state", "=", "posted"),
               ("invoice_date", ">=", self.date_from), ("invoice_date", "<=", self.date_to),
               ("company_id", "=", self.env.company.id)]
        if self.only_pending:
            dom.append(("btk_efaktur_exported", "=", False))
        return dom

    def action_export(self):
        self.ensure_one()
        moves = self.env["account.move"].search(self._domain(), order="invoice_date, id")
        company_partner = self.env.company.partner_id
        seller_tin = (company_partner.btk_npwp or company_partner.vat or "").replace(".", "").replace("-", "")
        seller_tku = (seller_tin.zfill(16) + "000000") if seller_tin else ""
        warnings = []
        if not seller_tin:
            warnings.append("NPWP perusahaan kosong (isi NPWP di partner perusahaan).")

        faktur, detail = io.StringIO(), io.StringIO()
        fw, dw = csv.writer(faktur), csv.writer(detail)
        fw.writerow(FAKTUR_HEADER)
        dw.writerow(DETAIL_HEADER)
        root = ET.Element(XML_TAGS["root"])
        ET.SubElement(root, XML_TAGS["seller_tin"]).text = seller_tin
        inv_list = ET.SubElement(root, XML_TAGS["list"])

        for idx, mv in enumerate(moves, 1):
            buyer = mv.partner_id
            tin = buyer.btk_tin or "0000000000000000"
            doc_type = "TIN" if buyer.btk_npwp else ("National ID" if buyer.btk_nik else "TIN")
            buyer_tku = buyer.btk_tku_id or "000000"
            addr = ", ".join(filter(None, [buyer.street, buyer.city]))
            ref = mv.name
            fw.writerow([idx, mv.invoice_date.isoformat(), "Normal", mv.btk_kode_transaksi or "04", "", "", ref, "",
                         seller_tku, tin, doc_type, "IDN", "", buyer.name or "", addr, buyer.email or "", buyer_tku])
            inv = ET.SubElement(inv_list, XML_TAGS["invoice"])
            for tag, val in (("date", mv.invoice_date.isoformat()), ("opt", "Normal"),
                             ("trx", mv.btk_kode_transaksi or "04"), ("ref", ref), ("seller_tku", seller_tku),
                             ("buyer_tin", tin), ("buyer_doc", doc_type), ("buyer_country", "IDN"),
                             ("buyer_docnum", ""), ("buyer_name", buyer.name or ""), ("buyer_addr", addr),
                             ("buyer_email", buyer.email or ""), ("buyer_tku", buyer_tku)):
                ET.SubElement(inv, XML_TAGS[tag]).text = val
            goods = ET.SubElement(inv, XML_TAGS["goods"])
            for line in mv.invoice_line_ids.filtered(lambda l: l.display_type == "product"):
                tmpl = line.product_id.product_tmpl_id
                code = tmpl.btk_goods_code or ""
                if not code:
                    warnings.append(f"{mv.name}: produk '{line.product_id.display_name}' belum punya Kode Barang/Jasa Coretax.")
                unit = tmpl.btk_unit_code or self.default_unit
                gross = line.price_unit * line.quantity
                disc = gross - line.price_subtotal
                dpp = line.price_subtotal
                other = dpp * 11 / 12 if mv.btk_kode_transaksi == "04" else dpp
                ppn = other * mv.btk_ppn_rate / 100.0
                dw.writerow([idx, "A", code, line.name or tmpl.name, unit, _num(line.price_unit), _num(line.quantity),
                             _num(disc), _num(dpp), _num(other), _num(mv.btk_ppn_rate), _num(ppn), "0", "0"])
                g = ET.SubElement(goods, XML_TAGS["good"])
                for tag, val in (("g_opt", "A"), ("g_code", code), ("g_name", line.name or tmpl.name),
                                 ("g_unit", unit), ("g_price", _num(line.price_unit)), ("g_qty", _num(line.quantity)),
                                 ("g_disc", _num(disc)), ("g_base", _num(dpp)), ("g_base_other", _num(other)),
                                 ("g_rate", _num(mv.btk_ppn_rate)), ("g_vat", _num(ppn)), ("g_stlg_rate", "0"),
                                 ("g_stlg", "0")):
                    ET.SubElement(g, XML_TAGS[tag]).text = val

        buf = io.BytesIO()
        ET.indent(root)
        ET.ElementTree(root).write(buf, encoding="utf-8", xml_declaration=True)
        tag = f"{self.date_from:%Y%m%d}-{self.date_to:%Y%m%d}"
        if self.mark_exported and moves:
            moves.write({"btk_efaktur_exported": True})
        uniq = list(dict.fromkeys(warnings))
        self.write({
            "state": "done", "invoice_count": len(moves),
            "warnings": "\n".join(uniq[:60]) + (f"\n... (+{len(uniq) - 60} lagi)" if len(uniq) > 60 else ""),
            "faktur_file": base64.b64encode(("﻿" + faktur.getvalue()).encode("utf-8")),
            "faktur_name": f"coretax_faktur_{tag}.csv",
            "detail_file": base64.b64encode(("﻿" + detail.getvalue()).encode("utf-8")),
            "detail_name": f"coretax_detailfaktur_{tag}.csv",
            "xml_file": base64.b64encode(buf.getvalue()),
            "xml_name": f"coretax_EXPERIMENTAL_{tag}.xml",
        })
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id,
                "view_mode": "form", "target": "new"}
