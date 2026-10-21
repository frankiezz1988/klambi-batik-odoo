from collections import defaultdict

from odoo import api, fields, models, _


class BtkProdBatch(models.Model):
    _name = "btk.prod.batch"
    _description = "Batch Produksi Jahit (subkontrak)"
    _order = "date_po desc, id desc"

    name = fields.Char("No. Batch (= Lot)", required=True, copy=False, readonly=True, default=lambda s: _("Baru"), index=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)
    currency_id = fields.Many2one(related="company_id.currency_id")
    product_id = fields.Many2one("product.product", "Produk Jadi", required=True, index=True)
    tailor_id = fields.Many2one("res.partner", "Penjahit", required=True, index=True)
    purchase_id = fields.Many2one("purchase.order", "PO Jasa Jahit", required=True, index=True, ondelete="cascade")
    purchase_line_id = fields.Many2one("purchase.order.line", required=True, index=True, ondelete="cascade")
    lot_id = fields.Many2one("stock.lot", "Lot", readonly=True)
    state = fields.Selection([
        ("ordered", "Dipesan"), ("handed", "Bahan diserahkan"), ("receiving", "Penerimaan sebagian"),
        ("qc", "Menunggu QC"), ("done", "Selesai"), ("cancel", "Batal")], default="ordered", readonly=True, index=True)
    # tanggal
    date_po = fields.Date("Tgl PO", readonly=True)
    date_due = fields.Date("Jatuh tempo", readonly=True)
    date_handover = fields.Date("Tgl serah bahan", readonly=True)
    date_first_receipt = fields.Date("Terima pertama", readonly=True)
    date_last_receipt = fields.Date("Terima terakhir", readonly=True)
    lead_days = fields.Integer("Lead time (hari)", readonly=True, help="Dari serah bahan sampai terima terakhir.")
    late_days = fields.Integer("Terlambat (hari)", readonly=True)
    # kuantitas
    qty_ordered = fields.Float("Dipesan", readonly=True, digits="Product Unit")
    qty_received = fields.Float("Diterima", readonly=True, digits="Product Unit")
    qty_checked = fields.Float("Diperiksa QC", readonly=True, digits="Product Unit")
    qty_rework = fields.Float("Rework", readonly=True, digits="Product Unit")
    qty_reject = fields.Float("Reject", readonly=True, digits="Product Unit")
    qty_pass = fields.Float("Lolos QC", readonly=True, digits="Product Unit")
    qty_sold = fields.Float("Terjual (bersih retur)", readonly=True, digits="Product Unit")
    reject_pct = fields.Float("Reject %", readonly=True)
    fpy_pct = fields.Float("First-pass yield %", readonly=True)
    # biaya
    deduct_pct = fields.Float("Potongan upah reject %", default=100.0)
    planned_material_unit = fields.Monetary("Bahan standar / pcs", readonly=True)
    planned_service_unit = fields.Monetary("Upah / pcs", readonly=True)
    material_cost = fields.Monetary("Bahan terpakai", readonly=True)
    waste_cost = fields.Monetary("Susut bahan", readonly=True)
    service_cost = fields.Monetary("Upah jahit", readonly=True)
    service_deduction = fields.Monetary("Potongan upah reject", readonly=True)
    total_cost = fields.Monetary("Total biaya", readonly=True)
    net_cost = fields.Monetary("Biaya bersih (setelah potongan)", readonly=True)
    unit_cost = fields.Monetary("HPP / pcs lolos QC", readonly=True)
    planned_unit_cost = fields.Monetary("HPP standar / pcs", readonly=True)
    variance_unit = fields.Monetary("Selisih HPP / pcs", readonly=True)
    variance_total = fields.Monetary("Selisih HPP total", readonly=True)
    material_eff_pct = fields.Float("Efisiensi bahan %", readonly=True)
    revenue = fields.Monetary("Pendapatan (DPP)", readonly=True)
    cogs_batch = fields.Monetary("HPP batch terjual", readonly=True)
    margin = fields.Monetary("Margin kotor batch", readonly=True)
    margin_pct = fields.Float("Margin %", readonly=True)
    material_ids = fields.One2many("btk.prod.batch.material", "batch_id", "Bahan baku")
    inspection_ids = fields.One2many("btk.qc.inspection", "batch_id", "Inspeksi QC")

    _uniq_line = models.Constraint("unique(purchase_line_id)", "Satu baris PO hanya punya satu batch.")

    # ---------------------------------------------------------------- pembuatan
    @api.model_create_multi
    def create(self, vals_list):
        for v in vals_list:
            if not v.get("name") or v["name"] == _("Baru"):
                v["name"] = self.env["ir.sequence"].next_by_code("btk.prod.batch") or _("Baru")
        return super().create(vals_list)

    @api.model
    def _create_from_po_line(self, line):
        po = line.order_id
        if self.search_count([("purchase_line_id", "=", line.id)]):
            return self.browse()
        bom = self.env["mrp.bom"].search([("type", "=", "subcontract"), ("product_tmpl_id", "=", line.product_id.product_tmpl_id.id),
                                          ("subcontractor_ids", "in", po.partner_id.ids)], limit=1)
        if not bom:
            return self.browse()
        mats = []
        mat_unit = 0.0
        for bl in bom.bom_line_ids:
            per = bl.product_qty / (bom.product_qty or 1.0)
            cost = bl.product_id.standard_price
            mat_unit += per * cost
            mats.append((0, 0, {"product_id": bl.product_id.id, "qty_per_unit": per, "unit_cost": cost}))
        return self.create({
            "product_id": line.product_id.id, "tailor_id": po.partner_id.id, "purchase_id": po.id, "purchase_line_id": line.id,
            "date_po": fields.Datetime.to_datetime(po.date_order).date() if po.date_order else fields.Date.context_today(self),
            "date_due": fields.Datetime.to_datetime(line.date_planned).date() if line.date_planned else False,
            "qty_ordered": line.product_qty, "planned_material_unit": mat_unit, "planned_service_unit": line.price_unit,
            "material_ids": mats})

    # ---------------------------------------------------------------- perhitungan
    def action_recompute(self):
        for b in self:
            b._recompute_one()
        return True

    @api.model
    def _cron_recompute(self):
        self.search([("state", "!=", "cancel")]).action_recompute()

    def _recompute_one(self):
        self.ensure_one()
        env = self.env
        pol, po = self.purchase_line_id, self.purchase_id
        lot = env["stock.lot"].search([("name", "=", self.name), ("product_id", "=", self.product_id.id)], limit=1)
        vals = {"lot_id": lot.id or False}
        if po.state == "cancel":
            vals["state"] = "cancel"
            self.write(vals)
            return
        recs = pol.move_ids.filtered(lambda m: m.state == "done" and m.picking_id.picking_type_code == "incoming")
        qty_recv = sum(recs.mapped("quantity"))
        rdates = sorted(fields.Datetime.to_datetime(d).date() for d in recs.mapped("date") if d)
        sub_loc = self.company_id.subcontracting_location_id
        resup = env["stock.move"].search([("picking_id.origin", "=", po.name), ("picking_id.picking_type_id.code", "=", "internal"),
                                          ("location_dest_id", "=", sub_loc.id), ("state", "=", "done")])
        hdates = sorted(fields.Datetime.to_datetime(d).date() for d in resup.mapped("date") if d)
        # bahan: alokasi pengiriman proporsional terhadap kebutuhan standar antar batch dalam PO yang sama
        sib = self.search([("purchase_id", "=", po.id)])
        std_total = defaultdict(float)
        for s in sib:
            for m in s.material_ids:
                std_total[m.product_id.id] += m.qty_per_unit * s.qty_ordered
        sent_total = defaultdict(float)
        for m in resup:
            sent_total[m.product_id.id] += m.quantity
        consumed = defaultdict(lambda: [0.0, 0.0])
        if lot:
            for mo in env["mrp.production"].search([("lot_producing_ids", "in", lot.ids), ("state", "=", "done")]):
                for mv in mo.move_raw_ids.filtered(lambda x: x.state == "done"):
                    consumed[mv.product_id.id][0] += mv.quantity
                    consumed[mv.product_id.id][1] += abs(mv.value or 0.0)
        waste = defaultdict(lambda: [0.0, 0.0])
        reject_cost = 0.0
        for sc in env["stock.scrap"].search([("btk_batch_id", "=", self.id), ("state", "=", "done")]):
            val = abs(sum(sc.move_ids.mapped("value")))
            if sc.product_id == self.product_id:
                reject_cost += val
            else:
                waste[sc.product_id.id][0] += sc.scrap_qty
                waste[sc.product_id.id][1] += val
        for m in self.material_ids:
            pid = m.product_id.id
            std = m.qty_per_unit * self.qty_ordered
            share = (m.qty_per_unit * self.qty_ordered / std_total[pid]) if std_total[pid] else 0.0
            m.write({"qty_std": m.qty_per_unit * qty_recv, "qty_sent": sent_total[pid] * share,
                     "qty_consumed": consumed[pid][0], "cost_consumed": consumed[pid][1],
                     "qty_waste": waste[pid][0], "cost_waste": waste[pid][1]})
        # QC
        insp = self.inspection_ids.filtered(lambda i: i.state == "done")
        checked, rej, rew = sum(insp.mapped("qty_checked")), sum(insp.mapped("qty_reject")), sum(insp.mapped("qty_rework"))
        qty_pass = max(qty_recv - rej, 0.0)
        material = sum(v[1] for v in consumed.values())
        waste_cost = sum(v[1] for v in waste.values())
        service = qty_recv * pol.price_unit
        deduction = rej * pol.price_unit * self.deduct_pct / 100.0
        total = material + waste_cost + service
        net = total - deduction
        unit = net / qty_pass if qty_pass else 0.0
        planned = self.planned_material_unit + self.planned_service_unit
        # penjualan per lot
        qty_sold = revenue = 0.0
        if lot:
            for ml in env["stock.move.line"].search([("lot_id", "=", lot.id), ("state", "=", "done")]):
                mv = ml.move_id
                if mv.location_dest_id.usage == "customer" and mv.sale_line_id:
                    sign, sl = 1.0, mv.sale_line_id
                elif mv.location_id.usage == "customer" and mv.origin_returned_move_id.sale_line_id:
                    sign, sl = -1.0, mv.origin_returned_move_id.sale_line_id
                else:
                    continue
                net_unit = sl.price_subtotal / sl.product_uom_qty if sl.product_uom_qty else 0.0
                qty_sold += sign * ml.quantity
                revenue += sign * ml.quantity * net_unit
        cogs = qty_sold * unit
        # status
        pend = [i for i in self.inspection_ids if i.state != "done"]
        recv_pickings = recs.mapped("picking_id")
        inspected_pickings = insp.mapped("picking_id")
        if recs and qty_recv >= self.qty_ordered - 1e-6 and not (recv_pickings - inspected_pickings) and not pend:
            state = "done"
        elif recs and (recv_pickings - inspected_pickings):
            state = "qc"
        elif recs:
            state = "receiving"
        elif resup:
            state = "handed"
        else:
            state = "ordered"
        due = self.date_due
        vals.update({
            "state": state, "date_handover": hdates[0] if hdates else False,
            "date_first_receipt": rdates[0] if rdates else False, "date_last_receipt": rdates[-1] if rdates else False,
            "lead_days": (rdates[-1] - hdates[0]).days if (rdates and hdates) else 0,
            "late_days": max((rdates[-1] - due).days, 0) if (rdates and due) else 0,
            "qty_received": qty_recv, "qty_checked": checked, "qty_rework": rew, "qty_reject": rej, "qty_pass": qty_pass,
            "reject_pct": 100.0 * rej / checked if checked else 0.0,
            "fpy_pct": 100.0 * (checked - rej - rew) / checked if checked else 0.0,
            "material_cost": material, "waste_cost": waste_cost, "service_cost": service, "service_deduction": deduction,
            "total_cost": total, "net_cost": net, "unit_cost": unit, "planned_unit_cost": planned,
            "variance_unit": (unit - planned) if qty_pass else 0.0, "variance_total": ((unit - planned) * qty_pass) if qty_pass else 0.0,
            "material_eff_pct": 100.0 * material / (material + waste_cost) if (material + waste_cost) else 0.0,
            "qty_sold": qty_sold, "revenue": revenue, "cogs_batch": cogs, "margin": revenue - cogs,
            "margin_pct": 100.0 * (revenue - cogs) / revenue if revenue else 0.0,
        })
        self.write(vals)


