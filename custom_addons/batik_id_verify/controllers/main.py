import datetime as dt

from odoo import http
from odoo.http import request

from .. import snapshot


class BatikVerify(http.Controller):
    @http.route("/batik/verify/snapshot.zip", type="http", auth="user", methods=["GET"])
    def snapshot_zip(self, label="", asof="", **kw):
        """Unduh snapshot (zip berisi CSV + manifest). Hanya Administrator (Settings)."""
        if not request.env.user.has_group("base.group_system"):
            return request.make_response("Forbidden", status=403)
        data = snapshot.build_zip(request.env, label=label or request.env.cr.dbname, asof=asof or None)
        fname = "snapshot_%s_%s.zip" % ((label or request.env.cr.dbname).replace("/", "_"), dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S"))
        return request.make_response(data, headers=[
            ("Content-Type", "application/zip"),
            ("Content-Disposition", 'attachment; filename="%s"' % fname),
            ("Cache-Control", "no-store"),
        ])
