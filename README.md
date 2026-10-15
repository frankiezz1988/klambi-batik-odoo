# Batik Retail – Odoo Community + OCA Accounting Demo

Demo akuntansi **Odoo Community 19.0 + OCA** untuk usaha retail batik fashion dengan channel **Store, Shopee, Tokopedia, TikTok Live, Instagram**. Fokus: HPP, cost tracking, audit trail, cashflow, neraca saldo/neraca, laba rugi, profitabilitas per channel, dan perpajakan Indonesia (PPN masukan/keluaran, e-Faktur/Coretax, PPh).

> **Status:** kode ditulis dan lolos cek sintaks, tetapi **belum pernah dijalankan end-to-end terhadap Odoo sungguhan** (sandbox pembuatnya tidak punya Docker daemon). Skrip provisioning dan seed dibuat *fail-soft*: tiap langkah dilaporkan `[OK]`/`[FAIL]` di akhir, jadi error API antar-versi mudah dilokalisasi. Jalankan `make setup` dan kirim ringkasan `[FAIL]` bila ada.

## Keputusan desain yang perlu Anda tahu

| Topik | Keputusan | Alasan |
|---|---|---|
| Versi Odoo | **19.0** (parameter `ODOO_VERSION`) | Odoo 20 baru diumumkan 24 Sep 2026, GA dijadwalkan Okt 2026. Branch OCA 19.0 sudah ada untuk semua repo yang dipakai. Pindah ke 20.0 setelah OCA bermigrasi. |
| Laporan keuangan | OCA `account_financial_report` (GL, Trial Balance, aging) + `mis_builder` (Laba Rugi, Neraca, Cashflow) | Community tidak punya `account_reports` (Enterprise). |
| e-Faktur / Coretax | Modul `batik_id_tax` (NSFP, kode transaksi, ref order) + **CSV staging** | Modul e-Faktur Indonesia resmi Odoo adalah Enterprise; `OCA/l10n-indonesia` tidak terawat untuk versi modern (isinya masih branch 8.0). Format XML Coretax **belum diverifikasi** — gunakan CSV staging untuk template Excel/converter DJP. |
| Hosting Cloudflare (free) | Cloudflare **Pages** = snapshot laporan statis + opsional **Tunnel** ke Odoo lokal | Odoo = Python + PostgreSQL, tidak bisa jalan di Pages/Workers free. |
| Costing | AVCO untuk semua kategori, **FIFO** untuk *Batik Tulis*; valuasi real-time + anglo-saxon | HPP muncul saat invoice → ikut dimensi analytic channel. |
| Pencatatan pembayaran | Payment langsung ke akun jurnal (tanpa bank statement) | Penyederhanaan demo. Produksi: impor statement + `account-reconcile`. |

## Quick start (lokal)

Prasyarat: Docker + Compose, Git, Make, Python 3.

```bash
cp .env.example .env
make setup            # oca → build → bootstrap → provision → seed (±15–30 menit)
make up               # http://localhost:8069  (db: batik_demo, admin / admin)
make snapshot         # laporan statis ke ./site  (buka site/index.html)
```

Langkah terpisah: `make oca | build | bootstrap | provision | seed`. Ulang dari nol: `make reset`.
Ukuran data: `DEMO_MONTHS` (default 6) dan `DEMO_ORDERS_PER_MONTH` (default 90) di `.env`.

User demo (password `demo1234`): `accountant@batik-demo.example`, `owner@batik-demo.example` (read-only/auditor), `kasir@batik-demo.example`.

## Isi repo

```
docker-compose.yml, Dockerfile     Odoo + Postgres (+ cloudflared opsional: profile "tunnel")
config/odoo.conf                   addons_path core + OCA + custom
oca-repos.txt, scripts/fetch_oca.sh   repo OCA yang di-clone (branch 19.0)
scripts/bootstrap.sh               DB → company ID/IDR → modul core → modul OCA satu per satu
scripts/provision/                 provision.py (CoA, pajak, analytic, jurnal, kategori, MIS), seed.py (data dummy), config.py
data/coa_retail_batik.csv          CoA retail overlay (edit CSV → jalankan ulang `make provision`)
custom_addons/batik_id_tax/        field NSFP / kode transaksi / ref order channel
scripts/snapshot/                  build_snapshot.py + template.html → situs statis
.github/workflows/                 ci.yml, deploy-pages.yml
docs/                              TAX_ACCOUNTING_ID.md, CLOUDFLARE.md, DEMO_SCRIPT.md
```

## Pemetaan kebutuhan → implementasi

