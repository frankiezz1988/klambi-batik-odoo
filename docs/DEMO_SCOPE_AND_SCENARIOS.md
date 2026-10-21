# Demo Klambi Bali: cakupan, data, dan skenario

Dokumen ini menjelaskan **apa yang ada (dan tidak ada) di demo**, **bagaimana datanya dibangun**, dan **skenario langkah-demi-langkah beserta angka acuan**, supaya tampilan di Odoo (Railway/VPS) dapat dicocokkan baris-per-baris dengan sandbox. Pencocokan data otomatis dijelaskan di [`VERIFY.md`](VERIFY.md).

Semua data bersifat **fiktif** (nama orang/usaha, NPWP, rekening). Periode data: **1 Juli – 17 Oktober 2026**, dengan saldo awal 30 Juni 2026. "Hari ini" dalam cerita = 17 Oktober 2026.

---

## 1. Posisi demo terhadap proposal

Proposal ("Implementasi Odoo Community untuk KlambiBali", 2 Okt 2026) mencakup Manufacturing, Inventory, Multi-Warehouse, Barcode, Marketplace, POS, Accounting, HR. **Demo ini difokuskan pada Accounting** (prioritas 8 di proposal) dengan rantai transaksi pendukung yang cukup agar angka akuntansinya *berasal dari transaksi*, bukan diketik. Rantai produksi **subkontrak jahit** (beli bahan → serah ke penjahit → terima barang jadi → QC → HPP per batch → penjualan) tersedia lengkap lewat addon `batik_id_production`; penjelasan dan skenarionya ada di [`PRODUKSI_JAHIT.md`](PRODUKSI_JAHIT.md). Modul custom yang bisa ditunda sengaja **tidak** dibuat.

Legenda: ✔ tercakup di demo · ◐ sebagian (native saja, tanpa custom) · ✘ belum (ditunda; bagian dari fase implementasi, bukan demo akuntansi)

| # | Pain point / bagian proposal | Status | Yang ada di demo | Yang belum (ditunda) |
|---|---|:-:|---|---|
| 1 | Miss stock & penyebabnya | ◐ | Stok hanya berubah lewat dokumen (receipt, transfer, MO, penjualan, scrap, adjustment). Stock opname 30 Sep dengan selisih per SKU + jurnal selisihnya. Riwayat pergerakan native per produk. | *Stock Trace* satu layar dan laporan *Stock Movement Reconciliation* (custom). |
| 2 | Kain → pakaian jadi, sisa & waste | ✔ (subkontrak) | 4 bahan baku (satuan meter / set) → 12 barang jadi lewat **BoM subkontrak** ke 4 penjahit Bali; **130 batch produksi** (1 PO jahit = 1 batch = 1 lot), serah bahan dengan buffer 6%, susut kain dilaporkan penjahit, **123 inspeksi QC** (lulus/rework/reject per jenis cacat), HPP per batch (bahan + susut + upah − potongan reject), efisiensi bahan dan performa penjahit. | MO internal (jahit sendiri) dengan work order & overhead, konversi yard↔meter, landed cost per batch. |
| 3 | Perpindahan antar-gudang | ◐ | 2 gudang (Gudang Utama + Toko Denpasar) dan lokasi Sortase (QC) → Stok Utama → Marketplace; transfer internal terjadwal (Senin/Kamis). | Alur Request → Approval → In-transit → Received dengan scan dan selisih terima (OCA tier validation + custom). |
| 4 | Barcode / scan | ✘ | Tidak didemokan (POS native mampu membaca barcode, tidak diperagakan). | Generator barcode, label, aplikasi scan HP/gudang (custom, inti nilai tambah proposal). |
| 5 | 500 resi marketplace | ✘ | Order marketplace sudah ada per channel (Shopee, Tokopedia, TikTok Live), nomor pesanan marketplace tersimpan di referensi pelanggan (`SPE-…`, `TKP-…`, `TTK-…`), **settlement/escrow per channel** lengkap dengan komisi, biaya layanan, PPN fee. | Import massal Excel, mapping SKU, error per baris, pencarian resi (custom); konektor API (fase 2). |
| 6 | Retur | ◐ | 28 nota kredit (retur pelanggan); retur "cacat" masuk scrap (reject), retur layak jual di-restock; denda & koreksi komisi marketplace tercatat. | Alur RMA/karantina berbasis resi dan laporan alasan retur (custom). |
| 7 | POS & live selling | ◐ | POS **Kasir Toko Denpasar** sudah dikonfigurasi (metode Tunai, QRIS, Kartu Debit/EDC, gudang & stok toko terpisah, produk tampil di POS) dan bisa dicoba langsung (`kasir@`). **Penjualan toko historis dicatat sebagai pesanan + faktur** channel Toko Denpasar dengan pembayaran tunai/QRIS, *bukan sesi POS* (tidak ada order/sesi POS di data), lengkap dengan setoran kas ke bank dan selisih kas. *Live* TikTok sebagai channel sendiri dengan biaya host/KOL/afiliasi. | Gudang D khusus live dan alur transfer balik sisa live (konfigurasi + custom ringan). |
| 8 | Pembelian kain → persediaan → hutang | ✔ | PO bahan baku → penerimaan → Sortase (QC) → bill vendor → hutang dengan jatuh tempo; penerimaan parsial; pembayaran terlambat; PPN masukan. | — |
| 9 | Laporan keuangan dari sumber sinkron | ✔ | **Inti demo ini**: neraca saldo, buku besar, laba rugi & neraca (MIS Builder), arus kas, umur piutang/hutang, laba rugi **per channel**, anggaran vs aktual, nilai persediaan vs GL, pajak (PPN/PPh). | Format laporan custom lanjutan sesuai permintaan klien. |
| 10 | Approval & audit trail | ◐ | 3 peran demo (akuntan, owner read-only, kasir); audit trail (OCA auditlog, 12 aturan) untuk dokumen & master; jurnal penjualan/pembelian terkunci hash; kunci periode tersedia. | Approval bertingkat (adjustment, perubahan harga, pembatalan struk) — OCA tier validation + konfigurasi. |
| 11 | Dashboard owner | ◐ | Laporan MIS Builder bulanan & per channel sebagai bahan dashboard; anggaran vs aktual. | Dashboard owner interaktif (custom). |
| HR | Absensi, payroll, pajak | ◐ | Payroll ringan 9 karyawan: gaji, tunjangan, **BPJS** (karyawan & perusahaan), **PPh 21 TER**, jurnal gaji otomatis dibagi per cost center. | Absensi/cuti/kalender libur Bali, upah borongan penjahit, THR/kasbon, bukti potong 1721-A1. |

