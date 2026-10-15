"""Helper umum untuk script yang dijalankan lewat `odoo shell` (variabel global `env`)."""
import contextlib
import json
import traceback

REGISTRY_PARAM = "batik_demo.registry"


class Steps:
    """Jalankan langkah satu per satu, fail-soft: 1 langkah gagal tidak menggagalkan sisanya."""

    def __init__(self, env):
        self.env = env
        self.results = []

    @contextlib.contextmanager
    def step(self, name):
        try:
            with self.env.cr.savepoint():
                yield
            self.env.cr.commit()
            self.results.append((name, "OK", ""))
            print(f"[OK]   {name}")
        except Exception as exc:  # noqa: BLE001 - sengaja menangkap semua agar fail-soft
            self.results.append((name, "FAIL", str(exc)[:300]))
            print(f"[FAIL] {name}: {exc}")
            traceback.print_exc()
            self.env.invalidate_all()

    def summary(self):
        print("\n==== RINGKASAN ====")
        for name, status, err in self.results:
            print(f"{status:5} {name}" + (f"  -> {err}" if err else ""))
        failed = [r for r in self.results if r[1] == "FAIL"]
        print(f"\n{len(self.results) - len(failed)}/{len(self.results)} langkah OK")
        return not failed


def load_registry(env):
    raw = env["ir.config_parameter"].sudo().get_param(REGISTRY_PARAM, "{}")
    return json.loads(raw)


def save_registry(env, data):
    reg = load_registry(env)
    reg.update(data)
    env["ir.config_parameter"].sudo().set_param(REGISTRY_PARAM, json.dumps(reg))
    return reg


def user_group_field(env):
    return "group_ids" if "group_ids" in env["res.users"]._fields else "groups_id"


def get_or_create(env, model, domain, vals):
    rec = env[model].search(domain, limit=1)
    return rec or env[model].create(vals)
