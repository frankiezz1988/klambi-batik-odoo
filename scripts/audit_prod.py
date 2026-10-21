# audit_prod.py : audit invarian alur produksi jahit (batch, serah bahan, terima, QC, HPP per batch). Jalankan di odoo shell:
#   odoo shell -d DB --no-http < scripts/audit_prod.py      Keluaran: PASS/FAIL per pemeriksaan; baris terakhir "AUDIT PRODUKSI: n FAIL".
from collections import defaultdict
env = env  # noqa: F821  (disediakan odoo shell)
fails, rows = [], []


def chk(name, ok, detail=""):
    rows.append((name, ok, detail))
    print("%-4s %-62s %s" % ("PASS" if ok else "FAIL", name, detail))
    if not ok:
        fails.append(name)


B = env["btk.prod.batch"].search([])
Q = env["btk.qc.inspection"].search([])
PO = env["purchase.order"]
cur = env.company.currency_id
tol = 1.0

# 1. satu batch per baris PO jasa jahit (BoM subkontrak) yang terkonfirmasi
tl = env["purchase.order.line"].search([("order_id.state", "in", ("purchase", "done")), ("product_id.bom_ids.type", "=", "subcontract")])
chk("1 batch = 1 baris PO jasa jahit", len(B.filtered(lambda b: b.state != "cancel")) == len(tl), "batch=%d baris_po=%d" % (len(B), len(tl)))

# 2. qty diterima batch = qty move masuk selesai pada baris PO
bad = []
for b in B:
    recs = b.purchase_line_id.move_ids.filtered(lambda m: m.state == "done" and m.picking_id.picking_type_code == "incoming")
    if abs(sum(recs.mapped("quantity")) - b.qty_received) > 1e-6:
        bad.append(b.name)
chk("2 qty diterima batch = penerimaan selesai", not bad, ",".join(bad[:5]))

# 3. setiap penerimaan batch selesai sudah punya inspeksi QC selesai; qty diperiksa = diterima
bad = [b.name for b in B if b.state == "done" and abs(b.qty_checked - b.qty_received) > 1e-6]
chk("3 batch selesai: qty QC = qty diterima", not bad, ",".join(bad[:5]))

# 4. reject QC = scrap produk jadi berlot, nilai terposting; qty scrap = Σ reject inspeksi
bad = []
for b in B:
    sc = env["stock.scrap"].search([("btk_batch_id", "=", b.id), ("state", "=", "done"), ("product_id", "=", b.product_id.id)])
    if abs(sum(sc.mapped("scrap_qty")) - b.qty_reject) > 1e-6:
        bad.append(b.name)
chk("4 qty reject = scrap produk jadi", not bad, ",".join(bad[:5]))
chk("4b scrap reject berlot (lot terisi)", not env["stock.scrap"].search_count([("btk_batch_id", "!=", False), ("product_id.tracking", "=", "lot"), ("lot_id", "=", False)]))

# 5. lot unik per produk, tiap batch bertanda terima punya lot bernama batch
bad = [b.name for b in B if b.qty_received and not b.lot_id]
chk("5 batch diterima punya lot", not bad, ",".join(bad[:5]))
env.cr.execute("select count(*) from (select name, product_id from stock_lot group by 1, 2 having count(*) > 1) x")
chk("5b lot unik per produk", env.cr.fetchone()[0] == 0)

# 6. bahan di penjahit: saldo batch (dikirim - terpakai - susut) = stok lokasi Subkontrak (per bahan), toleransi kecil
sub = env.company.subcontracting_location_id
bal = defaultdict(float)
for m in B.material_ids:
    bal[m.product_id.id] += m.qty_balance
quant = defaultdict(float)
for q in env["stock.quant"].search([("location_id", "child_of", sub.id)]):
    quant[q.product_id.id] += q.quantity
diff = {p: (bal[p], quant[p]) for p in set(bal) | set(quant) if abs(bal[p] - quant[p]) > 0.5}
chk("6 saldo bahan di penjahit = stok lokasi Subkontrak", not diff,
    "; ".join("%s: batch=%.2f stok=%.2f" % (env["product.product"].browse(p).default_code, a, b) for p, (a, b) in list(diff.items())[:4]))
neg = [q for q in env["stock.quant"].search([("quantity", "<", 0), ("location_id.usage", "=", "internal")])]
chk("6b stok internal tidak negatif", not neg, "%d quant" % len(neg))
negs = env["stock.quant"].search_count([("quantity", "<", -0.001), ("location_id", "child_of", sub.id)])
chk("6c stok di penjahit tidak negatif", negs == 0, "%d quant" % negs)

