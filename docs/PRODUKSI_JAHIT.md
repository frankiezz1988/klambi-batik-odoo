# Produksi jahit (subkontrak): dari bahan baku sampai HPP per batch

Dokumen ini menjawab pertanyaan "bagaimana proses manufaktur/assembly dan penanganan bahan baku Klambi Bali?". Semua yang tertulis di sini sudah ada di data demo dan bisa dibuka di Odoo; yang belum ada dicatat jujur di bagian **Batas dan backlog**.

## 1. Model bisnis (asumsi demo)
Klambi Bali tidak punya pabrik. Kain dan aksesori dibeli sendiri, lalu **diserahkan ke penjahit/konveksi Bali** yang menjahit dan mengirim barang jadi. Perusahaan membayar **upah jahit per pcs**. Ini **subkontrak** (*subcontracting*) di Odoo: bahan tetap milik Klambi Bali sampai dipakai penjahit.

Penjahit: Konveksi Ni Made Sari (Gianyar), Penjahit Bu Wayan Tabanan, Taylor Ketut Jaya (Denpasar), CV Garment Dewata (Badung, PKP).

## 2. Alur end-to-end dan di mana melihatnya di Odoo

| # | Langkah bisnis | Dokumen/aksi Odoo | Menu | Dampak persediaan dan akuntansi |
|---|---|---|---|---|
| 1 | Beli kain dan aksesori | PO bahan baku (satuan meter / set) → Penerimaan `WH/IN` ke **Sortase (QC)** → pindah ke **Stok Utama** | Pembelian → Pesanan; Inventaris → Operasi | Persediaan bahan bertambah (AVCO); bill vendor → hutang usaha + PPN masukan |
| 2 | Pesan jahit | **PO jasa jahit** ke penjahit untuk SKU barang jadi (BoM *subcontract*). Saat PO dikonfirmasi Odoo membuat **batch produksi** (nomor `BTH-YYMMDD-nnn`, juga jadi **nomor lot**), MO subkontrak, dan transfer *Resupply Subkontraktor* | Pembelian → Pesanan; **Produksi Jahit → Batch Produksi** | Belum ada jurnal; komitmen upah tercatat di PO |
| 3 | Serah bahan ke penjahit | Validasi transfer **Resupply Subkontraktor** (kain dikirim dengan buffer 6% dari kebutuhan BoM) | Inventaris → Operasi → Resupply | Bahan pindah dari Stok Utama ke lokasi **Subkontrak** (milik kita, di penjahit); nilai tetap di akun persediaan |
| 4 | Terima barang jadi | Validasi **Penerimaan** `WH/IN` dari penjahit (bisa parsial/backorder, bisa terlambat). Odoo menyelesaikan MO: komponen terpakai sesuai BoM keluar dari lokasi Subkontrak, barang jadi masuk **Sortase (QC)** berlot batch | Inventaris → Operasi → Penerimaan | **Nilai barang jadi = bahan terpakai + upah jahit** (diperiksa audit: selisih ≤ Rp 1) |
| 5 | QC di Sortase | **Inspeksi QC** per batch: jumlah diperiksa, temuan per jenis cacat (jahitan, ukuran, motif, noda, aksesori, label), disposisi **reject** (di-scrap) atau **rework** (diperbaiki penjahit). Susut kain dilaporkan penjahit dan di-scrap dari lokasi Subkontrak | **Produksi Jahit → Inspeksi QC**; Analisis Cacat QC | Reject → scrap berlot → akun *Selisih Opname, Reject & Penyesuaian* (analytic Gudang & Produksi); susut kain → beban yang sama |
| 6 | Pindah ke stok jual | Transfer *Storage* Sortase → **Stok Utama** (hanya yang lolos QC) | Inventaris → Operasi | Stok siap jual (Marketplace / Toko lewat transfer internal) |
| 7 | Tagihan penjahit | Bill dari PO jasa jahit **setelah QC**, ada baris **Potongan upah reject QC** (reject × upah) dan PPh 23 (juga PPN bila PKP) | Akuntansi → Pemasok → Tagihan | Hutang usaha; potongan mengurangi beban upah |
| 8 | Jual | SO per channel; pengiriman memakai **lot** (strategi keluar bawaan Odoo: FIFO), jadi tiap penjualan bisa ditelusuri ke batch | Penjualan; POS | HPP keluar dari persediaan; retur (28 retur di demo) masuk lagi atau di-scrap bila cacat |
| 9 | Analisis | **HPP per Batch & Performa Penjahit**: bahan, susut, upah, potongan reject, HPP/pcs vs standar BoM, selisih, efisiensi bahan, lead time, keterlambatan, reject %, first-pass yield, terjual, pendapatan, HPP terjual, margin | **Produksi Jahit → Analisis** (pivot/grafik) | Hanya laporan; dihitung ulang otomatis (cron harian) dan tiap penerimaan/QC/scrap |

