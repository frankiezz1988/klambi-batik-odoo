# Pencocokan data antar lingkungan (sandbox ↔ Railway/VPS)

Tujuan: membuktikan bahwa data di Railway/VPS **identik** dengan data yang diaudit di sandbox, dan menunjukkan **persis di mana** berbeda
bila tidak. Mekanismenya: modul `batik_id_verify` mengekspor seluruh data bisnis & konfigurasi ke CSV deterministik (berbasis *kunci alami*,
bukan ID), lalu `scripts/verify/compare_snapshots.py` membandingkan dua snapshot.

Semuanya **read-only** (hanya SELECT + baca ORM); aman dijalankan di instance demo.

## Isi snapshot (45 dataset)
| Kelompok | Dataset |
|---|---|
| Konfigurasi | `company`, `currencies_active`, `accounts`, `journals`, `taxes`, `analytic_accounts`, `sequences`, `users`, `modules`, `init_marks`, `config_env` |
| Master | `partners`, `products` (termasuk hash foto), `boms`, `employees` |
| Akuntansi | `moves`, `move_lines`, `payments`, `bank_statement_lines`, `trial_balance`, `trial_balance_monthly`, `pl_by_analytic`, `aging`, `assets`, `asset_lines`, `budget_items`, `mis_report_kpis` |
| Penjualan/Pembelian | `sale_orders`, `sale_lines`, `purchase_orders`, `purchase_lines` |
| Gudang/Produksi | `pickings`, `stock_moves`, `stock_quants`, `valuation`, `mrp_productions`, `scraps` |
| Payroll & audit | `payroll_runs`, `payroll_lines`, `auditlog_rules`, `auditlog_summary` |
| Ringkasan | `kpi` (74 angka kunci: omzet per bulan/channel, laba rugi, saldo akun, dokumen), `table_counts` (jumlah baris tiap tabel bisnis), `filestore_integrity` (lampiran/foto di DB benar-benar ada di filestore) |
| Volatil (hanya diagnostik) | `config_env`, `table_counts_volatile` (sesi, cron, cache asset web, log) — tidak dihitung sebagai selisih |

Kunci baris = nomor dokumen / kode akun / SKU / login (bukan ID database); angka dibulatkan; tanggal ISO. Dua database dengan isi sama
menghasilkan berkas yang sama persis.

## Berkas referensi
`deploy/seed/reference_snapshot.zip` = snapshot database hasil **restore dump** yang dikirim (`klambi.sql.gz` + `filestore.tgz`), diverifikasi
identik dengan sandbox. Anda tidak perlu menjalankan sandbox untuk membandingkan: cukup ambil snapshot Railway lalu bandingkan dengan berkas ini.

## A. Mengambil snapshot dari Railway (tanpa SSH)
Dari laptop Anda (hanya butuh Python 3.8+, tanpa pustaka tambahan):
```bash
python3 scripts/verify/fetch_snapshot.py https://klambi-bali.odoo.kolondam.dev railway admin 'PASSWORD_ADMIN' railway_snapshot.zip
# password lewat env (tidak masuk riwayat shell):  ODOO_PASSWORD='...' python3 scripts/verify/fetch_snapshot.py <url> railway admin - railway_snapshot.zip
```
`railway` = nama database (nilai `PGDATABASE`/`ODOO_DB` di Railway). Login harus **admin** (grup Settings). Opsi `--asof 2026-10-17`
mengubah tanggal acuan umur piutang (default sudah 17 Okt 2026; jangan diubah bila ingin cocok dengan referensi).

Alternatif lewat UI: *Pengaturan → Teknis → Snapshot Verifikasi Data (CSV)* (aktifkan mode pengembang) mengunduh ZIP yang sama.

## B. Membandingkan
```bash
python3 scripts/verify/compare_snapshots.py deploy/seed/reference_snapshot.zip railway_snapshot.zip \
        --out hasil_cek --label-a referensi --label-b railway
```
Keluaran: ringkasan per dataset di layar + folder `hasil_cek/` berisi `report.txt` (rincian baris), `kpi_side_by_side.txt` (74 angka kunci
berdampingan, selisih ditandai `<== BEDA`), dan `diff_<dataset>.csv` untuk tiap dataset yang berbeda. Kode keluar 0 = identik, 1 = ada selisih.

Membandingkan dua lingkungan lain (mis. sandbox vs VPS) sama saja: dua folder/ZIP snapshot apa pun.

## C. Membuat snapshot di mesin yang punya shell Odoo (sandbox/VPS)
```bash
SNAP_OUT=/tmp/snap SNAP_LABEL=sandbox odoo shell -d <db> --no-http < scripts/verify/run_snapshot.py
python3 scripts/verify/compare_snapshots.py deploy/seed/reference_snapshot.zip /tmp/snap
```
Di Railway tanpa HTTP: `railway ssh`, lalu jalankan perintah yang sama dengan opsi koneksi dari `/tmp/odoo.conf`.

## Cara membaca hasil
| Status | Arti |
|---|---|
| `OK` | dataset identik |
| `DIFF` + kolom `hny-A` / `hny-B` | ada baris hanya di satu sisi (mis. dokumen baru yang Anda buat di Railway) |
| `DIFF` + kolom `berubah` | kunci sama, nilai berbeda (mis. harga produk diubah); rinciannya di `report.txt` per kolom |
| `DIFF (volatil)` | diabaikan dari vonis akhir |

Selisih yang **wajar** setelah instance dipakai: `users` (login baru), `auditlog_*` (perubahan yang Anda lakukan dicatat), `moves`/`sale_orders`
(dokumen baru), `modules`/`init_marks` (modul atau tahap init bertambah setelah dump dibuat), `table_counts` (ikut berubah). Itu justru
tujuannya: setiap perubahan terlihat. Selisih pada `accounts`, `taxes`, `trial_balance`, `valuation`, `filestore_integrity` yang **tidak**
Anda kerjakan sendiri patut dicurigai (dump rusak/terpotong, restore gagal, versi image beda).

Contoh `filestore_integrity` = `missing:<model>`: lampiran/foto tercatat di DB tetapi berkasnya tidak ada di filestore (mis. `filestore.tgz`
tidak ter-extract atau volume `/var/lib/odoo` terhapus).

## Pemeriksaan konsistensi internal
Dataset `kpi` memuat total debit = total kredit, dan ringkasan dokumen. Selain itu bandingkan angka rujukan di
[`DEMO_SCOPE_AND_SCENARIOS.md`](DEMO_SCOPE_AND_SCENARIOS.md) (Bagian 4) dengan layar Odoo.

## Memperbarui referensi
Bila dump diganti, buat ulang referensi dari hasil **restore** dump itu (bukan dari database sumber), agar mencakup uji restore:
restore ke DB kosong → `run_snapshot.py` → ZIP-kan folder keluaran (termasuk `manifest.json`) menjadi `deploy/seed/reference_snapshot.zip`.
