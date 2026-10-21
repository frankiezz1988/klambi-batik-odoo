from odoo import api, fields, models


class StockScrap(models.Model):
    _inherit = "stock.scrap"

    btk_batch_id = fields.Many2one("btk.prod.batch", "Batch produksi", index=True)

    def action_validate(self):
        res = super().action_validate()
        self.btk_batch_id.action_recompute()
        return res


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    btk_batch_ids = fields.One2many("btk.prod.batch", "purchase_id", "Batch produksi")
    btk_batch_count = fields.Integer(compute="_compute_btk_batch_count")

    def _compute_btk_batch_count(self):
        for po in self:
            po.btk_batch_count = len(po.btk_batch_ids)

    def button_confirm(self):
        res = super().button_confirm()
        for po in self.filtered(lambda p: p.state == "purchase"):
            for line in po.order_line.filtered(lambda l: l.product_id and not l.display_type):
                self.env["btk.prod.batch"]._create_from_po_line(line)
        return res

    def action_view_btk_batches(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "name": "Batch Produksi", "res_model": "btk.prod.batch",
                "view_mode": "list,form", "domain": [("purchase_id", "=", self.id)]}


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def button_validate(self):
        Batch = self.env["btk.prod.batch"]
        for pk in self.filtered(lambda p: p.picking_type_code == "incoming" and p.purchase_id):
            for mv in pk.move_ids.filtered(lambda m: m.purchase_line_id and m.product_id.tracking == "lot"):
                b = Batch.search([("purchase_line_id", "=", mv.purchase_line_id.id)], limit=1)
                if not b:
                    continue
                for ml in mv.move_line_ids.filtered(lambda l: not l.lot_id and not l.lot_name):
                    ml.lot_name = b.name
        res = super().button_validate()
        done = self.filtered(lambda p: p.state == "done")
        pls = done.move_ids.purchase_line_id
        if pls:
            Batch.search([("purchase_line_id", "in", pls.ids)]).action_recompute()
        return res
