# Catatan serah-terima antar agen

Entri terbaru di atas. Format: lihat `docs/DEVELOPMENT.md` bagian 10.

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