**Demo script proposal (Bagian 5, 11 langkah)** pada demo ini:

| Langkah proposal | Status | Padanan di demo |
|---|:-:|---|
| 1 Beli 100 yard kain (PO, receipt, hutang) | ✔ | PO bahan baku (meter) → penerimaan → bill → hutang. |
| 2 Raw material masuk, nilai bertambah | ✔ | Penerimaan 2-langkah ke Sortase (QC) → Stok Utama; valuasi masuk akun Persediaan. |
| 3 MO berdasarkan BoM, waste tercatat | ✔ (subkontrak) | PO jasa jahit memicu MO subkontrak + pasokan bahan ke penjahit; susut kain dan reject QC = scrap berlot; HPP per batch. |
| 4 Jadi produk, assign barcode | ✘ | Ditunda. |
| 5 Masuk Gudang B, transfer ke C (approval, in transit) | ◐ | Transfer internal tanpa approval/scan. |
| 6 Scan saat terima di C, selisih | ✘ | Ditunda (opname menunjukkan selisih stok). |
| 7 Sebagian ke Gudang D (live) | ◐ | Transfer ke lokasi Marketplace + penjualan channel TikTok Live. |
| 8 Import 500 order marketplace | ✘ | Ditunda; order marketplace sudah ada sebagai data. |
| 9 Stok turun, HPP tercatat, jurnal otomatis | ✔ | Setiap pengiriman menjurnal HPP & persediaan (AVCO; FIFO untuk Batik Tulis). |
| 10 Laba rugi & inventory ter-update | ✔ | MIS Laba Rugi/Neraca, nilai persediaan. |
| 11 Lacak resi dan retur | ◐ | Dari nomor pesanan marketplace → order → pengiriman → faktur → jurnal HPP → nota kredit/scrap. |

---

## 2. Profil bisnis & cerita data

**Klambi Bali** — retail busana batik berbasis Denpasar (zona WITA), satu perusahaan, mata uang **hanya IDR**. Barang jadi dibuat oleh **penjahit/konveksi Bali** (subkontrak) dari kain yang dibeli perusahaan; sebagian dibeli jadi (aksesori dan batik tulis dari pengrajin Yogya/Cirebon/Pekalongan).