| Kebutuhan | Implementasi |
|---|---|
| HPP & cost tracking | Valuasi persediaan real-time, AVCO/FIFO per kategori, **landed cost** ongkos angkut pembelian (`stock_landed_costs`), COGS diposting saat invoice |
| Audit trail | OCA `auditlog` (create/write/unlink 12 model akuntansi/stok/master) + chatter tracking NSFP + hash chain jurnal penjualan/pembelian + `account_invoice_constraint_chronology` + `account_journal_lock_date`/`account_lock_date_update` + user auditor read-only. Opsional `DEMO_LOCK=1` mengunci periode lama |
| Cashflow | Escrow marketplace → settlement ke bank; laporan arus kas langsung di snapshot + `mis_builder_cash_flow` |
| Neraca saldo / Neraca / Laba Rugi | OCA `account_financial_report` (Trial Balance, GL, Open Items, Aged Partner) + template MIS "Laba Rugi" & "Neraca" |
| Profit per channel | Analytic plan **Channel Penjualan** (5 akun) pada baris invoice, komisi, MDR, iklan, kemasan; tim penjualan (`crm.team`) per channel |
| CoA retail | `data/coa_retail_batik.csv` (±50 akun: escrow, persediaan interim, PPN/PPh, komisi marketplace, iklan, HPP) di atas CoA `l10n_id` |
| PPN / PPh | Lihat bagian pajak di bawah dan `docs/TAX_ACCOUNTING_ID.md` |

### Dummy data yang dihasilkan
16 SKU batik (tulis/cap/printing/aksesoris), 6 pemasok, PO + receipt + vendor bill bulanan, ratusan sales order → delivery → invoice (NSFP unik) → pembayaran, settlement tiap 10 hari per channel (komisi, biaya layanan, afiliasi live, MDR, PPN masukan atas fee, PPh 22 dipungut), biaya bulanan (sewa + PPh 4(2), listrik, gaji + PPh 21, host live + PPN + PPh 23, iklan per channel, kemasan teralokasi multi-channel), rekap PPN bulanan, PPh Final, dan setoran pajak ke bank. Seed deterministik (`DEMO_SEED`).

## Asumsi pajak (verifikasi dengan konsultan pajak sebelum dipakai nyata)

- **PPN:** tarif 12% dengan DPP nilai lain 11/12 untuk BKP non-mewah → beban efektif **11%** (PMK 131/2024). Pajak dibuat sebagai satu tarif efektif 11% agar total invoice benar; kode transaksi faktur **04**.
- **PPh 22 marketplace:** 0,5% dari omzet bruto di luar PPN, dipungut Shopee/Tokopedia/Lazada/Blibli mulai **1 Agustus 2026** (PMK 37/2025). Pembebasan omzet ≤ Rp500 juta berlaku untuk **WP orang pribadi** yang menyerahkan surat pernyataan; demo memakai PT sehingga dipungut. Dicatat sebagai pajak dibayar dimuka lalu dikreditkan ke PPh Final.
- **PPh Final UMKM 0,5%** (PP 55/2022) — dari pengetahuan umum, tidak diverifikasi ulang saat riset. Cek kelayakan & ambang omzet terkini.
- **PPh 23 (2%)** jasa host live/agency, **PPh 4(2) (10%)** sewa, **PPh 21** gaji (disederhanakan 4% flat, bukan TER).
- Retail B2C umumnya memakai faktur pajak **digunggung**; demo membuat NSFP per invoice untuk memperlihatkan alurnya.

## Deploy: GitHub → Cloudflare (free)

Detail di `docs/CLOUDFLARE.md`. Ringkas:

1. Push repo ke GitHub. `ci.yml` jalan di setiap PR/branch.
2. Di GitHub → Settings → Secrets/Variables: `CLOUDFLARE_API_TOKEN` (izin *Cloudflare Pages: Edit*), `CLOUDFLARE_ACCOUNT_ID`, variable `CF_PAGES_PROJECT`.
3. Push ke `main` → `deploy-pages.yml` membangun Odoo sementara di runner, seed data kecil, export snapshot, lalu `wrangler pages deploy` (Direct Upload; free tier 500 build Git/bulan tidak terpakai).
4. Ingin Odoo hidup terlihat dari internet? `docker compose --profile tunnel up -d` dengan `CLOUDFLARE_TUNNEL_TOKEN` (Cloudflare Tunnel gratis, butuh domain di Cloudflare). Lindungi dengan Cloudflare Access.

## Batasan yang diketahui

- Belum diuji penuh (lihat status di atas); nama field/API Odoo 19 yang berubah antar versi ditangani sebagian secara dinamis, sisanya ditandai fail-soft.
- Nomor jurnal valuasi stok memakai bulan saat seed (tanggal sudah di-backdate lewat SQL); tanggal akuntansi benar, urutan nomor tidak per bulan.
- Tidak ada payroll/PPh 21 TER penuh, penyusutan aset, retur penjualan, maupun rekonsiliasi bank otomatis.
- Format XML Coretax belum diimplementasikan; hanya CSV staging.
