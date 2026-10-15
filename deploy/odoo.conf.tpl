; Di-render oleh deploy/deploy.sh dengan envsubst. Jangan commit hasil render (.rendered/ di .gitignore).
[options]
addons_path = /usr/lib/python3/dist-packages/odoo/addons,/mnt/oca-addons/account-financial-reporting,/mnt/oca-addons/account-financial-tools,/mnt/oca-addons/account-invoicing,/mnt/oca-addons/account-analytic,/mnt/oca-addons/account-reconcile,/mnt/oca-addons/server-tools,/mnt/oca-addons/mis-builder,/mnt/oca-addons/reporting-engine,/mnt/oca-addons/bank-statement-import,/mnt/custom-addons
admin_passwd = ${ADMIN_PASSWD}
db_name = ${ODOO_DB}
dbfilter = ^${ODOO_DB}$
list_db = False
proxy_mode = True
workers = ${ODOO_WORKERS}
max_cron_threads = 1
gevent_port = 8072
; batas memori per worker (byte): soft 640MB / hard 768MB
limit_memory_soft = 671088640
limit_memory_hard = 805306368
limit_time_cpu = 600
limit_time_real = 1200
log_level = ${ODOO_LOG_LEVEL}
