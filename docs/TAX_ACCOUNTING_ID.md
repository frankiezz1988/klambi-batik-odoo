# Praktik akuntansi & pajak Indonesia dalam demo

Bukan nasihat pajak. Angka/tarif perlu diverifikasi terhadap peraturan terbaru dan situasi perusahaan.

## 1. Struktur CoA retail (overlay `data/coa_retail_batik.csv`)
| Kelompok | Contoh akun | Catatan |
|---|---|---|
| 1110 Kas & setara kas | Kas Toko, Bank BCA, Settlement QRIS, **Saldo Escrow** Shopee/Tokopedia/TikTok, Payment Gateway | Escrow = piutang ke platform, bukan kas, sampai settlement |
| 1130 Persediaan | Persediaan Barang Dagang, interim diterima/dikirim | Valuasi real-time (anglo-saxon) |
| 1140 Pajak dimuka | PPN Masukan, **PPh 22 dibayar dimuka** (dipungut marketplace) | PPh 22 dikreditkan ke PPh Final/tahunan |
| 2130 Utang pajak | PPN Keluaran, Utang PPN, PPh 21, 23, 4(2), PPh Final | |
| 4110 Pendapatan | Penjualan, diskon, retur | analytic channel wajib (jika `account_analytic_required` aktif) |
| 5xxx HPP | HPP, ongkos angkut pembelian, selisih/rusak | |
| 6110 Beban channel | Komisi, biaya layanan, afiliasi/live, MDR | per channel via analytic |
| 6120 Pemasaran | Iklan digital, host live/KOL | |
| 6130/62 Operasional | Kemasan, gaji, sewa, listrik, penyusutan, admin bank | |
| 6910 Pajak | Beban PPh Final UMKM | |

## 2. Alur PPN
1. Invoice penjualan: PPN Keluaran 11% efektif (12% × DPP 11/12), kode transaksi 04, NSFP di invoice.
2. Pembelian dari PKP & fee marketplace: PPN Masukan (fee marketplace dicatat saat settlement).
3. Akhir bulan (`PAJAK` journal): rekap keluaran − masukan → *Utang PPN Kurang Bayar* atau *PPN Lebih Bayar*; setor bulan berikutnya.
4. Laporan: OCA `account_tax_balance` (saldo pajak per periode) + tab *Pajak* di snapshot.

## 3. e-Faktur → Coretax
- e-Faktur desktop (CSV) digantikan Coretax (impor XML / template Excel + converter DJP). Template Excel Faktur Pajak Keluaran sudah diperbarui ke versi 1.6 (converter XML masih 1.5 saat riset dilakukan).
- Demo menyediakan `efaktur_staging.csv` (tanggal, NSFP, kode transaksi, ref order, DPP, DPP nilai lain, PPN, total). **Bukan** file siap impor; petakan ke template resmi DJP.
- Retail B2C: pertimbangkan faktur pajak digunggung (tanpa identitas pembeli).

## 4. PPh
| Jenis | Perlakuan di demo |
|---|---|
| PPh 22 marketplace 0,5% (PMK 37/2025; ditunda, mulai 1 Nov 2026) | Dipotong dari settlement mulai `PPH22_START`, debit *PPh 22 Dibayar Dimuka*. Pungutan 1 Agt-31 Okt 2026 (jika ada) wajib dikembalikan marketplace |
| PPh Final UMKM 0,5% omzet | Accrual bulanan, disetor bulan berikutnya, dikurangi kredit PPh 22 |
| PPh 23 2% jasa | Pajak pembelian bernilai negatif pada bill agency |
| PPh 4(2) 10% sewa | Pajak pembelian bernilai negatif pada bill sewa |
| PPh 21 gaji | Disederhanakan 4% flat (produksi: TER/Pasal 17 + BPJS, bukan modul Community) |

## 5. Kontrol & audit (best practice)
- Hash chain jurnal penjualan/pembelian (inalterability), penomoran kronologis, lock date per jurnal/periode.
- Audit log perubahan: akun, pajak, jurnal, produk (harga/HPP), partner (NPWP), SO/PO, picking.
- Segregation of duties: akuntan, kasir, owner read-only.
- Rekonsiliasi: escrow marketplace ↔ settlement; PPN buku ↔ SPT Masa; stok fisik ↔ valuasi.
- Closing bulanan: kunci periode setelah PPN dilaporkan.

## Tambahan (v2)
- **Coretax:** NSFP diterbitkan sistem saat faktur ditandatangani; `batik_id_coretax` menyediakan impor NSFP dari
  hasil Coretax, ekspor Excel/XML (XML eksperimental), pengecekan kelengkapan (NPWP/NIK pembeli, DPP nilai lain).
- **PPh 21 TER:** `batik_id_payroll` (kategori A/B/C, Jan–Nov). Desember (Pasal 17) belum ada. BPJS: tarif & batas upah dicek tiap tahun.
- **Lembar kerja SPT/bupot (snapshot):** `spt_ppn_keluaran.csv`, `spt_ppn_masukan.csv`, `bupot_pph21_23_4ayat2.csv`,
  `pph22_dipungut_marketplace.csv`. Draf rekonsiliasi, bukan pelaporan resmi.
- **Aset tetap, retur penjualan, rekonsiliasi bank:** lihat README.