# 7. biaya: nilai barang jadi pada MO subkontrak (komponen + upah) = bahan terpakai + upah batch (toleransi pembulatan)
bad = []
for b in B.filtered(lambda x: x.qty_received and x.lot_id):
    mos = env["mrp.production"].search([("lot_producing_ids", "in", b.lot_id.ids), ("state", "=", "done")])
    val = sum(abs(m.value or 0.0) for m in mos.move_finished_ids.filtered(lambda x: x.state == "done"))
    exp = b.material_cost + b.service_cost
    if abs(val - exp) > max(tol, 0.002 * exp):
        bad.append("%s nilai=%.0f hitung=%.0f" % (b.name, val, exp))
chk("7 nilai barang jadi (MO subkon) = bahan + upah", not bad, "; ".join(bad[:3]))

# 8. HPP/pcs wajar vs standar (+-35%), selisih total konsisten
bad = [b.name for b in B if b.qty_pass and not (0.65 * b.planned_unit_cost <= b.unit_cost <= 1.35 * b.planned_unit_cost)]
chk("8 HPP/pcs dalam +-35% dari standar", not bad, ",".join(bad[:5]))
bad = [b.name for b in B if abs(b.variance_total - b.variance_unit * b.qty_pass) > tol]
chk("8b selisih total = selisih/pcs x lolos", not bad)

# 9. penjualan per lot tidak melebihi qty diterima; pendapatan & margin konsisten
bad = [b.name for b in B if b.qty_sold - b.qty_received > 1e-6]
chk("9 terjual (bersih retur) <= diterima", not bad, ",".join(bad[:5]))
bad = [b.name for b in B if abs(b.margin - (b.revenue - b.cogs_batch)) > tol]
chk("9b margin = pendapatan - HPP batch", not bad)

# 10. tagihan penjahit: potongan upah reject di bill = Σ service_deduction; semua PO jahit selesai punya bill terposting
ded = 0.0
for l in env["account.move.line"].search([("move_id.move_type", "=", "in_invoice"), ("move_id.state", "=", "posted"), ("name", "like", "Potongan upah reject QC%")]):
    ded += -l.price_subtotal
sd = sum(B.mapped("service_deduction"))
chk("10 potongan upah reject di tagihan = Σ batch", abs(ded - sd) <= max(tol, 0.01 * sd), "bill=%.0f batch=%.0f" % (ded, sd))
nobill = [po.name for po in B.mapped("purchase_id") if all(b.state == "done" for b in po.btk_batch_ids) and not po.invoice_ids.filtered(lambda i: i.state == "posted")]
chk("10b PO jahit selesai punya tagihan posted", not nobill, ",".join(nobill[:5]))

# 11. analytic: scrap/susut/selisih terposting ke analytic Gudang & Produksi bila ada nilai
# (diperiksa umum oleh audit_v2; di sini hanya hitung scrap tanpa jurnal)
nos = [s.name for s in env["stock.scrap"].search([("btk_batch_id", "!=", False), ("state", "=", "done")]) if not s.move_ids]
chk("11 scrap batch punya move stok", not nos, ",".join(nos[:5]))

# ringkasan manajemen
print("\n-- Ringkasan batch --")
print("batch=%d selesai=%d  QC=%d  pcs diterima=%.0f reject=%.0f (%.1f%%) rework=%.0f" % (
    len(B), len(B.filtered(lambda b: b.state == 'done')), len(Q), sum(B.mapped('qty_received')), sum(B.mapped('qty_reject')),
    100 * sum(B.mapped('qty_reject')) / max(sum(B.mapped('qty_checked')), 1), sum(B.mapped('qty_rework'))))
print("%-28s %6s %8s %8s %6s %10s" % ("penjahit", "batch", "diterima", "reject%", "telat", "HPP/pcs avg"))
per = defaultdict(list)
for b in B:
    per[b.tailor_id.name].append(b)
for t, bs in sorted(per.items()):
    rc = sum(x.qty_received for x in bs)
    chk_ = sum(x.qty_checked for x in bs)
    up = sum(x.net_cost for x in bs) / max(sum(x.qty_pass for x in bs), 1)
    print("%-28s %6d %8.0f %7.1f%% %6d %10.0f" % (t[:28], len(bs), rc, 100 * sum(x.qty_reject for x in bs) / max(chk_, 1), sum(1 for x in bs if x.late_days), up))
print("\nAUDIT PRODUKSI: %d FAIL dari %d pemeriksaan" % (len(fails), len(rows)))
