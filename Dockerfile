ARG ODOO_VERSION=19.0
FROM odoo:${ODOO_VERSION}

USER root
COPY requirements.txt /tmp/requirements.txt
# OCA modules kadang butuh lib python tambahan (openpyxl/xlsxwriter untuk report XLSX, dll.)
RUN pip install --no-cache-dir --break-system-packages -r /tmp/requirements.txt \
    || pip install --no-cache-dir -r /tmp/requirements.txt

USER odoo
