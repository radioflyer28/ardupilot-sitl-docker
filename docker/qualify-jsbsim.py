#!/usr/bin/env python3
"""Opt-in installed ArduCopter/JSBSim coupling, flight and failure qualification."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

REPO = Path(__file__).resolve().parent.parent


def flight_client(endpoint):
    from pymavlink import mavutil
    link = mavutil.mavlink_connection(endpoint, source_system=254)
    events = []
    samples = []
    latest = {}
    last_heartbeat = 0

    def pump(timeout=.2):
        nonlocal last_heartbeat
        if time.monotonic() - last_heartbeat > 1:
            link.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS,
                                    mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
            last_heartbeat = time.monotonic()
        message = link.recv_match(blocking=True, timeout=timeout)
        if message is not None and message.get_srcSystem() == 1 and message.get_srcComponent() == 1:
            latest[message.get_type()] = message
            if message.get_type() == "STATUSTEXT":
                events.append(message.text)
                print(message.text, file=sys.stderr, flush=True)
        return message

    def wait(predicate, timeout, description):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            pump()
            if predicate():
                return
        raise RuntimeError(f"timeout: {description}; recent status: {events[-12:]}")

    def command(command_id, *params):
        values = list(params) + [0] * (7 - len(params))
        link.mav.command_long_send(1, 1, command_id, 0, *values)

    def mode(name):
        link.set_mode(link.mode_mapping()[name])
        wait(lambda: latest.get("HEARTBEAT") and latest["HEARTBEAT"].custom_mode == link.mode_mapping()[name],
             10, name)

    def armed():
        return latest.get("HEARTBEAT") and bool(latest["HEARTBEAT"].base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)

    def altitude():
        return latest["GLOBAL_POSITION_INT"].relative_alt / 1000

    try:
        wait(lambda: "HEARTBEAT" in latest, 10, "heartbeat")
        link.target_system, link.target_component = 1, 1
        assert latest["HEARTBEAT"].autopilot == mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA
        link.mav.request_data_stream_send(1, 1, mavutil.mavlink.MAV_DATA_STREAM_ALL, 10, 1)
        wait(lambda: "GLOBAL_POSITION_INT" in latest and "EKF_STATUS_REPORT" in latest and
             latest["EKF_STATUS_REPORT"].flags & 1 and latest["EKF_STATUS_REPORT"].flags & 16,
             60, "normal EKF attitude and absolute horizontal position")
        parameters = {}
        for name in ("FRAME_CLASS", "FRAME_TYPE", "AHRS_EKF_TYPE", "MOT_PWM_MIN", "MOT_PWM_MAX"):
            latest.pop("PARAM_VALUE", None)
            link.mav.param_request_read_send(1, 1, name.encode(), -1)
            wait(lambda: latest.get("PARAM_VALUE") and latest["PARAM_VALUE"].param_id == name,
                 5, f"parameter {name}")
            parameters[name] = latest["PARAM_VALUE"].param_value
        assert parameters == {"FRAME_CLASS": 1, "FRAME_TYPE": 1, "AHRS_EKF_TYPE": 3,
                              "MOT_PWM_MIN": 1000, "MOT_PWM_MAX": 2000}, parameters
        mode("GUIDED")
        command(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1)
        wait(armed, 20, "normal arming (no force-arm)")
        command(mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 5)
        wait(lambda: altitude() >= 4.5, 40, "takeoff to 5m")
        # Allow settling before the ten-second hover acceptance window.
        settle = time.monotonic() + 5
        while time.monotonic() < settle:
            pump()
        origin = latest["GLOBAL_POSITION_INT"]
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            message = pump()
            if message and message.get_type() == "GLOBAL_POSITION_INT":
                attitude = latest.get("ATTITUDE")
                north = (message.lat - origin.lat) * 1e-7 * 111319.5
                east = (message.lon - origin.lon) * 1e-7 * 111319.5 * math.cos(math.radians(message.lat * 1e-7))
                sample = {"altitude": altitude(), "drift": math.hypot(north, east),
                          "roll": attitude.roll, "pitch": attitude.pitch}
                samples.append(sample)
                assert 3 <= sample["altitude"] <= 7, sample
                assert sample["drift"] < 4, sample
                assert abs(sample["roll"]) < .45 and abs(sample["pitch"]) < .45, sample
        assert len(samples) >= 20, "insufficient hover samples"
        command(mavutil.mavlink.MAV_CMD_CONDITION_YAW, 90, 20, 1, 0)
        wait(lambda: abs((latest["GLOBAL_POSITION_INT"].hdg / 100 - 90 + 180) % 360 - 180) < 15,
             30, "guided yaw to 90 degrees")
        mode("LAND")
        wait(lambda: not armed(), 60, "landing and auto-disarm")
        assert altitude() < .5, altitude()
        print(json.dumps({"passed": True, "parameters": parameters, "hover_samples": samples,
                          "landed_altitude": altitude(), "status_text": events}))
    finally:
        link.close()


def qualify(args):
    output = Path(args.output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("output must be empty")
    output.mkdir(parents=True, exist_ok=True)
    project = "jsbsim-qualify-" + uuid.uuid4().hex[:10]
    env = dict(os.environ, ARDUCOPTER_JSBSIM_IMAGE=args.autopilot_image, JSBSIM_IMAGE=args.simulator_image,
               SITL_PORT=str(args.port), SITL_BIND_ADDRESS="127.0.0.1", LAT="37.1971467",
               LON="-80.5780381", ALT="618", DIR="0")
    env["JSBSIM_MODEL"] = args.model
    local = args.deployment == "local"
    filename = "compose.jsbsim" if local else "compose.jsbsim-split"
    base = ["docker", "compose", "-p", project, "-f", str(REPO / (filename + ".yml"))]
    if args.models_dir:
        env["JSBSIM_MODELS_DIR"] = str(Path(args.models_dir).resolve())
        base.extend(["-f", str(REPO / (filename + "-models.yml"))])
    physics_root = "/home/ardupilot/runs/work/physics" if local else "/physics"
    services = ("sitl",) if local else ("sitl", "physics")
    report = {"passed": False, "project": project, "deployment": args.deployment, "cases": []}
    containers = {}

    def run(command, timeout=120, check=True):
        result = subprocess.run(command, env=env, text=True, capture_output=True, timeout=timeout)
        with (output / "commands.log").open("a") as log:
            log.write(f"{command!r}\n{result.stdout}\n{result.stderr}\n")
        if check and result.returncode:
            raise RuntimeError(f"command failed: {command!r}\n{result.stdout}\n{result.stderr}")
        return result

    def compose(*command, **kwargs):
        return run([*base, *command], **kwargs)

    try:
        simulator_image = args.autopilot_image if local else args.simulator_image
        for name, image in (("autopilot", args.autopilot_image), ("simulator", simulator_image)):
            report[name] = json.loads(run(["docker", "image", "inspect", image]).stdout)[0]["Id"]
        report["installed_helpers"] = {}
        for image, prefix, names in (
            (args.autopilot_image, "/usr/local/bin", ["run-sitl.sh", "run-sitl.py", "sitl_config.py", "run_state.py",
                                                    "launch-sitl.py", "sitl-terminal.py", "upload-plan-artifacts.py"]),
            (simulator_image, "/usr/local/bin" if local else "/opt/sitl", ["jsbsim_adapter.py", "run_state.py"])):
            expected = {name: hashlib.sha256((REPO / "docker" / name).read_bytes()).hexdigest() for name in names}
            code = ("import hashlib,json,pathlib; print(json.dumps({name:hashlib.sha256("
                    f"(pathlib.Path({prefix!r})/name).read_bytes()).hexdigest() for name in {names!r}" + "}))")
            actual = json.loads(run(["docker", "run", "--rm", "--entrypoint", "python3", image, "-c", code]).stdout)
            assert actual == expected, (image, actual, expected)
            report["installed_helpers"].setdefault(image, {}).update(actual)
        compose("up", "-d", "--wait", "--wait-timeout", "90")
        for name in services:
            containers[name] = compose("ps", "--quiet", name).stdout.strip()
        if local:
            containers["physics"] = containers["sitl"]
        details = json.loads(run(["docker", "inspect", containers["sitl"]]).stdout)[0]
        assert details["NetworkSettings"]["Ports"]["5760/tcp"] == [{"HostIp": "127.0.0.1", "HostPort": str(args.port)}]
        report["cases"].append("installed readiness and localhost publication")
        report["networks"] = list(details["NetworkSettings"]["Networks"])
        if not args.skip_flight:
            flight = run([args.client_python, str(Path(__file__).resolve()), "--flight-client",
                          f"tcp:127.0.0.1:{args.port}"], timeout=260)
            report["flight"] = json.loads(flight.stdout)
            report["cases"].append("normal EKF, takeoff, 10s hover, yaw, land and disarm")
            run(["docker", "cp", f"{containers['physics']}:{physics_root}/work/truth.jsonl", str(output / "flight-truth.jsonl")])
            truth = [json.loads(line) for line in (output / "flight-truth.jsonl").read_text().splitlines()]
            assert len(truth) > 200, "missing physics truth"
            assert max(-row["state"]["position"][2] for row in truth) > 4, "physics never took off"
            assert all(b["state"]["timestamp"] > a["state"]["timestamp"] for a, b in zip(truth, truth[1:])), "nonmonotonic physics time"
            report["physics_truth_samples"] = len(truth)
        else:
            report["flight"] = {"skipped": True}
        victim = args.fault
        survivor = "sitl" if local or victim == "physics" else "physics"
        root = "/home/ardupilot/runs" if survivor == "sitl" else physics_root
        if victim == "stop":
            compose("stop", "--timeout", "15")
        elif local and victim == "physics":
            code = f"import json,os,signal; os.kill(json.load(open('{physics_root}/status.json'))['pid'], signal.SIGKILL)"
            run(["docker", "exec", containers["sitl"], "python3", "-c", code])
        elif local:
            run(["docker", "exec", containers["sitl"], "pkill", "-KILL", "-x", "arducopter"])
        else:
            run(["docker", "kill", containers[victim]])
        stopped = run(["docker", "wait", containers[survivor]], timeout=20)
        assert stopped.stdout.strip() in (("0", "143") if victim == "stop" else ("1",)), stopped.stdout
        run(["docker", "cp", f"{containers[survivor]}:{root}/status.json", str(output / "survivor-status.json")])
        expected = "stopped" if victim == "stop" else "failed"
        assert json.loads((output / "survivor-status.json").read_text())["state"] == expected
        if local and victim != "physics":
            run(["docker", "cp", f"{containers['sitl']}:{physics_root}/status.json", str(output / "physics-stop.json")])
            assert json.loads((output / "physics-stop.json").read_text())["state"] == "stopped"
        report["cases"].append("graceful stop" if victim == "stop" else f"{victim} death stops {survivor}")
        report["passed"] = True
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        try:
            logs = compose("logs", "--no-color", check=False)
            (output / "containers.log").write_text(logs.stdout + logs.stderr)
            for name, root in (("physics", physics_root), ("sitl", "/home/ardupilot/runs")):
                service = "sitl" if local else name
                ident = containers.get(name) or compose("ps", "-a", "--quiet", service).stdout.strip()
                if ident:
                    run(["docker", "cp", f"{ident}:{root}", str(output / name)])
        except Exception as exc:
            report["passed"] = False
            report["collection_error"] = str(exc)
        try:
            compose("down", "--volumes", "--remove-orphans")
        except Exception as exc:
            report["passed"] = False
            report["cleanup_error"] = str(exc)
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    if not report["passed"]:
        raise RuntimeError("qualification collection or cleanup failed")
    print(f"PASS JSBSim qualification: {output}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--flight-client")
    p.add_argument("--output")
    p.add_argument("--client-python", default="/usr/bin/python3.10")
    p.add_argument("--port", type=int, default=5760)
    p.add_argument("--skip-flight", action="store_true", help="qualify startup/failure only, not flight")
    p.add_argument("--fault", choices=("physics", "sitl", "stop"), default="physics")
    p.add_argument("--deployment", choices=("local", "split"), default="local")
    p.add_argument("--model", default="F450")
    p.add_argument("--models-dir")
    p.add_argument("--autopilot-image")
    p.add_argument("--simulator-image", default="jsbsim:qualify-1.3.3-split")
    args = p.parse_args()
    args.autopilot_image = args.autopilot_image or f"ardupilot-sitl:qualify-4.6.3-jsbsim-{args.deployment}"
    if args.flight_client:
        flight_client(args.flight_client)
    elif args.output:
        qualify(args)
    else:
        p.error("--output is required")


if __name__ == "__main__":
    main()
