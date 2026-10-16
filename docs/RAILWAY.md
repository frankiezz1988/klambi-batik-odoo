# Demo di Railway (trial $5) + subdomain Cloudflare

Railway membangun image dari repo GitHub Anda dan auto-deploy setiap push. Tidak perlu server, SSH, atau GitHub Actions.
Laptop tidak menjalankan Odoo sama sekali.

## Batas trial (dicek di dokumentasi Railway, Okt 2026)
- Kredit sekali pakai **$5**, berlaku maks **30 hari**, mana yang habis duluan.
- **RAM maks 1 GB per service**, shared vCPU, maks 5 service per project, **volume maks 500 MB**.
- Akun GitHub terverifikasi = Full Trial (akses jaringan penuh; perlu untuk clone OCA saat build).
- Setelah habis: plan Free ($1/bulan, tidak menumpuk). **Volume trial dihapus 30 hari setelah kredit habis.**
- Tarif: memori ~$10/GB-bulan, CPU ~$20/vCPU-bulan, volume ~$0.15/GB-bulan.

Perkiraan kasar (tidak diukur): Odoo ~0,6 GB + Postgres ~0,25 GB jalan 24 jam ≈ **$9-10/bulan**, jadi $5 cukup sekitar
**2 minggu** non-stop. Seed data juga memakai CPU. Fitur App Sleeping kemungkinan tidak membantu: koneksi DB dan cron Odoo
dihitung sebagai aktivitas keluar sehingga service tidak tidur. Hemat: hentikan (Remove/stop deployment) saat tidak dipakai.
Untuk demo lebih dari 2-3 minggu, rencanakan Hobby ($5/bulan, volume 5 GB) atau VPS (`docs/VPS_STAGING_PROD.md`).

Ukuran data default di Railway sengaja kecil (3 bulan x 30 order) agar muat 500 MB dan 1 GB RAM.

## Langkah
1. **Push repo ke GitHub** (dari laptop):
   ```bash
   unzip batik-odoo-demo.zip && cd batik-odoo-demo
   git remote add origin git@github.com:<user>/<repo>.git   # repo kosong (private disarankan)
   git push -u origin main
   ```
2. Di Railway (sudah login GitHub): **New project > Deploy from GitHub repo** > pilih repo. Izinkan Railway Github App.
   Deploy pertama akan gagal/berhenti sampai variable diatur; tidak masalah.
3. **Tambah Postgres:** di project, *+ New > Database > PostgreSQL*.
4. **Service Odoo** (service dari repo) > *Variables*:
   | Variable | Nilai |
   |---|---|
   | `RAILWAY_DOCKERFILE_PATH` | `deploy/railway/Dockerfile` |
   | `RAILWAY_RUN_UID` | `0` (agar volume bisa ditulis; Odoo tetap jalan sebagai user `odoo`) |
   | `PGHOST` | `${{Postgres.PGHOST}}` |
   | `PGPORT` | `${{Postgres.PGPORT}}` |
   | `PGUSER` | `${{Postgres.PGUSER}}` |
   | `PGPASSWORD` | `${{Postgres.PGPASSWORD}}` |
   | `PGDATABASE` | `${{Postgres.PGDATABASE}}` |
   | `ADMIN_PASSWD` | password master Odoo (acak, panjang) |
   | `SEED_DEMO` | `1` (isi data dummy) |
   | `DEMO_MONTHS` / `DEMO_ORDERS_PER_MONTH` | opsional, default `3` / `30` |
   (Nama service Postgres di `${{...}}` harus sama dengan nama di project Anda.)
5. **Volume:** service Odoo > *Settings > Volumes > Add*, mount path `/var/lib/odoo` (filestore/session). Postgres sudah punya volume sendiri.
6. **Jaringan:** *Settings > Networking > Generate Domain* untuk URL `*.up.railway.app` (port otomatis dari `$PORT`).
7. Deploy. **Deploy pertama = inisialisasi + seed**, perkiraan 20-45 menit (CPU shared; tidak diukur). Pantau *Deployments > Logs*
   (`[1/5]`...`[5/5]`). Login: `admin` dan password awal Odoo `admin` (**ganti segera**).

Inisialisasi bertahap dan bisa dilanjutkan bila container restart. Jika seed terhenti di tengah (mis. OOM di batas 1 GB), seed tidak
diulang otomatis agar data tidak ganda; log akan menjelaskan. Perbaikan: kosongkan DB (hapus service/volume Postgres, buat lagi), kecilkan
`DEMO_ORDERS_PER_MONTH` (mis. 15), deploy ulang.

## Subdomain di Cloudflare
1. Railway: service Odoo > *Networking > Custom Domain* > `demo.domainanda.com`. Railway menampilkan target CNAME (dan mungkin TXT verifikasi).
2. Cloudflare DNS: tambahkan `CNAME demo -> <target dari Railway>` (dan TXT bila diminta).
3. Mulai dengan **DNS only** (awan abu-abu) sampai sertifikat Railway aktif. Bila ingin proxied (oranye) agar bisa memakai Cloudflare Access,
   set SSL/TLS mode **Full** (bukan Flexible, itu menyebabkan loop redirect).
4. Pasang **Cloudflare Access** (Zero Trust, gratis) untuk `demo.domainanda.com` agar demo tidak terbuka publik. Cloudflare Tunnel tidak dipakai di Railway.
5. Odoo: Pengaturan > Teknis > Parameter Sistem, set `web.base.url` = `https://demo.domainanda.com`.

## Operasional
- Update kode: push ke `main` -> Railway rebuild (build ~ beberapa menit karena clone OCA) dan restart. Skema modul custom yang berubah perlu
  `-u`: jalankan lewat Railway CLI `railway ssh`, lalu `runuser -u odoo -- odoo -c /tmp/odoo.conf -d $ODOO_DB -u batik_id_tax,batik_id_coretax,batik_id_payroll --stop-after-init`.
- Backup: fitur backup volume Railway tidak tersedia di trial; untuk data penting, `pg_dump` dari laptop memakai `railway connect`/connection string publik Postgres.
- Biaya: pantau *Usage* di dashboard Railway.

## Catatan jujur
Belum pernah dibangun/dijalankan di Railway (sandbox pembuat tanpa Docker). Titik risiko: build image (clone OCA), memori 1 GB saat install
modul dan seed, kecocokan versi modul OCA 19.0. Kirim log bila ada tahap gagal.
