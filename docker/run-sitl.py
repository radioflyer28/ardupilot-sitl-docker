#!/usr/bin/env python3
"""Validate, stage, supervise, initialize and monitor one ArduPilot vehicle."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
from types import SimpleNamespace

from run_state import RunDirectory, atomic_json, enable_subreaper, healthcheck, stop_groups
from sitl_config import ConfigError, resolve, sim_arguments

HELPERS = Path(__file__).resolve().parent


def uploader_module():
    spec = importlib.util.spec_from_file_location("sitl_upload", HELPERS / "upload-plan-artifacts.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def plan_args(config):
    paths = config["plans"]
    return SimpleNamespace(config_dir=config["config_dir"], mission=paths["MISSION_FILE"], fence=paths["FENCE_FILE"], rally=paths["RALLY_FILE"])


def stage_scripts(config, work):
    dest = work / "scripts"
    temp = work / ".scripts-staging"
    if temp.is_symlink() or dest.is_symlink():
        raise ConfigError("managed script directories must not be symlinks")
    if temp.exists():
        shutil.rmtree(temp)
    temp.mkdir()
    if config["scripts"]:
        shutil.copytree(config["scripts"], temp, dirs_exist_ok=True)
    if config["lua_script"]:
        shutil.copy2(config["lua_script"], temp / Path(config["lua_script"]).name)
    if dest.exists():
        shutil.rmtree(dest)
    temp.rename(dest)


def child_status(root):
    records = list((root / "children").glob("*.json"))
    for path in records:
        record = json.loads(path.read_text())
        if record["state"] != "running":
            raise RuntimeError(f"vehicle process stopped: {record}")
        if time.time() - record["updated"] > 5:
            raise RuntimeError("vehicle process monitor stopped reporting")
    return bool(records)


def physics_ready(config, started):
    """Require fresh advancing-physics reports, not merely a simulator process."""
    physics = config.get("physics")
    if not physics:
        return True
    try:
        status = json.loads(Path(physics["status_file"]).read_text())
    except FileNotFoundError:
        return False
    updated = status.get("updated", 0)
    if updated < started:
        return False  # previous run's status must not establish readiness
    if status.get("state") in ("failed", "stopped"):
        raise RuntimeError(f"JSBSim stopped: {status.get('error', status['state'])}")
    if not 0 <= time.time() - updated < 3:
        return False
    if status.get("state") != "ready" or status.get("frames", 0) < 2:
        return False
    if status.get("backend") != "jsbsim" or status.get("model") != physics["model"]:
        raise RuntimeError("unexpected physics backend/model")
    if status.get("location") != config["location"]:
        raise RuntimeError("autopilot and JSBSim initial locations differ")
    return status.get("simulation_time", 0) > 0


def local_physics_command(config):
    physics = config.get("physics")
    if not physics or physics["deployment"] != "local":
        return None
    command = [physics["python"], str(HELPERS / "jsbsim_adapter.py"),
               "--run-dir", str(Path(physics["status_file"]).parent),
               "--listen", "127.0.0.1", "--model", physics["model"],
               "--start-timeout", str(config["timeout"]),
               "--location", *map(str, config["location"])]
    if physics["model_dir"]:
        command.extend(["--model-dir", physics["model_dir"]])
    return command


def run(config):
    if config.get("physics"):
        config["model"] = "JSON:" + socket.gethostbyname(config["physics"]["host"])
    enable_subreaper()
    processes = []
    requested_signal = 0

    def stop(signum, _frame):
        nonlocal requested_signal
        requested_signal = signum

    previous = {s: signal.signal(s, stop) for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        with RunDirectory(config["run_dir"], config["state"]) as directory:
            try:
                directory.status("preparing")
                atomic_json(config["health_file"], {"run_dir": str(directory.root)})
                stage_scripts(config, directory.work)
                if config.get("physics"):
                    # The physical model requires this fixed motor/output contract.
                    # Append last so a user parameter layer cannot silently remap it.
                    parameters = directory.root / "tmp/jsbsim.parm"
                    parameters.write_text("FRAME_CLASS 1\nFRAME_TYPE 1\nSIM_RATE_HZ 800\n"
                                          "SERVO1_FUNCTION 33\nSERVO2_FUNCTION 34\n"
                                          "SERVO3_FUNCTION 35\nSERVO4_FUNCTION 36\n"
                                          "MOT_PWM_MIN 1000\nMOT_PWM_MAX 2000\n"
                                          "AHRS_EKF_TYPE 3\nEK3_ENABLE 1\n")
                    config["params"] = [*config["params"], str(parameters)]
                effective = directory.root / "effective-config.json"
                atomic_json(effective, config)
                env = dict(os.environ, SITL_RITW_TERMINAL=str(HELPERS / "sitl-terminal.py"),
                           SITL_CHILD_DIR=str(directory.root / "children"), TMPDIR=str(directory.root / "tmp"), PYTHONUNBUFFERED="1")
                # Session tokens and terminal selection belong to this run.
                env.pop("SIM_VEHICLE_SESSION", None)
                command = [sys.executable, str(HELPERS / "launch-sitl.py"), str(effective), *sim_arguments(config, directory.work)]
                directory.status("starting")
                started = time.time()
                physics_child = None
                physics_command = local_physics_command(config)
                if physics_command:
                    physics_child = subprocess.Popen(physics_command, env=env, start_new_session=True)
                    processes.append(physics_child)
                launcher = subprocess.Popen(command, cwd=config["root"], env=env, start_new_session=True)
                processes.append(launcher)
                upload_command = [sys.executable, str(HELPERS / "upload-plan-artifacts.py"),
                                  "--master", config["master"], "--target-system", str(config["sysid"]),
                                  "--target-component", "1", "--timeout", str(config["timeout"]), "--wait-ready"]
                for name, path in config["plans"].items():
                    if path:
                        upload_command.extend(["--" + name.removesuffix("_FILE").lower(), path])
                initializer = subprocess.Popen(upload_command, env=env, start_new_session=True)
                processes.append(initializer)
                ready = False
                deadline = time.monotonic() + config["timeout"]
                while not requested_signal:
                    if physics_child is not None and physics_child.poll() is not None:
                        raise RuntimeError(f"local JSBSim exited with status {physics_child.returncode}")
                    if launcher.poll() is not None:
                        raise RuntimeError(f"sim_vehicle exited with status {launcher.returncode}")
                    vehicle_running = child_status(directory.root)
                    result = initializer.poll()
                    if result is not None and result != 0:
                        raise RuntimeError(f"vehicle initialization failed with status {result}")
                    physics_ok = physics_ready(config, started)
                    if ready and not physics_ok:
                        raise RuntimeError("JSBSim physics progress stopped")
                    if not ready and result == 0 and vehicle_running and physics_ok:
                        ready = True
                        print(f"run-sitl: ready; SYSID={config['sysid']}; run directory={directory.root}", flush=True)
                    if not ready and time.monotonic() > deadline:
                        raise RuntimeError("startup timed out before vehicle initialization completed")
                    directory.status("ready" if ready else "initializing", sysid=config["sysid"])
                    time.sleep(0.2)
                directory.status("stopping")
                return 128 + requested_signal
            except Exception as exc:
                directory.status("failed", error=str(exc))
                raise
            finally:
                stop_groups(processes, config["stop_timeout"])
                if requested_signal:
                    directory.status("stopped")
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main():
    try:
        config = resolve()
        if config.get("healthcheck"):
            return 0 if healthcheck(config["run_dir"]) else 1
        uploader_module().selected_plans(plan_args(config))
        if config["print_effective_config"]:
            print(json.dumps(config, indent=2))
            return 0
        if config["validate"]:
            print("run-sitl: configuration valid")
            return 0
        return run(config)
    except (ConfigError, RuntimeError, ValueError, OSError) as exc:
        print(f"run-sitl: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
