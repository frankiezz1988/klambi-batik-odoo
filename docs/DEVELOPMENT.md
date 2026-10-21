# Panduan pengembangan untuk agen (lokal ↔ sandbox ↔ Railway)

Untuk agen AI atau developer yang bekerja **di laptop (repo lokal)** dan perlu tetap sinkron dengan agen lain yang memegang mesin build berat
(sandbox) dan dengan instance demo di Railway. Baca bagian 1–3 sebelum mengubah apa pun. Ringkasan satu layar ada di `AGENTS.md`.

## 1. Peran tiap lingkungan

| Lingkungan | Dipakai untuk | Tidak dipakai untuk |
|---|---|---|
| **Laptop lokal** (spek rendah, tanpa Docker/Odoo) | Edit kode, dokumen, konfigurasi; cek statis; git | Menjalankan Odoo, seed, membuat dump |
| **Sandbox** (Odoo 19 + Postgres sungguhan, lihat `scripts/sandbox/`) | Uji jalan kode, seed penuh (±35 mnt), audit data, membuat **dump** dan **snapshot referensi** | Menjadi sumber kebenaran; menyimpan data permanen (bisa reset) |
| **Railway** (demo, `klambi-bali.odoo.kolondam.dev`) | Target demo; hasil restore dump; pengujian UI | Tempat membuat/mengubah data demo untuk dipertahankan |
| **GitHub** (`frankiezz1988/klambi-batik-odoo`, private) | **Sumber kebenaran**: kode + dump + referensi | — |

Prinsip: **kode adalah sumber, dump adalah artefak build.** Data demo tidak pernah diedit langsung; ia lahir dari `seed` lalu dibekukan menjadi dump.

## 2. Aturan yang tidak boleh dilanggar

1. **Jangan mengedit data di Railway/sandbox lalu menganggapnya tersimpan.** Ubah kode seed/provision → bangun ulang di sandbox → dump baru.
2. **Jangan menyentuh `deploy/seed/*` dari laptop** (`klambi.sql.gz`, `filestore.tgz`, `reference_snapshot.zip`, `SHA256SUMS`). Hanya sandbox yang membuatnya; ketiganya harus berasal dari satu build yang sama. Konflik binary di berkas ini: ambil versi sandbox.
3. **Jangan menjalankan seed ORM di Railway** (memori 1 GB, 35 menit, tidak idempoten). Jalur normal = restore dump (`SEED_MODE` default).
4. **Seed harus deterministik.** Tanpa `set` dari string yang diiterasi tanpa `sorted()`, tanpa `random` tanpa seed, tanpa waktu sistem nyata (jam digeser `freezegun`). Jalankan dengan `PYTHONHASHSEED=0`.
5. **Hanya IDR.** Jangan mengaktifkan mata uang lain.
6. **Data fiktif saja.** Tidak ada nama, NPWP, rekening, atau alamat asli.
7. **Angka pajak berdasarkan peraturan yang bisa dikutip.** PPN efektif 11% (12% × DPP 11/12, PMK 131/2024); PPh 22 marketplace mulai `2026-11-01` (`PPH22_START`). Jangan mengubah tarif tanpa sumber, dan jangan mengklaim "patuh pajak" (lihat `docs/TAX_ACCOUNTING_ID.md`).
8. **Tidak ada rahasia di repo** (password, token, `ADMIN_PASSWD`). Rahasia hanya di Variables Railway / `.env` lokal (diabaikan git).
9. **Jangan melemahkan pemeriksaan agar lolos** (menghapus invarian, memperlebar toleransi). Perbaiki penyebabnya atau catat sebagai butir terbuka.
10. **Laporkan fakta vs asumsi.** Yang belum dijalankan harus ditulis "belum diuji", bukan "berfungsi".

## 3. Peta repo: mengubah apa → menyentuh apa → apa yang harus diulang