**Rantai pasok:** pemasok kain (CV Tekstil Pekalongan Mulia, PT Kain Printing Bandung Sejahtera, UD Aksesori Jahit Denpasar) → *Sortase (QC)* → *Stok Utama* → *Marketplace* (stok untuk Shopee/Tokopedia/TikTok/IG) | *Stok Toko* (Toko Denpasar). Bahan baku dikirim ke penjahit (lokasi Subkontrak); barang jadi diterima di Sortase.

**Channel penjualan (tim penjualan & analytic):** Toko Denpasar (POS), Marketplace – Shopee, Marketplace – Tokopedia, Live – TikTok Shop, Instagram & WhatsApp, B2B – Reseller & Korporat.

**Persona pelanggan (simulasi kapasitas pembeli):** pembeli toko (walk-in perorangan), pembeli marketplace (mayoritas dari luar Bali, nama disamarkan seperti `Nur ***96`), pembeli live TikTok, pelanggan IG/WA, **12 reseller** dan **8 korporat/instansi** (B2B, tempo 30 hari). ±300 pelanggan perorangan dengan alamat dominan Bali (Denpasar, Badung, Gianyar, Tabanan, Buleleng, dll.) dan sebagian luar Bali.

**Cerita per bulan** (angka lihat Bagian 4):

| Bulan | Kejadian utama |
|---|---|
| Juli | Bulan pertama data. Order B2B besar (reseller & korporat/seragam) mengangkat omzet; laba baik. |
| Agustus | Perayaan 17-an. Host live TikTok mulai (Agu), iklan marketplace naik, kamera/lighting live dibeli (aset 3 Agu). Biaya naik lebih cepat dari omzet, laba menipis. |
| September | 9.9 dan TikTok Live ramai. **Harga kain naik 8% mulai 1 Sep** menekan margin. Opname stok 30 Sep (selisih). Penjahit terlambat pada model seragam/sarimbit (akhir Sep). |
| Oktober (s.d. 17) | Hari Batik 2 Okt (puncak harian), 10.10. Harga jual Dress Sekar Jagad & Sarimbit dinaikkan 1 Okt (tercatat di audit log). **PPh 22 marketplace belum berlaku** (ditunda sampai 1 Nov 2026). Bulan belum ditutup (penyusutan, BPJS, PPh Final & rekap PPN Okt belum dibukukan). |

---

## 3. Konfigurasi yang sudah di-setup

| Area | Isi |
|---|---|
| Perusahaan | Klambi Bali, Denpasar, zona waktu Asia/Makassar (WITA), bahasa id_ID. |
| Mata uang | **IDR saja** aktif (USD & lainnya dinonaktifkan). |
| Bagan akun | CoA retail batik (±175 akun): kas/bank per kanal, **saldo escrow per marketplace**, persediaan, PPN masukan/keluaran, utang PPh 21/23/4(2)/Final, BPJS, aset tetap & akumulasi, HPP, selisih persediaan, beban per channel (komisi, layanan, afiliasi, MDR, denda, iklan, KOL, ongkir, kemasan), beban umum (gaji, BPJS, sewa toko & gudang, listrik, perawatan, bank, jamuan non-kredit, penyusutan, PPh Final). |
| Pajak | **PPN 12% × DPP 11/12 = efektif 11%** (penjualan & pembelian), PPh 23 jasa 2%, PPh 4(2) sewa 10% (dipotong), PPh Final UMKM 0,5%, PPh 21 TER. Pajak bawaan l10n_id diarsipkan; PPh 22 marketplace dijadwalkan 1 Nov 2026. |
| Analytic | Plan **Channel Penjualan** (6 channel) dan plan **Cost Center** (Kantor Pusat, Gudang & Produksi, Toko Denpasar); 100% baris pendapatan, HPP, dan beban berisi analytic. |
| Gudang & lokasi | Gudang Utama (`WH`, penerimaan 2-langkah): *Sortase (QC)* → *Stok Utama*, lokasi *Marketplace*; gudang *Toko Denpasar* (`TKO`): *Stok Toko*; lokasi *Subkontrak* (di penjahit). |
| Costing | Batik Tulis = **FIFO**; Batik Cap, Printing, Aksesoris, Bahan Baku = **AVCO**; valuasi otomatis (real-time). |
| Produk | 4 bahan baku, 12 barang jadi buatan sendiri (BoM subkontrak), 7 barang beli jadi (aksesori & batik tulis dari pengrajin); foto produk (pola parang, kawung, megamendung, truntum, lasem, sekar jagad). |
| Daftar harga | Default, Reseller (diskon grosir 30%), Korporat (diskon 12%). |
| POS | *Kasir Toko Denpasar*: metode Tunai, QRIS, Kartu Debit (EDC). |
| Jurnal | INV (penjualan, hash), TAGIH (pembelian, hash), BCA (operasional), BCA2 (rekening rekonsiliasi), KTOK (kas toko), QRIS, SHPE/TKPD/TTOK (escrow), PGW, SETL (settlement & penyesuaian), STJ (valuasi persediaan), PAJAK, PYRL (gaji), ASET. |
| Aset tetap | 5 aset peralatan (garis lurus 4 tahun), penyusutan bulanan otomatis, aset saldo awal + kamera live (Agu). |
| Anggaran | Anggaran Operasional 2026 (Jul–Okt): pendapatan, HPP, beban channel, beban umum. |
| Laporan MIS | Laba Rugi Bulanan, Neraca Bulanan, Cash Flow, **Laba Rugi per Channel** (+ satu laporan per channel). |
| Audit & kontrol | OCA auditlog (12 model), jurnal INV & TAGIH terkunci hash; modul `account_analytic_required`, `account_invoice_constraint_chronology`, kunci tanggal (OCA) terpasang. |
| Pengguna | `admin` (semua hak bisnis), `accountant@batik-demo.example` (Akuntan), `owner@batik-demo.example` (read-only audit), `kasir@batik-demo.example` (kasir/POS). Password demo `demo1234` untuk tiga terakhir. **Ganti semua password bila instance terbuka publik.** |
| Payroll | 9 karyawan (kasir, admin, gudang & QC, manajer toko, host live), BPJS, PPh 21 TER; run Jul–Sep sudah diposting. |