Saldo bahan yang masih ada di penjahit per batch: **Produksi Jahit → Saldo Bahan di Penjahit** (diserahkan − terpakai − susut). Audit memastikan totalnya sama dengan stok lokasi Subkontrak.

## 3. Rumus HPP per batch
- Bahan terpakai = nilai komponen pada MO subkontrak (sesuai BoM, valuasi AVCO/FIFO produk).
- Susut bahan = nilai scrap kain dari lokasi Subkontrak yang dilaporkan penjahit.
- Upah jahit = qty diterima × harga jasa pada PO.
- Potongan upah reject = qty reject × harga jasa × persentase potongan (default 100%).
- HPP bersih = bahan + susut + upah − potongan; **HPP/pcs = HPP bersih ÷ pcs lolos QC**.
- Selisih HPP = HPP/pcs − HPP standar (BoM bahan + upah standar).
- Margin batch = pendapatan (DPP) penjualan batch − (pcs terjual bersih retur × HPP/pcs).

## 4. Skenario cerita yang tertanam di data
- Kenaikan harga kain 8% mulai 1 September → HPP batch September lebih tinggi dari standar.
- Penerimaan parsial/backorder dari penjahit (3 penerimaan) dan keterlambatan model seragam/sarimbit akhir September.
- Reject QC dan rework berbeda tiap penjahit (Bu Wayan Tabanan paling tinggi, CV Garment Dewata paling rendah); susut kain berbeda tiap penjahit.
- Retur cacat dari pelanggan masuk scrap berlot (6 pcs), tetap tertelusur ke batch.
- Opname stok 30 Sep (selisih kecil pada 2 SKU) dan piutang B2B macet (cerita pada modul akuntansi).

## 5. Cara demo (±8 menit)
1. **Produksi Jahit → Batch Produksi**: buka satu batch; tunjukkan tanggal (PO, serah bahan, terima), bahan yang diserahkan, status.
2. Tab **Bahan baku**: diserahkan vs terpakai vs susut vs sisa di penjahit.
3. Tab **Inspeksi QC**: temuan per jenis cacat, reject/rework.
4. **Analisis → HPP per Batch**: urutkan menurut *Selisih HPP*; bandingkan antar penjahit (reject %, keterlambatan, HPP/pcs).
5. Dari batch, buka PO jasa jahit → tagihan penjahit: tunjukkan baris potongan upah reject.
6. **Inventaris → Produk → lot**: telusuri satu lot ke pengiriman ke pelanggan (traceability).
7. Laporan keuangan: persediaan (GL) = nilai stok; HPP di Laba Rugi per channel.

## 6. Batas dan backlog (jujur)
Sudah ada: subkontrak berbasis BoM, lot per batch, QC dengan cacat dan disposisi, HPP/margin per batch, potongan upah reject, performa penjahit.
Belum ada (kandidat presentasi berikutnya):
- **Modul Quality Odoo resmi** (checklist/QC point/alert) bersifat Enterprise; di sini QC dibangun sebagai addon kecil `batik_id_production`. Belum ada foto temuan, sampling AQL, atau tanda tangan inspektur.
- **MO internal** (jahit sendiri) dengan *work order*, work center, jam kerja, dan overhead pabrik; sekarang seluruh produksi lewat penjahit luar.
- **Upah borongan lewat payroll** (penjahit sebagai pekerja harian), THR/kasbon penjahit.
- **Rencana kebutuhan bahan (MRP/reorder otomatis)** dengan lead time kain dan minimum stok; pembelian kain sekarang diatur planner demo.
- **Konversi satuan yard↔meter**, biaya angkut kain (landed cost) per batch, dan alokasi biaya overhead.
- Pencatatan **harga standar vs aktual per batch** sudah dihitung, tetapi belum otomatis menyesuaikan harga standar produk.
