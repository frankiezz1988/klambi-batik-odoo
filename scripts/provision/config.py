"""Konfigurasi demo Klambi Bali (v2). Semua angka DUMMY / ilustrasi; nama & NPWP fiktif.

Garis waktu tetap (tidak bergantung tanggal sistem) supaya hasil seed deterministik:
  1 Juli 2026 (go-live / saldo awal) s.d. 17 Oktober 2026 (hari 'kini' pada data demo).
"""
import datetime as dt
import os

SEED = int(os.environ.get("DEMO_SEED", "2026"))
SCALE = float(os.environ.get("DEMO_SCALE", "1.0"))        # 1.0 = skala penuh; 0.1 untuk uji cepat
START = dt.date.fromisoformat(os.environ.get("DEMO_START", "2026-07-01"))
END = dt.date.fromisoformat(os.environ.get("DEMO_END", "2026-10-17"))
DEMO_LOCK = os.environ.get("DEMO_LOCK", "0") == "1"
# kompatibilitas skrip lama
MONTHS = 4

COMPANY = {
    "name": os.environ.get("COMPANY_NAME", "Klambi Bali"),
    "street": "Jl. Raya Sesetan No. 88, Sesetan",
    "street2": "Kec. Denpasar Selatan",
    "city": "Denpasar",
    "zip": "80223",
    "vat": "0123456789012000",  # NPWP 16 digit - DUMMY
    "email": "finance@batik-demo.example",
    "phone": "+62 361 000 000",
    "tz": "Asia/Makassar",       # WITA
}

# ---- Pajak (PMK 131/2024: PPN 12% x DPP 11/12 => efektif 11% untuk BKP non-mewah)
PPN_EFFECTIVE = 11.0
PPH23_RATE = 2.0
PPH42_SEWA_RATE = 10.0
PPH_FINAL_UMKM_RATE = 0.5
PPH22_MARKETPLACE_RATE = 0.5
# PMK 37/2025 ditunda: berlaku 1 Nov 2026 -> pada data Jul-Okt belum ada PPh 22 yang dipungut marketplace.
PPH22_START = os.environ.get("PPH22_START", "2026-11-01")

# ---- Channel. rev = target DPP (omzet sebelum PPN) per bulan penuh dalam JUTA rupiah [Jul, Agu, Sep, Okt]
# aov = rata-rata DPP per order (rupiah). fees: (label, % DPP, kunci akun).
CHANNELS = [
    {"code": "STORE", "name": "Toko Denpasar (POS)", "team": "Toko Denpasar",
     "rev": [68, 62, 74, 78], "aov": 650_000, "ref": "POS", "wallet": "bank_qris", "journal": "QRIS",
     "fees": [("MDR QRIS/EDC", 0.7, "fee_payment")], "pph22": False},
    {"code": "B2B", "name": "B2B - Reseller & Korporat", "team": "B2B",
     "rev": [52, 58, 66, 66], "aov": 9_500_000, "ref": "B2B", "wallet": None, "journal": "BCA",
     "fees": [], "pph22": False},
    {"code": "SHOPEE", "name": "Marketplace - Shopee", "team": "Shopee",
     "rev": [48, 48, 70, 70], "aov": 360_000, "ref": "SPE", "wallet": "wallet_shopee", "journal": "SHPE",
     "fees": [("Komisi Shopee", 8.0, "fee_comm"), ("Biaya Layanan & Transaksi", 4.5, "fee_service")], "pph22": True},
    {"code": "TOKPED", "name": "Marketplace - Tokopedia", "team": "Tokopedia",
     "rev": [16, 15, 18, 18], "aov": 400_000, "ref": "TKP", "wallet": "wallet_tokped", "journal": "TKPD",
     "fees": [("Komisi Tokopedia", 6.5, "fee_comm"), ("Biaya Layanan & Transaksi", 3.0, "fee_service")], "pph22": True},
    {"code": "TIKTOK", "name": "Live - TikTok Shop", "team": "TikTok Live",
     "rev": [28, 32, 56, 60], "aov": 430_000, "ref": "TTK", "wallet": "wallet_tiktok", "journal": "TTOK",
     "fees": [("Komisi TikTok Shop", 5.5, "fee_comm"), ("Komisi Afiliasi Live", 8.0, "fee_aff"),
              ("Biaya Layanan & Transaksi", 2.5, "fee_service")], "pph22": True},
    {"code": "INSTAGRAM", "name": "Instagram & WhatsApp", "team": "Instagram & WhatsApp",
     "rev": [24, 22, 28, 30], "aov": 850_000, "ref": "IGM", "wallet": "wallet_gateway", "journal": "PGW",
     "fees": [("MDR Payment Gateway", 1.8, "fee_payment")], "pph22": False},
]
COST_CENTERS = ["Kantor Pusat", "Gudang & Produksi", "Toko Denpasar"]