---

## 4. Angka acuan (hasil audit sandbox)

Angka berikut diambil dari snapshot referensi (`deploy/seed/reference_snapshot.zip`) dan harus **sama persis** di Railway/VPS yang di-restore dari dump yang sama.

**Omzet penjualan (DPP, order terkonfirmasi)**

| Bulan | Order (terkonfirmasi) | Omzet DPP (Rp jt) | AOV (Rp) |
|---|---:|---:|---:|
| Jul | 227 | 226,6 | 998.213 |
| Agu | 312 | 253,5 | 812.350 |
| Sep | 335 | 299,3 | 893.446 |
| Okt (s.d. 17) | 201 | 188,2 | 936.565 |
| **Total** | **1075** | **967,6** | 900.094 |

**Omzet per channel (Rp juta)**

| Channel | Jul | Agu | Sep | Okt (s.d. 17) | Total |
|---|---:|---:|---:|---:|---:|
| B2B | 66,5 | 43,7 | 73,4 | 56,9 | 240,5 |
| Instagram & WhatsApp | 16,8 | 14,9 | 28,5 | 11,9 | 72,1 |
| Shopee | 44,4 | 60,0 | 62,4 | 37,1 | 203,9 |
| TikTok Live | 23,7 | 46,9 | 54,2 | 30,7 | 155,5 |
| Toko Denpasar | 59,0 | 72,1 | 65,9 | 42,5 | 239,4 |
| Tokopedia | 16,2 | 15,9 | 15,0 | 9,1 | 56,2 |

**Laba rugi per bulan (Rp juta)** — *penjualan bersih setelah retur; ** sebelum pajak penghasilan badan; PPh Final UMKM sudah termasuk biaya operasional.

| Bulan | Pendapatan | HPP | Laba kotor | Margin kotor | Biaya operasional* | Penyusutan | Laba bersih** |
|---|---:|---:|---:|---:|---:|---:|---:|
| Jul | 223,6 | 116,3 | 107,3 | 48.0% | 87,3 | 1,0 | 19,1 |
| Agu | 242,5 | 127,3 | 115,2 | 47.5% | 106,0 | 1,3 | 7,9 |
| Sep | 290,9 | 157,0 | 134,0 | 46.0% | 112,0 | 1,4 | 20,6 |
| Okt (s.d. 17) | 185,1 | 103,6 | 81,5 | 44.0% | 81,5 | 0,0 | 0,0 |
| **Kumulatif** | **942,2** | **504,2** | **438,0** | **46.5%** | **386,8** | **3,7** | **47,6** |

