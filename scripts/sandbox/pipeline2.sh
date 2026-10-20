#!/usr/bin/env bash
# pipeline2.sh DB : bangun DB dasar (base -> company -> core -> extra -> provision -> master)
. $(dirname $0)/env.sh
DB=$1; cd $B
psq postgres -qc "drop database if exists $DB" -c "create database $DB owner odoo"
PGPASSWORD=postgres /usr/lib/postgresql/16/bin/psql -h /var/tmp/pgb -p 5544 -U postgres $DB -qc "create extension if not exists unaccent" -c "create extension if not exists pg_trgm"
CORE="account,l10n_id,sale_management,purchase,stock,stock_account,stock_landed_costs,mrp,mrp_subcontracting,point_of_sale"
EXTRA=(batik_id_tax batik_id_coretax batik_id_payroll auditlog account_financial_report account_tax_balance
  partner_statement mis_builder mis_builder_cash_flow account_analytic_required account_invoice_constraint_chronology
  account_journal_lock_date account_lock_date_update account_fiscal_year account_move_template report_xlsx
  account_asset_management mis_builder_budget account_statement_base account_reconcile_oca account_statement_import_file batik_id_verify)
t0=$(date +%s)
echo "[1] base $(date +%T)"
odoo -d $DB -i base --stop-after-init --without-demo=true --load-language=id_ID > p2_base.txt 2>&1 || echo "BASE GAGAL"
echo "[2] company+core $(date +%T)"
oshell -d $DB --no-http < /mnt/scripts/provision/run_company.py > p2_company.txt 2>&1 || echo "company rc=$?"
odoo -d $DB -i "$CORE" --stop-after-init --without-demo=true > p2_core.txt 2>&1 || echo "core rc=$?"
echo "[3] extras $(date +%T)"
odoo -d $DB -i "$(IFS=,; echo "${EXTRA[*]}")" --stop-after-init --without-demo=true > p2_extra.txt 2>&1 || echo "extra rc=$?"
echo "[4] provision $(date +%T)"
oshell -d $DB --no-http < /mnt/scripts/provision/run_provision.py > p2_provision.txt 2>&1 || echo "prov rc=$?"
echo "[4b] master $(date +%T)"
oshell -d $DB --no-http < /mnt/scripts/provision/run_master.py > p2_master.txt 2>&1 || echo "master rc=$?"
echo "done $(date +%T) total $(( $(date +%s)-t0 ))s"
