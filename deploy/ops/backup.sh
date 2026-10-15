#!/usr/bin/env bash
# Backup DB (pg_dump custom format) + filestore. Pakai:  deploy/ops/backup.sh <staging|prod>
# Retensi default 14 backup terakhir (KEEP=n untuk ubah). Simpan salinan off-site (mis. rclone ke R2/B2).
set -euo pipefail
STACK="${1:?usage: backup.sh <staging|prod>}"
cd "$(dirname "$0")/../.."
set -a; . "./env.${STACK}"; set +a
P="batik-${STACK}"; TS="$(date +%Y%m%d-%H%M%S)"; KEEP="${KEEP:-14}"
mkdir -p "${BACKUP_DIR}"
docker compose -p "$P" --env-file "env.${STACK}" -f deploy/compose.vps.yml exec -T db \
  pg_dump -U "$PG_USER" -Fc "$ODOO_DB" > "${BACKUP_DIR}/${ODOO_DB}-${TS}.dump"
docker run --rm -v "${P}_odoo-data:/data:ro" -v "${BACKUP_DIR}:/out" alpine \
  tar czf "/out/${ODOO_DB}-${TS}.filestore.tgz" -C /data .
ls -1t "${BACKUP_DIR}"/*.dump 2>/dev/null | tail -n +$((KEEP+1)) | xargs -r rm -f
ls -1t "${BACKUP_DIR}"/*.filestore.tgz 2>/dev/null | tail -n +$((KEEP+1)) | xargs -r rm -f
echo "backup OK: ${BACKUP_DIR}/${ODOO_DB}-${TS}.{dump,filestore.tgz}"
