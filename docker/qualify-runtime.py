#!/usr/bin/env python3
"""Opt-in real-firmware qualification using already-built images; never builds.

Default mode mounts current helpers over an existing firmware environment.
--installed instead exercises the image's installed ENTRYPOINT/helpers and
available Docker HEALTHCHECK. Both modes mount read-only test inputs.
Results and container logs are retained beneath the selected artifact directory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

REPO = Path(__file__).resolve().parent.parent

# Runs inside the image's Python environment; require MAVLink 2 before import.
CLIENT = r'''
import json, os, struct, sys, time
from pathlib import Path
os.environ["MAVLINK20"] = "1"
from pymavlink import mavutil
mode, instance, sysid = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
port = 5760 + instance * 10 if mode == "direct" else 21000 + instance
m = mavutil.mavlink_connection(f"tcp:127.0.0.1:{port}", source_system=254, source_component=191)
# Behave as an active GCS: tcpin routers may not service a silent subscriber
# until it sends traffic. Keep this handshake bounded rather than retrying tests.
h = None
deadline = time.monotonic() + 10
while time.monotonic() < deadline:
    m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
    candidate = m.wait_heartbeat(timeout=1)
    if candidate and candidate.get_srcSystem() == sysid and candidate.get_srcComponent() == 1:
        h = candidate
        break
assert h, "expected autopilot heartbeat was not received"
m.target_system, m.target_component = sysid, 1
operation = sys.argv[4]
result = {"sysid": h.get_srcSystem()}
def receive(kind, condition=lambda msg: True):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        msg = m.recv_match(type=kind, blocking=True, timeout=0.5)
        if msg and msg.get_srcSystem() == sysid and condition(msg):
            return msg
    raise AssertionError(f"missing {kind}")
if operation == "plans":
    examples = Path("/qualification/configs/examples")
    # Independent fixture expectations: do not reuse the uploader's parser/encoder.
    mission = []
    for line in (examples / "mission/missions/simple-copter.waypoints").read_text().splitlines()[1:]:
        fields = line.split()
        if fields:
            mission.append((int(fields[2]), int(fields[3]), list(map(float, fields[4:8])),
                            float(fields[8]), float(fields[9]), float(fields[10])))
    points = json.loads((examples / "plan-artifacts/fences/simple-polygon.json").read_text())["fences"][0]["points"]
    fence = [(5, mavutil.mavlink.MAV_CMD_NAV_FENCE_POLYGON_VERTEX_INCLUSION,
              [float(len(points)), 0., 0., 0.], p["lat"], p["lon"], 0.) for p in points]
    rally = [(6, mavutil.mavlink.MAV_CMD_NAV_RALLY_POINT, [0., 0., 0., 0.],
              p["lat"], p["lon"], p["alt"]) for p in json.loads((examples / "plan-artifacts/rally/recovery-points.json").read_text())["points"]]
    expected = {0: mission, 1: fence, 2: rally}
    result["counts"] = {}
    canonical_frame = lambda value: {0: 5, 3: 6, 10: 11}.get(value, value)
    def float32(value):
        return struct.unpack("<f", struct.pack("<f", value))[0]
    def coordinate_matches(actual, coordinate):
        integer_value = round(coordinate * 1e7)
        # Legacy MISSION_REQUEST requires float coordinates. ArduPilot scales
        # those in float32 before storing int32. Permit exactly that conversion,
        # or the native integer path, plus one integer unit of quantization.
        legacy_value = int(float32(float32(coordinate) * 1e7))
        return min(abs(actual - integer_value), abs(actual - legacy_value)) <= 1
    for plan_type, items in expected.items():
        m.mav.mission_request_list_send(sysid, 1, plan_type)
        response = receive("MISSION_COUNT", lambda msg: msg.mission_type == plan_type)
        assert response.count == len(items), (plan_type, response.count, len(items))
        result["counts"][plan_type] = response.count
        for seq, (frame, command, params, lat, lon, alt) in enumerate(items):
            m.mav.mission_request_int_send(sysid, 1, seq, plan_type)
            item = receive("MISSION_ITEM_INT", lambda msg: msg.mission_type == plan_type and msg.seq == seq)
            assert item.command == command, (plan_type, seq, item)
            assert canonical_frame(item.frame) == canonical_frame(frame), (plan_type, seq, item.frame, frame)
            assert all(abs(a - b) < 1e-5 for a, b in zip((item.param1, item.param2, item.param3, item.param4), params)), (plan_type, seq, item)
            if plan_type == 0 and seq == 0:
                # Item 0 is synthesized from current home, not stored from upload.
                # Home can still be unset: managed readiness does not promise GPS.
                result["home_readback"] = {"lat_int": item.x, "lon_int": item.y, "alt": item.z}
            else:
                assert coordinate_matches(item.x, lat) and coordinate_matches(item.y, lon), (plan_type, seq, item.to_dict(), lat, lon)
                assert abs(item.z - alt) < .01, (plan_type, seq, item.z, alt)
        result["payload_verified"] = True
        m.mav.mission_ack_send(sysid, 1, mavutil.mavlink.MAV_MISSION_ACCEPTED, plan_type)
    m.mav.command_long_send(sysid,1,mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE,0,148,0,0,0,0,0,0)
    version = receive("AUTOPILOT_VERSION")
    result["flight_sw_version"] = hex(version.flight_sw_version)
    result["flight_custom_version"] = bytes(version.flight_custom_version).hex()
elif operation == "set":
    m.mav.param_set_send(sysid,1,b"SIM_WIND_SPD",2.5,mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
    p=receive("PARAM_VALUE", lambda msg: msg.param_id == "SIM_WIND_SPD")
    assert p.param_value == 2.5
    result["SIM_WIND_SPD"] = p.param_value
elif operation in ("resume", "fresh"):
    m.mav.param_request_read_send(sysid,1,b"SIM_WIND_SPD",-1)
    p=receive("PARAM_VALUE", lambda msg: msg.param_id == "SIM_WIND_SPD")
    assert p.param_value == (2.5 if operation == "resume" else 0), p
    result["SIM_WIND_SPD"] = p.param_value
m.close()
print(json.dumps(result))
'''


def command(*args, check=True, **kwargs):
    result = subprocess.run(args, text=True, capture_output=True, timeout=30, **kwargs)
    if check and result.returncode:
        raise RuntimeError(f"{args}: {result.stderr or result.stdout}")
    return result


def wait_for(predicate, label, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.2)
    raise RuntimeError(f"timed out: {label}")


def json_file(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return {}


class Container:
    def __init__(self, image, output, env, script=None, uid=None):
        self.name = "sitl-qualify-" + uuid.uuid4().hex[:10]
        self.output = output
        self.closed = False
        self.output.mkdir(parents=True, exist_ok=True)
        self.log = (output / (self.name + ".log")).open("w")
        args = ["docker", "run", "--name", self.name, "--init", "--stop-timeout", "20",
                "-v", f"{REPO}:/qualification:ro", "-v", f"{output}:/results"]
        if script:
            args.extend(["--entrypoint", "bash"])
        if uid:
            args.extend(["--user", uid])
        for key, value in env.items():
            args.extend(["-e", f"{key}={value}"])
        args.append(image)
        if script:
            args.append(script)
        self.process = subprocess.Popen(args, stdout=self.log, stderr=subprocess.STDOUT)

    def wait_state(self, state):
        def ready():
            if self.process.poll() is not None:
                raise RuntimeError(f"{self.name}: early exit {self.process.returncode}; see {self.log.name}")
            return json_file(self.output / "run/status.json").get("state") == state
        wait_for(ready, f"{self.name} {state}")
        if state == "ready":
            health = json.loads(command("docker", "inspect", self.name).stdout)[0]["Config"].get("Healthcheck")
            if health:
                wait_for(lambda: json.loads(command("docker", "inspect", self.name).stdout)[0]["State"]["Health"]["Status"] == "healthy",
                         f"{self.name} installed Docker HEALTHCHECK")

    def exec(self, *args, **kwargs):
        return command("docker", "exec", "-i", self.name, *args, **kwargs)

    def client(self, mode, instance, sysid, operation):
        result = self.exec("python3", "-", mode, str(instance), str(sysid), operation, input=CLIENT)
        return json.loads(result.stdout.strip().splitlines()[-1])

    def stop(self):
        started = time.monotonic()
        command("docker", "stop", self.name)
        code = self.process.wait(timeout=25)
        elapsed = time.monotonic() - started
        assert code in (0, 143), code
        assert elapsed < 18, elapsed
        assert json_file(self.output / "run/status.json")["state"] == "stopped"
        return {"exit_code": code, "seconds": round(elapsed, 3)}

    def close(self):
        if self.closed:
            return
        try:
            command("docker", "rm", "-f", self.name)
            self.process.wait(timeout=25)
            self.closed = True
        finally:
            self.log.close()


def ardupilot(image, output, installed=False):
    results = []
    script = None if installed else "/qualification/docker/run-sitl.sh"
    for mode, instance, sysid in (("direct", 0, 1), ("mavproxy", 1, 2)):
        case = output / mode
        env = {"SITL_RUN_DIR": "/results/run", "NO_MAVPROXY": "1" if mode == "direct" else "0",
               "INSTANCE": str(instance), "SYSID": str(sysid), "PLAN_UPLOAD_TIMEOUT": "40",
               "SITL_CONFIG_DIR": "/qualification/configs/examples/initial-state",
               "PARAM_FILE": "initial-state.parm", "LUA_SCRIPT": "/qualification/docker/qualification-ready.lua",
               "MISSION_FILE": "/qualification/configs/examples/mission/missions/simple-copter.waypoints",
               "FENCE_FILE": "/qualification/configs/examples/plan-artifacts/fences/simple-polygon.json",
               "RALLY_FILE": "/qualification/configs/examples/plan-artifacts/rally/recovery-points.json"}
        if mode == "mavproxy":
            env["PROXY"] = f"--out=tcpin:127.0.0.1:{21000 + instance}"
        container = Container(image, case, env, script)
        try:
            container.wait_state("ready")
            container.exec("python3", "/usr/local/bin/run-sitl.py" if installed else "/qualification/docker/run-sitl.py", "--healthcheck")
            wait_for(lambda: (case / "run/work/lua-qualification.txt").exists(), "Lua executed in effective work dir")
            plans = container.client(mode, instance, sysid, "plans")
            container.client(mode, instance, sysid, "set")
            time.sleep(2)  # firmware parameter persistence, not process readiness polling
            stopped = container.stop()
            assert (case / "run/work/scripts/initial-state.lua").is_file()
            container.close()
            env["SITL_STATE"] = "resume"
            # Persisted plans must remain even when selection is removed.
            for key in ("MISSION_FILE", "FENCE_FILE", "RALLY_FILE"):
                env.pop(key)
            env["PARAM_FILE"] = ""
            env["LUA_SCRIPT"] = ""
            env["SITL_CONFIG_DIR"] = "/configs"
            container = Container(image, case, env, script)
            container.wait_state("ready")
            resumed = container.client(mode, instance, sysid, "resume")
            container.client(mode, instance, sysid, "plans")
            assert not (case / "run/work/scripts/initial-state.lua").exists()
            container.stop()
            container.close()
            env["SITL_STATE"] = "fresh"
            container = Container(image, case, env, script)
            container.wait_state("ready")
            fresh = container.client(mode, instance, sysid, "fresh")
            assert len(list((case / "run/history").iterdir())) == 1
            container.exec("pkill", "-KILL", "-x", "arducopter")
            code = container.process.wait(timeout=20)
            assert code == 1, code
            assert json_file(case / "run/status.json")["state"] == "failed"
            record = {"mode": mode, "plans": plans, "resume": resumed, "fresh": fresh,
                      "graceful_stop": stopped, "crash_exit": code, "lua_executed": True}
            results.append(record)
            print("PASS", json.dumps(record), flush=True)
        finally:
            container.close()
    # Exercise the process-local overlay against real upstream VehicleInfo.
    metadata = "/home/ardupilot/ardupilot/Tools/autotest/pysim/vehicleinfo.py"
    metadata_json = metadata.removesuffix(".py") + ".json"
    hash_command = ['bash', '-c', 'sha256sum "$1"; if [ -f "$2" ]; then sha256sum "$2"; fi', 'qualify', metadata, metadata_json]
    original = command("docker", "run", "--rm", "--entrypoint", "bash", image, *hash_command[1:]).stdout
    bundle = Container(image, output / "bundle", {"SITL_RUN_DIR": "/results/run", "NO_MAVPROXY": "1",
                       "SITL_CONFIG_DIR": "/qualification/configs/frames/arducopter-quad"}, script)
    try:
        bundle.wait_state("ready")
        current = bundle.exec(*hash_command).stdout
        assert current == original
        effective = json_file(output / "bundle/run/effective-config.json")
        assert effective["params"] == ["/qualification/configs/frames/arducopter-quad/copter.parm"]
        record = {"mode": "bundle", "metadata_backend": "json" if metadata_json in original else "python",
                  "upstream_metadata_unchanged": True, "metadata_sha256": original, "graceful_stop": bundle.stop()}
        results.append(record)
        print("PASS", json.dumps(record), flush=True)
    finally:
        bundle.close()
    return results


def px4(image, client_image, output, installed=False):
    results = []
    env = {"PX4_RUN_DIR": "/results/run", "INSTANCE": "0", "SYSID": "7"}
    def native(container, module, *args):
        return container.exec("bash", "-c", '"$PX4_ROOT/build/$PX4_BUILD_DIR/bin/px4-' + module + '" --instance 0 "$@"', "qualify", *args).stdout
    for state in ("fresh", "resume", "fresh"):
        env["SITL_STATE"] = state
        if len(results) == 2:
            env["SYSID"] = ""
        container = Container(image, output, env, None if installed else "/qualification/docker/run-px4-sih.sh")
        try:
            container.wait_state("running")
            wait_for(lambda: "Startup script returned successfully" in Path(container.log.name).read_text(), "PX4 startup complete")
            # Native uORB and simulator checks prove more than process liveness.
            wait_for(lambda: "xy_valid: True" in native(container, "listener", "vehicle_local_position", "-n", "1"),
                     "PX4 estimator receives simulated position", timeout=20)
            simulator = native(container, "simulator_sih", "status")
            assert "Running in lockstep mode" in simulator, simulator
            sysid = 7 if env["SYSID"] else 1
            beat = command("docker", "run", "--rm", "--network", "container:" + container.name,
                           "--entrypoint", "python3", client_image, "-c",
                           'from pymavlink import mavutil; m=mavutil.mavlink_connection("udpin:0.0.0.0:14550"); '
                           'h=m.wait_heartbeat(timeout=10); assert h; print(h.get_srcSystem()); '
                           f'assert h.get_srcSystem()=={sysid}').stdout.strip()
            assert int(beat) == sysid
            value = native(container, "param", "show", "-q", "MPC_XY_VEL_MAX").strip()
            assert abs(float(value) - (7.25 if state == "resume" else 12)) < 0.001, value
            version = native(container, "ver", "all")
            assert "PX4 git-hash:" in version, version
            if not results:
                native(container, "param", "set", "MPC_XY_VEL_MAX", "7.25")
                native(container, "param", "save")
            record = {"state": state, "sysid": sysid, "MPC_XY_VEL_MAX": float(value), "lockstep": True, "position_valid": True,
                      "version": version}
            if len(results) == 2:
                container.exec("pkill", "-KILL", "-x", "px4")
                code = container.process.wait(timeout=20)
                assert code == 137, code
                assert json_file(output / "run/status.json")["state"] == "failed"
                assert len(list((output / "run/history").iterdir())) == 1
                record["crash_exit"] = code
            else:
                record["graceful_stop"] = container.stop()
            results.append(record)
            print("PASS", json.dumps(record), flush=True)
        finally:
            container.close()
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", choices=("ardupilot", "px4"), default="ardupilot")
    parser.add_argument("--installed", action="store_true", help="exercise the image's installed ENTRYPOINT/helpers, not mounted launch code")
    parser.add_argument("--image", default="ardupilot-sitl:copter-4.6.3")
    parser.add_argument("--client-image", default="ardupilot-sitl:copter-4.6.3", help="existing pymavlink-equipped image for PX4 wire checks")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("--output must be empty; use a new directory for each qualification run")
    output.mkdir(parents=True, exist_ok=True)
    report = {"image": args.image, "image_inspect": json.loads(command("docker", "image", "inspect", args.image).stdout)[0]["Id"],
              "family": args.family, "command": sys.argv, "git_revision": command("git", "-C", str(REPO), "rev-parse", "HEAD").stdout.strip(),
              "helper_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((REPO / "docker").iterdir()) if p.is_file()},
              "scope": "installed image ENTRYPOINT/helpers and available Docker HEALTHCHECK" if args.installed else "current helpers mounted into existing firmware image; no image build"}
    try:
        report["results"] = ardupilot(args.image, output, args.installed) if args.family == "ardupilot" else px4(args.image, args.client_image, output, args.installed)
        report["passed"] = True
    except Exception as exc:
        report["passed"] = False
        report["error"] = str(exc)
        raise
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
