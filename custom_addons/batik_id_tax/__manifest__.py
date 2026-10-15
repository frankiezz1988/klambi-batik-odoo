{
    "name": "Batik Demo - Pajak Indonesia (NSFP, DPP Nilai Lain, NPWP/NIK, Lembar Faktur)",
    "summary": "Field NSFP, kode transaksi, DPP nilai lain 11/12 & PPN 12% pada invoice, identitas pajak "
               "(NPWP/NIK/ID TKU) pada partner, kode barang/jasa Coretax pada produk, dan lembar pendukung faktur.",
    "version": "19.0.2.0.0",
    "category": "Accounting/Localizations",
    "author": "Demo",
    "license": "LGPL-3",
    "depends": ["account", "product"],
    "data": [
        "views/menus.xml",
        "views/account_move_views.xml",
        "views/res_partner_views.xml",
        "views/product_views.xml",
        "report/faktur_report.xml",
    ],
    "installable": True,
    "application": False,
}
