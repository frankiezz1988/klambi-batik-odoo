#!/usr/bin/env bash
# Inisialisasi bertahap & fail-soft. Tiap tahap ditandai di DB (batik.init.*) sehingga restart melanjutkan, bukan mengulang.
set -uo pipefail
DB="$ODOO_DB"
# Odoo 19 memberi prioritas env PGUSER/PGHOST/PGPASSWORD/PGPORT di atas file config -> kosongkan, kirim lewat CLI.
# Catatan: sub-perintah `shell` harus tepat setelah `odoo`, opsi diletakkan sesudahnya.
ODOO_PRE=(runuser -u odoo -- env -u PGUSER -u PGPASSWORD -u PGHOST -u PGPORT -u PGDATABASE)
ODOO_OPTS=(-c /tmp/odoo.conf --db_host="$PGHOST" --db_port="$PGPORT" --db_user="$ODOO_PGUSER" --db_password="$ODOO_PGPASSWORD")
odoo_srv()   { "${ODOO_PRE[@]}" odoo "${ODOO_OPTS[@]}" "$@"; }
odoo_shell() { "${ODOO_PRE[@]}" odoo shell "${ODOO_OPTS[@]}" "$@"; }
mark_get() { python3 /opt/batik/dbmark.py get "$1"; }
mark_set() { python3 /opt/batik/dbmark.py set "$1"; }

CORE="account,l10n_id,sale_management,purchase,stock,stock_account,stock_landed_costs"
EXTRA=(batik_id_tax batik_id_coretax batik_id_payroll auditlog account_financial_report account_tax_balance
  partner_statement mis_builder mis_builder_cash_flow account_analytic_required account_invoice_constraint_chronology
  account_journal_lock_date account_lock_date_update account_fiscal_year account_move_template report_xlsx
  account_asset_management mis_builder_budget account_statement_base account_reconcile_oca account_statement_import_file)

if ! mark_get base; then
  echo ">> [1/5] base + bahasa Indonesia"
  odoo_srv -d "$DB" -i base --stop-after-init --without-demo=all --load-language=id_ID || exit 1
  mark_set base
fi
if ! mark_get core; then
  echo ">> [2/5] company Indonesia/IDR lalu modul core"
  odoo_shell -d "$DB" --no-http < /mnt/scripts/provision/run_company.py || exit 1
  odoo_srv -d "$DB" -i "$CORE" --stop-after-init --without-demo=all || exit 1
  mark_set core
fi
if ! mark_get modules; then
  echo ">> [3/5] modul OCA + custom (satu per satu)"
  FAILED=()
  for m in "${EXTRA[@]}"; do
    echo "   - $m"
    odoo_srv -d "$DB" -i "$m" --stop-after-init --without-demo=all >"/tmp/install_$m.log" 2>&1 \
      || { echo "     !! GAGAL $m"; tail -n 5 "/tmp/install_$m.log"; FAILED+=("$m"); }
  done
  [ ${#FAILED[@]} -gt 0 ] && echo "Modul gagal: ${FAILED[*]}"
  mark_set modules
fi
if ! mark_get provisioned; then
  echo ">> [4/5] provisioning (CoA, pajak, analytic, jurnal)"
  odoo_shell -d "$DB" --no-http < /mnt/scripts/provision/run_provision.py && mark_set provisioned
fi
if [ "${SEED_DEMO:-1}" = "1" ] && ! mark_get seeded; then
  if mark_get seed_started; then
    echo "!! Seed pernah dimulai tapi tidak selesai (mungkin kehabisan memori). TIDAK diulang otomatis agar data tidak ganda."
    echo "   Reset: kosongkan DB (hapus & buat ulang service Postgres/volume) lalu deploy ulang, dengan DEMO_ORDERS_PER_MONTH lebih kecil."
  else
    echo ">> [5/5] seed data demo (${DEMO_MONTHS} bulan x ${DEMO_ORDERS_PER_MONTH} order)"
    mark_set seed_started
    odoo_shell -d "$DB" --no-http < /mnt/scripts/provision/run_seed.py && mark_set seeded
  fi
fi
echo ">> init selesai"
