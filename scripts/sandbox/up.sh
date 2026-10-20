#!/usr/bin/env bash
# up.sh : hidupkan lagi Postgres sandbox setelah container di-restart (disk bertahan, proses tidak). Idempoten.
B=/usr/lib/postgresql/16/bin; D=/var/tmp/pgb
mkdir -p $D; chown pgtest $D 2>/dev/null
if PGPASSWORD=odoo $B/psql -h $D -p 5544 -U odoo postgres -Atc "select 1" >/dev/null 2>&1; then echo "postgres sudah hidup"; exit 0; fi
rm -f $D/d/postmaster.pid $D/.s.PGSQL.5544*
su pgtest -c "$B/pg_ctl -D $D/d -o '-p 5544 -k $D' -l $D/log -w start" | tail -1
PGPASSWORD=odoo $B/psql -h $D -p 5544 -U odoo postgres -Atc "select datname from pg_database where datname like 'kl2%'" | tr '\n' ' '; echo