SETTLEMENT_LAG_DAYS = 3          # pembayaran masuk escrow setelah barang diterima
SETTLEMENT_PAYOUT_DAYS = 7       # pencairan escrow -> bank per 7 hari (mingguan)

# Peristiwa yang menggeser permintaan (pengali harian). (mulai, selesai, pengali, channel|None, nama)
EVENTS = [
    (dt.date(2026, 8, 14), dt.date(2026, 8, 17), 1.35, None, "Promo Kemerdekaan 17-an"),
    (dt.date(2026, 9, 9), dt.date(2026, 9, 9), 1.6, ("SHOPEE", "TOKPED", "TIKTOK"), "Promo 9.9"),
    (dt.date(2026, 10, 1), dt.date(2026, 10, 3), 1.35, None, "Hari Batik Nasional (2 Okt)"),
    (dt.date(2026, 10, 10), dt.date(2026, 10, 10), 1.7, ("SHOPEE", "TOKPED", "TIKTOK"), "Promo 10.10"),
]
WEEKDAY = {"STORE": [0.8, 0.8, 0.85, 0.9, 1.0, 1.5, 1.45], "B2B": [1.2, 1.2, 1.2, 1.2, 1.1, 0.3, 0.0],
           "SHOPEE": [1.0, 0.95, 0.95, 1.0, 1.05, 1.0, 1.05], "TOKPED": [1.0, 0.95, 0.95, 1.0, 1.05, 1.0, 1.05],
           "TIKTOK": [0.8, 0.9, 1.3, 0.9, 1.3, 1.5, 1.0], "INSTAGRAM": [1.0, 1.0, 1.0, 1.0, 1.1, 1.0, 0.9]}

# ---- Biaya operasional bulanan (dummy). Tanggal = hari dalam bulan.
MONTHLY_COSTS = {
    "rent_toko": 12_000_000, "rent_gudang": 6_500_000, "utilities": 4_200_000,
    "kol_agency": [0, 4_000_000, 5_000_000, 5_500_000],   # host live dimulai Agustus
    "ads": {"INSTAGRAM": 2_500_000, "TIKTOK": [1_500_000, 3_000_000, 4_000_000, 4_500_000],
            "SHOPEE": [2_000_000, 2_800_000, 3_500_000, 3_800_000], "TOKPED": [800_000, 1_000_000, 1_200_000, 1_200_000]},
    "packaging_pct": 2.2,            # % dari DPP penjualan non-toko (kemasan, bubble wrap, kartu ucapan)
    "shipping_pct": 2.8,             # % dari DPP B2B + Instagram (ongkir yang ditanggung penjual)
    "bank_fee": 185_000,
    "maintenance": 1_350_000,
}
CLOTH_PRICE_RISE = {"from": dt.date(2026, 9, 1), "pct": 8.0}   # kenaikan harga kain Sept -> tekanan margin
OPENING = {"bank": 140_000_000, "cash": 6_500_000, "equipment": 43_500_000,
           "ar": [("Butik Kebaya Denpasar Rani", 12_480_000, "2026-06-12", "2026-07-12")],
           "ap": [("CV Tekstil Pekalongan Mulia", 18_650_000, "2026-06-15", "2026-07-15")]}

CATEGORIES = [
    {"name": "Batik Tulis", "cost_method": "fifo"},
    {"name": "Batik Cap", "cost_method": "average"},
    {"name": "Batik Printing", "cost_method": "average"},
    {"name": "Aksesoris & Kain", "cost_method": "average"},
    {"name": "Bahan Baku", "cost_method": "average"},
]

