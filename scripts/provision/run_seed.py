import sys

sys.path.insert(0, "/mnt/scripts/provision")
import seed  # noqa: E402

seed.run(env)  # noqa: F821
env.cr.commit()  # noqa: F821
