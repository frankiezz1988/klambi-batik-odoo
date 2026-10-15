"""Parameter statutori. VERIFIKASI setiap tahun (batas upah & tarif BPJS berubah)."""
# Persentase terhadap upah
BPJS = {
    "jht_ee": 2.0, "jht_er": 3.7,      # Jaminan Hari Tua
    "jp_ee": 1.0, "jp_er": 2.0,        # Jaminan Pensiun (ada batas upah)
    "jkk_er": 0.24,                    # Jaminan Kecelakaan Kerja - kelompok risiko sangat rendah (0,24%-1,74%)
    "jkm_er": 0.30,                    # Jaminan Kematian
    "kes_ee": 1.0, "kes_er": 4.0,      # BPJS Kesehatan (ada batas upah)
}
JP_WAGE_CAP = 10_547_400      # contoh nilai tahun 2025; PERBARUI sesuai ketetapan BPJS Ketenagakerjaan tahun berjalan
KES_WAGE_CAP = 12_000_000

# Kategori TER (PMK 168/2023): A = TK/0, TK/1, K/0 ; B = TK/2, TK/3, K/1, K/2 ; C = K/3
PTKP_CHOICES = [("TK0", "TK/0"), ("TK1", "TK/1"), ("TK2", "TK/2"), ("TK3", "TK/3"),
                ("K0", "K/0"), ("K1", "K/1"), ("K2", "K/2"), ("K3", "K/3")]
TER_CATEGORY = {"TK0": "A", "TK1": "A", "K0": "A", "TK2": "B", "TK3": "B", "K1": "B", "K2": "B", "K3": "C"}
