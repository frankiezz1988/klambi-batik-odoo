#!/usr/bin/env bash
# Membuat dump database demo (untuk jalur restore Railway/VPS) dari DB yang sudah di-seed & divalidasi.
# Pakai (contoh di sandbox/VPS yang punya odoo + psql + pg_dump):
#   SRC_DB=kl2_t FILESTORE=/path/data/filestore/kl2_t OUT=deploy/seed bash scripts/build_dump.sh
# Hasil: $OUT/klambi.sql.gz (SQL polos tanpa owner/ACL) dan $OUT/filestore.tgz (foto produk, dll).
# Perintah `odoo_shell` / `psql` / `pg_dump` mengikuti environment pemanggil (PG* env / ~/.pgpass).
set -euo pipefail
: "${SRC_DB:?SRC_DB kosong}" "${FILESTORE:?FILESTORE kosong}"
OUT="${OUT:-deploy/seed}"; mkdir -p "$OUT"
PSQL=(psql -qAt -v ON_ERROR_STOP=1 -d "$SRC_DB")
# 1) penanda tahap init agar init.sh di target tidak mengulang provisioning/seed
for k in base core modules provisioned seed_started seeded patch_channel_reports postinit_v1; do
  "${PSQL[@]}" -c "delete from ir_config_parameter where key='batik.init.$k'" \
     -c "insert into ir_config_parameter(key,value,create_date,write_date) values ('batik.init.$k','1',now(),now())"
done
# 2) buang artefak yang dibangun ulang otomatis / spesifik mesin
"${PSQL[@]}" -c "delete from ir_attachment where url like '/web/assets/%' or url like '/web/static/src/%'" \
  -c "delete from ir_config_parameter where key in ('database.create_date','web.base.url.freeze')" \
  -c "delete from bus_bus" 2>/dev/null || true
"${PSQL[@]}" -c "delete from res_users_log" -c "delete from ir_logging" 2>/dev/null || true
# 3) dump (SQL polos, di-restore dengan psql oleh init.sh)
pg_dump --no-owner --no-acl --no-comments "$SRC_DB" | gzip -9 > "$OUT/klambi.sql.gz"
# 4) filestore (hanya berkas yang dirujuk DB)
tar -C "$FILESTORE" -czf "$OUT/filestore.tgz" .
ls -la "$OUT/klambi.sql.gz" "$OUT/filestore.tgz"
sha256sum "$OUT/klambi.sql.gz" "$OUT/filestore.tgz" > "$OUT/SHA256SUMS"
