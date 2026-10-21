#!/usr/bin/env python3
"""Bandingkan dua snapshot (hasil modul batik_id_verify) baris-per-baris: sandbox vs Railway/VPS.

Pemakaian:
    python3 scripts/verify/compare_snapshots.py A B [--out DIR] [--tol 0.005] [--max-detail 15] [--ignore ds1,ds2] [--label-a sandbox --label-b railway]

A dan B boleh berupa folder snapshot atau berkas .zip. Hanya memakai pustaka standar Python 3.8+.
Hasil: ringkasan di layar + DIR/report.txt, DIR/kpi_side_by_side.txt, DIR/diff_<dataset>.csv (satu per dataset yang berbeda).
Kode keluar: 0 = identik (di luar dataset volatil/info dan tabel sistem; --strict menonaktifkan pengecualian), 1 = ada selisih, 2 = masukan tidak valid.
"""
import argparse
import csv
import io
import json
import os
import sys
import zipfile


def load(path):
    data, manifest = {}, None
    if os.path.isdir(path):
        names = {f: os.path.join(path, f) for f in os.listdir(path)}
        opener = lambda p: open(p, "r", encoding="utf-8", newline="")  # noqa: E731
    elif zipfile.is_zipfile(path):
        z = zipfile.ZipFile(path)
        names = {n: n for n in z.namelist()}
        opener = lambda n: io.TextIOWrapper(z.open(n), encoding="utf-8", newline="")  # noqa: E731
    else:
        sys.exit("Bukan folder/zip snapshot: %s" % path)
    if "manifest.json" not in names:
        sys.exit("manifest.json tidak ada di %s" % path)
    with opener(names["manifest.json"]) as f:
        manifest = json.load(f)
    for fname, p in names.items():
        if fname.endswith(".csv"):
            with opener(p) as f:
                rows = list(csv.reader(f))
            data[fname[:-4]] = (rows[0], rows[1:]) if rows else ([], [])
    return manifest, data


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def same(a, b, tol):
    if a == b:
        return True
    fa, fb = num(a), num(b)
    return fa is not None and fb is not None and abs(fa - fb) <= tol


def index(header, rows, keycols):
    ki = [header.index(k) for k in keycols if k in header]
    idx, dup = {}, 0
    for r in rows:
        k = "|".join(r[i] for i in ki)
        if k in idx:
            dup += 1
            k = "%s##dup%d" % (k, dup)
        idx[k] = r
    return idx


