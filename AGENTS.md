# AGENTS.md — ringkasan untuk agen (detail: `docs/DEVELOPMENT.md`)

Proyek: demo akuntansi **Odoo 19 Community + OCA** untuk "Klambi Bali" (retail batik, Denpasar). Data fiktif Jul–17 Okt 2026, IDR saja.

1. **Baca dulu** `docs/HANDOFF.md` (keadaan terkini) lalu `docs/DEVELOPMENT.md` (aturan, peta repo, deploy).
2. Kerja di **cabang** `agen/<topik>`; jangan push ke `main` (auto-deploy Railway). Penulis commit = pemilik repo.
3. Laptop lokal tidak menjalankan Odoo: lakukan cek statis (`make lint`, `bash -n`), serahkan uji jalan ke agen sandbox (`scripts/sandbox/README.md`).
4. **Jangan sentuh `deploy/seed/*`** (dump, filestore, referensi) dari lokal; itu artefak build sandbox yang saling terkait.
5. Data demo tidak diedit langsung: ubah `scripts/provision/*` → seed di sandbox → dump baru → referensi baru → `RESET_DB=<token baru>` di Railway.
6. Seed harus deterministik (urutkan `set`, `random` ber-seed, waktu digeser `freezegun`, `PYTHONHASHSEED=0`).
7. Verifikasi antar lingkungan: `docs/VERIFY.md` (`scripts/verify/`). Cakupan & skenario demo: `docs/DEMO_SCOPE_AND_SCENARIOS.md`.
8. Tidak ada rahasia di repo. Tarif pajak harus bersumber (PPN efektif 11%; PPh 22 marketplace mulai 2026-11-01).
9. Tulis fakta vs asumsi; yang belum diuji ditulis "belum diuji". Tambahkan entri di `docs/HANDOFF.md` setiap selesai.
