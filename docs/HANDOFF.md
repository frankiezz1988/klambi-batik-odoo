# Catatan serah-terima antar agen

Entri terbaru di atas. Format: lihat `docs/DEVELOPMENT.md` bagian 10.

## 2026-10-21 — sandbox — produksi jahit (batch, QC, HPP per batch), dump v6
- Latar belakang: pada presentasi, alur manufaktur/subkontrak (beli bahan → serah ke penjahit → terima barang jadi → QC → HPP per batch) dicatat sebagai backlog. Ternyata dasar subkontrak sudah ada di seed; yang ditambah adalah sisi batch/lot, QC, susut, HPP per batch, dan analisisnya.
- Berubah: addon baru `custom_addons/batik_id_production` (batch = 1 baris PO jahit = 1 lot; inspeksi QC dengan jenis cacat; saldo bahan di penjahit; laporan HPP per batch, performa penjahit); `scripts/provision/{config,supply,seed}.py` (lot per batch, buffer kain 6%, susut kain, QC, potongan upah reject, opname aman untuk SKU stok tipis, FIFO lot); `scripts/audit_prod.py` (18 pemeriksaan); `batik_id_verify` +4 dataset (`prod_batches`, `prod_batch_materials`, `qc_inspections`, `qc_findings`; total 49); peringatan `tracking` payroll diperbaiki; `docs/PRODUKSI_JAHIT.md` baru; DEMO_SCOPE (angka acuan dibuat ulang dari snapshot, skenario 19–22), DEMO_SCRIPT (langkah 2b), VERIFY, DEVELOPMENT, README disesuaikan.
- Dump baru (menggantikan v5): `klambi.sql.gz` sha256 `bc5b34cd…`, `filestore.tgz` `83a213c8…` (512 berkas, hanya yang dirujuk DB), `reference_snapshot.zip` `c21b4d5a…` (49 dataset). Seed: 4/4 OK, 2.810 kejadian, 0 gagal; audit umum bersih (neraca saldo seimbang Rp 5.316.501.251, stok tidak negatif, analytic 100%); `audit_prod.py` 0 FAIL dari 18. Restore ke DB kosong → snapshot identik dengan sumber (juga dengan `--strict`).
- Data berubah dibanding v5 (angka lama tidak berlaku): PO 155, MO 132 (123 selesai, 9 berjalan), 130 batch, 123 inspeksi QC, 155 scrap, omzet DPP Rp 967,6 jt, laba kumulatif Rp 47,6 jt, piutang Rp 112,3 jt, hutang Rp 186,1 jt, selisih GL persediaan vs valuasi Rp 40.005.
- Belum diuji: deploy dump ini ke Railway (perlu `RESET_DB` dengan token **baru**, mis. `run6`, karena database Railway sudah punya penanda init); tampilan UI hanya dilihat lewat tangkapan layar sandbox (6 layar).
- Butir terbuka: (1) selisih GL persediaan vs valuasi Rp 40.005, belum ditelusuri; (2) `<>` deprecated, sumber belum dilacak; (3) MO internal/work order, konversi yard↔meter, landed cost per batch belum ada (backlog di `PRODUKSI_JAHIT.md` bagian 6); (4) ganti password default `admin/admin` & `demo1234`.
- Menunggu: pemilik repo — commit, push, set `RESET_DB=run6` (hapus setelah selesai), lalu jalankan `docs/VERIFY.md` bagian A–B terhadap `reference_snapshot.zip` baru.

## 2026-10-20 (sore) — sandbox — verifikasi Railway + patch pembanding
- Diverifikasi: snapshot Railway (db=railway, Odoo 19.0-20261015) vs `reference_snapshot.zip`: seluruh dataset bisnis identik (moves 2.810, move_lines 12.499, trial balance, KPI 74, stok, valuasi, filestore, modul 118, init_marks). Selisih hanya `table_counts` (tabel sistem: wizard yang di-GC, katalog modul, jejak akses) dan `auditlog_summary` (+1 `res.partner|write`, diduga aktivitas pemilik; belum dipastikan).
- Berubah: `scripts/verify/compare_snapshots.py` mengecualikan tabel sistem (`SYSTEM_TABLE_PREFIX`) dan `auditlog_summary` (info), opsi `--strict`; `docs/VERIFY.md` bagian "Pengecualian otomatis". Diuji dengan snapshot sintetis: selisih sistem → exit 0; selisih tabel bisnis → exit 1; `--strict` → exit 1; identik → exit 0.
- Belum diuji: pembandingan ulang pada snapshot Railway asli (satu tabel sistem ke-16 di `table_counts` belum teridentifikasi; bila masih muncul, tambahkan prefiksnya setelah diperiksa). Tidak perlu deploy ulang (hanya skrip dan dokumen).

## 2026-10-20 — sandbox — dump v2 final, pipeline verifikasi, dokumentasi
- Berubah: seed Jul–17 Okt 2026 (6 channel, ±1.075 order terkonfirmasi), dump + filestore + `reference_snapshot.zip`, modul `batik_id_verify` + `scripts/verify/*`, `docs/DEMO_SCOPE_AND_SCENARIOS.md`, `docs/VERIFY.md`, `docs/DEVELOPMENT.md`, `scripts/sandbox/*`, `Dockerfile` Railway disamakan (keduanya menyalin `deploy/seed/`).
- Dump: `klambi.sql.gz` sha256 `97f519c7…`, `filestore.tgz` `d5d5bc7c…`, `reference_snapshot.zip` `43d81214…`.
- Diverifikasi (sandbox): seed 4/4 OK; audit bersih (neraca seimbang, stok tidak negatif, analytic 100%, GL = subledger); restore dump ke DB kosong + snapshot == referensi (45 dataset, termasuk integritas filestore); fetch snapshot via HTTP dengan login admin berhasil; Railway restore berhasil (log pemilik, Odoo naik tanpa ERROR).
- Belum diuji: perbandingan snapshot **Railway** vs referensi (pemilik repo menjalankan `docs/VERIFY.md` bagian A–B); modul custom di bawah Odoo image Railway selain yang sudah tampak di log.
- Butir terbuka:
  1. Selisih GL persediaan vs Σ valuasi produk Rp 34.686 (0,03%), sumber belum ditelusuri.
  2. Warning `btk.payroll.run.state: unknown parameter 'tracking'` (`custom_addons/batik_id_payroll/models/payroll.py`, hapus `tracking=False` atau gunakan `mail.thread`).
  3. `DeprecationWarning: Operator '<>'` saat membuka daftar item jurnal; sumber (core/OCA/custom) belum dilacak.
  4. Dump berisi satu koreksi langsung di DB (stok negatif BC-KMJ-002 −2 dikoreksi 17 Okt). Kode `seed.py` sudah diubah agar opname memakai BC-KMJ-001 sehingga tidak terulang, tetapi **seed ulang dari kode akan menghasilkan data yang sedikit berbeda dari dump**. Dump tetap yang berlaku.
  5. `README.md` bagian awal (status "belum pernah dijalankan", `DEMO_MONTHS`, "16 SKU", "5 akun channel") sebagian usang; rujukan terbaru: `docs/DEMO_SCOPE_AND_SCENARIOS.md`.
  6. Instance Railway publik dengan password default (`admin/admin`, `demo1234`): ganti atau pasang Cloudflare Access.
- Menunggu: pemilik repo — commit, push, jalankan verifikasi Railway, kirim `report.txt` + `kpi_side_by_side.txt` bila ada selisih.
