"""Owned run directories, atomic status, and bounded process-group shutdown."""
from __future__ import annotations

import argparse
import ctypes
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import uuid


def atomic_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name + f".{os.getpid()}.tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n")
    temp.replace(path)


def healthcheck(root):
    try:
        status = json.loads((Path(root) / "status.json").read_text())
        return status["state"] == "ready" and 0 <= time.time() - status["updated"] < 5
    except (OSError, ValueError, KeyError):
        return False


class RunDirectory:
    """Never clear arbitrary user directories; archive only our marked workspace."""
    def __init__(self, root, state):
        self.root = Path(root)
        self.state = state
        self.work = self.root / "work"
        self.lock = None

    def __enter__(self):
        self.root.mkdir(parents=True, exist_ok=True)
        lock_path = self.root / ".sitl.lock"
        if lock_path.is_symlink():
            raise ValueError("run lock must not be a symlink")
        self.lock = lock_path.open("a+")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            marker = self.root / ".sitl-managed"
            if not marker.exists():
                if any(p.name != ".sitl.lock" for p in self.root.iterdir()):
                    raise ValueError(f"refusing unowned nonempty run directory: {self.root}; choose an empty directory")
                marker.write_text("1\n")
            if marker.is_symlink() or marker.read_text() != "1\n":
                raise ValueError("invalid run directory marker")
            for path in (self.work, self.root / "history", self.root / "children", self.root / "tmp"):
                if path.is_symlink():
                    raise ValueError(f"managed path must not be a symlink: {path}")
            if self.state == "fresh" and self.work.exists():
                history = self.root / "history"
                history.mkdir(exist_ok=True)
                self.work.rename(history / uuid.uuid4().hex)
            self.work.mkdir(exist_ok=True)
            for name in ("children", "tmp"):
                path = self.root / name
                if path.exists():
                    shutil.rmtree(path)
                path.mkdir()
            return self
        except Exception:
            self.lock.close()
            raise

    def status(self, state, **details):
        atomic_json(self.root / "status.json", {"state": state, "pid": os.getpid(), "updated": time.time(), **details})

    def __exit__(self, *args):
        self.lock.close()


def enable_subreaper():
    # sim_vehicle intentionally detaches terminal children. Adopt and reap them
    # on Linux even when this wrapper is not container PID 1.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), "could not become child subreaper")


def reap_children():
    try:
        while os.waitpid(-1, os.WNOHANG)[0]:
            pass
    except ChildProcessError:
        pass


def stop_groups(processes, timeout):
    # Include detached grandchildren: upstream terminal launchers return early.
    groups = [p.pid for p in processes]
    for group in groups:
        try:
            os.killpg(group, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for process in processes:
            process.poll()
        reap_children()
        alive = False
        for group in groups:
            try:
                os.killpg(group, 0)
                alive = True
            except ProcessLookupError:
                pass
        if not alive:
            break
        time.sleep(0.05)
    for group in groups:
        try:
            os.killpg(group, signal.SIGKILL)
        except ProcessLookupError:
            pass
    for process in processes:
        process.wait()
    # Reap adopted grandchildren after SIGKILL as well.
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        reap_children()
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            break
        if pid == 0:
            time.sleep(0.01)


def main():
    """PX4 state/process wrapper; running is deliberately not MAVLink-ready."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--state", choices=("fresh", "resume"), default="fresh")
    parser.add_argument("--stop-timeout", type=float, default=10)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or not 0 < args.stop_timeout <= 300:
        parser.error("command and stop timeout in (0, 300] required")
    requested = 0

    def stop(signum, _frame):
        nonlocal requested
        requested = signum

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    enable_subreaper()
    try:
        with RunDirectory(Path(args.root).resolve(), args.state) as directory:
            processes = []
            try:
                directory.status("starting")
                child = subprocess.Popen(command, cwd=directory.work, start_new_session=True)
                processes.append(child)
                while child.poll() is None and not requested:
                    directory.status("running")
                    time.sleep(0.2)
                result = 128 + requested if requested else child.returncode
                directory.status("stopping")
            finally:
                stop_groups(processes, args.stop_timeout)
            directory.status("stopped" if result in (0, 130, 143) else "failed", code=result)
            return result if result >= 0 else 128 - result
    except (ValueError, OSError) as exc:
        print(f"run-state: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