| Perubahan | Berkas utama | Setelah itu |
|---|---|---|
| CoA, akun | `data/coa_retail_batik.csv`, `scripts/provision/provision.py` | build ulang di sandbox → dump baru |
| Pajak, jurnal, analytic, gudang, POS, anggaran, MIS | `scripts/provision/provision.py`, `config.py` | idem |
| Perusahaan, channel, biaya bulanan, target omzet, produk, penjahit, nama Bali | `scripts/provision/config.py`, `master.py` | idem |
| Pola order & pasokan (perencana murni, tanpa Odoo) | `scripts/provision/plan.py`, `supply.py` | uji murni di laptop boleh; hasil akhir lewat sandbox |
| Mesin kejadian (urutan dokumen, jurnal, edge case) | `scripts/provision/seed.py` | seed penuh di sandbox + audit |
| Gambar produk | `scripts/provision/art.py` | build ulang (filestore ikut berubah) |
| Modul custom | `custom_addons/batik_id_*` | uji di sandbox; bila skema berubah, upgrade `-u` (lihat 7) |
| Verifikasi data | `custom_addons/batik_id_verify`, `scripts/verify/*` | perbarui referensi bila dataset berubah |
| Produksi jahit (batch, QC, HPP per batch) | `custom_addons/batik_id_production`, `scripts/provision/{config,supply,seed}.py`, `scripts/audit_prod.py`, `docs/PRODUKSI_JAHIT.md` | seed ulang → `audit_prod.py` harus 0 FAIL → dump + referensi baru → `RESET_DB` token baru |
| Deploy Railway | `Dockerfile`, `deploy/railway/*` | push; uji di Railway |
| Dokumen | `docs/*`, `README.md` | angka di dokumen harus dicocokkan dengan snapshot |

Modul custom: prefiks `batik_id_`, field `btk_` / `l10n_id_*`, lisensi LGPL-3, depends minimal. **Jangan membuat modul custom untuk hal yang bisa native/OCA**, dan jangan memaksakan fitur proposal yang ditunda (barcode, import marketplace, approval bertingkat, Stock Trace, RMA, dashboard owner) — lihat `docs/DEMO_SCOPE_AND_SCENARIOS.md` bagian 1 dan 8.

## 4. Alur kerja dan sinkronisasi

### 4.1 Git
- Repo remote hanya satu: GitHub. `main` terhubung ke Railway (auto-deploy tiap push) → **jangan push eksperimen ke `main`**.
- Cabang: `agen/<topik>` (mis. `agen/fix-payroll-warning`). Merge ke `main` oleh pemilik repo setelah verifikasi.
- Commit kecil, pesan imperatif berbahasa Indonesia/Inggris konsisten; satu topik per commit. Penulis commit = akun pemilik (`git config user.name/email` lokal pada repo, jangan global). Tambahkan trailer `Co-Authored-By: <agen>` bila agen yang menulis.
- Jangan commit berkas besar selain `deploy/seed/*`. `__pycache__`, `.env`, `site/`, `addons-oca/*` sudah di `.gitignore`.

### 4.2 Sinkron antar agen
Hub = GitHub. Agen sandbox saat ini **tidak punya kredensial push**; hasilnya dikirim ke pemilik repo (zip/patch) lalu di-commit. Dua cara yang aman:

```bash
# Dari sandbox -> lokal: kirim cabang sebagai bundle (tanpa remote)
git bundle create agen.bundle main..HEAD            # di sumber
git fetch agen.bundle HEAD:agen/dari-sandbox        # di tujuan
# atau patch biasa
git format-patch main..HEAD -o patches/             # di sumber
git am patches/*.patch                              # di tujuan
```
Bila memakai zip: ekstrak ke **cabang bersih**, `git status` harus hanya menampilkan perubahan yang disengaja (waspadai CRLF; `.gitattributes` memaksa LF untuk `*.sh`, `*.py`, `Dockerfile*`, `*.yml`).

### 4.3 Catatan serah-terima (`docs/HANDOFF.md`)
Setiap agen **menambah entri di atas** saat selesai: tanggal, siapa, apa yang berubah, apa yang menunggu, versi dump (sha256). Agen berikutnya membaca file ini lebih dulu. Format di akhir dokumen ini.

### 4.4 Siapa mengerjakan apa
- **Lokal**: perubahan kode/dokumen yang bisa dicek statis; menyiapkan cabang; menulis permintaan verifikasi.
- **Sandbox**: segala yang butuh Odoo jalan; membangun dump + referensi; audit; mengirim hasil.
- **Pemilik repo**: commit/merge, mengatur Variables Railway, ganti password, memicu deploy.
Bila perubahan lokal butuh uji jalan, tulis di HANDOFF: *cabang*, *apa yang diubah*, *apa yang harus diverifikasi*, *kriteria lulus* — lalu minta agen sandbox menjalankannya.