# ---- Bahan baku: sku, nama, satuan, harga beli (ex PPN), pemasok
RAW = [
    ("RM-KAIN-CAP", "Kain Katun Batik Cap (per meter)", "m", 42_000, "CV Tekstil Pekalongan Mulia"),
    ("RM-KAIN-PRT", "Kain Katun Printing Motif (per meter)", "m", 18_000, "PT Kain Printing Bandung Sejahtera"),
    ("RM-KAIN-RAY", "Kain Rayon Printing (per meter)", "m", 26_000, "PT Kain Printing Bandung Sejahtera"),
    ("RM-ACC-SET", "Aksesori Jahit Set (kancing, benang, furing, label)", "Unit", 9_000, "UD Aksesori Jahit Denpasar"),
]
# ---- Barang jadi buatan sendiri (subkontrak penjahit): sku, nama, kategori, harga jual ex PPN, bobot permintaan,
#      (bahan, meter), jumlah set aksesori, ongkos jahit/pcs, pola gambar, warna
MADE = [
    ("BC-KMJ-001", "Kemeja Batik Cap Kawung Pria", "Batik Cap", 279_000, 5, ("RM-KAIN-CAP", 2.2), 1, 32_000, "kawung", "indigo"),
    ("BC-KMJ-002", "Kemeja Batik Cap Lasem Slimfit", "Batik Cap", 309_000, 4, ("RM-KAIN-CAP", 2.2), 1, 34_000, "lasem", "maroon"),
    ("BC-KMJ-003", "Kemeja Batik Cap Seragam Lengan Panjang", "Batik Cap", 289_000, 3, ("RM-KAIN-CAP", 2.3), 1, 33_000, "parang", "brown"),
    ("BC-BLS-001", "Blouse Batik Cap Truntum Wanita", "Batik Cap", 249_000, 5, ("RM-KAIN-CAP", 1.8), 1, 28_000, "truntum", "teal"),
    ("BC-DRS-001", "Dress Batik Cap Sekar Jagad", "Batik Cap", 369_000, 5, ("RM-KAIN-CAP", 2.6), 1, 45_000, "sekarjagad", "plum"),
    ("BC-SRB-001", "Sarimbit Batik Cap Couple Set", "Batik Cap", 589_000, 4, ("RM-KAIN-CAP", 4.6), 2, 75_000, "parang", "indigo"),
    ("BC-KBY-001", "Kebaya Modern Batik Cap Truntum", "Batik Cap", 439_000, 3, ("RM-KAIN-CAP", 2.4), 2, 60_000, "truntum", "maroon"),
    ("BP-KMJ-001", "Kemeja Batik Printing Motif Modern", "Batik Printing", 159_000, 4, ("RM-KAIN-PRT", 2.2), 1, 30_000, "megamendung", "teal"),
    ("BP-DRS-001", "Dress Batik Printing Kasual", "Batik Printing", 215_000, 4, ("RM-KAIN-RAY", 2.4), 1, 40_000, "kawung", "plum"),
    ("BP-OTR-001", "Outer Batik Printing Cardigan", "Batik Printing", 229_000, 3, ("RM-KAIN-RAY", 2.0), 1, 38_000, "lasem", "brown"),
    ("BP-KDS-001", "Kemeja Anak Batik Printing", "Batik Printing", 129_000, 2, ("RM-KAIN-PRT", 1.2), 1, 22_000, "megamendung", "indigo"),
    ("BP-BLS-001", "Blouse Batik Printing Harian", "Batik Printing", 169_000, 3, ("RM-KAIN-RAY", 1.8), 1, 27_000, "truntum", "teal"),
]
# ---- Barang jadi beli jadi dari pengrajin: sku, nama, kategori, HPP beli (ex PPN), harga jual, bobot, pemasok, pola, warna
BOUGHT = [
    ("BT-KMJ-001", "Kemeja Batik Tulis Parang Pria", "Batik Tulis", 310_000, 659_000, 3, "Pengrajin Batik Tulis Solo", "parang", "brown"),
    ("BT-DRS-001", "Dress Batik Tulis Mega Mendung", "Batik Tulis", 395_000, 829_000, 2, "Pengrajin Batik Tulis Cirebon", "megamendung", "indigo"),
    ("BT-KAI-001", "Kain Batik Tulis Sidomukti 2m", "Batik Tulis", 520_000, 1_090_000, 2, "Pengrajin Batik Tulis Yogya", "kawung", "maroon"),
    ("AK-SCF-001", "Scarf Batik Sutra Printing", "Aksesoris & Kain", 55_000, 149_000, 3, "Pengrajin Batik Pekalongan", "sekarjagad", "plum"),
    ("AK-MSK-001", "Masker & Pouch Batik Set", "Aksesoris & Kain", 18_000, 55_000, 2, "UD Aksesori Jahit Denpasar", "kawung", "teal"),
    ("AK-TAS-001", "Tote Bag Batik Cap", "Aksesoris & Kain", 42_000, 109_000, 2, "Pengrajin Batik Pekalongan", "lasem", "brown"),
    ("AK-KAI-002", "Kain Batik Cap Panjang 2m", "Aksesoris & Kain", 85_000, 209_000, 3, "Pengrajin Batik Pekalongan", "parang", "maroon"),
]
# penjahit subkontrak (Bali): nama, kota, PKP?, kapasitas pcs/minggu, produk utama (awalan sku)
TAILORS = [
    ("Konveksi Ni Made Sari", "Gianyar", False, 90, ("BC-KMJ", "BC-BLS")),
    ("Penjahit Bu Wayan Tabanan", "Tabanan", False, 70, ("BC-DRS", "BC-KBY", "BP-DRS")),
    ("Taylor Ketut Jaya", "Denpasar", False, 80, ("BC-SRB", "BP-KDS", "BP-BLS")),
    ("CV Garment Dewata", "Badung", True, 120, ("BP-KMJ", "BP-OTR", "BC-KMJ-003")),
]
SUPPLIER_PKP = {   # nama -> (PKP?, hari tempo)
    "CV Tekstil Pekalongan Mulia": (True, 30), "PT Kain Printing Bandung Sejahtera": (True, 30),
    "UD Aksesori Jahit Denpasar": (False, 0), "Pengrajin Batik Tulis Solo": (False, 14),
    "Pengrajin Batik Tulis Cirebon": (False, 14), "Pengrajin Batik Tulis Yogya": (False, 14),
    "Pengrajin Batik Pekalongan": (False, 14),
}

