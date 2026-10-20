# Skrip sandbox (mesin build berat)

Dipakai di mesin yang menjalankan Odoo 19 + Postgres sungguhan (sandbox agen / VPS), **bukan** di laptop. Path di skrip ini bergantung pada
`SANDBOX_DIR` (folder berisi `odoo/`, `oca/`, `venv/`, `data/`, `odoo.conf`) dan tiga symlink ke repo: `/mnt/scripts`, `/mnt/custom-addons`, `/mnt/data`.

## Membangun ulang mesin dari nol (±10 menit + unduhan)
```bash
export SANDBOX_DIR=$HOME/sandbox; mkdir -p $SANDBOX_DIR && cd $SANDBOX_DIR
git clone --depth 1 -b 19.0 https://github.com/odoo/odoo.git odoo
mkdir oca && for r in $(grep -vE '^\s*(#|$)' <repo>/oca-repos.txt); do git clone --depth 1 -b 19.0 https://github.com/OCA/$r.git oca/$r; done
python3.12 -m venv venv && . venv/bin/activate
pip install -r odoo/requirements.txt -r <repo>/requirements.txt pillow   # + paket OCA bila diminta saat install modul
sudo ln -sfn <repo>/scripts /mnt/scripts; sudo ln -sfn <repo>/custom_addons /mnt/custom-addons; sudo ln -sfn <repo>/data /mnt/data
cp <repo>/scripts/sandbox/odoo.conf.example odoo.conf && sed -i "s#SANDBOX_DIR#$SANDBOX_DIR#g" odoo.conf
```
Postgres 16 lokal (cluster sendiri, tanpa fsync agar cepat; hanya untuk sandbox, bukan produksi):
```bash
D=/var/tmp/pgb/d; initdb -D $D -A trust -E UTF8     # jalankan sebagai user non-root (mis. pgtest)
pg_ctl -D $D -o "-p 5544 -k /var/tmp/pgb -c fsync=off -c synchronous_commit=off -c full_page_writes=off -c max_locks_per_transaction=256" start
psql -h /var/tmp/pgb -p 5544 -U postgres -c "create role odoo login createdb password 'odoo'" -c "alter role postgres password 'postgres'"
```
Setelah container restart (proses mati, disk tetap): `bash scripts/sandbox/up.sh`.

## Skrip
| Skrip | Fungsi |
|---|---|
| `env.sh` | fungsi `odoo`, `oshell`, `psq` (butuh `SANDBOX_DIR`) |
| `up.sh` | hidupkan lagi Postgres sandbox setelah restart (idempoten) |
| `pipeline2.sh <db>` | DB dasar: base → company IDR → modul core → OCA + custom → provision → master (±3 menit) |
| `seedrun.sh` | seed penuh Jul–17 Okt di DB `kl2_t` (template `kl2_m`), ±35 menit, jalankan di latar belakang |
| `run.sh <db> <skrip.py>` | jalankan skrip Python di `odoo shell` tanpa log INFO |

Alur membuat dump baru: `pipeline2.sh kl2` → `createdb kl2_m -T kl2` → `createdb kl2_t -T kl2_m` → `seedrun.sh` → `run_patch_channel_reports.py` + `run_postinit.py`
→ `scripts/audit_v2.py` → `scripts/build_dump.sh` → restore ke DB kosong + `scripts/verify/run_snapshot.py` → perbarui `deploy/seed/reference_snapshot.zip`.
