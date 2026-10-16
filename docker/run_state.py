"""Owned run directories, atomic status, and bounded process-group shutdown."""
from __future__ import annotations

import argparse
import ctypes
import fcntl
import json
import importlib.util
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import uuid
from types import SimpleNamespace


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


def px4_initializer(args):
    """Validate selected plans before claiming a run root or starting firmware."""
    helpers = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("px4_plan_upload", helpers / "upload-plan-artifacts.py")
    uploader = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = uploader
    spec.loader.exec_module(uploader)
    instance = int(os.environ.get("INSTANCE") or "0")
    if not 0 <= instance <= 254:
        raise ValueError("INSTANCE must be between 0 and 254")
    sysid = (args.target_system if args.target_system is not None else
             int(os.environ.get("PX4_PARAM_MAV_SYS_ID") or os.environ.get("SYSID") or instance + 1))
    if not 1 <= sysid <= 255:
        raise ValueError("target system must be between 1 and 255")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        raise ValueError("initialization timeout must be finite and positive")
    config_dir = Path(os.environ.get("SITL_CONFIG_DIR") or "/configs").resolve()
    plans = uploader.selected_plans(SimpleNamespace(
        config_dir=config_dir, mission=os.environ.get("MISSION_FILE"),
        fence=os.environ.get("FENCE_FILE"), rally=os.environ.get("RALLY_FILE")))
    master = args.master or f"udpin:127.0.0.1:{31000 + instance}"
    command = [sys.executable, str(helpers / "upload-plan-artifacts.py"),
               "--master", master, "--target-system", str(sysid), "--target-component", "1",
               "--autopilot", "px4", "--timeout", str(args.timeout), "--wait-ready",
               "--config-dir", str(config_dir)]
    for label, path, _items in plans:
        command.extend(["--" + label, str(path.resolve())])
    return command, sysid


def main():
    """Supervise PX4 and advertise readiness only after MAVLink initialization."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--state", choices=("fresh", "resume"), default="fresh")
    parser.add_argument("--stop-timeout", type=float, default=10)
    parser.add_argument("--timeout", type=float, default=os.environ.get("PLAN_UPLOAD_TIMEOUT") or "60")
    parser.add_argument("--master", default=os.environ.get("PLAN_UPLOAD_MASTER"))
    parser.add_argument("--target-system", type=int)
    parser.add_argument("--healthcheck", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.healthcheck:
        return 0 if healthcheck(args.root) else 1
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or not 0 < args.stop_timeout <= 300:
        parser.error("command and stop timeout in (0, 300] required")
    requested = 0
    result = 1

    def stop(signum, _frame):
        nonlocal requested
        requested = signum

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        initialize, sysid = px4_initializer(args)
        relay_enabled = os.environ.get("PX4_GCS_RELAY") or "0"
        if relay_enabled not in ("0", "1"):
            raise ValueError("PX4_GCS_RELAY must be 0 or 1")
        enable_subreaper()
        with RunDirectory(Path(args.root).resolve(), args.state) as directory:
            processes = []
            try:
                directory.status("starting", sysid=sysid)
                relay = None
                relay_ready = directory.root / "tmp/gcs-relay.json"
                if relay_enabled == "1":
                    instance = int(os.environ.get("INSTANCE") or "0")
                    relay = subprocess.Popen([
                        sys.executable, str(Path(__file__).with_name("px4-gcs-relay.py")),
                        "--listen-port", str(18670 + instance), "--native-port", str(18570 + instance),
                        "--ready-file", str(relay_ready)], start_new_session=True)
                    processes.append(relay)
                child = subprocess.Popen(command, cwd=directory.work, start_new_session=True)
                processes.append(child)
                initializer = subprocess.Popen(initialize, start_new_session=True)
                processes.append(initializer)
                deadline = time.monotonic() + args.timeout
                ready = False
                while not requested:
                    if child.poll() is not None:
                        result = child.returncode or 1
                        raise RuntimeError(f"PX4 exited with status {child.returncode}")
                    if relay is not None and relay.poll() is not None:
                        raise RuntimeError(f"PX4 GCS relay exited with status {relay.returncode}")
                    initialized = initializer.poll()
                    if initialized is not None and initialized != 0:
                        raise RuntimeError(f"PX4 initialization failed with status {initialized}")
                    if not ready and initialized == 0 and (relay is None or relay_ready.is_file()):
                        ready = True
                        print(f"run-px4: ready; SYSID={sysid}; run directory={directory.root}", flush=True)
                    if not ready and time.monotonic() > deadline:
                        raise RuntimeError("PX4 initialization timed out")
                    directory.status("ready" if ready else "initializing", sysid=sysid)
                    time.sleep(0.2)
                directory.status("stopping")
                return 128 + requested
            except Exception as exc:
                directory.status("failed", error=str(exc), code=result)
                raise
            finally:
                stop_groups(processes, args.stop_timeout)
                if requested:
                    directory.status("stopped")
    except (ValueError, OSError, RuntimeError, ImportError) as exc:
        print(f"run-px4: {exc}", file=sys.stderr)
        return result if result >= 0 else 128 - result
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    sys.exit(main())