# Mitra jasa / platform (kota, PKP)
SERVICE_PARTNERS = {
    "landlord_toko": ("CV Sewa Ruko Sesetan Permai", "Denpasar"),
    "landlord_gudang": ("Bapak I Wayan Sudarta (Sewa Gudang)", "Badung"),
    "utility": ("PLN & Provider Internet Bali", "Denpasar"),
    "agency": ("PT Live Host Kreatif Dewata", "Denpasar"),
    "packaging": ("Toko Kemasan Mandiri Denpasar", "Denpasar"),
    "meta": ("Meta Ads (Instagram)", "Jakarta"), "tiktok_ads": ("TikTok Ads", "Jakarta"),
    "shopee_ads": ("Shopee Ads", "Jakarta"), "tokped_ads": ("Tokopedia Ads", "Jakarta"),
    "shopee_platform": ("Shopee International Indonesia", "Jakarta"),
    "tokped_platform": ("PT Tokopedia (Fee Platform)", "Jakarta"),
    "tiktok_platform": ("TikTok Shop Indonesia", "Jakarta"),
    "gateway": ("Payment Gateway Provider", "Jakarta"), "bank": ("Bank BCA", "Jakarta"),
    "ekspedisi": ("PT Ekspedisi Nusantara Cepat", "Denpasar"),
    "maint": ("CV Servis Dewata Teknik", "Denpasar"),
    "resto": ("Rumah Makan Bumbu Bali (Jamuan Klien)", "Denpasar"),
    "ads_agency": ("Studio Foto & Video Pelangi", "Denpasar"),
    "camera": ("Toko Kamera & Elektronik Dewata", "Denpasar"),
}

# ---- Pelanggan
BALI_AREAS = {
    "Denpasar": [("Sesetan", "80223"), ("Renon", "80235"), ("Sanur", "80228"), ("Panjer", "80234"),
                 ("Dauh Puri", "80113"), ("Pemogan", "80221"), ("Kesiman", "80237"), ("Tegal Harum", "80111")],
    "Badung": [("Kuta", "80361"), ("Seminyak", "80361"), ("Canggu", "80361"), ("Jimbaran", "80361"),
               ("Nusa Dua", "80363"), ("Mengwi", "80351"), ("Dalung", "80352"), ("Sading", "80351")],
    "Gianyar": [("Ubud", "80571"), ("Sukawati", "80582"), ("Gianyar", "80511"), ("Tegallalang", "80561"), ("Blahbatuh", "80581")],
    "Tabanan": [("Tabanan Kota", "82111"), ("Kediri", "82121"), ("Penebel", "82152")],
    "Klungkung": [("Semarapura", "80751")], "Bangli": [("Bangli Kota", "80611")],
    "Karangasem": [("Amlapura", "80811")], "Buleleng": [("Singaraja", "81111"), ("Lovina", "81151")],
    "Jembrana": [("Negara", "82211")],
}
BALI_CITY_W = {"Denpasar": 34, "Badung": 30, "Gianyar": 14, "Tabanan": 7, "Klungkung": 3, "Bangli": 2, "Karangasem": 2,
               "Buleleng": 5, "Jembrana": 3}