## 5. Pengujian tanpa Odoo lokal

Di laptop (cukup Python 3.10+):
```bash
make lint                                      # py_compile semua .py
bash -n deploy/railway/*.sh scripts/*.sh scripts/sandbox/*.sh
python3 -c "import ast,sys; [ast.parse(open(f).read()) for f in sys.argv[1:]]" $(git ls-files '*.py')
python3 -c "import xml.dom.minidom as m,sys; [m.parse(f) for f in sys.argv[1:]]" $(git ls-files '*.xml')
# perencana order & pasokan berjalan tanpa Odoo (murni Python) -> boleh diuji lokal:
python3 -I -c "import sys; sys.path.insert(0,'scripts/provision'); import plan, supply; o=plan.build(); s=supply.build(o); print(len(o), s['stats'])"
```
Uji yang **tidak** bisa dilakukan lokal: apa pun yang memanggil ORM Odoo (provision, seed, modul custom, XML view). Jangan menyatakannya lulus; serahkan ke sandbox.

Uji di sandbox (lihat `scripts/sandbox/README.md`): `pipeline2.sh` → seed → `scripts/audit_v2.py` → restore dump ke DB kosong → `scripts/verify/run_snapshot.py` → bandingkan dengan referensi.

## 6. Invarian data yang harus selalu benar

Diperiksa oleh `scripts/audit_v2.py` dan dataset `kpi` pada snapshot:
- total debit = total kredit; tidak ada jurnal draft;
- tidak ada stok internal negatif;
- saldo GL piutang/hutang = Σ sisa item terbuka (subledger);
- 100% baris pendapatan, HPP, dan beban punya analytic (Channel atau Cost Center);
- hanya IDR aktif; 6 channel; omzet bulanan Rp 200–350 jt (Okt parsial s.d. 17); margin kotor ±45–55%;
- GL persediaan ≈ Σ `total_value` produk (selisih diketahui Rp 40.005 = butir terbuka, bukan target);
- semua lampiran/foto di DB ada di filestore (`filestore_integrity`).

Garis waktu tetap: `C.START=2026-07-01` s.d. `C.END=2026-10-17`, saldo awal 30 Jun. Oktober sengaja **belum ditutup** (tanpa penyusutan/BPJS/PPh Final/rekap PPN Okt).

## 7. Deploy & operasi Railway

**Variables service Odoo:** `RAILWAY_DOCKERFILE_PATH` boleh kosong (Dockerfile root terdeteksi otomatis) atau menunjuk `deploy/railway/Dockerfile` (isinya dijaga identik dengan Dockerfile root; **keduanya harus menyalin `deploy/seed/`**, kalau tidak dump tidak ada di image dan restore dilewati), `RAILWAY_RUN_UID=0`, `PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE` (referensi ke service Postgres), `ADMIN_PASSWD`, `BASE_URL=https://klambi-bali.odoo.kolondam.dev`, opsional `SEED_MODE` (kosong = restore dump), `RESET_DB`, `SEED_ACCEPT`, `PPH22_START`. Volume di `/var/lib/odoo`. Batas trial: RAM 1 GB, volume 500 MB.

**Urutan init (`deploy/railway/init.sh`)** — ditandai di DB (`batik.init.*`: `base, core, modules, provisioned, seed_started, seeded, patch_channel_reports, postinit_v1`), jadi restart melanjutkan, bukan mengulang:
`[0] restore dump` (hanya bila DB kosong) → `[3/5]` pasang modul yang belum terpasang → post-init (hak admin, `web.base.url`) → patch laporan.

| Situasi | Tindakan |
|---|---|
| Perubahan kode saja (tanpa skema/data) | push → rebuild otomatis |
| Modul custom bertambah | tambahkan ke daftar `EXTRA` di `init.sh` **dan** `scripts/sandbox/pipeline2.sh`; terpasang otomatis saat boot |
| Skema modul custom berubah | `railway ssh` lalu `runuser -u odoo -- odoo -c /tmp/odoo.conf -d $ODOO_DB -u <modul> --stop-after-init` |
| Data demo berubah (seed/provision) | sandbox membuat dump baru + referensi → commit → pemilik set `RESET_DB=<token BARU>` (token yang sama tidak mereset) → deploy |
| Mau restore ulang tanpa perubahan data | `RESET_DB=<token baru>` |
| Restore gagal | log `[0]` menampilkan 15 baris terakhir; init jatuh ke jalur build bertahap (lambat) — sebaiknya perbaiki dump, bukan mengandalkan jalur ini |

