"""Penanda tahap inisialisasi di ir_config_parameter. Pakai: dbmark.py get|set <key>  (exit 0 = ada/ok)."""
import os
import sys

import psycopg2

conn = psycopg2.connect(host=os.environ["PGHOST"], port=os.environ.get("PGPORT", "5432"),
                        user=os.environ["PGUSER"], password=os.environ["PGPASSWORD"],
                        dbname=os.environ["ODOO_DB"])
conn.autocommit = True
cur = conn.cursor()
cur.execute("select to_regclass('public.ir_config_parameter')")
has_table = cur.fetchone()[0] is not None
mode, key = sys.argv[1], "batik.init." + sys.argv[2]
if mode == "get":
    if not has_table:
        sys.exit(1)
    cur.execute("select 1 from ir_config_parameter where key=%s", (key,))
    sys.exit(0 if cur.fetchone() else 1)
if mode == "set":
    if not has_table:
        sys.exit(2)
    cur.execute("delete from ir_config_parameter where key=%s", (key,))
    cur.execute("insert into ir_config_parameter (key, value, create_date, write_date) values (%s,'1',now(),now())", (key,))
    sys.exit(0)
sys.exit(3)
