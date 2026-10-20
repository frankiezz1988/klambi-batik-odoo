# Dipakai oleh skrip lain di folder ini (source). SANDBOX_DIR = folder kerja yang berisi odoo/ oca/ data/ odoo.conf venv/
: "${SANDBOX_DIR:?set SANDBOX_DIR ke folder kerja sandbox (berisi odoo/ oca/ venv/ data/ odoo.conf)}"
B=$SANDBOX_DIR
export PATH=$B/venv/bin:$PATH
export PGPASSWORD=odoo
odoo()  { python $B/odoo/odoo-bin -c $B/odoo.conf "$@"; }
oshell(){ python $B/odoo/odoo-bin shell -c $B/odoo.conf "$@"; }
psq(){ /usr/lib/postgresql/16/bin/psql -h /var/tmp/pgb -p 5544 -U odoo "$@"; }
