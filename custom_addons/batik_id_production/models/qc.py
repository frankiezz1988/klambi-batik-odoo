from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BtkQcDefect(models.Model):
    _name = "btk.qc.defect"
    _description = "Jenis cacat QC"
    _order = "code"

    code = fields.Char(required=True)
    name = fields.Char("Jenis cacat", required=True)
    active = fields.Boolean(default=True)


class BtkQcInspection(models.Model):
    _name = "btk.qc.inspection"
    _description = "Inspeksi QC penerimaan jahit (Sortase)"
    _order = "date desc, id desc"

    name = fields.Char("No. QC", required=True, copy=False, readonly=True, default=lambda s: _("Baru"))
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)
    batch_id = fields.Many2one("btk.prod.batch", "Batch", required=True, index=True, ondelete="cascade")
    product_id = fields.Many2one(related="batch_id.product_id", store=True)
    tailor_id = fields.Many2one(related="batch_id.tailor_id", store=True)
    picking_id = fields.Many2one("stock.picking", "Penerimaan", index=True)
    date = fields.Datetime("Tanggal", default=fields.Datetime.now, required=True)
    inspector_id = fields.Many2one("res.users", "Pemeriksa", default=lambda s: s.env.user)
    qty_received = fields.Float("Diterima", digits="Product Unit")
    qty_checked = fields.Float("Diperiksa", digits="Product Unit")
    line_ids = fields.One2many("btk.qc.inspection.line", "inspection_id", "Temuan")
    qty_reject = fields.Float("Reject", compute="_compute_qty", store=True, digits="Product Unit")
    qty_rework = fields.Float("Rework", compute="_compute_qty", store=True, digits="Product Unit")
    qty_pass = fields.Float("Lolos", compute="_compute_qty", store=True, digits="Product Unit")
    result = fields.Selection([("pass", "Lulus"), ("conditional", "Lulus bersyarat"), ("fail", "Ditolak")],
                              compute="_compute_qty", store=True, string="Hasil")
    state = fields.Selection([("draft", "Draf"), ("done", "Selesai"), ("cancel", "Batal")], default="draft", index=True)
    scrap_id = fields.Many2one("stock.scrap", "Scrap reject", readonly=True)
    note = fields.Text("Catatan")

    @api.model_create_multi
    def create(self, vals_list):
        for v in vals_list:
            if not v.get("name") or v["name"] == _("Baru"):
                v["name"] = self.env["ir.sequence"].next_by_code("btk.qc.inspection") or _("Baru")
        return super().create(vals_list)

    @api.depends("line_ids.qty", "line_ids.disposition", "qty_checked", "qty_received")
    def _compute_qty(self):
        for r in self:
            rej = sum(r.line_ids.filtered(lambda l: l.disposition == "reject").mapped("qty"))
            rew = sum(r.line_ids.filtered(lambda l: l.disposition == "rework").mapped("qty"))
            r.qty_reject, r.qty_rework = rej, rew
            r.qty_pass = (r.qty_checked or r.qty_received) - rej
            tot = r.qty_checked or r.qty_received
            r.result = "pass" if not (rej or rew) else ("fail" if tot and rej / tot > 0.10 else "conditional")

    def action_done(self):
        for r in self:
            if r.state != "draft":
                continue
            if r.qty_reject and not r.scrap_id:
                lot = r.batch_id.lot_id or self.env["stock.lot"].search([("name", "=", r.batch_id.name), ("product_id", "=", r.product_id.id)], limit=1)
                if not lot:
                    raise UserError(_("Lot %s belum ada; validasi penerimaan terlebih dahulu.", r.batch_id.name))
                loc = r.picking_id.location_dest_id if r.picking_id else self.env["stock.warehouse"].search([], limit=1).wh_input_stock_loc_id
                why = ", ".join(sorted({l.defect_id.name for l in r.line_ids if l.disposition == "reject"}))
                sc = self.env["stock.scrap"].create({
                    "product_id": r.product_id.id, "scrap_qty": r.qty_reject, "location_id": loc.id, "lot_id": lot.id,
                    "origin": "Reject QC %s (%s)" % (r.name, why), "btk_batch_id": r.batch_id.id})
                sc.action_validate()
                r.scrap_id = sc
            r.state = "done"
            r.batch_id.action_recompute()
        return True

    def action_cancel(self):
        self.filtered(lambda r: r.state == "draft").write({"state": "cancel"})


class BtkQcInspectionLine(models.Model):
    _name = "btk.qc.inspection.line"
    _description = "Temuan inspeksi QC"

    inspection_id = fields.Many2one("btk.qc.inspection", required=True, ondelete="cascade", index=True)
    defect_id = fields.Many2one("btk.qc.defect", "Jenis cacat", required=True)
    qty = fields.Float("Jumlah (pcs)", digits="Product Unit", required=True)
    disposition = fields.Selection([("reject", "Reject (scrap)"), ("rework", "Perbaikan oleh penjahit")], default="reject", required=True)
