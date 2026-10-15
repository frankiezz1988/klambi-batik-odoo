# Dijalankan via: odoo shell -d DB < run_company.py   (variabel `env` disediakan oleh odoo shell)
import sys

sys.path.insert(0, "/mnt/scripts/provision")
import provision  # noqa: E402

provision.setup_company(env)  # noqa: F821
env.cr.commit()  # noqa: F821
