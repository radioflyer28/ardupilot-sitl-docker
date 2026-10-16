#!/usr/bin/env python3
"""One ArduCopter JSON peer driving the pinned JSBSim F450 physical model."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
import shutil
import signal
import socket
import struct
import time

from run_state import RunDirectory, atomic_json

VERSION = "1.3.3"
MOTORS = ("FR", "AL", "FL", "AR")  # ArduCopter quad-X outputs 1..4
FT = 0.3048
EXCHANGE_HZ = 800
PHYSICS_HZ = 1600


def decode_packet(data):
    if len(data) < 8:
        raise ValueError("truncated actuator packet")
    magic, rate, frame = struct.unpack_from("<HHI", data)
    channels = {18458: 16, 29569: 32}.get(magic)
    if channels is None or len(data) != 8 + 2 * channels:
        raise ValueError("invalid actuator magic or packet size")
    # ArduPilot's advertised rate converges gradually during boot. The JSON
    # contract permits a backend-selected rate; our fixed 800 Hz time is authoritative.
    if not 1 <= rate <= 4000:
        raise ValueError(f"invalid advertised actuator rate: {rate}")
    pwm = struct.unpack_from(f"<{channels}H", data, 8)
    if any(p > 2200 or 0 < p < 800 for p in pwm[:4]):
        raise ValueError("motor PWM outside supported range")
    return frame, pwm


def motor_inputs(pwm):
    return [max(0.0, min(1.0, (p - 1000) / 1000)) for p in pwm[:4]]


class Exchange:
    """Exactly one peer and sequential frames; retries never advance physics."""
    def __init__(self):
        self.peer = None
        self.frame = None
        self.response = None

    def receive(self, data, peer, step):
        frame, pwm = decode_packet(data)
        if self.peer is not None and peer != self.peer:
            raise ValueError("another autopilot attempted to use this physics instance")
        if self.frame is not None:
            delta = (frame - self.frame) & 0xffffffff
            if delta == 0:
                return self.response, False
            if delta != 1:
                raise ValueError("actuator frame discontinuity; restart the whole scenario")
        result = step(pwm)
        response = ("\n" + json.dumps(result, allow_nan=False, separators=(",", ":")) + "\n").encode()
        self.peer, self.frame, self.response = peer, frame, response
        return response, True


def validate_selection(source, name):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
        raise ValueError("model name must be a simple aircraft directory name")
    if source is None:
        if name != "F450":
            raise ValueError("non-default models require --model-dir / JSBSIM_MODEL_DIR")
        return
    entry = Path(source) / "aircraft" / name / f"{name}.xml"
    if not entry.is_file() or not (Path(source) / "engine").is_dir():
        raise ValueError(f"catalog requires {entry} and an engine/ directory")
    ET.parse(entry)


def stage_catalog(destination, source, name):
    validate_selection(source, name)
    shutil.copytree(Path(source) / "aircraft" / name, destination / "aircraft" / name)
    for folder in ("engine", "systems"):
        if (Path(source) / folder).is_dir():
            shutil.copytree(Path(source) / folder, destination / folder)
    # This is a compatibility check, not proof of correct rotor geometry or tuning.
    inputs = {node.text.strip() for path in destination.rglob("*.xml")
              for node in ET.parse(path).iter("input") if node.text}
    if not {f"adapter/motor-{i}" for i in range(4)} <= inputs:
        raise ValueError("custom quad-X must consume adapter/motor-0 through adapter/motor-3; export F450 as a starting point")
    return model_hashes(destination)


def model_hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def export_catalog(destination):
    import jsbsim
    from importlib.metadata import distribution
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("export destination must not already exist")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as tmp:
        staged = Path(tmp) / "catalog"
        prepare_model(staged, Path(jsbsim.get_default_root_dir()))
        package = distribution("jsbsim")
        license_path = next(p for p in package.files if str(p).endswith("licenses/COPYING"))
        shutil.copyfile(package.locate_file(license_path), staged / "COPYING")
        (staged / "SOURCE.txt").write_text(
            f"JSBSim {jsbsim.__version__} assets: https://github.com/JSBSim-Team/jsbsim/tree/v{jsbsim.__version__}\n"
            "F450.xml is the project-owned direct-motor composition; retain asset license notices.\n")
        staged.rename(destination)


def prepare_model(destination, source):
    """Copy pinned assets into an owned temporary tree; never patch installed data."""
    model = destination / "aircraft/F450"
    shutil.copytree(source / "aircraft/F450", model)
    shutil.copytree(source / "engine", destination / "engine")
    # Project-owned composition: retain physics, omit upstream pilot controller and
    # sensor/noise systems. Version 2.0 is the format understood by JSBSim 1.3.3.
    channels = "".join(
        f'<channel name="Motor {name}"><pure_gain name="motor-{name}">'
        f'<input>adapter/motor-{index}</input><gain>1</gain>'
        '<clipto><min>0</min><max>1</max></clipto>'
        f'<output>fcs/throttle-pos-norm[{index}]</output></pure_gain></channel>'
        for index, name in enumerate(MOTORS))
    model.joinpath("F450.xml").write_text(
        '<?xml version="1.0"?>\n<fdm_config name="F450 direct motors" version="2.0" release="ALPHA">'
        '<fileheader/><metrics file="Metrics.xml"/><mass_balance file="Mass.xml"/>'
        '<ground_reactions file="Gear.xml"/><propulsion file="Propulsion.xml"/>'
        f'<flight_control name="Direct motors">{channels}</flight_control>'
        '<aerodynamics file="Aero.xml"/></fdm_config>\n')
    return model_hashes(destination)


class QuadX:
    def __init__(self, temporary_root, location, name="F450", source=None):
        import jsbsim  # optional on hosts; required only for physics execution
        if jsbsim.__version__ != VERSION:
            raise ValueError(f"requires JSBSim {VERSION}, found {jsbsim.__version__}")
        self.location = location
        validate_selection(source, name)
        self.hashes = (prepare_model(temporary_root, Path(jsbsim.get_default_root_dir())) if source is None
                       else stage_catalog(temporary_root, source, name))
        self.fdm = f = jsbsim.FGFDMExec(str(temporary_root))
        f.set_debug_level(0)
        f.disable_output()
        if not f.load_model(name):
            raise ValueError(f"could not load {name}")
        if f.get_propulsion().get_num_engines() != 4:
            raise ValueError("the quad-X adapter requires exactly four propulsion engines")
        for index in range(4):
            f[f"adapter/motor-{index}"] = 0.0
        f.set_dt(1 / PHYSICS_HZ)  # two substeps; gyro rate exceeds 1.8x the 400 Hz control loop
        lat, lon, alt, heading = location
        for key, value in {"ic/lat-geod-deg": lat, "ic/long-gc-deg": lon,
                           "ic/terrain-elevation-ft": alt / FT,
                           "ic/h-sl-ft": alt / FT + .5,
                           "ic/psi-true-deg": heading}.items():
            f[key] = value
        if not f.run_ic():
            raise ValueError(f"could not initialize {name}")
        # Settle the landing gear before starting the coupled simulation clock.
        for _ in range(2 * PHYSICS_HZ):
            if not f.run():
                raise ValueError(f"{name} ground settling failed")
        self.elapsed = 0.0
        self.origin_n = f["position/from-start-neu-n-ft"]
        self.origin_e = f["position/from-start-neu-e-ft"]

    def step(self, pwm):
        f = self.fdm
        for index, value in enumerate(motor_inputs(pwm)):
            f[f"adapter/motor-{index}"] = value
        for _ in range(2):
            if not f.run():
                raise RuntimeError("JSBSim stopped stepping")
        self.elapsed += 1 / EXCHANGE_HZ
        return self.state()

    def state(self):
        f = self.fdm
        state = {"timestamp": self.elapsed,
                 "imu": {"gyro": [f[f"velocities/{axis}-rad_sec"] for axis in "pqr"],
                         "accel_body": [f[f"accelerations/a-pilot-{axis}-ft_sec2"] * FT for axis in "xyz"]},
                 "position": [(f["position/from-start-neu-n-ft"] - self.origin_n) * FT,
                              (f["position/from-start-neu-e-ft"] - self.origin_e) * FT,
                              self.location[2] - f["position/h-sl-ft"] * FT],
                 "velocity": [f[f"velocities/v-{axis}-fps"] * FT for axis in ("north", "east", "down")],
                 "attitude": [f[f"attitude/{axis}-rad"] for axis in ("phi", "theta", "psi")]}
        # A numeric blowup must fail closed, not inject NaN into the estimator.
        json.dumps(state, allow_nan=False)
        return state


def serve(args):
    stopped = False

    def stop(_signum, _frame):
        nonlocal stopped
        stopped = True

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, stop)
    validate_selection(args.model_dir, args.model)
    if args.model_dir:
        source, run = Path(args.model_dir).resolve(), Path(args.run_dir).resolve()
        if source.is_relative_to(run) or run.is_relative_to(source):
            raise ValueError("model catalog and owned run directory must be separate")
    with RunDirectory(args.run_dir, "fresh") as directory:
        try:
            directory.status("preparing", backend="jsbsim", model=args.model)
            model = QuadX(directory.root / "tmp/model", args.location, args.model, args.model_dir)
            atomic_json(directory.work / "model-manifest.json", {
                "jsbsim": VERSION, "model": args.model, "source": str(Path(args.model_dir).resolve()) if args.model_dir else "packaged",
                "interface": "direct-motor-quad-x", "location": args.location,
                "step_hz": PHYSICS_HZ, "actuator_hz": EXCHANGE_HZ, "hashes": model.hashes})
            exchange = Exchange()
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock, (directory.work / "truth.jsonl").open("w") as log:
                sock.bind((args.listen, args.port))
                sock.settimeout(.2)
                directory.status("listening", backend="jsbsim", model=args.model)
                deadline = time.monotonic() + args.start_timeout
                count = 0
                last_status = 0
                while not stopped:
                    if time.monotonic() > deadline:
                        raise TimeoutError("physics actuator link timed out")
                    try:
                        data, peer = sock.recvfrom(65535)
                    except socket.timeout:
                        continue
                    started = time.monotonic()
                    response, advanced = exchange.receive(data, peer, model.step)
                    if advanced:
                        deadline = started + args.link_timeout
                        count += 1
                        # Real-time pacing: retries return the cached state immediately.
                        time.sleep(max(0, 1 / EXCHANGE_HZ - (time.monotonic() - started)))
                    sock.sendto(response, peer)
                    if advanced and count % (EXCHANGE_HZ // 20) == 0:  # 20 Hz ground truth and motors
                        log.write(json.dumps({"frame": exchange.frame, "pwm": decode_packet(data)[1][:4],
                                              "state": model.state()}, allow_nan=False) + "\n")
                        log.flush()
                    if advanced and time.monotonic() - last_status > .2:
                        directory.status("ready", backend="jsbsim", model=args.model, frames=count,
                                         simulation_time=model.elapsed, peer=list(peer), location=args.location)
                        last_status = time.monotonic()
            directory.status("stopped")
        except Exception as exc:
            directory.status("failed", error=str(exc))
            raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-dir")
    p.add_argument("--model", default=os.environ.get("JSBSIM_MODEL") or "F450")
    p.add_argument("--model-dir", type=Path, default=os.environ.get("JSBSIM_MODEL_DIR") or None)
    p.add_argument("--export-models", type=Path, help="export an editable native catalog to a new directory")
    p.add_argument("--listen", default="0.0.0.0")
    p.add_argument("--port", type=int, default=9002)
    p.add_argument("--location", type=float, nargs=4, default=[37.1971467, -80.5780381, 618, 0])
    p.add_argument("--start-timeout", type=float, default=60)
    p.add_argument("--link-timeout", type=float, default=5)
    args = p.parse_args()
    if args.export_models:
        if args.run_dir:
            p.error("--export-models cannot be combined with --run-dir")
        export_catalog(args.export_models)
        return
    if not args.run_dir:
        p.error("--run-dir is required for simulation")
    if not all(math.isfinite(x) for x in args.location + [args.start_timeout, args.link_timeout]):
        p.error("arguments must be finite")
    if not (-90 <= args.location[0] <= 90 and -180 <= args.location[1] <= 180 and
            0 <= args.location[3] <= 360 and 1 <= args.port <= 65535 and
            args.start_timeout > 0 and args.link_timeout > 0):
        p.error("arguments out of range")
    serve(args)


if __name__ == "__main__":
    main()