# Tabel sistem/teknis yang jumlah barisnya wajar berbeda antar instance (pemakaian, wizard sementara,
# daftar modul, jejak audit akses). Baris-baris ini dikecualikan dari penilaian 'table_counts'
# dan hanya dilaporkan sebagai informasi. Data bisnis dinilai oleh dataset lain (moves, stock, dst).
SYSTEM_TABLE_PREFIX = (
    "ir_module_", "ir_model_data", "ir_ui_", "ir_translation", "ir_asset", "ir_actions", "ir_act_",
    "auditlog_http_", "auditlog_log", "bus_", "digest_", "discuss_channel", "mail_", "iap_",
    "res_lang_install", "res_users_log", "res_users_settings", "res_users_apikeys", "res_device",
    "account_move_reversal", "account_payment_register", "account_asset_compute", "stock_return_picking",
    "base_language_install", "change_production_qty", "base_import_", "wizard_", "ir_cron", "ir_logging",
)
# Dataset yang hanya informasi (cermin aktivitas pengguna), tidak menggagalkan perbandingan.
INFO_DATASETS = {"auditlog_summary"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--out", default="compare_out")
    ap.add_argument("--tol", type=float, default=0.005)
    ap.add_argument("--max-detail", type=int, default=15)
    ap.add_argument("--ignore", default="")
    ap.add_argument("--strict", action="store_true", help="nilai semua dataset, tanpa pengecualian tabel sistem/info")
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    args = ap.parse_args()
    ignore = {x for x in args.ignore.split(",") if x}
    ma, da = load(args.a)
    mb, db = load(args.b)
    la, lb = args.label_a, args.label_b
    os.makedirs(args.out, exist_ok=True)
    out = []

    def p(s=""):
        out.append(s)
        print(s)

    p("PERBANDINGAN SNAPSHOT")
    p("  %-8s : %s | db=%s | odoo=%s | %s UTC | asof=%s" % (la, args.a, ma.get("database"), ma.get("odoo_version"), ma.get("generated_utc"), ma.get("asof")))
    p("  %-8s : %s | db=%s | odoo=%s | %s UTC | asof=%s" % (lb, args.b, mb.get("database"), mb.get("odoo_version"), mb.get("generated_utc"), mb.get("asof")))
    if ma.get("asof") != mb.get("asof"):
        p("  ! PERINGATAN: tanggal acuan (asof) berbeda; dataset 'aging' tidak sebanding. Ulang snapshot dengan asof sama.")
    for lab, m in ((la, ma), (lb, mb)):
        for k, v in sorted(m.get("errors", {}).items()):
            p("  ! %s: dataset %s tidak terbentuk -> %s" % (lab, k, v))
    p("")
    names = sorted(set(da) | set(db))
    meta = {**mb.get("datasets", {}), **ma.get("datasets", {})}
    summary, details, total_bad = [], [], 0
    for ds in names:
        vol = bool(meta.get(ds, {}).get("volatile"))
        if ds in ignore:
            continue
        if ds not in da or ds not in db:
            summary.append((ds, "-", "-", "-", "-", "-", "HILANG di %s" % (la if ds not in da else lb), vol))
            total_bad += 0 if vol else 1
            continue
        (ha, ra), (hb, rb) = da[ds], db[ds]
        skipped = 0
        if ds == "table_counts" and not args.strict:
            n0 = len(ra) + len(rb)
            ra = [r for r in ra if not r[0].startswith(SYSTEM_TABLE_PREFIX)]
            rb = [r for r in rb if not r[0].startswith(SYSTEM_TABLE_PREFIX)]
            skipped = n0 - len(ra) - len(rb)
        if ds in INFO_DATASETS and not args.strict:
            vol = True
        keycols = meta.get(ds, {}).get("key") or [ha[0]]
        ia, ib = index(ha, ra, keycols), index(hb, rb, keycols)
        only_a = sorted(set(ia) - set(ib))
        only_b = sorted(set(ib) - set(ia))
        cols = [c for c in ha if c in hb and c not in keycols]
        changed, rowsdiff = 0, []
        for k in sorted(set(ia) & set(ib)):
            ra_, rb_ = ia[k], ib[k]
            bad = [(c, ra_[ha.index(c)], rb_[hb.index(c)]) for c in cols if not same(ra_[ha.index(c)], rb_[hb.index(c)], args.tol)]
            if bad:
                changed += 1
                rowsdiff.extend((k, c, x, y) for c, x, y in bad)
        hdr_note = "" if ha == hb else "KOLOM BEDA"
        status = "OK" if not (only_a or only_b or changed or hdr_note) else ("DIFF (volatil)" if vol else "DIFF")
        if skipped:
            status += " [%d baris tabel sistem diabaikan]" % (skipped // 2)
        summary.append((ds, len(ra), len(rb), len(only_a), len(only_b), changed, status + (" " + hdr_note if hdr_note else ""), vol))
        if status.startswith("DIFF") and not vol:
            total_bad += 1
        if only_a or only_b or changed:
            details.append((ds, vol, only_a, only_b, rowsdiff))
            with open(os.path.join(args.out, "diff_%s.csv" % ds), "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, lineterminator="\n")
                w.writerow(["jenis", "kunci", "kolom", la, lb])
                for k in only_a:
                    w.writerow(["hanya_di_" + la, k, "", "|".join(ia[k]), ""])
                for k in only_b:
                    w.writerow(["hanya_di_" + lb, k, "", "", "|".join(ib[k])])
                for k, c, x, y in rowsdiff:
                    w.writerow(["beda_nilai", k, c, x, y])
    p("%-26s %8s %8s %7s %7s %8s  %s" % ("dataset", "baris " + la[:3], "baris " + lb[:3], "hny-" + la[:3], "hny-" + lb[:3], "berubah", "status"))
    p("-" * 100)
    for ds, na, nb, oa, ob, ch, st, vol in summary:
        p("%-26s %8s %8s %7s %7s %8s  %s%s" % (ds, na, nb, oa, ob, ch, st, "  [info/volatil: tidak dihitung]" if vol else ""))
    p("")
    for ds, vol, only_a, only_b, rowsdiff in details:
        p("== %s%s" % (ds, "  (info/volatil, tidak dihitung)" if vol else ""))
        for k in only_a[: args.max_detail]:
            p("   hanya di %s: %s" % (la, k))
        if len(only_a) > args.max_detail:
            p("   ... +%d lagi" % (len(only_a) - args.max_detail))
        for k in only_b[: args.max_detail]:
            p("   hanya di %s: %s" % (lb, k))
        if len(only_b) > args.max_detail:
            p("   ... +%d lagi" % (len(only_b) - args.max_detail))
        for k, c, x, y in rowsdiff[: args.max_detail]:
            p("   %s [%s]: %s=%r  %s=%r" % (k, c, la, x, lb, y))
        if len(rowsdiff) > args.max_detail:
            p("   ... +%d selisih nilai lagi (lihat diff_%s.csv)" % (len(rowsdiff) - args.max_detail, ds))
        p("")
    if "kpi" in da and "kpi" in db:
        ka = {r[0]: r[1] for r in da["kpi"][1]}
        kb = {r[0]: r[1] for r in db["kpi"][1]}
        with open(os.path.join(args.out, "kpi_side_by_side.txt"), "w", encoding="utf-8") as f:
            f.write("%-62s %22s %22s  %s\n" % ("angka kontrol", la, lb, ""))
            for k in sorted(set(ka) | set(kb)):
                a, b = ka.get(k, "-"), kb.get(k, "-")
                f.write("%-62s %22s %22s  %s\n" % (k, a, b, "" if same(a, b, args.tol) else "<== BEDA"))
    verdict = "LULUS: kedua lingkungan identik (di luar dataset volatil)." if total_bad == 0 else "GAGAL: %d dataset berbeda (lihat atas dan diff_*.csv)." % total_bad
    p(verdict)
    with open(os.path.join(args.out, "report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    sys.exit(0 if total_bad == 0 else 1)


if __name__ == "__main__":
    main()
