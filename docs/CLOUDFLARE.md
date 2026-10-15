# GitHub → Cloudflare (tier gratis)

## Apa yang bisa dan tidak bisa
- **Bisa:** hosting statis (laporan snapshot) di Cloudflare Pages; Cloudflare Tunnel untuk mengekspos Odoo yang berjalan di laptop/VPS; Cloudflare Access untuk login.
- **Tidak bisa (free):** menjalankan Odoo itu sendiri di Pages/Workers (butuh proses Python + PostgreSQL jangka panjang).
- Batas Pages free yang relevan: 500 build Git/bulan, 20.000 file/site, 25 MiB/file, 1 build bersamaan. Deploy via `wrangler pages deploy` (Direct Upload) tidak memakai kuota build Git.

## Opsi A – Snapshot laporan otomatis (default)
1. Buat API token Cloudflare dengan izin **Account → Cloudflare Pages → Edit**.
2. GitHub repo → *Settings → Secrets and variables → Actions*:
   - Secret `CLOUDFLARE_API_TOKEN`, secret `CLOUDFLARE_ACCOUNT_ID`
   - Variable `CF_PAGES_PROJECT` (mis. `batik-demo`)
3. Push ke `main`, atau jalankan manual *Actions → Build demo & deploy → Run workflow* (bisa atur jumlah bulan/order).
4. Situs: `https://<project>.pages.dev`. Lindungi dengan **Cloudflare Access** (Zero Trust → Access → Applications → Self-hosted, kebijakan email; gratis hingga 50 pengguna). File `_headers` sudah memasang `noindex`.

Pipeline ini membangun Odoo di runner GitHub (±25–40 menit untuk 4 bulan × 45 order). Repo publik = menit Actions gratis.

## Opsi B – Odoo hidup lewat Tunnel
```bash
# Dashboard Cloudflare → Zero Trust → Networks → Tunnels → Create → Docker → salin token
echo 'CLOUDFLARE_TUNNEL_TOKEN=eyJ...' >> .env
# di dashboard: Public hostname demo.domainanda.com → Service http://odoo:8069
docker compose --profile tunnel up -d
```
Tanpa domain: `cloudflared tunnel --url http://localhost:8069` memberi URL `trycloudflare.com` sementara (cocok untuk presentasi singkat).
Wajib: ganti `admin_passwd` di `config/odoo.conf`, ganti password user demo, pasang Access di depan hostname.

## Alur develop → deploy
`develop lokal (make up)` → `git push` → `ci.yml` (lint) → merge ke `main` → `deploy-pages.yml` (build+seed+snapshot+deploy).
Perubahan CoA: edit `data/coa_retail_batik.csv` lalu `make provision` (idempotent: akun ada → diperbarui).
