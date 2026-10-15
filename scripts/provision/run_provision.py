import sys

sys.path.insert(0, "/mnt/scripts/provision")
import provision  # noqa: E402

provision.run(env)  # noqa: F821
env.cr.commit()  # noqa: F821
