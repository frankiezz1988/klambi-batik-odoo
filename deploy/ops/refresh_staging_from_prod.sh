#!/usr/bin/env bash
# Salin data prod ke staging untuk uji realistis, dengan NETRALISASI agar staging tidak mengirim email/
# memproses pembayaran nyata: server email, cron, dan kredensial integrasi dimatikan.
# Pakai:  deploy/ops/refresh_staging_from_prod.sh   (dijalankan dari clone mana pun di VPS)
set -euo pipefail
cd "$(dirname "$0")/../.."
ROOT="$(pwd)"
PROD_DIR="${PROD_DIR:-/opt/batik/prod}"; STG_DIR="${STG_DIR:-/opt/batik/staging}"
( cd "$PROD_DIR" && bash deploy/ops/backup.sh prod )
set -a; . "$PROD_DIR/env.prod"; PD="$BACKUP_DIR"; PDB="$ODOO_DB"; . "$STG_DIR/env.staging"; set +a
DUMP="$(ls -1t "$PD/${PDB}"-*.dump | head -1)"; FS="${DUMP%.dump}.filestore.tgz"
( cd "$STG_DIR" && bash deploy/ops/restore.sh staging "$DUMP" "$FS" )
set -a; . "$STG_DIR/env.staging"; set +a
docker compose -p batik-staging --env-file "$STG_DIR/env.staging" -f "$STG_DIR/deploy/compose.vps.yml" exec -T db \
  psql -U "$PG_USER" -d "$ODOO_DB" <<'SQL'
UPDATE ir_mail_server SET active = false;
UPDATE ir_cron SET active = false ;
SQL
echo "Staging di-refresh dari prod. Cron & server email dimatikan. Aktifkan cron manual bila perlu menguji."
