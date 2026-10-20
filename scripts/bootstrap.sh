#!/usr/bin/env bash
# Bootstrap DB dari nol: base -> company (IDR/Indonesia) -> modul core -> modul OCA/custom (satu per satu, fail-soft).
set -uo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a
DB="${ODOO_DB:-batik_demo}"
COMPOSE="${COMPOSE_CMD:-${COMPOSE:-docker compose}}"
RUN=($COMPOSE run --rm -T odoo)

CORE="account,l10n_id,sale_management,purchase,stock,stock_account,stock_landed_costs,mrp,mrp_subcontracting,point_of_sale"
# OCA + custom: dipasang satu per satu supaya 1 modul bermasalah tidak menggagalkan semuanya
EXTRA_MODULES=(
  batik_id_tax
  batik_id_coretax
  batik_id_payroll
  auditlog
  account_financial_report
  account_tax_balance
  partner_statement
  mis_builder
  mis_builder_cash_flow
  account_analytic_required
  account_invoice_constraint_chronology
  account_journal_lock_date
  account_lock_date_update
  account_fiscal_year
  account_move_template
  report_xlsx
  account_asset_management
  mis_builder_budget
  account_statement_base
  account_reconcile_oca
  account_statement_import_file
  batik_id_verify
)

$COMPOSE up -d db
echo ">> [1/4] base + bahasa Indonesia"
"${RUN[@]}" odoo -d "$DB" -i base --stop-after-init --without-demo=true --load-language=id_ID || exit 1

echo ">> [2/4] company: Indonesia / IDR (harus sebelum modul accounting)"
"${RUN[@]}" odoo shell -d "$DB" --no-http < scripts/provision/run_company.py || exit 1

echo ">> [3/4] modul core: $CORE"
"${RUN[@]}" odoo -d "$DB" -i "$CORE" --stop-after-init --without-demo=true || exit 1

echo ">> [4/4] modul OCA + custom"
FAILED=()
for m in "${EXTRA_MODULES[@]}"; do
  echo "   - install $m"
  if ! "${RUN[@]}" odoo -d "$DB" -i "$m" --stop-after-init --without-demo=true >"/tmp/install_$m.log" 2>&1; then
    echo "     !! GAGAL ($m) -> lihat /tmp/install_$m.log (tail di bawah)"
    tail -n 5 "/tmp/install_$m.log"
    FAILED+=("$m")
  fi
done

echo
if [ ${#FAILED[@]} -gt 0 ]; then
  echo "Modul gagal terpasang: ${FAILED[*]}"
  echo "Demo tetap bisa jalan; hapus modul itu dari scripts/bootstrap.sh atau cek kompatibilitas branch 19.0."
else
  echo "Semua modul terpasang."
fi
