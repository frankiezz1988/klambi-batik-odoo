# Demo di VPS (satu stack) + subdomain Cloudflare

Kode ditulis di laptop; Odoo jalan di VPS. Laptop spek rendah aman: tidak ada Docker/Odoo di laptop.

```
laptop (edit, commit, push main) -> GitHub Actions -> SSH ke VPS -> deploy.sh -> https://demo.domainanda.com
```
Satu stack bernama `staging` (= demo). Bila nanti perlu prod, jalankan `deploy.sh prod` dengan `env.prod`
dari salinan `env.staging.example` (port berbeda) di VPS yang sama atau lain. Tidak perlu sekarang.

## VPS
Ubuntu/Debian, 2 vCPU / 4 GB RAM + swap 2 GB (perkiraan, belum diukur; seed data paling berat, kecilkan
`DEMO_ORDERS_PER_MONTH` bila mepet). Pasang: Docker + compose plugin, git, gettext-base, make.

## Setup awal (sekali)
```bash
sudo mkdir -p /opt/batik && sudo chown $USER /opt/batik && cd /opt/batik
git clone <repo-url> staging && cd staging
cp deploy/env.staging.example env.staging && chmod 600 env.staging   # isi password acak
```

## Subdomain lewat Cloudflare Tunnel (domain sudah di Cloudflare)
Tidak perlu buka port, tidak perlu sertifikat, DNS dibuat otomatis.
1. Dashboard Cloudflare > Zero Trust > Networks > Tunnels > *Create tunnel* > Cloudflared > beri nama `batik-demo`.
2. Salin **token** ke `CLOUDFLARE_TUNNEL_TOKEN` di `env.staging` (`COMPOSE_PROFILES=tunnel` sudah di contohnya).
3. Tab *Public Hostname* > *Add*: subdomain `demo`, domain Anda, Service **HTTP** `odoo:8069`.
   (Nama `odoo` = service di jaringan Docker yang sama, jadi port host tidak dipakai.)
4. **Lindungi:** Zero Trust > Access > Applications > *Self-hosted* untuk `demo.domainanda.com`, kebijakan
   "Allow" email Anda/tim (gratis sampai 50 user). Tanpa ini demo terbuka ke publik.
5. Di Odoo: Pengaturan > Teknis > Parameter Sistem, set `web.base.url` ke `https://demo.domainanda.com`.

## Deploy pertama
```bash
cd /opt/batik/staging && bash deploy/deploy.sh staging main
```
Membuat DB, memasang modul, provisioning, dan seed data demo (±15-30 menit). Login `admin` /
password yang Anda atur di Odoo (ganti segera). Perbarui kemudian: `git pull && bash deploy/deploy.sh staging`.

Akses darurat tanpa Cloudflare (SSH tunnel): `ssh -L 18069:127.0.0.1:18069 user@ip-vps` lalu `http://localhost:18069`.

## Otomatis dari GitHub
Secrets repo: `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY` (kunci khusus deploy), opsional `VPS_PORT`.
Buat Environment `staging`. Push ke `main` = deploy. Bila belum mau otomatis, hapus workflow dan deploy manual.

## Operasional
- Backup: `bash deploy/ops/backup.sh staging` (jadwalkan cron harian). Restore: `deploy/ops/restore.sh`.
- Reset demo: `docker compose -p batik-staging --env-file env.staging -f deploy/compose.vps.yml down -v`, lalu deploy ulang.

## Catatan jujur
Skrip belum dijalankan di VPS sungguhan (hanya cek sintaks). Jalankan deploy pertama dan kirim log bila ada error.
