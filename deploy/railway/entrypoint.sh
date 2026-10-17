#!/usr/bin/env bash
# Entrypoint Railway: tulis odoo.conf dari env, inisialisasi DB bila belum (bertahap, bisa dilanjutkan), lalu start Odoo.
# Variable yang dibutuhkan: PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE (referensi dari service Postgres Railway),
# ADMIN_PASSWD. Opsional: SEED_DEMO (default 1), DEMO_MONTHS, DEMO_ORDERS_PER_MONTH, PPH22_START, ODOO_DB.
set -euo pipefail

# Diagnostik: tampilkan status variable (nilai hanya untuk yang bukan rahasia)
echo ">> cek variable"
for v in PGHOST PGPORT PGUSER PGDATABASE; do echo "   $v=${!v:-<KOSONG>}"; done
for v in PGPASSWORD DATABASE_URL ADMIN_PASSWD; do
  if [ -n "${!v:-}" ]; then echo "   $v=<ada>"; else echo "   $v=<KOSONG>"; fi
done

# Cadangan: bila PGHOST kosong tapi DATABASE_URL ada, pecah URL-nya
if [ -z "${PGHOST:-}" ] && [ -n "${DATABASE_URL:-}" ]; then
  echo ">> PGHOST kosong; memakai DATABASE_URL"
  eval "$(python3 - <<'PY'
import os, shlex
from urllib.parse import urlparse, unquote
u = urlparse(os.environ["DATABASE_URL"])
vals = (("PGHOST", u.hostname), ("PGPORT", u.port or 5432), ("PGUSER", unquote(u.username or "")),
        ("PGPASSWORD", unquote(u.password or "")), ("PGDATABASE", (u.path or "/").lstrip("/")))
for k, v in vals:
    print("export %s=%s" % (k, shlex.quote(str(v or ""))))
PY
)"
fi

: "${PGHOST:?PGHOST kosong. Di service Odoo tambahkan variable DATABASE_URL=\${{Postgres.DATABASE_URL}} (atau PGHOST dll)}"
: "${PGUSER:?PGUSER kosong}" "${PGPASSWORD:?PGPASSWORD kosong}" "${ADMIN_PASSWD:?ADMIN_PASSWD kosong}"
export ODOO_DB="${ODOO_DB:-${PGDATABASE:-railway}}"
export PGPORT="${PGPORT:-5432}"

# Odoo menolak db_user=postgres. Buat/sinkronkan role aplikasi non-superuser lewat kredensial admin.
export ODOO_PGUSER="${ODOO_PGUSER:-odoo_app}" ODOO_PGPASSWORD="${ODOO_PGPASSWORD:-$PGPASSWORD}"
python3 /opt/batik/dbmark.py role || {
  echo "!! gagal membuat role aplikasi; memakai PGUSER apa adanya"
  export ODOO_PGUSER="$PGUSER" ODOO_PGPASSWORD="$PGPASSWORD"
}
export DEMO_MONTHS="${DEMO_MONTHS:-3}" DEMO_ORDERS_PER_MONTH="${DEMO_ORDERS_PER_MONTH:-30}"

chown -R odoo:odoo /var/lib/odoo 2>/dev/null || true
rm -f /tmp/odoo.conf   # sisa run sebelumnya (milik user odoo) tidak boleh ditimpa root di /tmp
cat > /tmp/odoo.conf <<CONF
[options]
addons_path = /usr/lib/python3/dist-packages/odoo/addons,/mnt/oca-addons/account-financial-reporting,/mnt/oca-addons/account-financial-tools,/mnt/oca-addons/account-invoicing,/mnt/oca-addons/account-analytic,/mnt/oca-addons/account-reconcile,/mnt/oca-addons/server-tools,/mnt/oca-addons/mis-builder,/mnt/oca-addons/reporting-engine,/mnt/oca-addons/bank-statement-import,/mnt/custom-addons
data_dir = /var/lib/odoo
admin_passwd = ${ADMIN_PASSWD}
db_host = ${PGHOST}
db_port = ${PGPORT}
db_user = ${ODOO_PGUSER}
db_password = ${ODOO_PGPASSWORD}
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
exec runuser -u odoo -- env -u PGUSER -u PGPASSWORD -u PGHOST -u PGPORT -u PGDATABASE \
  odoo -c /tmp/odoo.conf --db_host="$PGHOST" --db_port="$PGPORT" --db_user="$ODOO_PGUSER" --db_password="$ODOO_PGPASSWORD"
