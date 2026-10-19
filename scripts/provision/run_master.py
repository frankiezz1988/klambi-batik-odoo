import sys

sys.path.insert(0, "/mnt/scripts/provision")
import master  # noqa: E402

master.run(env)  # noqa: F821
env.cr.commit()  # noqa: F821
