# Jalankan lewat odoo shell:   SNAP_OUT=/tmp/snap SNAP_LABEL=sandbox odoo shell -d <db> --no-http < scripts/verify/run_snapshot.py
# Menulis folder CSV + manifest.json (read-only terhadap database).
import os

from odoo.addons.batik_id_verify import snapshot

out = os.environ.get("SNAP_OUT", "/tmp/snapshot")
m = snapshot.write_dir(env, out, label=os.environ.get("SNAP_LABEL", ""), asof=os.environ.get("SNAP_ASOF") or None)  # noqa: F821
print("SNAPSHOT -> %s : %d dataset, %d error" % (out, len(m["datasets"]), len(m["errors"])))
for k, v in sorted(m["errors"].items()):
    print("  ! %s: %s" % (k, v))
