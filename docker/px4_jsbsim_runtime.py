"""PX4-specific external-physics preflight, startup contract and readiness."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import subprocess
import time

from jsbsim_adapter import validate_selection
from run_state import atomic_json

HELPERS = Path(__file__).resolve().parent


def resolve(args, sysid, env=None):
    env = os.environ if env is None else env
    backend = env.get("DYNAMICS_BACKEND") or "internal"
    if backend == "internal":
        return None
    if backend != "jsbsim":
        raise ValueError("PX4 DYNAMICS_BACKEND must be internal or jsbsim")
    if args.state != "fresh" or int(env.get("INSTANCE") or "0") != 0:
        raise ValueError("PX4 JSBSim requires fresh state and INSTANCE=0")
    if float(env.get("PX4_SIM_SPEED_FACTOR") or env.get("SPEEDUP") or "1") != 1:
        raise ValueError("PX4 JSBSim currently requires SPEEDUP=1")
    if env.get("PX4_SIM_MODEL") != "jsbsim_quadrotor_x":
        raise ValueError("PX4 JSBSim requires MODEL=jsbsim_quadrotor_x")
    if env.get("PX4_SIMULATOR") not in (None, "", "jsbsim"):
        raise ValueError("PX4_SIMULATOR conflicts with JSBSim")
    if env.get("PX4_SYS_AUTOSTART") not in (None, "", "3010"):
        raise ValueError("PX4_SYS_AUTOSTART must select airframe 3010")
    if any(env.get(k) for k in ("PX4_SIM_HOSTNAME", "PX4_SIM_HOST_ADDR", "PX4_JSBSIM_PARAMS")):
        raise ValueError("managed JSBSim owns PX4 simulator host and parameter staging; use JSBSIM_HOST")
    location = [float(env.get("PX4_HOME_"+native) or env.get(alias) or default)
                for native, alias, default in (("LAT", "LAT", "37.1971467"),
                                               ("LON", "LON", "-80.5780381"), ("ALT", "ALT", "618"))]
    location.append(float(env.get("DIR") or "0"))
    if (not all(math.isfinite(v) for v in location) or not -60 < location[0] < 60
            or not -180 <= location[1] <= 180 or not -500 <= location[2] <= 10000
            or not 0 <= location[3] <= 360):
        raise ValueError("PX4 JSBSim home lies outside supported ranges")
    root = Path(args.root).resolve()
    deployment = env.get("JSBSIM_DEPLOYMENT") or "local"
    if deployment not in ("local", "external"):
        raise ValueError("JSBSIM_DEPLOYMENT must be local or external")
    model = env.get("JSBSIM_MODEL") or "F450"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", model):
        raise ValueError("invalid JSBSIM_MODEL")
    source = env.get("JSBSIM_MODEL_DIR") or None
    python = env.get("JSBSIM_PYTHON") or "/opt/jsbsim-venv/bin/python3"
    if deployment == "local":
        if env.get("JSBSIM_HOST") or env.get("JSBSIM_STATUS_FILE"):
            raise ValueError("local physics does not accept host/status overrides")
        if not Path(python).is_file() or not os.access(python, os.X_OK):
            raise ValueError(f"missing physics Python: {python}")
        python = str(Path(python).absolute())  # retain venv symlink identity
        validate_selection(source, model)
        if source:
            source = str(Path(source).resolve())
            if Path(source).is_relative_to(root) or root.is_relative_to(source):
                raise ValueError("read-only models and writable run root must be separate")
        host, status = "127.0.0.1", root/"work/physics/status.json"
    else:
        if source:
            raise ValueError("mount/select the catalog in the external physics container")
        host = env.get("JSBSIM_HOST") or "physics"
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", host):
            raise ValueError("invalid JSBSIM_HOST")
        status = Path(env.get("JSBSIM_STATUS_FILE") or "/physics/status.json").resolve()
        if status.is_relative_to(root) or root.is_relative_to(status.parent):
            raise ValueError("external status must be outside the owned run root")
    return dict(deployment=deployment, model=model, model_dir=source, python=python,
                host=host, status_file=str(status), location=location, sysid=sysid,
                seed=int(env.get("JSBSIM_SEED") or "0"), timeout=args.timeout)


def parameters(rotors, sysid):
    if len(rotors) != 4:
        raise ValueError("physics must report four rotors")
    result = {"MAV_SYS_ID": sysid, "IMU_INTEG_RATE": 400, "CA_AIRFRAME": 0,
              "CA_ROTOR_COUNT": 4, "EKF2_MULTI_IMU": 1, "EKF2_MULTI_MAG": 1}
    for i, rotor in enumerate(rotors):
        position, km = rotor["position"], rotor["km"]
        if (len(position) != 3 or not all(math.isfinite(v) and abs(v) < 100 for v in position)
                or km != (.05 if i < 2 else -.05)):
            raise ValueError("invalid model rotor geometry")
        for axis, value in zip("XYZ", position):
            result[f"CA_ROTOR{i}_P{axis}"] = value
        result[f"CA_ROTOR{i}_KM"] = km
        result[f"CA_ROTOR{i}_AX"] = 0
        result[f"CA_ROTOR{i}_AY"] = 0
        result[f"CA_ROTOR{i}_AZ"] = -1
    for i in range(1, 17):
        result[f"PWM_MAIN_FUNC{i}"] = 100+i if i <= 4 else 0
    return result


class PhysicsSession:
    def __init__(self, config, directory, processes):
        self.config = config
        self.directory = directory
        self.processes = processes
        self.child = None
        self.instance_id = None

    def status(self):
        if self.child is not None and self.child.poll() is not None:
            raise RuntimeError(f"PX4 JSBSim exited with status {self.child.returncode}")
        try:
            status = json.loads(Path(self.config["status_file"]).read_text())
        except FileNotFoundError:
            return None
        if not 0 <= time.time()-status.get("updated", 0) < 3:
            return None
        if status.get("state") in ("failed", "stopped"):
            raise RuntimeError(f"PX4 JSBSim stopped: {status.get('error', status['state'])}")
        for key, expected in (("backend", "jsbsim"), ("protocol", "px4-mavlink"),
                              ("model", self.config["model"]), ("location", self.config["location"]),
                              ("sysid", self.config["sysid"])):
            if status.get(key) != expected:
                raise RuntimeError(f"physics {key} does not match PX4 configuration")
        if self.instance_id is not None and status.get("instance_id") != self.instance_id:
            raise RuntimeError("physics restarted; restart the whole scenario")
        return status

    def prepare(self, stopped):
        config = self.config
        if config["deployment"] == "local":
            command = [config["python"], str(HELPERS/"px4_jsbsim_adapter.py"),
                       "--run-dir", str(Path(config["status_file"]).parent), "--listen", "127.0.0.1",
                       "--model", config["model"], "--sysid", str(config["sysid"]),
                       "--seed", str(config["seed"]), "--start-timeout", str(config["timeout"]),
                       "--location", *map(str, config["location"])]
            if config["model_dir"]:
                command += ["--model-dir", config["model_dir"]]
            self.child = subprocess.Popen(command, start_new_session=True)
            self.processes.append(self.child)
        deadline = time.monotonic()+config["timeout"]
        while True:
            if stopped():
                raise InterruptedError("stopped while preparing physics")
            status = self.status()
            if status and status.get("state") == "listening":
                break
            if status and status.get("state") in ("ready", "initializing"):
                raise RuntimeError("physics already has a PX4 peer; restart the scenario")
            if time.monotonic() > deadline:
                raise TimeoutError("PX4 JSBSim model preparation timed out")
            time.sleep(.05)
        self.instance_id = status["instance_id"]
        contract = parameters(status["rotors"], config["sysid"])
        script = self.directory.root/"tmp/jsbsim-parameters.sh"
        script.write_text("".join(f"param set {key} {value} || return 1\n" for key, value in contract.items()))
        env = dict(os.environ, PX4_JSBSIM_PARAMS=str(script))
        if config["deployment"] == "local":
            env["PX4_SIM_HOST_ADDR"] = config["host"]
        else:
            env["PX4_SIM_HOSTNAME"] = config["host"]
        atomic_json(self.directory.root/"effective-config.json", {
            "family": "px4", "physics": config, "physics_instance": self.instance_id,
            "parameters": contract})
        return env

    def ready(self):
        status = self.status()
        return bool(status and status.get("state") == "ready" and status.get("frames", 0) >= 2
                    and status.get("simulation_time", 0) > 0)
