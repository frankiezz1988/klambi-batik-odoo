"""Konfigurasi demo: perusahaan, channel, produk, tarif. Semua angka DUMMY / ilustrasi."""
import os

SEED = int(os.environ.get("DEMO_SEED", "2026"))
MONTHS = int(os.environ.get("DEMO_MONTHS", "6"))
ORDERS_PER_MONTH = int(os.environ.get("DEMO_ORDERS_PER_MONTH", "90"))
DEMO_LOCK = os.environ.get("DEMO_LOCK", "0") == "1"

COMPANY = {
    "name": "PT Batik Kawung Nusantara (DEMO)",
    "street": "Jl. Malioboro No. 1",
    "city": "Yogyakarta",
    "zip": "55213",
    "vat": "0123456789012000",  # NPWP 16 digit - DUMMY
    "email": "finance@batik-demo.example",
    "phone": "+62 274 000000",
}

# ---- Pajak (acuan: PMK 131/2024 -> PPN 12% x DPP nilai lain 11/12 untuk BKP non-mewah = efektif 11%)
PPN_EFFECTIVE = 11.0          # % dari harga jual (12% x 11/12)
PPH23_RATE = 2.0              # jasa (agency live/KOL badan, jasa promosi) - dipotong oleh kita
PPH42_SEWA_RATE = 10.0        # PPh 4(2) final sewa tanah/bangunan - dipotong oleh kita
PPH_FINAL_UMKM_RATE = 0.5     # PP 55/2022, % omzet bruto bulanan (omzet <= Rp4,8 M)
PPH22_MARKETPLACE_RATE = 0.5  # PMK 37/2025, dipungut marketplace dari omzet bruto di luar PPN
# PMK 37/2025: semula 1 Agustus 2026, DITUNDA (Menkeu Purbaya; PENG-46/PJ.09/2026, 5 Agt 2026) -> berlaku 1 November 2026.
# PPh 22 yang telanjur dipungut sejak 1 Agustus wajib dikembalikan marketplace. Ubah tanggal ini bila jadwal berubah lagi.
PPH22_START = os.environ.get("PPH22_START", "2026-11-01")

# ---- Channel penjualan
# fees: (label, rate % terhadap DPP/penjualan bersih, akun) - angka ilustrasi, bukan tarif resmi platform
CHANNELS = [
    {"code": "STORE", "name": "Store - Yogyakarta", "partner": "Pelanggan Toko (Walk-in)",
     "team": "Store", "weight": 0.27, "discount": (0.0, 0.10), "wallet": "bank_qris",
     "fees": [("MDR QRIS/EDC", 0.7, "fee_payment")], "pph22": False, "ref_prefix": "STR"},
    {"code": "SHOPEE", "name": "Marketplace - Shopee", "partner": "Pembeli Shopee",
     "team": "Shopee", "weight": 0.28, "discount": (0.05, 0.25), "wallet": "wallet_shopee",
     "fees": [("Komisi Shopee", 8.0, "fee_comm"), ("Biaya Layanan & Transaksi", 4.5, "fee_service")],
     "pph22": True, "ref_prefix": "SPE"},
    {"code": "TOKPED", "name": "Marketplace - Tokopedia", "partner": "Pembeli Tokopedia",
     "team": "Tokopedia", "weight": 0.15, "discount": (0.03, 0.20), "wallet": "wallet_tokped",
     "fees": [("Komisi Tokopedia", 6.5, "fee_comm"), ("Biaya Layanan & Transaksi", 3.0, "fee_service")],
     "pph22": True, "ref_prefix": "TKP"},
    {"code": "TIKTOK", "name": "Live - TikTok Shop", "partner": "Pembeli TikTok Shop",
     "team": "TikTok Live", "weight": 0.18, "discount": (0.10, 0.35), "wallet": "wallet_tiktok",
     "fees": [("Komisi TikTok Shop", 5.5, "fee_comm"), ("Komisi Afiliasi Live", 8.0, "fee_aff"),
              ("Biaya Layanan & Transaksi", 2.5, "fee_service")],
     "pph22": True, "ref_prefix": "TTK"},
    {"code": "INSTAGRAM", "name": "Instagram / DM & Live IG", "partner": "Pelanggan Instagram",
     "team": "Instagram", "weight": 0.12, "discount": (0.0, 0.15), "wallet": "wallet_gateway",
     "fees": [("MDR Payment Gateway", 1.8, "fee_payment")], "pph22": False, "ref_prefix": "IGM"},
]
COST_CENTERS = ["Kantor Pusat", "Gudang", "Toko Yogyakarta"]

SETTLEMENT_LAG_DAYS = 3
SETTLEMENT_BUCKET_DAYS = 10

