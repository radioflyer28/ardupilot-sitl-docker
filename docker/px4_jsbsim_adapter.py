#!/usr/bin/env python3
"""One PX4 simulator-MAVLink peer driving the shared JSBSim quad-X model."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import random
import select
import signal
import socket
import time
import uuid

from jsbsim_adapter import QuadX, FT, VERSION, PHYSICS_HZ, validate_selection, export_catalog
from run_state import RunDirectory, atomic_json

EXCHANGE_HZ = 400
CLOCK_ORIGIN_US = 1_000_000
# White-noise densities follow the pinned upstream bridge's IMU/mag defaults.
# Pressure noise is a project simulation baseline, not a calibrated sensor model.
NOISE_STD = {"accel": .004 * math.sqrt(EXCHANGE_HZ),
             "gyro": math.radians(70 / 3600) * math.sqrt(EXCHANGE_HZ),
             "mag": .0004 * math.sqrt(EXCHANGE_HZ), "pressure_hpa": .01}


def magnetic_body(attitude, field):
    """NED magnetic vector to FRD body; Euler angles are roll, pitch, yaw."""
    roll, pitch, yaw = attitude
    sr, cr = math.sin(roll), math.cos(roll)
    sp, cp = math.sin(pitch), math.cos(pitch)
    sy, cy = math.sin(yaw), math.cos(yaw)
    n, e, d = field
    return [cp*cy*n + cp*sy*e - sp*d,
            (sr*sp*cy-cr*sy)*n + (sr*sp*sy+cr*cy)*e + sr*cp*d,
            (cr*sp*cy+sr*sy)*n + (cr*sp*sy-sr*cy)*e + cr*cp*d]


def earth_field(location):
    from pymavlink.mavextra import get_mag_field_ef
    result = get_mag_field_ef(*location[:2])
    if result is None:
        raise ValueError("home lies outside the magnetic table; choose a supported latitude")
    declination, inclination, strength = result
    d, i = math.radians(declination), math.radians(inclination)
    return [strength*math.cos(i)*math.cos(d), strength*math.cos(i)*math.sin(d), strength*math.sin(i)]


def rotor_geometry(fdm):
    """JSBSim structural inches to PX4 body metres, relative to actual CG."""
    cg = [fdm[f"inertia/cg-{axis}-in"] for axis in "xyz"]
    result = []
    for index, (sx, sy) in enumerate(((1, 1), (-1, -1), (1, -1), (-1, 1))):
        prefix = f"propulsion/engine[{index}]/"
        x, y, z = [fdm[prefix + axis + "-position"] for axis in "xyz"]
        position = [(cg[0]-x)*.0254, (y-cg[1])*.0254, (cg[2]-z)*.0254]
        sense = fdm[prefix + "propeller-sense"]
        values = [*position, sense, fdm[prefix+"pitch-angle-rad"], fdm[prefix+"yaw-angle-rad"]]
        if (not all(math.isfinite(v) for v in values) or position[0]*sx <= 0 or position[1]*sy <= 0
                or sense != (1 if index < 2 else -1)
                or abs(values[-2]-math.pi/2) > 1e-6 or abs(values[-1]) > 1e-6):
            raise ValueError("PX4 requires vertical quad-X rotors in FR/AL/FL/AR order with +/+/-/- sense")
        result.append({"position": position, "km": .05*sense})
    return result


class ActuatorClock:
    """Validate one SYSID/component and exact lockstep replies; retries never step."""
    def __init__(self, sysid):
        self.sysid = sysid
        self.last = None

    def accept(self, message, sent):
        if message.get_type() != "HIL_ACTUATOR_CONTROLS":
            return None
        if message.get_srcSystem() != self.sysid or message.get_srcComponent() != 1:
            raise ValueError("unexpected simulator actuator identity")
        if not message.flags & 1:
            raise ValueError("PX4 simulator lockstep must be enabled")
        stamp = message.time_usec
        if stamp > sent or (self.last is not None and stamp < self.last):
            raise ValueError("actuator clock discontinuity; restart the scenario")
        if stamp != sent or stamp == self.last:
            return None
        values = list(message.controls[:4])
        if len(values) != 4 or not all(math.isfinite(v) and 0 <= v <= 1 for v in values):
            raise ValueError("PX4 motor commands must be four normalized finite values")
        self.last = stamp
        return values if message.mode & 128 else [0.0]*4


class Wire:
    def __init__(self, sock):
        self.sock = sock

    def write(self, data):
        self.sock.sendall(data)


def send_sensors(out, model, state, stamp, frame, field, rng):
    f = model.fdm
    altitude = f["position/h-sl-ft"]*FT
    lat = f["position/lat-geod-deg"]
    lon = (f["position/long-gc-deg"]+180) % 360 - 180
    pressure = 1013.25*(1-2.25577e-5*altitude)**5.25588
    accel = [v+rng.gauss(0, NOISE_STD["accel"]) for v in state["imu"]["accel_body"]]
    gyro = [v+rng.gauss(0, NOISE_STD["gyro"]) for v in state["imu"]["gyro"]]
    mag = [v+rng.gauss(0, NOISE_STD["mag"]) for v in magnetic_body(state["attitude"], field)]
    pressure += rng.gauss(0, NOISE_STD["pressure_hpa"])
    values = [*accel, *gyro, *mag, pressure, 0, altitude, 15-altitude*.0065]
    if not all(math.isfinite(v) for v in [lat, lon, *values]):
        raise ValueError("non-finite simulated sensor output")
    out.hil_sensor_send(stamp, *values, 0x1fff)
    if frame % (EXCHANGE_HZ // 10) == 0:
        vn, ve, vd = state["velocity"]
        out.hil_gps_send(stamp, 3, round(lat*1e7), round(lon*1e7), round(altitude*1000),
                         30, 50, round(math.hypot(vn, ve)*100), round(vn*100), round(ve*100),
                         round(vd*100), round(math.degrees(math.atan2(ve, vn))%360*100)%36000, 12)
    # Truth goes only to PX4's simulator ground-truth topics, not estimator aiding.
    if frame % (EXCHANGE_HZ // 50) == 0:
        from pymavlink.quaternion import QuaternionBase
        q = QuaternionBase(state["attitude"]).q
        out.hil_state_quaternion_send(stamp, q, *state["imu"]["gyro"], round(lat*1e7),
                                       round(lon*1e7), round(altitude*1000),
                                       *[round(v*100) for v in state["velocity"]], 0, 0,
                                       *[round(v/9.80665*1000) for v in state["imu"]["accel_body"]])


def finish_disconnect(directory, identity, stopped, timeout, reason):
    """Invalidate readiness now; allow Compose's ordered SIGTERM to follow EOF."""
    directory.status("disconnected", **identity, error=reason)
    deadline = time.monotonic()+timeout
    while not stopped() and time.monotonic() < deadline:
        time.sleep(min(.05, max(0, deadline-time.monotonic())))
    if stopped():
        directory.status("stopped", **identity)
        return
    directory.status("failed", error=reason)
    raise ConnectionError(reason)


