import base64
import csv
import io

from odoo import fields, models
from odoo.exceptions import UserError


class NsfpImport(models.TransientModel):
    _name = "btk.nsfp.import"
    _description = "Impor NSFP dari Coretax"

    file = fields.Binary(string="File CSV", required=True, attachment=False)
    filename = fields.Char()
    result = fields.Text(readonly=True)
    state = fields.Selection([("draft", "Draft"), ("done", "Selesai")], default="draft")

    def action_import(self):
        """CSV dengan header: invoice_number (atau ref_order), nsfp. Pemisah koma atau titik koma."""
        self.ensure_one()
        raw = base64.b64decode(self.file).decode("utf-8-sig", errors="replace")
        dialect = csv.Sniffer().sniff(raw[:2048], delimiters=",;\t")
        rows = list(csv.DictReader(io.StringIO(raw), dialect=dialect))
        if not rows or "nsfp" not in {k.strip().lower() for k in rows[0]}:
            raise UserError(self.env._("Header wajib: invoice_number (atau ref_order) dan nsfp."))
        Move = self.env["account.move"]
        ok, missing, dup = 0, [], []
        for row in rows:
            r = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            nsfp = r.get("nsfp")
            key = r.get("invoice_number") or r.get("ref_order")
            if not nsfp or not key:
                continue
            move = Move.search([("move_type", "=", "out_invoice"),
                                "|", ("name", "=", key), ("btk_channel_ref", "=", key)], limit=1)
            if not move:
                missing.append(key)
                continue
            clash = Move.search_count([("id", "!=", move.id), ("btk_nsfp", "=", nsfp), ("move_type", "in", ("out_invoice", "out_refund"))])
            if clash:
                dup.append(f"{key} ({nsfp})")
                continue
            move.write({"btk_nsfp": nsfp, "btk_efaktur_exported": True})
            ok += 1
        lines = [f"Berhasil: {ok}", f"Invoice tidak ditemukan: {len(missing)}", f"NSFP bentrok: {len(dup)}"]
        if missing:
            lines.append("Tidak ditemukan: " + ", ".join(missing[:30]))
        if dup:
            lines.append("Bentrok: " + ", ".join(dup[:30]))
        self.write({"state": "done", "result": "\n".join(lines)})
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id,
                "view_mode": "form", "target": "new"}
