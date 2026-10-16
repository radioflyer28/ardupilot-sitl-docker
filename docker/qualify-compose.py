#!/usr/bin/env python3
"""Opt-in installed-image/Compose qualification with real host MAVLink clients.

Uses an isolated Compose project and removes only its own containers/volumes.
Requires an explicitly selected host Python with pymavlink installed. No builds.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import uuid

REPO = Path(__file__).resolve().parent.parent
CLIENT = r'''
import os, sys, time, json
os.environ["MAVLINK20"] = "1"
from pymavlink import mavutil
port, sysid, operation = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
family = sys.argv[4] if len(sys.argv) > 4 else "ardupilot"
endpoint = f"udpout:127.0.0.1:{port}" if family == "px4" else f"tcp:127.0.0.1:{port}"
m = mavutil.mavlink_connection(endpoint, source_system=254, source_component=191)
h = None
deadline = time.monotonic() + 10
while time.monotonic() < deadline:
    m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
    candidate = m.wait_heartbeat(timeout=1)
    if candidate and candidate.get_srcSystem() == sysid and candidate.get_srcComponent() == 1:
        h = candidate
        break
assert h, "missing expected autopilot heartbeat"
if family == "px4":
    assert h.autopilot == mavutil.mavlink.MAV_AUTOPILOT_PX4
parameter = "MPC_XY_VEL_MAX" if family == "px4" else "SIM_WIND_SPD"
changed = 7.25 if family == "px4" else 2.5
initial = 12 if family == "px4" else 0
if operation == "set":
    m.mav.param_set_send(sysid, 1, parameter.encode(), changed, mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
else:
    m.mav.param_request_read_send(sysid, 1, parameter.encode(), -1)
deadline = time.monotonic() + 10
value = None
while time.monotonic() < deadline:
    p = m.recv_match(type="PARAM_VALUE", blocking=True, timeout=.5)
    if p and p.get_srcSystem() == sysid and p.get_srcComponent() == 1 and p.param_id == parameter:
        value = p.param_value
        break
assert value is not None
expected = changed if operation in ("set", "resume") else initial
assert value == expected, (operation, value, expected)
local_port = m.port.getsockname()[1] if family == "px4" else None
m.close()
print(json.dumps({"port": port, "sysid": sysid, parameter: value, "local_port": local_port}))
'''


def finalize_report(compose, report, output):
    """Always attempt teardown and retain failures; cleanup is part of passing."""
    errors = []
    for args in (("logs", "--no-color"), ("down", "--volumes", "--remove-orphans")):
        try:
            result = compose(*args, check=False)
            if result.returncode:
                errors.append(f"{args[0]} exited {result.returncode}")
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{args[0]}: {exc}")
    if errors:
        report["passed"] = False
        report["cleanup_errors"] = errors
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    if errors:
        raise RuntimeError("qualification cleanup failed: " + "; ".join(errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--family", choices=("ardupilot", "px4"), default="ardupilot")
    parser.add_argument("--client-python", required=True, help="host Python executable with pymavlink")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("use a new/empty output directory")
    px4 = args.family == "px4"
    ports = (18570,) if px4 else (5760, 5770, 5780)
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM if px4 else socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", port))
    subprocess.run([args.client_python, "-c", "import pymavlink"], check=True)
    output.mkdir(parents=True, exist_ok=True)
    project = "sitl-qualify-" + uuid.uuid4().hex[:10]
    state_key = "SITL_STATE" if px4 else "QUALIFY_STATE"
    image_key = "PX4_SIH_IMAGE" if px4 else "ARDUPILOT_SITL_IMAGE"
    env = dict(os.environ, **{image_key: args.image, state_key: "fresh"},
               SITL_BIND_ADDRESS="127.0.0.1", PX4_GCS_PORT="18570", SYSID="1")
    base = ["docker", "compose", "--project-name", project,
            "-f", str(REPO / ("compose.px4-sih.yml" if px4 else "compose.sitl.yml"))]
    if not px4:
        base.extend(["-f", str(REPO / "docker/compose.qualification.yml")])
    if px4:
        env.update(MODEL="sihsim_quadx", MISSION_FILE="", FENCE_FILE="", RALLY_FILE="")
    services = ["px4"] if px4 else [f"sitl-{i}" for i in range(3)]
    run_root = "/artifacts/run" if px4 else "/home/ardupilot/runs"
    mount_root = "/artifacts" if px4 else run_root
    report = {"image": args.image, "family": args.family, "project": project, "cases": []}
    with (output / "commands.log").open("w") as log:
        def run(argv, check=True, **kwargs):
            result = subprocess.run(argv, env=env, text=True, capture_output=True, timeout=180, **kwargs)
            log.write(json.dumps(argv) + "\n" + result.stdout + result.stderr + "\n")
            log.flush()
            if check and result.returncode:
                raise RuntimeError(f"command failed: {argv}; see {output}/commands.log")
            return result

        def compose(*cmd, **kwargs):
            return run([*base, *cmd], **kwargs)

        def snapshots():
            data = []
            for i, service in enumerate(services):
                ident = compose("ps", "--quiet", service).stdout.strip()
                details = json.loads(run(["docker", "inspect", ident]).stdout)[0]
                assert details["State"]["Health"]["Status"] == "healthy"
                container_port = "18670/udp" if px4 else f"{ports[i]}/tcp"
                binding = details["NetworkSettings"]["Ports"][container_port]
                assert binding == [{"HostIp": "127.0.0.1", "HostPort": str(ports[i])}], binding
                mounts = [m for m in details["Mounts"] if m["Destination"] == mount_root]
                assert len(mounts) == 1 and mounts[0]["Type"] == "volume"
                data.append({"id": ident, "volume": mounts[0]["Name"], "health": "healthy"})
            assert len({d["volume"] for d in data}) == len(services)
            return data

        def clients(operation):
            return [json.loads(run([args.client_python, "-", str(port), str(i + 1), operation, args.family],
                                   input=CLIENT).stdout) for i, port in enumerate(ports)]

        try:
            report["image_id"] = json.loads(run(["docker", "image", "inspect", args.image]).stdout)[0]["Id"]
            compose("up", "-d", "--wait", "--wait-timeout", "100")
            initial = snapshots()
            set_values = clients("set")
            if px4:
                # A new host process gets a new UDP source port: replies must follow it.
                report["reconnected_host_clients"] = clients("resume")
            time.sleep(2)  # allow firmware's asynchronous parameter storage to settle
            report["cases"].append({"phase": "initial", "services": initial, "host_clients": set_values})
            # Graceful down must retain named volumes; recreation must reuse them.
            compose("down")
            for item in initial:
                run(["docker", "volume", "inspect", item["volume"]])
            env[state_key] = "resume"
            compose("up", "-d", "--wait", "--wait-timeout", "100")
            resumed = snapshots()
            assert [d["volume"] for d in initial] == [d["volume"] for d in resumed]
            assert all(a["id"] != b["id"] for a, b in zip(initial, resumed))
            report["cases"].append({"phase": "resume-after-down", "services": resumed, "host_clients": clients("resume")})
            env[state_key] = "fresh"
            compose("up", "-d", "--wait", "--wait-timeout", "100")
            fresh = snapshots()
            for item in fresh:
                run(["docker", "exec", item["id"], "python3", "-c",
                     f"from pathlib import Path; assert len(list(Path('{run_root}/history').iterdir()))==1"])
            report["cases"].append({"phase": "fresh-recreate", "services": fresh, "host_clients": clients("fresh")})
            if px4:
                ident = fresh[0]["id"]
                run(["docker", "exec", ident, "pkill", "-f", "px4-gcs-relay.py"])
                assert run(["docker", "wait", ident]).stdout.strip() == "1"
                status = output / "relay-failure-status.json"
                run(["docker", "cp", f"{ident}:{run_root}/status.json", str(status)])
                assert json.loads(status.read_text())["state"] == "failed"
                report["relay_failure_stops_vehicle"] = True
            report["passed"] = True
        except Exception as exc:
            report["passed"] = False
            report["error"] = str(exc)
            raise
        finally:
            finalize_report(compose, report, output)
    print(f"PASS {args.family} Compose: installed health, loopback host clients, named volumes, "
          "down/resume retention, fresh archive/reset, cleanup", flush=True)


if __name__ == "__main__":
    main()