Setelah restore pertama, **ganti password** `admin` dan `demo1234` (instance publik), atau pasang Cloudflare Access.

## 8. Jebakan Odoo 19 (sudah ditemui; hindari mengulang)

- Aplikasi akuntansi Community = menu **Penagihan/Invoicing**; akun admin perlu grup akuntansi agar menu muncul (dilakukan `run_postinit.py`).
- Kode akun disimpan per-perusahaan di `account_account.code_store` (jsonb); nama/nilai terjemahan dan field *company-dependent* (`property_cost_method`, dll.) juga jsonb → di SQL pakai `->>'en_US'` / `->>(company_id)::text`.
- Odoo menolak `db_user=postgres`: pakai role aplikasi (`odoo_app`). Env `PG*` **mengalahkan** file config; kosongkan lewat `env -u` dan kirim opsi `--db_*` di CLI.
- Sub-perintah `odoo shell` harus tepat setelah `odoo`, opsi sesudahnya.
- `--without-demo=true` (bukan `all`, yang justru memasang data demo).
- `product.product_category_all` tidak ada; `auditlog.rule` dikonfirmasi lewat `set_to_confirmed()`.
- Field/ORM yang berubah: `group_ids` (bukan `groups_id`) pada user; `is_storable`; `stock.move.quantity`; operator domain `<>` deprecated (pakai `!=`); `tracking=` pada `fields.Selection` tanpa `mail.thread` memicu warning.
- `stock.scrap` memakai lokasi `usage='inventory'` → jurnalnya mengikuti akun valuasi lokasi itu (akun 5130101).
- Aset: profil tidak bisa diubah setelah ada jurnal; penamaan aset dari saldo awal harus ditangani saat pembuatan.
- `mrp_subcontracting`: PO jasa jahit otomatis membuat *Resupply Subkontraktor* + MO subkontrak; jurnal valuasi harus diverifikasi (sudah, pada probe sandbox).
- Cron berjalan saat Odoo hidup (mis. pembersihan quant nol, "Procurement: run scheduler") → raw `stock_quant` bisa berubah; snapshot memakai agregat sehingga tidak terpengaruh.
- Drop schema pada DB besar butuh `max_locks_per_transaction` tinggi; Postgres Railway memakai pengaturan default.
- Model dan menu Indonesia: nama menu mengikuti bahasa pengguna (`id_ID`); sebagian menu OCA berbahasa Inggris.

## 9. Definisi selesai (checklist)

Setiap perubahan:
- [ ] Cek statis lokal lulus (bagian 5).
- [ ] Tidak melanggar aturan bagian 2; tidak ada rahasia/berkas besar baru.
- [ ] Dokumen terkait diperbarui (angka di `DEMO_SCOPE_AND_SCENARIOS.md` bila data berubah).
- [ ] Entri baru di `docs/HANDOFF.md`.

Perubahan yang mempengaruhi data/skema, tambahan:
- [ ] Sandbox: seed penuh `4/4 langkah OK`, `audit_v2.py` bersih (bagian 6).
- [ ] Dump + filestore + referensi dibuat **dari satu build**, dan referensi berasal dari **restore** dump itu (bukan dari DB sumber).
- [ ] `compare_snapshots.py` referensi vs restore baru: `LULUS`.
- [ ] Setelah deploy: ambil snapshot Railway dan bandingkan (`docs/VERIFY.md`); selisih hanya yang bisa dijelaskan.

## 10. Template entri HANDOFF
```markdown
## 2026-MM-DD — <agen/lingkungan> — <topik>
- Berubah: <berkas / perilaku>
- Cabang/commit: <nama>  | Dump: klambi.sql.gz sha256 <8 awal> (atau "tidak berubah")
- Diverifikasi: <apa yang dijalankan + hasil> | Belum diuji: <apa>
- Menunggu: <tindakan untuk agen/pemilik berikutnya>
```
