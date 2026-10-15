SHELL := /bin/bash
-include .env
export
DB ?= $(or $(ODOO_DB),batik_demo)
RUN = docker compose run --rm -T odoo

.PHONY: setup oca build bootstrap provision seed finalize snapshot up down reset logs shell lint

setup: oca build bootstrap provision seed   ## setup penuh dari nol (~15-30 menit)

oca:                                   ## clone repo OCA (branch ODOO_VERSION)
	bash scripts/fetch_oca.sh

build:
	docker compose build odoo

bootstrap:                             ## DB + company IDR + modul core + OCA + custom
	bash scripts/bootstrap.sh

provision:                             ## CoA retail, pajak, analytic channel, jurnal, kategori produk, MIS
	$(RUN) odoo shell -d $(DB) --no-http < scripts/provision/run_provision.py

seed:                                  ## data dummy + audit rule + user demo
	$(RUN) odoo shell -d $(DB) --no-http < scripts/provision/run_seed.py

snapshot:                              ## export laporan statis ke ./site (butuh Odoo jalan di :8069)
	python3 scripts/snapshot/build_snapshot.py --out site

up:
	docker compose up -d odoo
down:
	docker compose down
reset:                                 ## hapus semua data (DB + filestore)
	docker compose down -v
logs:
	docker compose logs -f odoo
shell:
	docker compose run --rm odoo odoo shell -d $(DB) --no-http

lint:
	python3 -m py_compile $$(git ls-files '*.py' 2>/dev/null || find . -name '*.py' -not -path './addons-oca/*')
