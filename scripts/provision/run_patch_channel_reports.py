"""Patch idempoten (tanpa reset): laporan MIS Laba Rugi per channel.
Dijalankan lewat `odoo shell` (variabel global env) oleh deploy/railway/init.sh."""
import sys

sys.path.insert(0, "/mnt/scripts/provision")
import config as C  # noqa: E402
from common import Steps, load_registry  # noqa: E402

s = Steps(env)  # noqa: F821


def periods(domain=None, name=None):
    base = {"mode": "relative", "type": "m", "offset": -2, "duration": 3}
    if name:
        base["name"] = name
    if domain:
        base["analytic_domain"] = domain
    return base


with s.step("MIS: Laba Rugi per channel"):
    reg = load_registry(env)
    report = env["mis.report"].search([("name", "=", "Laba Rugi - Retail Batik")], limit=1)
    if not report:
        raise RuntimeError("template MIS 'Laba Rugi - Retail Batik' tidak ditemukan")
    Inst = env["mis.report.instance"]
    made = []
    # 1) satu laporan, kolom per channel (perbandingan profitabilitas), 3 bulan terakhir
    name = "Laba Rugi per Channel (3 bulan)"
    if not Inst.search([("name", "=", name)], limit=1):
        cols = [(0, 0, periods(None, "Semua channel"))]
        for ch in C.CHANNELS:
            dom = str([("analytic_distribution", "in", [reg["analytic"][ch["code"]]])])
            cols.append((0, 0, periods(dom, ch["name"])))
        Inst.create({"name": name, "report_id": report.id, "company_id": env.company.id, "period_ids": cols})
        made.append(name)
    # 2) satu laporan per channel, kolom per bulan
    for ch in C.CHANNELS:
        nm = f"Laba Rugi - {ch['name']}"
        if Inst.search([("name", "=", nm)], limit=1):
            continue
        dom = str([("analytic_distribution", "in", [reg["analytic"][ch["code"]]])])
        cols = [(0, 0, {"name": f"M-{i}" if i else "Bulan ini", "mode": "relative", "type": "m",
                        "offset": -i, "duration": 1, "analytic_domain": dom}) for i in range(2, -1, -1)]
        Inst.create({"name": nm, "report_id": report.id, "company_id": env.company.id, "period_ids": cols})
        made.append(nm)
    print("Laporan MIS dibuat: " + (", ".join(made) if made else "(sudah ada)"))

s.summary()
env.cr.commit()  # noqa: F821
