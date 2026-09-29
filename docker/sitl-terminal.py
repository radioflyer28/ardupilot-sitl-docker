#!/usr/bin/env python3
"""Headless terminal adapter for sim_vehicle's SITL_RITW_TERMINAL hook.

Keep the actual vehicle attached to container stdout and publish its exit status
instead of relying on sim_vehicle's indefinite --no-mavproxy wait loop.
"""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from run_state import atomic_json


def main():
    record = Path(os.environ["SITL_CHILD_DIR"]) / f"{os.getpid()}.json"
    child = None
    stopped = False

    def stop(signum, _frame):
        nonlocal stopped
        stopped = True
        if child is not None and child.poll() is None:
            child.send_signal(signum)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        # Upstream writes a shell-quoted script using bash printf %q. Execute with
        # bash, even when upstream's generated shebang says /bin/sh.
        child = subprocess.Popen(["bash", sys.argv[1]])
        while child.poll() is None:
            atomic_json(record, {"state": "running", "pid": child.pid, "updated": time.time()})
            time.sleep(0.2)
        atomic_json(record, {"state": "stopped" if stopped else "exited", "code": child.returncode, "updated": time.time()})
        return child.returncode if child.returncode >= 0 else 128 - child.returncode
    except Exception as exc:
        atomic_json(record, {"state": "failed", "error": str(exc), "updated": time.time()})
        raise


if __name__ == "__main__":
    sys.exit(main())