# Biaya bulanan (dummy). split = alokasi analytic ke channel (kode channel -> %)
MONTHLY_COSTS = {
    "rent": 12_000_000,
    "utilities": 2_500_000,
    "salary": 28_000_000,
    "pph21_rate": 4.0,                 # % dari gaji, disederhanakan
    "kol_agency": 6_000_000,           # agency host live TikTok (PPN + PPh 23)
    "ads": {"INSTAGRAM": 9_000_000, "TIKTOK": 7_500_000, "SHOPEE": 4_000_000, "TOKPED": 2_000_000},
    "packaging": 3_000_000,
    "packaging_split": {"STORE": 20, "SHOPEE": 30, "TOKPED": 15, "TIKTOK": 20, "INSTAGRAM": 15},
}
OPENING_CAPITAL = 500_000_000

CATEGORIES = [
    {"name": "Batik Tulis", "cost_method": "fifo"},
    {"name": "Batik Cap", "cost_method": "average"},
    {"name": "Batik Printing", "cost_method": "average"},
    {"name": "Aksesoris & Kain", "cost_method": "average"},
]

# sku, nama, kategori, HPP dasar (beli, sebelum PPN), harga jual (sebelum PPN), bobot permintaan, vendor
PRODUCTS = [
    ("BT-KMJ-001", "Kemeja Batik Tulis Parang Pria", "Batik Tulis", 310_000, 595_000, 3, "Pengrajin Solo"),
    ("BT-DRS-001", "Dress Batik Tulis Mega Mendung", "Batik Tulis", 395_000, 749_000, 2, "Pengrajin Cirebon"),
    ("BT-KAI-001", "Kain Batik Tulis Sidomukti 2m", "Batik Tulis", 520_000, 985_000, 1, "Pengrajin Yogya"),
    ("BC-KMJ-001", "Kemeja Batik Cap Kawung Pria", "Batik Cap", 120_000, 249_000, 8, "Pengrajin Pekalongan"),
    ("BC-KMJ-002", "Kemeja Batik Cap Lasem Slimfit", "Batik Cap", 135_000, 279_000, 6, "Pengrajin Lasem"),
    ("BC-BLS-001", "Blouse Batik Cap Truntum Wanita", "Batik Cap", 105_000, 219_000, 7, "Pengrajin Pekalongan"),
    ("BC-DRS-001", "Dress Batik Cap Sekar Jagad", "Batik Cap", 155_000, 329_000, 5, "Pengrajin Lasem"),
    ("BC-SRB-001", "Sarimbit Batik Cap Couple Set", "Batik Cap", 260_000, 529_000, 4, "Pengrajin Pekalongan"),
    ("BP-KMJ-001", "Kemeja Batik Printing Motif Modern", "Batik Printing", 62_000, 139_000, 10, "Konveksi Bandung"),
    ("BP-DRS-001", "Dress Batik Printing Kasual", "Batik Printing", 78_000, 169_000, 8, "Konveksi Bandung"),
    ("BP-OTR-001", "Outer Batik Printing Cardigan", "Batik Printing", 92_000, 199_000, 5, "Konveksi Bandung"),
    ("BP-KDS-001", "Kemeja Anak Batik Printing", "Batik Printing", 48_000, 109_000, 6, "Konveksi Bandung"),
    ("AK-SCF-001", "Scarf Batik Sutra Printing", "Aksesoris & Kain", 55_000, 129_000, 5, "Pengrajin Yogya"),
    ("AK-MSK-001", "Masker & Pouch Batik Set", "Aksesoris & Kain", 18_000, 49_000, 6, "Konveksi Bandung"),
    ("AK-TAS-001", "Tote Bag Batik Cap", "Aksesoris & Kain", 42_000, 99_000, 5, "Pengrajin Pekalongan"),
    ("AK-KAI-002", "Kain Batik Cap Panjang 2m", "Aksesoris & Kain", 85_000, 189_000, 4, "Pengrajin Pekalongan"),
]

VENDORS = [
    "Pengrajin Solo", "Pengrajin Cirebon", "Pengrajin Yogya", "Pengrajin Pekalongan",
    "Pengrajin Lasem", "Konveksi Bandung",
]
SERVICE_PARTNERS = {
    "landlord": "CV Sewa Gedung Malioboro",
    "utility": "PLN & Provider Internet",
    "agency": "PT Live Host Kreatif (Agency)",
    "packaging": "Toko Kemasan Mandiri",
    "meta": "Meta Ads (Instagram)",
    "tiktok_ads": "TikTok Ads",
    "shopee_ads": "Shopee Ads",
    "tokped_ads": "Tokopedia Ads",
    "shopee_platform": "Shopee International Indonesia",
    "tokped_platform": "PT Tokopedia (Fee Platform)",
    "tiktok_platform": "TikTok Shop Indonesia",
    "gateway": "Payment Gateway Provider",
    "bank": "Bank BCA",
}
