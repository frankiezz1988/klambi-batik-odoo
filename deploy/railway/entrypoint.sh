#!/usr/bin/env bash
# Entrypoint Railway: tulis odoo.conf dari env, inisialisasi DB bila belum (bertahap, bisa dilanjutkan), lalu start Odoo.
# Variable yang dibutuhkan: PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE (referensi dari service Postgres Railway),
# ADMIN_PASSWD. Opsional: SEED_DEMO (default 1), DEMO_MONTHS, DEMO_ORDERS_PER_MONTH, PPH22_START, ODOO_DB.
set -euo pipefail
: "${PGHOST:?set PGHOST (referensi service Postgres)}"
: "${PGUSER:?}" "${PGPASSWORD:?}" "${ADMIN_PASSWD:?set ADMIN_PASSWD}"
export ODOO_DB="${ODOO_DB:-${PGDATABASE:-railway}}"
export PGPORT="${PGPORT:-5432}"
export DEMO_MONTHS="${DEMO_MONTHS:-3}" DEMO_ORDERS_PER_MONTH="${DEMO_ORDERS_PER_MONTH:-30}"

chown -R odoo:odoo /var/lib/odoo 2>/dev/null || true
cat > /tmp/odoo.conf <<CONF
[options]
addons_path = /usr/lib/python3/dist-packages/odoo/addons,/mnt/oca-addons/account-financial-reporting,/mnt/oca-addons/account-financial-tools,/mnt/oca-addons/account-invoicing,/mnt/oca-addons/account-analytic,/mnt/oca-addons/account-reconcile,/mnt/oca-addons/server-tools,/mnt/oca-addons/mis-builder,/mnt/oca-addons/reporting-engine,/mnt/oca-addons/bank-statement-import,/mnt/custom-addons
data_dir = /var/lib/odoo
admin_passwd = ${ADMIN_PASSWD}
db_host = ${PGHOST}
db_port = ${PGPORT}
db_user = ${PGUSER}
db_password = ${PGPASSWORD}
db_name = ${ODOO_DB}
dbfilter = ^${ODOO_DB}\$
list_db = False
http_interface = 0.0.0.0
http_port = ${PORT:-8069}
proxy_mode = True
workers = 0
max_cron_threads = 1
limit_time_cpu = 900
limit_time_real = 3600
log_level = info
CONF
chown odoo:odoo /tmp/odoo.conf

bash /opt/batik/init.sh || echo "!! init.sh selesai dengan error (lihat log di atas); Odoo tetap dijalankan"

echo ">> start Odoo di port ${PORT:-8069}"
exec runuser -u odoo -- odoo -c /tmp/odoo.conf
