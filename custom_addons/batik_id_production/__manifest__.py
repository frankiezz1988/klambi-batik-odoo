{
    "name": "Batik Demo - Produksi Jahit (Batch, QC, HPP per Batch)",
    "summary": "Alur subkontrak jahit: batch produksi (lot) per baris PO jasa jahit, serah bahan ke penjahit, "
               "penerimaan barang jadi, inspeksi QC di Sortase (lulus/rework/reject + alasan), analisis HPP per batch "
               "(kain, upah, susut, potongan reject), efisiensi bahan, performa penjahit dan margin per batch.",
    "version": "19.0.1.0.0",
    "category": "Manufacturing",
    "author": "Demo",
    "license": "LGPL-3",
    "depends": ["stock", "stock_account", "purchase", "purchase_stock", "mrp", "mrp_subcontracting", "sale_stock"],
    "data": [
        "security/ir.model.access.csv",
        "data/data.xml",
        "views/batch_views.xml",
        "views/qc_views.xml",
        "views/menu.xml",
    ],
    "installable": True,
    "application": False,
}
