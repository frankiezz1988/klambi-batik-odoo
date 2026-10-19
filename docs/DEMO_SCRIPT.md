# Skenario demo Klambi Bali (±25 menit)

Data: **1 Jul – 17 Okt 2026**, 1 perusahaan (Klambi Bali, Denpasar), mata uang IDR saja, 2 gudang (Gudang Utama + Toko Denpasar),
6 channel. Login `admin / admin` (ganti), `accountant@` (akuntan), `owner@` (read-only/auditor), `kasir@` (POS), password `demo1234`.

## Cerita bisnis (yang bisa dituturkan)
| Bulan | Omzet DPP | Yang terjadi |
|---|---|---|
| Juli | ±Rp 227 jt | Saldo awal 30 Jun. Order B2B besar (reseller & korporat seragam) mendongkrak bulan pertama; laba ±Rp 20 jt. |
| Agustus | ±Rp 254 jt | 17-an. Mulai host live TikTok + iklan marketplace naik; biaya naik lebih cepat dari omzet → laba menipis (±Rp 10 jt). |
| September | ±Rp 299 jt | 9.9 + TikTok Live ramai; harga kain naik 8% mulai 1 Sep menekan margin; opname 30 Sep (selisih stok). |
| Oktober (s.d. 17) | ±Rp 190 jt | Hari Batik 2 Okt, 10.10; denda keterlambatan kirim Shopee; PPh 22 marketplace **belum berlaku** (ditunda s.d. 1 Nov 2026). |

Struktur margin yang muncul (analytic per channel, Jul–17 Okt): Toko Denpasar & B2B memberi laba terbesar; **TikTok Live** omzet besar tapi
margin tipis setelah iklan + host + komisi afiliasi; Shopee sehat; Tokopedia & Instagram kecil tapi stabil.

## Alur demo
1. **Peta channel** – *Penjualan → Pesanan*, kelompokkan per Tim Penjualan; bandingkan AOV (toko ±Rp 0,9 jt, Shopee ±Rp 0,5 jt, B2B ±Rp 10 jt).
2. **Rantai pasok ringan** – *Pembelian*: PO kain/aksesori → *Inventaris*: Penerimaan → **Sortase (QC)** → Stok Utama; PO penjahit (subkontrak) →
   Resupply Subkontraktor → MO subkontrak → barang jadi diterima. Edge case: penjahit terlambat, penerimaan parsial, 23 pcs reject QC (scrap).
   Transfer internal Senin/Kamis: Stok Utama → **Marketplace** dan → **Toko Denpasar**.
3. **HPP & costing** – kategori: Batik Tulis = FIFO, lainnya AVCO; buka satu penerimaan → jurnal valuasi; HPP per SKU tercermin di laba kotor (±47–52%).
4. **Toko (POS)** – arus uang terbesar: tunai (selisih kas kecil saat setoran) + QRIS/EDC → settlement bank; tunjukkan jurnal `KTOK`, `QRIS`, setoran (`STJ`).
5. **Settlement marketplace** – jurnal `SETL`: escrow gross → bank net, komisi, biaya layanan, PPN masukan atas fee, denda.
6. **Profit per channel** – MIS Builder *Laba Rugi per channel* (kolom = channel) atau *Akuntansi → Pelaporan → Analytic*; bahas TikTok vs Shopee vs B2B.
7. **Laporan keuangan** – OCA: Trial Balance, General Ledger, Aged Partner, Tax Balance; MIS: Laba Rugi & Neraca bulanan, Arus Kas; bandingkan vs **Anggaran** (4 bulan).
8. **Piutang/Hutang** – Aged Partner: satu piutang reseller **macet 31–60 hari (Rp 10,4 jt)**; hutang pemasok/penjahit sebagian terlambat & dibayar parsial.
9. **Pajak** – jurnal `PAJAK`: rekap PPN (efektif 11% = 12% × DPP 11/12), PPh Final UMKM 0,5%, PPh 21 TER, PPh 23 jasa, PPh 4(2) sewa; unduh CSV e-Faktur/Coretax staging.
10. **Aset & penyusutan** – *Akuntansi → Aset*: 5 aset (kamera live dibeli 3 Agu) + jadwal bulanan.
11. **Payroll** – karyawan per cost center: beban gaji/BPJS terbagi ke Kantor Pusat / Gudang & Produksi / Toko.
12. **Audit trail & kontrol** – *Teknis → Audit → Logs*: harga produk naik 1 Okt, alamat pemasok diubah; jurnal terposting terkunci hash; `owner@` read-only.
13. **Rekonsiliasi bank** – jurnal BCA2: mutasi belum direkonsiliasi (OCA `account_reconcile_oca`).