Selisih "omzet order" (967,6 jt) vs "pendapatan akun penjualan" (943,8 jt) = **Rp 25,4 jt retur** (nota kredit).

**Kontribusi per channel (kumulatif Jul–17 Okt, Rp juta; tanpa biaya umum kantor/toko/gudang)**

| Channel | Pendapatan | HPP | Beban channel (komisi, iklan, KOL, kemasan, ongkir) | Kontribusi | % kontribusi |
|---|---:|---:|---:|---:|---:|
| Toko Denpasar (POS) | 236,2 | 115,1 | 0,9 | 120,2 | 50.9% |
| B2B - Reseller & Korporat | 236,0 | 134,4 | 12,0 | 89,6 | 38.0% |
| Marketplace - Shopee | 197,4 | 100,9 | 39,7 | 56,8 | 28.8% |
| Live - TikTok Shop | 146,3 | 80,3 | 52,8 | 13,1 | 9.0% |
| Instagram & WhatsApp | 70,8 | 34,8 | 14,5 | 21,5 | 30.4% |
| Marketplace - Tokopedia | 55,4 | 27,8 | 9,9 | 17,7 | 31.9% |

Bacaan cerita: toko & B2B penyumbang laba terbesar; **TikTok Live** omzet besar tetapi kontribusi hanya ±9% (iklan + host + afiliasi); Shopee sehat; Tokopedia & Instagram kecil tapi stabil.

**Posisi akun utama per 17 Okt 2026**

| Akun | Saldo (Rp) |
|---|---:|
| 1110101 Kas Toko | 8.798.810 |
| 1110201 Bank BCA - Operasional | 228.167.987 |
| 1110202 Bank - Settlement QRIS/EDC | 5.814.430 |
| 1110301 Saldo Escrow Shopee | 14.047.258 |
| 1110302 Saldo Escrow Tokopedia | 6.674.924 |
| 1110303 Saldo Escrow TikTok Shop | 18.157.092 |
| 1110304 Saldo Payment Gateway | 626.571 |
| 11210010 Piutang Usaha | 112.282.982 |
| 1130101 Persediaan Barang Dagang | 117.413.564 |
| 1140101 PPN Masukan | 9.882.705 |
| 1210101 Peralatan (harga perolehan) | 65.500.000 |
| 1210102 Akumulasi penyusutan | -3.663.784 |
| 21100010 Hutang Usaha | -186.096.860 |
| 2130101 PPN Keluaran | -20.365.401 |
| 2130202 Utang PPh 23 | -1.268.006 |
| 2130203 Utang PPh 4(2) Final | -3.700.000 |
| 2130301 Utang BPJS | -5.752.960 |
| 2140101 Biaya masih harus dibayar | -22.154.839 |
| 3110101 Modal disetor | -292.584.400 |

Total debit = total kredit (neraca saldo seimbang): **Rp 5.316.501.251**. Laba berjalan kumulatif ±Rp 47,6 jt.

**Umur piutang & hutang (per 17 Okt)**

| | Belum jatuh tempo | 1-30 hari | 31-60 hari | 61-90 hari | >90 hari | Total |
|---|---:|---:|---:|---:|---:|---:|
| Piutang (per 17 Okt) | 84.577.871 | 17.340.487 | 10.364.625 | 0 | 0 | 112.282.982 |
| Hutang (per 17 Okt) | 178.212.147 | 7.884.713 | 0 | 0 | 0 | 186.096.860 |

Anggaran vs aktual (pendapatan & HPP):

| Bulan | Pendapatan: anggaran | aktual | HPP: anggaran | aktual |
|---|---:|---:|---:|---:|
| Jul | 210,0 | 223,6 | 100,0 | 116,3 |
| Agu | 250,0 | 242,5 | 120,0 | 127,3 |
| Sep | 290,0 | 290,9 | 138,0 | 157,0 |

**Dokumen**

| Dokumen | Jumlah |
|---|---:|
| entry/posted | 1635 |
| in_invoice/posted | 203 |
| out_invoice/posted | 1075 |
| out_refund/posted | 28 |
| mo/confirmed | 9 |
| mo/done | 123 |
| picking/assigned | 8 |
| picking/cancel | 13 |
| picking/done | 1525 |
| purchase_order/purchase | 155 |
| sale_order/cancel | 13 |
| sale_order/sale | 1075 |

**Stok internal per lokasi (unit)**