class BtkProdBatchMaterial(models.Model):
    _name = "btk.prod.batch.material"
    _description = "Bahan baku per batch (serah-terima ke penjahit)"
    _order = "batch_id, id"

    batch_id = fields.Many2one("btk.prod.batch", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="batch_id.company_id", store=True)
    currency_id = fields.Many2one(related="batch_id.currency_id")
    tailor_id = fields.Many2one(related="batch_id.tailor_id", store=True)
    product_id = fields.Many2one("product.product", "Bahan", required=True)
    qty_per_unit = fields.Float("BoM / pcs", digits="Product Unit")
    unit_cost = fields.Monetary("Biaya standar / unit")
    qty_std = fields.Float("Kebutuhan standar (diterima)", digits="Product Unit", readonly=True)
    qty_sent = fields.Float("Diserahkan ke penjahit (alokasi)", digits="Product Unit", readonly=True)
    qty_consumed = fields.Float("Terpakai (BoM)", digits="Product Unit", readonly=True)
    qty_waste = fields.Float("Susut dilaporkan", digits="Product Unit", readonly=True)
    qty_balance = fields.Float("Sisa di penjahit", digits="Product Unit", compute="_compute_balance", store=True)
    cost_consumed = fields.Monetary("Nilai terpakai", readonly=True)
    cost_waste = fields.Monetary("Nilai susut", readonly=True)

    @api.depends("qty_sent", "qty_consumed", "qty_waste")
    def _compute_balance(self):
        for r in self:
            r.qty_balance = r.qty_sent - r.qty_consumed - r.qty_waste
