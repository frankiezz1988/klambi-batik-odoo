"""Patch idempoten (tanpa reset): laporan MIS Laba Rugi per channel.
Dijalankan lewat `odoo shell` (variabel global env) oleh deploy/railway/init.sh."""
import sys

sys.path.insert(0, "/mnt/scripts/provision")
import config as C  # noqa: E402
from common import Steps, load_registry  # noqa: E402

s = Steps(env)  # noqa: F821


import datetime as dt  # noqa: E402

from dateutil.relativedelta import relativedelta  # noqa: E402

# Periode TETAP (data demo berhenti 17 Okt 2026), bukan relatif ke tanggal hari ini
MONTHS = [C.START.replace(day=1) + relativedelta(months=i) for i in range(4)]


def fixed(d0, d1, name, domain=None):
    base = {"name": name, "mode": "fix", "manual_date_from": d0, "manual_date_to": d1}
    if domain:
        base["analytic_domain"] = domain
    return base


def periods(domain=None, name=None):
    return fixed(C.START, C.END, name or "Jul - 17 Okt 2026", domain)


with s.step("MIS: Laba Rugi per channel"):
    reg = load_registry(env)
    report = env["mis.report"].search([("name", "=", "Laba Rugi - Retail Batik")], limit=1)
    if not report:
        raise RuntimeError("template MIS 'Laba Rugi - Retail Batik' tidak ditemukan")
    Inst = env["mis.report.instance"]
    made = []
    # 1) satu laporan, kolom per channel (perbandingan profitabilitas), 3 bulan terakhir
    name = "Laba Rugi per Channel (Jul - 17 Okt 2026)"
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
        cols = [(0, 0, fixed(m, min((m + relativedelta(months=1)) - dt.timedelta(days=1), C.END),
                             f"{m:%b %Y}" + (" (s.d. 17)" if m.month == C.END.month else ""), dom)) for m in MONTHS]
        Inst.create({"name": nm, "report_id": report.id, "company_id": env.company.id, "period_ids": cols})
        made.append(nm)
    print("Laporan MIS dibuat: " + (", ".join(made) if made else "(sudah ada)"))

s.summary()
env.cr.commit()  # noqa: F821