def serve(args):
    from pymavlink.dialects.v20 import common as mavlink
    stopped = False

    def stop(_signum, _frame):
        nonlocal stopped
        stopped = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stop)
    field = earth_field(args.location)
    instance_id = uuid.uuid4().hex
    rng = random.Random(args.seed)
    with RunDirectory(args.run_dir, "fresh") as directory:
        try:
            identity = dict(backend="jsbsim", protocol="px4-mavlink", model=args.model,
                            location=args.location, instance_id=instance_id, sysid=args.sysid)
            directory.status("preparing", **identity)
            model = QuadX(directory.root/"tmp/model", args.location, args.model, args.model_dir)
            geometry = rotor_geometry(model.fdm)
            identity["rotors"] = geometry
            atomic_json(directory.work/"model-manifest.json", {
                **identity, "jsbsim": VERSION, "hashes": model.hashes, "step_hz": PHYSICS_HZ,
                "actuator_hz": EXCHANGE_HZ, "seed": args.seed, "sensor_noise_std": NOISE_STD})
            deadline = time.monotonic()+args.start_timeout
            with socket.socket() as listener, (directory.work/"truth.jsonl").open("w") as truth:
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                listener.bind((args.listen, args.port))
                listener.listen(1)
                listener.settimeout(.2)
                connection = None
                while not stopped and connection is None:
                    if time.monotonic() > deadline:
                        raise TimeoutError("PX4 simulator connection timed out")
                    directory.status("listening", **identity)
                    try:
                        connection, peer = listener.accept()
                    except socket.timeout:
                        pass
                if connection is not None:
                    with connection as sock:
                        sock.settimeout(.2)
                        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                        out = mavlink.MAVLink(Wire(sock), srcSystem=args.sysid, srcComponent=200)
                        incoming = mavlink.MAVLink(None)
                        clock = ActuatorClock(args.sysid)
                        controls = [0.0]*4
                        state = model.state()
                        count = 0
                        last_status = 0
                        while not stopped:
                            started = time.monotonic()
                            if clock.last is None and started > deadline:
                                raise TimeoutError("PX4 actuator bootstrap timed out")
                            stamp = CLOCK_ORIGIN_US + count*(1_000_000//EXCHANGE_HZ)
                            send_sensors(out, model, state, stamp, count, field, rng)
                            reply_deadline = started+(args.link_timeout if clock.last is not None else 1/EXCHANGE_HZ)
                            received = None
                            while not stopped and time.monotonic() < reply_deadline and received is None:
                                wait = min(.2, max(0, reply_deadline-time.monotonic()))
                                if not select.select([sock], [], [], wait)[0]:
                                    continue
                                data = sock.recv(65536)
                                if not data:
                                    raise ConnectionError("PX4 simulator disconnected")
                                for message in incoming.parse_buffer(data) or []:
                                    accepted = clock.accept(message, stamp)
                                    if accepted is not None:
                                        received = accepted
                            if stopped:
                                break
                            if received is not None:
                                controls = received
                            elif clock.last is not None:
                                raise TimeoutError("PX4 actuator progress timed out")
                            # Shared 800 Hz model interface; four 1600 Hz physics substeps per PX4 exchange.
                            for _ in range(2):
                                state = model.step([1000+1000*v for v in controls])
                            count += 1
                            if count % (EXCHANGE_HZ//20) == 0:
                                truth.write(json.dumps({"frame": count, "controls": controls,
                                                        "state": state}, allow_nan=False)+"\n")
                                truth.flush()
                            if time.monotonic()-last_status > .2:
                                directory.status("ready" if clock.last is not None else "initializing",
                                                 **identity, frames=count, simulation_time=model.elapsed, peer=list(peer))
                                last_status = time.monotonic()
                            time.sleep(max(0, 1/EXCHANGE_HZ-(time.monotonic()-started)))
            directory.status("stopped", **identity)
        except ConnectionError as exc:
            finish_disconnect(directory, identity, lambda: stopped, args.link_timeout, str(exc))
        except Exception as exc:
            directory.status("failed", error=str(exc))
            raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-dir", type=Path)
    p.add_argument("--model", default=os.environ.get("JSBSIM_MODEL") or "F450")
    p.add_argument("--model-dir", type=Path, default=os.environ.get("JSBSIM_MODEL_DIR") or None)
    p.add_argument("--export-models", type=Path)
    p.add_argument("--listen", default="0.0.0.0")
    p.add_argument("--port", type=int, default=4560)
    p.add_argument("--sysid", type=int, default=1)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--location", type=float, nargs=4, default=[37.1971467, -80.5780381, 618, 0])
    p.add_argument("--start-timeout", type=float, default=60)
    p.add_argument("--link-timeout", type=float, default=5)
    args = p.parse_args()
    if args.export_models:
        if args.run_dir:
            p.error("export and simulation are separate operations")
        export_catalog(args.export_models)
        return
    if not args.run_dir:
        p.error("--run-dir is required")
    if (not all(math.isfinite(v) for v in [*args.location, args.start_timeout, args.link_timeout])
            or not -60 < args.location[0] < 60 or not -180 <= args.location[1] <= 180
            or not -500 <= args.location[2] <= 10000 or not 0 <= args.location[3] <= 360
            or not 1 <= args.port <= 65535 or not 1 <= args.sysid <= 255
            or args.start_timeout <= 0 or args.link_timeout <= 0):
        p.error("invalid home, identity, port or timeout")
    validate_selection(args.model_dir, args.model)
    if args.model_dir:
        source, root = args.model_dir.resolve(), args.run_dir.resolve()
        if source.is_relative_to(root) or root.is_relative_to(source):
            p.error("catalog and owned run directory must be separate")
    serve(args)


if __name__ == "__main__":
    main()