OUT_OF_BALI = [   # kota, provinsi (kode state Odoo), kode pos dasar, bobot
    ("Jakarta Selatan", "JK", "12150", 14), ("Bandung", "JB", "40115", 8), ("Surabaya", "JI", "60241", 11),
    ("Malang", "JI", "65145", 4), ("Yogyakarta", "YO", "55281", 6), ("Semarang", "JT", "50241", 5),
    ("Makassar", "SN", "90231", 4), ("Mataram", "NB", "83121", 5), ("Kupang", "NT", "85111", 2),
    ("Balikpapan", "KI", "76114", 3), ("Tangerang", "BT", "15111", 7), ("Bekasi", "JB", "17141", 6),
    ("Depok", "JB", "16411", 4), ("Solo", "JT", "57141", 3), ("Medan", "SU", "20112", 3),
]
FIRST_BALI = ["Wayan", "Made", "Nyoman", "Ketut", "Putu", "Kadek", "Komang", "Gede", "Luh", "Ayu", "Gusti", "Dewa", "Agung", "Ida Bagus"]
LAST_BALI = ["Suartana", "Wijaya", "Artha", "Pratiwi", "Mahendra", "Sudiarta", "Adnyana", "Suryani", "Kusuma", "Permana",
             "Saputra", "Wirawan", "Widiastuti", "Santika", "Antara", "Darmawan", "Lestari", "Utami", "Dewi", "Putra"]
FIRST_ID = ["Budi", "Siti", "Agus", "Rina", "Dewi", "Hendra", "Yuliana", "Fajar", "Indah", "Rizky", "Ahmad", "Nur", "Eka",
            "Dian", "Andi", "Lina", "Joko", "Maya", "Reza", "Tika"]
LAST_ID = ["Santoso", "Rahmawati", "Hartono", "Marlina", "Kartika", "Gunawan", "Nugroho", "Permata", "Pratama", "Hidayat",
           "Wulandari", "Setiawan", "Kurniawan", "Anggraini", "Susanto", "Handayani", "Firmansyah", "Puspita"]
STREETS = ["Jl. Raya", "Jl. Teuku Umar", "Jl. Sunset Road", "Jl. By Pass Ngurah Rai", "Jl. Gatot Subroto", "Jl. Hayam Wuruk",
           "Jl. Imam Bonjol", "Jl. Pulau Misol", "Jl. WR Supratman", "Jl. Raya Mas", "Jl. Gunung Agung", "Jl. Diponegoro",
           "Jl. Melati", "Jl. Kenanga", "Jl. Cempaka", "Gg. Mawar"]
RESELLERS = [   # nama, kota, provinsi, diskon %, termin (hari), PKP?
    ("Butik Kebaya Denpasar Rani", "Denpasar", "BA", 30, 30, False), ("Toko Batik Ubud Sari", "Gianyar", "BA", 30, 30, False),
    ("Galeri Oleh-Oleh Sukawati", "Gianyar", "BA", 32, 30, True), ("Bali Souvenir Kuta Corner", "Badung", "BA", 28, 14, True),
    ("Pasar Seni Batik Sanur (Ni Luh Rai)", "Denpasar", "BA", 30, 30, False), ("Rumah Sandang Singaraja", "Buleleng", "BA", 28, 30, False),
    ("Batik Lombok Mataram Trade", "Mataram", "NB", 27, 30, True), ("Toko Sandang Jaya Makassar", "Makassar", "SN", 26, 45, True),
    ("Rumah Batik Surabaya Online (Dewi)", "Surabaya", "JI", 28, 30, False), ("Lapak Batik Jakarta Selatan", "Jakarta Selatan", "JK", 27, 30, True),
    ("Butik Nusantara Yogyakarta", "Yogyakarta", "YO", 28, 30, False), ("Dewata Fashion Hub", "Badung", "BA", 31, 30, True),
]
CORPORATES = [  # nama, kota, jenis, PKP
    ("PT Dwipa Segara Hospitality", "Badung", "hotel", True), ("CV Arta Dharma Kreasi", "Denpasar", "kantor", True),
    ("Yayasan Pendidikan Widya Dharma", "Denpasar", "sekolah", False), ("Koperasi Karyawan Bumi Sari", "Tabanan", "koperasi", False),
    ("PT Pantai Indah Resort Management", "Badung", "hotel", True), ("PT Gapura Wisata Nusantara", "Gianyar", "travel", True),
    ("BPR Dewata Mandiri (Sampel)", "Denpasar", "bank", True), ("PT Sinar Bali Logistik", "Badung", "kantor", True),
]
