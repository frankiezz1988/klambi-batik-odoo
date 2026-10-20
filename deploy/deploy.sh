#!/usr/bin/env bash
# Deploy satu stack di VPS:  deploy/deploy.sh <staging|prod> [git-ref]
# Dijalankan DI DALAM clone repo (mis. /opt/batik/staging atau /opt/batik/prod).
# Langkah: checkout ref -> OCA -> render config -> build -> up -> update modul custom/OCA yang berubah.
set -euo pipefail
STACK="${1:?usage: deploy.sh <staging|prod> [git-ref]}"
REF="${2:-}"
cd "$(dirname "$0")/.."
ENVF="env.${STACK}"
[ -f "$ENVF" ] || { echo "!! $ENVF tidak ada (salin dari deploy/env.${STACK}.example)"; exit 1; }
set -a; . "./$ENVF"; set +a
COMPOSE=(docker compose -p "batik-${STACK}" --env-file "$ENVF" -f deploy/compose.vps.yml)

if [ -n "$REF" ]; then
  git fetch --tags --prune origin
  git checkout -q --detach "$REF" 2>/dev/null || git checkout -q --detach "origin/$REF"
fi
echo ">> ${STACK} @ $(git rev-parse --short HEAD)"

# Backup sebelum prod berubah
if [ "$STACK" = "prod" ] && "${COMPOSE[@]}" ps --status running db 2>/dev/null | grep -q db; then
  bash deploy/ops/backup.sh prod || { echo "!! backup gagal, deploy dibatalkan"; exit 1; }
fi

bash scripts/fetch_oca.sh
mkdir -p .rendered "${BACKUP_DIR}"
envsubst < deploy/odoo.conf.tpl > ".rendered/${STACK}.odoo.conf"

"${COMPOSE[@]}" build odoo
"${COMPOSE[@]}" up -d db
RUN=("${COMPOSE[@]}" run --rm -T odoo)

if ! "${COMPOSE[@]}" exec -T db psql -U "$PG_USER" -lqt | cut -d'|' -f1 | grep -qw "$ODOO_DB"; then
  echo ">> DB ${ODOO_DB} belum ada -> inisialisasi"
  COMPOSE_CMD="docker compose -p batik-${STACK} --env-file ${ENVF} -f deploy/compose.vps.yml" \
    bash scripts/bootstrap.sh
  if [ "${SEED_DEMO:-0}" = "1" ]; then
    "${RUN[@]}" odoo shell -d "$ODOO_DB" --no-http < scripts/provision/run_provision.py
    "${RUN[@]}" odoo shell -d "$ODOO_DB" --no-http < scripts/provision/run_seed.py
  else
    "${RUN[@]}" odoo shell -d "$ODOO_DB" --no-http < scripts/provision/run_provision.py
    echo ">> SEED_DEMO=0: hanya CoA/pajak/jurnal yang diprovisi (tanpa data dummy)"
  fi
else
  echo ">> DB ada -> update modul custom"
  "${RUN[@]}" odoo -d "$ODOO_DB" -u batik_id_tax,batik_id_coretax,batik_id_payroll,batik_id_verify --stop-after-init || \
    echo "!! update modul custom gagal (lihat log)"
fi

"${COMPOSE[@]}" up -d odoo
echo ">> selesai. Odoo di 127.0.0.1:${ODOO_PORT} (publik lewat Cloudflare Tunnel)"
