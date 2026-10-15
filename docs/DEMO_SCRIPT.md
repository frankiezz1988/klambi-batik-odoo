# Skenario demo (±20 menit)

Login `admin / admin` (atau `owner@batik-demo.example` untuk perspektif auditor).

1. **Peta channel** – *Penjualan → Pesanan*: kelompokkan per Tim Penjualan (Store/Shopee/Tokopedia/TikTok Live/Instagram).
2. **HPP & costing** – *Inventory → Konfigurasi → Kategori Produk*: Batik Tulis = FIFO, lainnya AVCO. Buka satu receipt → jurnal valuasi; buka *Landed Cost* → biaya angkut terdistribusi ke HPP.
3. **Jurnal invoice** – buka invoice: NSFP, kode transaksi 04, baris pendapatan + PPN Keluaran, baris HPP dengan analytic channel.
4. **Settlement marketplace** – *Akuntansi → Jurnal → Settlement*: gross escrow → bank net, komisi, PPN masukan fee, PPh 22 (setelah 1 Agt 2026).
5. **Profit per channel** – *Akuntansi → Pelaporan → Analytic*: pivot per akun Channel; atau tab *Profit per Channel* di snapshot.
6. **Laporan OCA** – *Pelaporan → OCA accounting reports*: Trial Balance, General Ledger, Aged Partner, Tax Balance.
7. **MIS Builder** – *Pelaporan → MIS Reports*: Laba Rugi & Neraca bulanan; ekspor XLSX.
8. **Pajak** – jurnal `PAJAK`: rekap PPN, PPh Final, setoran; unduh `efaktur_staging.csv`.
9. **Audit trail** – *Pengaturan → Teknis → Audit → Logs*: perubahan harga produk, alamat vendor, deskripsi pajak. Coba edit invoice terposting sebagai akuntan → ditolak (hash/lock).
10. **Kontrol** – coba backdate entri ke periode terkunci (jalankan seed dengan `DEMO_LOCK=1`).

## Tambahan demo (v2)
1. Akuntansi > Aset: 4 aset tetap + jadwal penyusutan bulanan.
2. Retur: buka invoice yang punya credit note; lihat jurnal HPP/persediaan terbalik.
3. Rekonsiliasi bank: jurnal BCA2 punya 5 mutasi belum direkonsiliasi (OCA `account_reconcile_oca`).
4. Payroll: Karyawan > Penggajian; lihat PPh 21 TER & BPJS pada jurnal.
5. Tab "SPT & Bupot" di snapshot + unduh CSV.
