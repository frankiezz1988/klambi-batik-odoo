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

Data demo (Jul - 17 Okt 2026, ±1.100 order, 6 channel) **tidak di-seed ulang di Railway**: dibangun dan divalidasi di sandbox, lalu dikirim
sebagai dump (`deploy/seed/klambi.sql.gz` + `filestore.tgz`, foto produk) yang di-restore sekali pada database kosong. Deploy pertama
cukup beberapa menit, bukan 30+ menit, dan hasilnya identik dengan yang diaudit.

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
   | `BASE_URL` | `https://klambi-bali.odoo.kolondam.dev` (mengisi `web.base.url`) |
   | `SEED_MODE` | kosong = restore dump (default). `build` = bangun dari nol dengan seed ORM (lambat, tidak disarankan) |
   (Nama service Postgres di `${{...}}` harus sama dengan nama di project Anda.)
5. **Volume:** service Odoo > *Settings > Volumes > Add*, mount path `/var/lib/odoo` (filestore/session). Postgres sudah punya volume sendiri.
6. **Jaringan:** *Settings > Networking > Generate Domain* untuk URL `*.up.railway.app` (port otomatis dari `$PORT`).
7. Deploy. **Deploy pertama = restore dump** (`[0] restore dump database demo` di log), lalu post-init. Login: `admin / admin`
   (**ganti**), atau `accountant@ / owner@ / kasir@batik-demo.example` dengan password `demo1234`.

**Mengosongkan & restore ulang:** set variable `RESET_DB=<token baru, mis. run5>` lalu deploy; database dikosongkan, filestore dihapus,
dump di-restore lagi. Bila restore gagal, log menampilkan 15 baris terakhir dan init jatuh ke jalur build bertahap.

## Membuat ulang dump (bila seed/konfigurasi berubah)
Dump dibuat di mesin yang punya Odoo + Postgres (sandbox/VPS), bukan di Railway:
```bash
# 1) bangun DB dasar (pipeline) -> seed:   odoo shell -d <db> < scripts/provision/run_seed.py   (±35 menit)
# 2) bekukan jadi dump:
SRC_DB=<db> FILESTORE=<data_dir>/filestore/<db> OUT=deploy/seed bash scripts/build_dump.sh
git add deploy/seed && git commit -m "refresh dump demo" && git push
```
Dump ±beberapa MB (di bawah batas 100 MB per file GitHub dan 500 MB volume Railway). Versi Odoo image Railway (`odoo:19.0`) harus
satu seri dengan yang dipakai membuat dump.

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

## Catatan
Alur restore sudah diuji di sandbox (dump -> DB kosong -> Odoo shell membaca data). Belum diuji di Railway itu sendiri; bila log restore
bermasalah, kirim log `[0]`.
