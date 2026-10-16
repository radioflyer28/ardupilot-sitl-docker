#!/usr/bin/env python3
"""Opt-in installed-image/Compose qualification with real host TCP clients.

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
m = mavutil.mavlink_connection(f"tcp:127.0.0.1:{port}", source_system=254, source_component=191)
m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
h = m.wait_heartbeat(timeout=10)
assert h and h.get_srcSystem() == sysid and h.get_srcComponent() == 1, h
if operation == "set":
    m.mav.param_set_send(sysid, 1, b"SIM_WIND_SPD", 2.5, mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
else:
    m.mav.param_request_read_send(sysid, 1, b"SIM_WIND_SPD", -1)
deadline = time.monotonic() + 10
value = None
while time.monotonic() < deadline:
    p = m.recv_match(type="PARAM_VALUE", blocking=True, timeout=.5)
    if p and p.get_srcSystem() == sysid and p.param_id == "SIM_WIND_SPD":
        value = p.param_value
        break
assert value is not None
expected = 2.5 if operation in ("set", "resume") else 0
assert value == expected, (operation, value, expected)
m.close()
print(json.dumps({"port": port, "sysid": sysid, "SIM_WIND_SPD": value}))
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
    parser.add_argument("--client-python", required=True, help="host Python executable with pymavlink")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("use a new/empty output directory")
    for port in (5760, 5770, 5780):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))
    subprocess.run([args.client_python, "-c", "import pymavlink"], check=True)
    output.mkdir(parents=True, exist_ok=True)
    project = "sitl-qualify-" + uuid.uuid4().hex[:10]
    env = dict(os.environ, ARDUPILOT_SITL_IMAGE=args.image, QUALIFY_STATE="fresh")
    base = ["docker", "compose", "--project-name", project,
            "-f", str(REPO / "compose.sitl.yml"), "-f", str(REPO / "docker/compose.qualification.yml")]
    report = {"image": args.image, "project": project, "cases": []}
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
            for i in range(3):
                ident = compose("ps", "--quiet", f"sitl-{i}").stdout.strip()
                details = json.loads(run(["docker", "inspect", ident]).stdout)[0]
                assert details["State"]["Health"]["Status"] == "healthy"
                binding = details["NetworkSettings"]["Ports"][f"{5760 + i * 10}/tcp"]
                assert binding == [{"HostIp": "127.0.0.1", "HostPort": str(5760 + i * 10)}], binding
                mounts = [m for m in details["Mounts"] if m["Destination"] == "/home/ardupilot/runs"]
                assert len(mounts) == 1 and mounts[0]["Type"] == "volume"
                data.append({"id": ident, "volume": mounts[0]["Name"], "health": "healthy"})
            assert len({d["volume"] for d in data}) == 3
            return data

        def clients(operation):
            return [json.loads(run([args.client_python, "-", str(5760 + i * 10), str(i + 1), operation],
                                   input=CLIENT).stdout) for i in range(3)]

        try:
            report["image_id"] = json.loads(run(["docker", "image", "inspect", args.image]).stdout)[0]["Id"]
            compose("up", "-d", "--wait", "--wait-timeout", "100")
            initial = snapshots()
            set_values = clients("set")
            time.sleep(2)  # allow firmware's asynchronous parameter storage to settle
            report["cases"].append({"phase": "initial", "services": initial, "host_clients": set_values})
            # Graceful down must retain named volumes; recreation must reuse them.
            compose("down")
            for item in initial:
                run(["docker", "volume", "inspect", item["volume"]])
            env["QUALIFY_STATE"] = "resume"
            compose("up", "-d", "--wait", "--wait-timeout", "100")
            resumed = snapshots()
            assert [d["volume"] for d in initial] == [d["volume"] for d in resumed]
            assert all(a["id"] != b["id"] for a, b in zip(initial, resumed))
            report["cases"].append({"phase": "resume-after-down", "services": resumed, "host_clients": clients("resume")})
            env["QUALIFY_STATE"] = "fresh"
            compose("up", "-d", "--wait", "--wait-timeout", "100")
            fresh = snapshots()
            for item in fresh:
                run(["docker", "exec", item["id"], "python3", "-c",
                     "from pathlib import Path; assert len(list(Path('/home/ardupilot/runs/history').iterdir()))==1"])
            report["cases"].append({"phase": "fresh-recreate", "services": fresh, "host_clients": clients("fresh")})
            report["passed"] = True
        except Exception as exc:
            report["passed"] = False
            report["error"] = str(exc)
            raise
        finally:
            finalize_report(compose, report, output)
    print("PASS Compose: installed health, three loopback host clients, distinct named volumes, "
          "down/resume retention, fresh archive/reset, cleanup", flush=True)


if __name__ == "__main__":
    main()
