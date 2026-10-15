#!/usr/bin/env bash
# Restore ke stack:  deploy/ops/restore.sh <staging|prod> <file.dump> [file.filestore.tgz]
# DESTRUKTIF: menimpa DB target. Untuk prod diminta konfirmasi ketik nama DB.
set -euo pipefail
STACK="${1:?usage: restore.sh <stack> <dump> [filestore.tgz]}"; DUMP="${2:?dump}"; FS="${3:-}"
cd "$(dirname "$0")/../.."
set -a; . "./env.${STACK}"; set +a
P="batik-${STACK}"; C=(docker compose -p "$P" --env-file "env.${STACK}" -f deploy/compose.vps.yml)
if [ "$STACK" = "prod" ]; then read -rp "Ketik '${ODOO_DB}' untuk menimpa DB prod: " a; [ "$a" = "$ODOO_DB" ] || exit 1; fi
"${C[@]}" stop odoo
"${C[@]}" exec -T db psql -U "$PG_USER" -d postgres -c "DROP DATABASE IF EXISTS \"$ODOO_DB\" WITH (FORCE);"
"${C[@]}" exec -T db psql -U "$PG_USER" -d postgres -c "CREATE DATABASE \"$ODOO_DB\" OWNER \"$PG_USER\";"
"${C[@]}" exec -T db pg_restore -U "$PG_USER" -d "$ODOO_DB" --no-owner < "$DUMP"
if [ -n "$FS" ]; then
  docker run --rm -v "${P}_odoo-data:/data" -v "$(dirname "$(realpath "$FS")"):/in:ro" alpine \
    sh -c "rm -rf /data/* && tar xzf /in/$(basename "$FS") -C /data"
fi
"${C[@]}" up -d odoo
echo "restore selesai"
