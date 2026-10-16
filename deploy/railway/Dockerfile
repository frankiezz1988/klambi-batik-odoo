# Image untuk Railway: semua kode (OCA + custom + script) DI-BAKE ke image, karena Railway tidak
# memakai bind mount dari repo. Pakai dengan variable service:  RAILWAY_DOCKERFILE_PATH=deploy/railway/Dockerfile
ARG ODOO_VERSION=19.0
FROM odoo:${ODOO_VERSION}
ARG ODOO_VERSION

USER root
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --break-system-packages -r /tmp/requirements.txt \
    || pip install --no-cache-dir -r /tmp/requirements.txt

# OCA (shallow) sesuai oca-repos.txt, branch = ODOO_VERSION
COPY oca-repos.txt /tmp/oca-repos.txt
RUN mkdir -p /mnt/oca-addons \
    && grep -vE '^\s*(#|$)' /tmp/oca-repos.txt | while read -r repo; do \
         git clone --depth 1 --branch "${ODOO_VERSION}" "https://github.com/OCA/${repo}.git" "/mnt/oca-addons/${repo}" \
         && rm -rf "/mnt/oca-addons/${repo}/.git"; \
       done

COPY custom_addons /mnt/custom-addons
COPY scripts /mnt/scripts
COPY data /mnt/data
COPY deploy/railway/entrypoint.sh deploy/railway/init.sh deploy/railway/dbmark.py /opt/batik/
RUN chmod +x /opt/batik/entrypoint.sh /opt/batik/init.sh

# Jalan sebagai root hanya untuk chown volume; Odoo sendiri dijalankan sebagai user `odoo` (runuser).
ENTRYPOINT ["/opt/batik/entrypoint.sh"]
