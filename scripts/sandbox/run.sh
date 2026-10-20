#!/usr/bin/env bash
# run.sh DB script.py  -> jalankan script di odoo shell, tampilkan tanpa log INFO
. $(dirname $0)/env.sh
oshell -d $1 --no-http < $2 2>&1 | grep -v " INFO \| WARNING "
