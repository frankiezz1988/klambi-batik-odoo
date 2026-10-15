{
    "name": "Batik Demo - Payroll Ringan (BPJS & PPh 21 TER)",
    "summary": "Karyawan, perhitungan BPJS (JHT/JP/JKK/JKM/Kesehatan) dan PPh 21 TER (PMK 168/2023) bulanan, "
               "dengan jurnal gaji otomatis. Desember (rekonsiliasi Pasal 17) belum diimplementasikan.",
    "version": "19.0.1.0.0",
    "category": "Accounting/Localizations",
    "author": "Demo",
    "license": "LGPL-3",
    "depends": ["account", "batik_id_tax"],
    "data": [
        "security/ir.model.access.csv",
        "data/btk.ter.rate.csv",
        "views/payroll_views.xml",
    ],
    "installable": True,
    "application": False,
}
