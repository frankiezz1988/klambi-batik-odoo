# Post-init idempoten (dijalankan di `odoo shell`): admin mendapat semua hak bisnis agar menu Akuntansi/Penjualan/
# Gudang/POS tampil, dan web.base.url diambil dari env BASE_URL bila ada.
import os, sys
sys.path.insert(0, "/mnt/scripts/provision")
from common import user_group_field  # noqa: E402

gf = user_group_field(env)  # noqa: F821
adm = env.ref("base.user_admin", raise_if_not_found=False)  # noqa: F821
XMLIDS = ["account.group_account_manager", "account.group_account_user", "account.group_account_invoice",
          "sales_team.group_sale_manager", "purchase.group_purchase_manager", "stock.group_stock_manager",
          "mrp.group_mrp_manager", "point_of_sale.group_pos_manager", "analytic.group_analytic_accounting",
          "uom.group_uom"]
n = 0
if adm:
    for x in XMLIDS:
        g = env.ref(x, raise_if_not_found=False)  # noqa: F821
        if g:
            adm.write({gf: [(4, g.id)]})
            n += 1
url = os.environ.get("BASE_URL", "").strip().rstrip("/")
if url:
    ICP = env["ir.config_parameter"].sudo()  # noqa: F821
    ICP.set_param("web.base.url", url)
    ICP.set_param("web.base.url.freeze", "True")
env.cr.commit()  # noqa: F821
print("POST-INIT: admin +%d grup%s" % (n, (", web.base.url=" + url) if url else ""))
