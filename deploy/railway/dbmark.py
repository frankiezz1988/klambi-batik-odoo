"""Helper DB untuk entrypoint Railway.
  dbmark.py role          buat/sinkronkan role aplikasi non-superuser (Odoo menolak db_user=postgres)
  dbmark.py get <tahap>   exit 0 bila tahap inisialisasi sudah ditandai
  dbmark.py set <tahap>   tandai tahap selesai
Koneksi admin dari PGHOST/PGPORT/PGUSER/PGPASSWORD, database ODOO_DB."""
import os
import sys

import psycopg2
from psycopg2 import sql


def connect(dbname):
    conn = psycopg2.connect(host=os.environ["PGHOST"], port=os.environ.get("PGPORT", "5432"),
                            user=os.environ["PGUSER"], password=os.environ["PGPASSWORD"], dbname=dbname)
    conn.autocommit = True
    return conn


mode = sys.argv[1]
db = os.environ["ODOO_DB"]

if mode == "role":
    app_user = os.environ["ODOO_PGUSER"]
    app_pw = os.environ["ODOO_PGPASSWORD"]
    cur = connect(db).cursor()
    cur.execute("select 1 from pg_roles where rolname=%s", (app_user,))
    action = "ALTER" if cur.fetchone() else "CREATE"
    cur.execute(sql.SQL(action + " ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(app_user), sql.Literal(app_pw)))
    cur.execute(sql.SQL("ALTER DATABASE {} OWNER TO {}").format(sql.Identifier(db), sql.Identifier(app_user)))
    cur.execute(sql.SQL("ALTER SCHEMA public OWNER TO {}").format(sql.Identifier(app_user)))
    for ext in ("unaccent", "pg_trgm"):
        try:
            cur.execute(sql.SQL("CREATE EXTENSION IF NOT EXISTS {}").format(sql.Identifier(ext)))
        except Exception as exc:  # noqa: BLE001
            print("peringatan: extension %s: %s" % (ext, str(exc).strip()))
    print("role aplikasi siap: %s" % app_user)
    sys.exit(0)

cur = connect(db).cursor()
cur.execute("select to_regclass('public.ir_config_parameter')")
has_table = cur.fetchone()[0] is not None
key = "batik.init." + sys.argv[2]
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
