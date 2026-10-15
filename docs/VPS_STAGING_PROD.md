# Staging + Prod di satu VPS (kode di laptop, jalan di VPS)

## Jawaban singkat: laptop spek rendah
Tidak masalah. Odoo + PostgreSQL tidak perlu jalan di laptop. Di laptop cukup editor, Git, dan lint
(`make lint`, `python -m py_compile`). Alur kerja:

```
laptop (edit + commit) -> push branch `staging` -> GitHub Actions -> SSH ke VPS -> deploy staging
                       -> uji di https://staging.contoh.com
                       -> tag v1.x.y -> (persetujuan manual) -> deploy prod
```
Alternatif: edit langsung di VPS lewat VS Code Remote-SSH (laptop hanya jadi layar).

## Dua stack di satu VPS: bisa
Dua *Docker Compose project* (`batik-staging`, `batik-prod`) dari file yang sama (`deploy/compose.vps.yml`),
masing-masing punya network, volume DB + filestore, port, password, dan database sendiri. Contoh di VPS:

```
/opt/batik/staging   clone repo, env.staging   port 127.0.0.1:18069 / 18072
/opt/batik/prod      clone repo, env.prod      port 127.0.0.1:8069  / 8072
/opt/batik/backups/{staging,prod}
```

Ukuran VPS (perkiraan kasar, **belum diukur**): 2 vCPU / 4 GB RAM + swap 2 GB cukup untuk staging
(workers=0, ~1 GB) + prod beban ringan (workers=2, ~1,8 GB). Seed data demo (`seed`) paling berat saat
berjalan; jalankan sekali di staging. Bila RAM mepet, turunkan `DEMO_ORDERS_PER_MONTH`, atau naik ke 8 GB.
Risiko berbagi VPS: staging yang boros memori bisa mengganggu prod (dibatasi `mem_limit`), dan satu VPS = satu titik
kegagalan. Pisahkan VPS saat prod menyimpan data nyata yang kritis.

## Setup awal (sekali)
```bash
# di VPS (Ubuntu/Debian): Docker + compose plugin, git, gettext-base (envsubst), swap
sudo mkdir -p /opt/batik && sudo chown $USER /opt/batik && cd /opt/batik
git clone <repo-url> staging && git clone <repo-url> prod
cp staging/deploy/env.staging.example staging/env.staging   # isi password acak, chmod 600
cp prod/deploy/env.prod.example       prod/env.prod
(cd staging && bash deploy/deploy.sh staging staging)        # arg2 = branch/tag/sha
(cd prod    && bash deploy/deploy.sh prod v1.0.0)
```
`SEED_DEMO=1` (staging) mengisi data dummy; `SEED_DEMO=0` (prod) hanya CoA/pajak/jurnal.

## Akses publik
`deploy/cloudflared/config.yml.example`: satu Cloudflare Tunnel, dua hostname. Prod dengan `workers>0`
perlu rute `/websocket` ke port 8072. Pasang **Cloudflare Access** di staging.
Port Odoo hanya di-bind ke 127.0.0.1; buka hanya SSH di firewall.

## GitHub Actions (`deploy-vps.yml`)
Secrets: `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY` (kunci khusus deploy), opsional `VPS_PORT`.
Buat Environment `staging` dan `production` (isi *Required reviewers* untuk `production`).
Push ke branch `staging` -> deploy staging. Tag `v*` -> deploy prod setelah disetujui.

## Operasional
- Backup: `deploy/ops/backup.sh prod` (otomatis sebelum deploy prod). Jadwalkan cron harian + salin off-site
  (mis. rclone ke Cloudflare R2). **Uji restore** berkala: `deploy/ops/restore.sh`.
- Uji dengan data prod: `deploy/ops/refresh_staging_from_prod.sh` (mematikan server email & cron di staging).
  Data prod berisi data pribadi: batasi akses staging.
- Rollback: deploy tag sebelumnya; bila migrasi merusak data, restore backup.
- Upgrade Odoo ke versi lain: ubah `ODOO_VERSION` + branch OCA, uji di staging dahulu.

## Catatan jujur
Skrip belum dijalankan di VPS sungguhan (hanya cek sintaks bash/YAML). Uji pertama di staging.
