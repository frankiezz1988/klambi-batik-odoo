#!/usr/bin/env python3
"""Unduh snapshot dari instance Odoo yang berjalan (Railway/VPS/sandbox) lewat HTTP, tanpa perlu SSH.

    python3 scripts/verify/fetch_snapshot.py https://klambi-bali.odoo.kolondam.dev railway admin 'PASSWORD' railway_snapshot.zip [--asof 2026-10-17]

Argumen: URL  nama-database  login  password  berkas-keluaran.  Login harus Administrator (grup Settings).
Password bisa juga lewat env ODOO_PASSWORD (lebih aman dari riwayat shell): ganti argumen password dengan '-'.
Hanya pustaka standar Python 3.8+.
"""
import http.cookiejar
import json
import os
import sys
import urllib.parse
import urllib.request


def main():
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    asof = ""
    if "--asof" in sys.argv:
        asof = sys.argv[sys.argv.index("--asof") + 1]
        a = [x for x in a if x != asof]
    if len(a) != 5:
        sys.exit(__doc__)
    url, db, login, pw, outfile = a
    url = url.rstrip("/")
    if pw == "-":
        pw = os.environ.get("ODOO_PASSWORD", "")
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    req = urllib.request.Request(url + "/web/session/authenticate", method="POST", headers={"Content-Type": "application/json"},
                                 data=json.dumps({"jsonrpc": "2.0", "method": "call", "params": {"db": db, "login": login, "password": pw}}).encode())
    res = json.load(op.open(req, timeout=120))
    if res.get("error") or not (res.get("result") or {}).get("uid"):
        sys.exit("Login gagal: %s" % (res.get("error", {}).get("data", {}).get("message") or "kredensial/db salah"))
    q = urllib.parse.urlencode({"label": db, "asof": asof} if asof else {"label": db})
    with op.open(url + "/batik/verify/snapshot.zip?" + q, timeout=900) as r, open(outfile, "wb") as f:
        data = r.read()
        f.write(data)
    print("OK: %s (%d KB)" % (outfile, len(data) // 1024))


if __name__ == "__main__":
    main()