| Lokasi | Qty |
|---|---:|
| Subkontrak | 1,010 |
| TKO/Stok Toko | 71 |
| WH/Marketplace | 93 |
| WH/Sortase (QC) | 54 |
| WH/Stok Utama | 431 |

Nilai persediaan GL akun 1130101 = **Rp 117.413.564**. Nilai valuasi per produk (jumlah `total_value`) berselisih **Rp 40.005 (0,03%)** terhadap GL; selisih ini belum ditelusuri sumbernya (dugaan: pembulatan biaya rata-rata pada scrap/opname) dan dicatat sebagai butir terbuka untuk UAT.

---

## 5. Skenario demo (±25 menit) dan titik cocok UI

Nama menu mengikuti antarmuka Indonesia yang sedang dipakai (sebagian menu OCA masih berbahasa Inggris). Kolom "Harus cocok" adalah angka yang bisa dibaca langsung di layar.

| # | Skenario | Jalur menu | Yang diperlihatkan | Harus cocok |
|---|---|---|---|---|
| 1 | **Peta channel** | Penjualan → Pesanan → Group by *Tim Penjualan* | 1.075 order terkonfirmasi (13 batal); AOV toko ±Rp 0,9 jt, Shopee ±Rp 0,5 jt, B2B ±Rp 10–13 jt; nomor pesanan marketplace di *Referensi Pelanggan* (mis. `SPE-260701-002`). | Total DPP Rp 967,6 jt |
| 2 | **Rantai pasok ringan** | Pembelian → Pesanan; Inventaris → Operasi | PO kain → Penerimaan (`WH/IN/…`) → Storage dari Sortase ke Stok Utama; PO jasa jahit → *Resupply Subkontraktor* + MO subkontrak + batch/lot; bill penjahit. Detail alur produksi: [`PRODUKSI_JAHIT.md`](PRODUKSI_JAHIT.md) (skenario 19–22). | 155 PO, 186 penerimaan, 154 storage, 60 resupply, 132 MO (123 selesai, 9 berjalan) |
| 3 | **Penerimaan parsial & penjahit terlambat** | Inventaris → penerimaan `WH/IN/00064`, `00143`, `00171` (backorder) | Tiga penerimaan berstatus backorder: asal PO P00045 (Konveksi Ni Made Sari, 7 Agu), P00110 (Penjahit Bu Wayan Tabanan, 18 Sep), P00131 (Bu Wayan Tabanan, 2 Okt); sebagian barang datang dulu, sisa menyusul beberapa hari kemudian. Empat batch terlambat 5–6 hari (`BTH-260807-032`, `BTH-260918-093`, `BTH-261002-105`, `BTH-261002-109`); terlihat di *Produksi Jahit → Batch Produksi* (kolom Terlambat). | 3 backorder, 4 batch terlambat |
| 4 | **Reject QC, susut kain & retur cacat** | Inventaris → Operasi → Scrap | 20 scrap *Reject QC* (23 pcs, jahitan cacat dll.), 123 scrap *Susut kain* (157 m, dilaporkan penjahit), dan 6 retur cacat pelanggan (15 pcs: SPE-260902-002, TTK-261006-001, TTK-260915-002, TKP-260908-001, TKP-260928-001, SPE-261002-003) → akun *Selisih Opname, Reject & Penyesuaian* (5130101) dengan analytic *Gudang & Produksi*. | 155 scrap |
| 5 | **HPP & costing** | Inventaris → Konfigurasi → Kategori Produk; buka satu pengiriman → jurnal valuasi | Batik Tulis FIFO, lainnya AVCO; jurnal HPP-Persediaan otomatis per pengiriman; HPP 52–54% dari penjualan. | Margin kotor Jul 48,0% · Agu 47,5% · Sep 46,0% |
| 6 | **Kenaikan harga kain 8%** | Laporan Laba Rugi Bulanan; HPP per SKU | Margin kotor turun dari 48,0% (Jul) ke 46,0% (Sep) dan 44,0% (Okt parsial). | Tabel Bagian 4 |
| 7 | **Toko** | Penjualan → Pesanan (tim *Toko Denpasar*); Penagihan → Jurnal `KTOK`, `QRIS`, `SETL` (setoran). POS → *Kasir Toko Denpasar* untuk mencoba transaksi baru | Tunai ±41% (95 pembayaran, Rp 111,5 jt) / QRIS & EDC ±59% (143 pembayaran, Rp 157,8 jt); setoran kas berkala ke bank dengan **selisih kas** kecil (7 kali, total Rp 365.000). Catatan: histori bukan sesi POS (lihat Bagian 1, #7). | Kas Toko Rp 8,8 jt |
| 8 | **Settlement marketplace** | Penagihan → Jurnal Entri (jurnal `SETL`), filter *Pencairan* | Escrow gross → bank net; komisi, biaya layanan, afiliasi, PPN fee; **denda Shopee Rp 175.000 (SETL/2026/09/0004)** dan **koreksi komisi afiliasi TikTok Rp 420.000 (SETL/2026/10/0006)**. | Saldo escrow Shopee 14,0 jt · Tokopedia 6,7 jt · TikTok 18,2 jt |
| 9 | **Profit per channel** | Penagihan → Laporan → MIS Reporting → *Laba Rugi per Channel* (kolom = channel) | Kontribusi per channel; TikTok vs Shopee vs B2B. | Tabel kontribusi Bagian 4 |
| 10 | **Laporan inti** | Penagihan → Laporan → OCA accounting reports (Trial Balance, General Ledger, Aged Partner) dan MIS (*Laba Rugi Bulanan*, *Neraca Bulanan*, *Cash Flow*) | Laporan lahir dari transaksi. Trial Balance 1 Jun–17 Okt: debit = kredit. | Rp 5.316.501.251 |
| 11 | **Piutang macet & hutang terlambat** | Laporan Partner / Aged Partner Balance | **INV/2026/00279** Batik Lombok Mataram Trade Rp 10,36 jt jatuh tempo 5 Sep (±42 hari lewat); bill `TAGIH/2026/09/0003` PT Kain Printing Bandung Rp 999.000 jatuh tempo 3 Okt, belum dibayar (dibayar terlambat sesuai pola). | Piutang 31–60 hari Rp 10.364.625 |
| 12 | **B2B tempo** | Penagihan → Faktur, filter tim B2B | Reseller/korporat (Koperasi Karyawan Bumi Sari, Rumah Sandang Singaraja, Lapak Batik Jakarta Selatan, …) dengan harga Reseller/Korporat dan jatuh tempo 30 hari. | Piutang Rp 112,3 jt |
| 13 | **Pajak** | Penagihan → Jurnal `PAJAK`; menu *Pajak ID* | Rekap PPN bulanan (keluaran − masukan), setoran PPN/PPh 21/23/4(2)/Final, iuran BPJS; PPN efektif 11% (12% × 11/12); jamuan klien **tanpa kredit PPN masukan** (`TAGIH/2026/08/0050`, `09/0028`, `10/0021`). Rekap Okt belum dibuat. | PPN Keluaran Rp 20,4 jt · Masukan Rp 9,9 jt |
| 14 | **Aset & penyusutan** | Penagihan → Assets | 5 aset, jadwal penyusutan bulanan; kamera & lighting live dibeli 3 Agu (Rp 22 jt). | Akumulasi Rp 3.663.784 |
| 15 | **Payroll & cost center** | Pajak ID/Karyawan & Penggajian; Jurnal `PYRL` | Gaji Jul Rp 36,1 jt, Agu & Sep Rp 40,4 jt (host live mulai Jul/Agu); BPJS; PPh 21 TER Rp 75.269/bulan; beban gaji dibagi ke 3 cost center. | 3 run posted |
| 16 | **Audit trail & kontrol** | Pengaturan (mode pengembang) → Teknis → Audit → Logs | Perubahan harga produk (Dress Sekar Jagad 369k→389k, Sarimbit 589k→619k) dan alamat pemilik ruko/lessor; jurnal terposting terkunci hash; `owner@` read-only. | 12 aturan audit aktif |
| 17 | **Rekonsiliasi bank** | Penagihan → Akuntansi → Reconcile (jurnal BCA2) | 5 mutasi bank belum direkonsiliasi (jasa kebersihan, servis AC, bunga, banner promo 10.10, biaya admin). | Saldo BCA2 −Rp 4.258.000 |
| 18 | **Anggaran vs aktual** | MIS Reporting → Anggaran Operasional 2026 | Pendapatan & HPP vs anggaran per bulan. | Tabel Bagian 4 |
| 19 | **Batch produksi jahit** | Produksi Jahit → Batch Produksi | 130 batch (`BTH-YYMMDD-nnn` = nomor lot) per baris PO jasa jahit; status Dipesan → Bahan diserahkan → Penerimaan sebagian → Menunggu QC → Selesai; contoh `BTH-261009-118` (Taylor Ketut Jaya, 30 pcs: lolos 29, reject 1, rework 1). | 130 batch, 121 selesai |
| 20 | **Serah bahan & saldo di penjahit** | Produksi Jahit → Saldo Bahan di Penjahit; Inventaris → Resupply Subkontraktor | Kain/aksesori diserahkan dengan buffer 6%; diserahkan − terpakai − susut = sisa di penjahit; saldo harus sama dengan stok lokasi *Subkontrak*. | Stok Subkontrak 1.010 unit; 60 resupply |
| 21 | **Inspeksi QC & analisis cacat** | Produksi Jahit → Inspeksi QC; Analisis | 123 inspeksi: temuan per jenis cacat (jahitan, ukuran, motif, noda, aksesori, label), disposisi reject (scrap) atau rework. | 23 pcs reject (0,9%), 50 pcs rework |
| 22 | **HPP per batch & performa penjahit** | Produksi Jahit → Analisis → HPP Batch | Bahan + susut + upah − potongan reject; HPP/pcs vs standar BoM; potongan upah reject di tagihan penjahit Rp 1.028.000. Reject: Bu Wayan Tabanan 2,0% (tertinggi), CV Garment Dewata 0,0%. | Σ potongan Rp 1.028.000 |

---

## 6. Katalog kasus tepi (edge case) yang sengaja ada

| Kasus | Di mana |
|---|---|
| Penerimaan parsial + backorder | `WH/IN/00064`, `WH/IN/00143`, `WH/IN/00171` |
| Penjahit terlambat 5–6 hari | 4 batch: `BTH-260807-032`, `BTH-260918-093`, `BTH-261002-105`, `BTH-261002-109` |
| Reject QC di Sortase | 20 scrap "Reject QC …" (23 pcs) + 123 scrap "Susut kain …" (157 m) |
| Retur cacat → scrap; retur layak → restock | 28 nota kredit `RINV/2026/…`; 6 scrap retur cacat (mis. TTK-261006-001) |
| Denda marketplace & koreksi komisi afiliasi | `SETL/2026/09/0004`, `SETL/2026/10/0006` |
| Selisih kas toko saat setoran | 7 entri `SETL` "Setoran kas toko ke bank" (Jul–Okt) |
| Pembelian PPN tidak dapat dikreditkan | jamuan klien (akun 6250101) |
| Piutang reseller macet 31–60 hari | `INV/2026/00279` |
| Hutang pemasok terlambat dibayar & parsial | bill PT Kain Printing Bandung (Sep) |
| Opname 30 Sep dengan selisih | 2 SKU disesuaikan: BC-KMJ-001 −2, AK-SCF-001 +1 (jurnal ke 5130101) |
| Bank belum rekonsiliasi | jurnal BCA2 (5 mutasi) |
| Kenaikan harga kain (HPP naik) | mulai 1 Sep |
| Perubahan harga jual (audit log) | 1 Okt |

---

## 7. Cara mencocokkan UI dengan data

1. Buka layar yang dimaksud (Bagian 5) dan baca angka di kolom "Harus cocok".
2. Untuk pencocokan menyeluruh, buat snapshot di Railway dan bandingkan dengan sandbox/`reference_snapshot.zip`: lihat [`VERIFY.md`](VERIFY.md). Hasilnya daftar selisih per dataset (jurnal, faktur, stok, partner, pajak, aset, payroll, dll.).
3. Perubahan yang Anda lakukan di Railway (mengubah harga, membuat faktur, login yang membuat sesi) akan muncul sebagai selisih — itu memang tujuannya.

## 8. Batasan & butir terbuka

- Data fiktif; tidak boleh dipakai sebagai laporan pajak.
- **PPh 22 marketplace** belum aktif di data (mulai 1 Nov 2026); ekspor **Coretax** di `batik_id_coretax` bersifat eksperimental/staging.
- Oktober belum ditutup (tanpa penyusutan, BPJS, PPh Final, rekap PPN bulan itu).
- Selisih nilai persediaan GL vs valuasi Rp 40.005 (lihat Bagian 4) — perlu ditelusuri bila akan dipakai sebagai bukti "persediaan = GL" di UAT.
- Produk bawaan POS "Tips" masih ada tetapi tidak dapat dijual.
- Fitur custom proposal yang ditunda: barcode/scan, import marketplace, approval bertingkat, Stock Trace, RMA/karantina, dashboard owner, absensi.
