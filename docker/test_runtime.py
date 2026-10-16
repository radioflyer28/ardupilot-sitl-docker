"""Host-only regression suite: python3 -m unittest discover -s docker -p 'test_*.py'."""
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import sitl_config
from run_state import RunDirectory, atomic_json, healthcheck

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runner = load("test_runner", "run-sitl.py")
upload = load("test_upload", "upload-plan-artifacts.py")


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ap = self.root / "ardupilot"
        loader = self.ap / "Tools/autotest/pysim/vehicleinfo.py"
        loader.parent.mkdir(parents=True)
        self.stock = {"ArduCopter": {"default_frame": "quad", "frames": {
            "quad": {"waf_target": "bin/arducopter", "model": "quad"},
            "hexa": {"waf_target": "bin/arducopter", "model": "hexa"}}}}
        loader.write_text("class VehicleInfo:\n    def __init__(self):\n        self.options = " + repr(self.stock) + "\n")
        self.binary = self.ap / "build/sitl/bin/arducopter"
        self.binary.parent.mkdir(parents=True)
        self.binary.write_text("#!/bin/sh\nexit 0\n")
        self.binary.chmod(0o755)
        self.cfg = self.root / "config"
        self.cfg.mkdir()
        self.env = {"ARDUPILOT_ROOT": str(self.ap), "SITL_CONFIG_DIR": str(self.cfg),
                    "SITL_RUN_DIR": str(self.root / "run"), "NO_MAVPROXY": "1"}

    def resolve(self, args=None, **env):
        return sitl_config.resolve(args or [], {**self.env, **env})


class ConfigTests(Fixture):
    def test_missing_bundle_fails_without_mutation(self):
        before = (self.ap / "Tools/autotest/pysim/vehicleinfo.py").read_bytes()
        with self.assertRaises(sitl_config.ConfigError):
            self.resolve(VEHICLEINFO_JSON="missing.json")
        self.assertEqual(before, (self.ap / "Tools/autotest/pysim/vehicleinfo.py").read_bytes())
        self.assertFalse((self.root / "run").exists())

    def test_invalid_json_fails_without_mutation(self):
        (self.cfg / "vehicleinfo.json").write_text("{")
        with self.assertRaises(sitl_config.ConfigError):
            self.resolve()
        self.assertFalse((self.ap / "Tools/autotest/pysim/vehicleinfo.json").exists())

    def test_bundle_and_ordered_parameter_layers(self):
        for name in ("base.parm", "middle.parm", "last.parm", "cli.parm"):
            (self.cfg / name).write_text("SCR_ENABLE 1\n")
        (self.cfg / "vehicleinfo.json").write_text(json.dumps({"ArduCopter": {"frames": {"quad": {"default_params_filename": "base.parm"}}}}))
        config = self.resolve(["--add-param-file", "cli.parm"], PARAM_FILES='["middle.parm"]', PARAM_FILE="last.parm")
        self.assertEqual([Path(p).name for p in config["params"]], ["base.parm", "middle.parm", "last.parm", "cli.parm"])
        self.assertEqual(config["vehicleinfo_overrides"]["ArduCopter"]["frames"]["quad"]["default_params_filename"], [str(self.cfg / "base.parm")])

    def test_cli_controls_all_derived_values(self):
        config = self.resolve(["-I", "2", "--sysid", "3", "--frame", "hexa", "--use-dir", str(self.root / "outputs")])
        self.assertEqual(config["master"], "tcp:127.0.0.1:5780")
        self.assertEqual(config["model"], "hexa")
        args = sitl_config.sim_arguments(config, Path(config["run_dir"]) / "work")
        self.assertEqual(args[args.index("-I") + 1], "2")
        self.assertIn(str(self.root / "outputs/work"), args)

    def test_proxy_master_abbreviation_rejected(self):
        with self.assertRaises(sitl_config.ConfigError):
            self.resolve(NO_MAVPROXY="0", PROXY="--mast=tcp:other:5760")

    def test_direct_mode_rejects_ignored_proxy_options(self):
        with self.assertRaises(sitl_config.ConfigError):
            self.resolve(PROXY="--out=udp:127.0.0.1:14550")
        with self.assertRaises(sitl_config.ConfigError):
            self.resolve(["--aircraft", "/tmp/logs"])

    def test_healthcheck_uses_active_cli_run_directory(self):
        pointer = self.root / "health.json"
        atomic_json(pointer, {"run_dir": str(self.root / "cli-run")})
        result = self.resolve(["--healthcheck"], SITL_HEALTH_FILE=str(pointer))
        self.assertEqual(result["run_dir"], str(self.root / "cli-run"))

    def test_proxy_private_port_is_not_serial_port(self):
        config = self.resolve(NO_MAVPROXY="0")
        self.assertEqual(config["master"], "tcp:127.0.0.1:20000")
        self.assertIn("--out=tcpin:127.0.0.1:20000", config["proxy_args"])
        self.assertIn("--non-interactive", config["proxy_args"])

    def test_unsafe_flags_rejected(self):
        for args in (["--udp"], ["--count", "2"], ["--sitl-instance-args", "--serial0=udp:foo"], ["--sys", "2"]):
            with self.subTest(args=args), self.assertRaises(SystemExit), patch("sys.stderr", new=io.StringIO()):
                self.resolve(args)

    def test_numeric_and_state_validation(self):
        for env in ({"SYSID": "0"}, {"INSTANCE": "-1"}, {"SPEEDUP": "nan"}, {"LAT": "91"}, {"SITL_STATE": "typo"}, {"NO_MAVPROXY": "yes"}):
            with self.subTest(env=env), self.assertRaises(sitl_config.ConfigError):
                self.resolve(**env)
        config = self.resolve(SITL_STATE="resume")
        self.assertNotIn("-w", sitl_config.sim_arguments(config, self.root / "work"))

    def test_speedup_matches_upstream_integer_parser(self):
        for speedup in ("1", "2", "2.0"):
            config = self.resolve(SPEEDUP=speedup)
            args = sitl_config.sim_arguments(config, self.root / "work")
            value = args[args.index("--speedup") + 1]
            self.assertEqual(value, str(int(value)))
        for speedup in ("0.5", "1.5", "0"):
            with self.subTest(speedup=speedup), self.assertRaises(sitl_config.ConfigError):
                self.resolve(SPEEDUP=speedup)

    def test_preflight_mission_has_no_side_effects(self):
        (self.cfg / "bad.waypoints").write_text("QGC WPL 110\nbad data\n")
        result = subprocess.run([sys.executable, str(HERE / "run-sitl.py"), "--validate"], env={**os.environ, **self.env, "MISSION_FILE": "bad.waypoints"}, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected 12 fields", result.stderr)
        self.assertFalse((self.root / "run").exists())


class RunDirectoryTests(Fixture):
    def test_fresh_archives_and_resume_preserves(self):
        root = self.root / "run"
        with RunDirectory(root, "fresh") as run:
            (run.work / "eeprom.bin").write_text("state")
        with RunDirectory(root, "resume") as run:
            self.assertEqual((run.work / "eeprom.bin").read_text(), "state")
        with RunDirectory(root, "fresh") as run:
            self.assertFalse((run.work / "eeprom.bin").exists())
        self.assertEqual(len(list(root.glob("history/*/eeprom.bin"))), 1)

    def test_unowned_nonempty_directory_is_not_deleted(self):
        root = self.root / "run"
        root.mkdir()
        (root / "precious").write_text("keep")
        with self.assertRaises(ValueError):
            with RunDirectory(root, "fresh"):
                pass
        self.assertEqual((root / "precious").read_text(), "keep")

    def test_exclusive_lock(self):
        with RunDirectory(self.root / "run", "fresh"):
            with self.assertRaises(BlockingIOError):
                with RunDirectory(self.root / "run", "fresh"):
                    pass

    def test_scripts_replaced_in_effective_work_directory(self):
        scripts = self.cfg / "scripts"
        scripts.mkdir()
        (scripts / "old.lua").write_text("return\n")
        root = self.root / "run"
        with RunDirectory(root, "fresh") as run:
            runner.stage_scripts(self.resolve(), run.work)
            self.assertTrue((run.work / "scripts/old.lua").exists())
        (scripts / "old.lua").unlink()
        with RunDirectory(root, "resume") as run:
            runner.stage_scripts(self.resolve(), run.work)
            self.assertFalse((run.work / "scripts/old.lua").exists())

    def test_stale_ready_is_unhealthy(self):
        atomic_json(self.root / "status.json", {"state": "ready", "updated": time.time() - 10})
        self.assertFalse(healthcheck(self.root))
        atomic_json(self.root / "status.json", {"state": "ready", "updated": time.time()})
        self.assertTrue(healthcheck(self.root))


class PX4Tests(Fixture):
    def test_native_env_mapping_and_owned_work_directory(self):
        build = self.root / "px4/build/px4_sitl_sih"
        (build / "bin").mkdir(parents=True)
        (build / "etc").mkdir()
        binary = build / "bin/px4"
        binary.write_text('#!/bin/sh\nprintf "%s|%s|%s|%s\\n" "$PWD" "$PX4_SIM_MODEL" "$PX4_PARAM_MAV_SYS_ID" "$*" > native.txt\n')
        binary.chmod(0o755)
        output = self.root / "px4-run"
        env = {**os.environ, "PX4_ROOT": str(self.root / "px4"), "PX4_RUN_DIR": str(output), "INSTANCE": "2", "SYSID": "3", "MODEL": "sihsim_quadx"}
        result = subprocess.run(["bash", str(HERE / "run-px4-sih.sh")], env=env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        record = (output / "work/native.txt").read_text()
        self.assertIn(f"{output}/work|sihsim_quadx|3|-i 2", record)
        self.assertEqual(json.loads((output / "status.json").read_text())["state"], "stopped")
        self.assertFalse(healthcheck(output))


class PackagingTests(unittest.TestCase):
    def test_runtime_copy_sources_are_in_build_context(self):
        import fnmatch
        import shlex
        allowed = [line[1:] for line in (HERE.parent / ".dockerignore").read_text().splitlines() if line.startswith("!")]
        for name in ("Dockerfile", "Dockerfile.px4-sih"):
            for line in (HERE.parent / name).read_text().splitlines():
                if line.startswith("COPY docker/"):
                    for source in shlex.split(line)[1:-1]:
                        self.assertTrue(any(fnmatch.fnmatchcase(source, pattern) for pattern in allowed), source)

    def test_installed_qualification_uses_image_entrypoint(self):
        qualifier = load("test_qualifier", "qualify-runtime.py")
        for script in (None, "/qualification/docker/run-sitl.sh"):
            with tempfile.TemporaryDirectory() as temp, patch.object(qualifier.subprocess, "Popen") as popen:
                container = qualifier.Container("test-image:local", Path(temp), {}, script)
                try:
                    args = popen.call_args.args[0]
                    self.assertEqual("--entrypoint" in args, script is not None)
                    self.assertEqual(args[-1], script or "test-image:local")
                finally:
                    container.log.close()


class QualificationCleanupTests(unittest.TestCase):
    def test_compose_cleanup_failure_is_retained_and_teardown_attempted(self):
        qualifier = load("test_compose_qualifier", "qualify-compose.py")
        failures = [(step, error) for step in ("logs", "down")
                    for error in (SimpleNamespace(returncode=1), subprocess.TimeoutExpired(step, 180))]
        for step, failure in failures:
            with self.subTest(step=step, failure=failure), tempfile.TemporaryDirectory() as temp:
                report = {"passed": True}
                calls = []
                def compose(*args, **kwargs):
                    calls.append(args)
                    if args[0] == step:
                        if isinstance(failure, Exception):
                            raise failure
                        return failure
                    return SimpleNamespace(returncode=0)
                with self.assertRaises(RuntimeError):
                    qualifier.finalize_report(compose, report, Path(temp))
                saved = json.loads((Path(temp) / "report.json").read_text())
                self.assertFalse(saved["passed"])
                self.assertTrue(saved["cleanup_errors"])
                self.assertEqual(calls[-1], ("down", "--volumes", "--remove-orphans"))

    def test_compose_cleanup_success_preserves_success(self):
        qualifier = load("test_compose_qualifier", "qualify-compose.py")
        with tempfile.TemporaryDirectory() as temp:
            qualifier.finalize_report(lambda *a, **kw: SimpleNamespace(returncode=0), {"passed": True}, Path(temp))
            self.assertTrue(json.loads((Path(temp) / "report.json").read_text())["passed"])

    def test_container_cleanup_is_checked_and_idempotent(self):
        qualifier = load("test_runtime_qualifier", "qualify-runtime.py")
        with tempfile.TemporaryDirectory() as temp, patch.object(qualifier.subprocess, "Popen"):
            container = qualifier.Container("test-image:local", Path(temp), {})
            with patch.object(qualifier, "command") as command:
                container.close()
                container.close()
                command.assert_called_once_with("docker", "rm", "-f", container.name)
            self.assertTrue(container.log.closed)


class PX4IdentityTests(unittest.TestCase):
    def test_sysid_hook_runs_before_upstream_mavlink_start(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = root / "init.d-posix/px4-rc.mavlink"
            script.parent.mkdir()
            script.write_text('printf "links-started\\n"\n')
            result = subprocess.run(["sh", "-c", 'param() { printf "%s\\n" "$*"; }; . "$1"', "test", str(HERE / "px4-rc.mavlink")],
                                    env={**os.environ, "PX4_RUNTIME_ETC": str(root), "PX4_PARAM_MAV_SYS_ID": "7"}, capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.splitlines(), ["set MAV_SYS_ID 7", "links-started"])


class LifecycleTests(Fixture):
    def setup_fake_vehicle(self, exit_early=False, fail_upload=False):
        # Exercise the actual supervisor, process-local overlay and terminal hook;
        # only the upstream vehicle and MAVLink transport are fake.
        simulator = self.ap / "Tools/autotest/sim_vehicle.py"
        simulator.write_text('''import os, pathlib, subprocess, time
from pysim import vehicleinfo
assert "ArduCopter" in vehicleinfo.VehicleInfo().options
script = pathlib.Path(os.environ["TMPDIR"]) / "vehicle.sh"
script.write_text("#!/bin/sh\\n" + os.environ["FAKE_VEHICLE_COMMAND"] + "\\n")
subprocess.Popen([os.environ["SITL_RITW_TERMINAL"], str(script)])
while True: time.sleep(1)
''')
        package = self.root / "pymavlink"
        package.mkdir()
        (package / "__init__.py").write_text("")
        (package / "mavutil.py").write_text('''from types import SimpleNamespace
mavlink = SimpleNamespace(MAV_AUTOPILOT_INVALID=8)
class Heartbeat:
    autopilot = 3
    system_status = 3
    def get_srcSystem(self): return 1
    def get_srcComponent(self): return 1
class Connection:
    def wait_heartbeat(self, **kw): return Heartbeat()
    def close(self): pass
def mavlink_connection(*args, **kwargs): return Connection()
''')
        if fail_upload:
            (package / "mavutil.py").write_text('raise ImportError("injected transport failure")\n')
        env = {**os.environ, **self.env, "PYTHONPATH": str(self.root), "PLAN_UPLOAD_TIMEOUT": "3", "SITL_STOP_TIMEOUT": "0.3",
               "SITL_HEALTH_FILE": str(self.root / "health.json"),
               "FAKE_VEHICLE_COMMAND": "sleep 0.5; exit 7" if exit_early else "exec sleep 60"}
        process = subprocess.Popen([sys.executable, str(HERE / "run-sitl.py")], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.clean_process, process)
        return process

    def clean_process(self, process):
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()

    def test_dead_vehicle_fails_instead_of_sleeping_forever(self):
        process = self.setup_fake_vehicle(exit_early=True)
        stdout, stderr = process.communicate(timeout=6)
        self.assertEqual(process.returncode, 1, stdout + stderr)
        self.assertIn("vehicle process stopped", stderr)
        self.assertEqual(json.loads((self.root / "run/status.json").read_text())["state"], "failed")
        self.assertFalse(healthcheck(self.root / "run"))

    def test_ready_then_sigterm_stops_vehicle_and_clears_health(self):
        process = self.setup_fake_vehicle()
        deadline = time.monotonic() + 4
        while not healthcheck(self.root / "run") and time.monotonic() < deadline:
            if process.poll() is not None:
                break
            time.sleep(0.02)
        self.assertTrue(healthcheck(self.root / "run"))
        records = list((self.root / "run/children").glob("*.json"))
        child_pid = json.loads(records[0].read_text())["pid"]
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 143, stdout + stderr)
        self.assertFalse(healthcheck(self.root / "run"))
        with self.assertRaises(ProcessLookupError):
            os.kill(child_pid, 0)

    def test_failed_initializer_fails_run(self):
        process = self.setup_fake_vehicle(fail_upload=True)
        stdout, stderr = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 1, stdout + stderr)
        self.assertIn("initialization failed", stderr)
        self.assertFalse(healthcheck(self.root / "run"))


class Message:
    def __init__(self, kind, seq=0, system=1, component=1, mission_type=1, result=0, autopilot=3):
        self.kind, self.seq, self.system, self.component = kind, seq, system, component
        self.mission_type, self.type, self.autopilot = mission_type, result, autopilot
        self.target_system, self.target_component = 255, 190
        self.system_status = 3

    def get_type(self):
        return self.kind

    def get_srcSystem(self):
        return self.system

    def get_srcComponent(self):
        return self.component


CONSTANTS = SimpleNamespace(MAV_MISSION_TYPE_MISSION=0, MAV_MISSION_TYPE_FENCE=1,
                            MAV_MISSION_TYPE_RALLY=2, MAV_MISSION_ACCEPTED=0, MAV_AUTOPILOT_INVALID=8)


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.patch = patch.object(upload, "load_mavutil", return_value=SimpleNamespace(mavlink=CONSTANTS))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.sent, self.counts = [], []
        self.items = [upload.PlanItem(i, "MAV_MISSION_TYPE_FENCE", 5, 5001, (3., 0., 0., 0.), 37., -80., 0.) for i in range(2)]

    def master(self, messages):
        iterator = iter(messages)
        return SimpleNamespace(source_system=255, source_component=190,
                               mav=SimpleNamespace(mission_count_send=lambda *a: self.counts.append(a),
                                                   mission_item_int_encode=lambda *a: ("int", *a),
                                                   mission_item_encode=lambda *a: ("float", *a), send=self.sent.append),
                               recv_match=lambda **kw: next(iterator, None))

    def test_duplicate_and_last_item_requests_resent(self):
        msgs = [Message("MISSION_REQUEST_INT", i) for i in (0, 0, 1, 1)] + [Message("MISSION_ACK")]
        upload.upload_items(self.master(msgs), Message("HEARTBEAT"), "fence", self.items, 1)
        self.assertEqual([v[3] for v in self.sent], [0, 0, 1, 1])

    def test_wrong_source_type_and_destination_ignored(self):
        wrong = Message("MISSION_REQUEST_INT", system=42)
        wrong_target = Message("MISSION_REQUEST_INT")
        wrong_target.target_system = 7
        msgs = [wrong, wrong_target, Message("MISSION_REQUEST_INT", mission_type=2),
                Message("MISSION_REQUEST_INT", 0), Message("MISSION_REQUEST_INT", 1), Message("MISSION_ACK")]
        upload.upload_items(self.master(msgs), Message("HEARTBEAT"), "fence", self.items, 1)
        self.assertEqual(len(self.sent), 2)

    def test_legacy_request_uses_float_item(self):
        msgs = [Message("MISSION_REQUEST", 0), Message("MISSION_ACK")]
        upload.upload_items(self.master(msgs), Message("HEARTBEAT"), "fence", self.items[:1], 1)
        self.assertEqual(self.sent[0][0], "float")
        self.assertEqual(self.sent[0][4], 0)
        self.assertEqual(self.sent[0][13], -80.)

    def test_empty_plan_clears(self):
        upload.upload_items(self.master([Message("MISSION_ACK")]), Message("HEARTBEAT"), "fence", [], 1)
        self.assertEqual(self.counts[0][2], 0)

    def test_rejection_and_early_ack_fail(self):
        for msg in (Message("MISSION_ACK", result=1), Message("MISSION_ACK")):
            with self.assertRaises(upload.PlanError):
                upload.upload_items(self.master([msg]), Message("HEARTBEAT"), "fence", self.items, 1)

    def test_timeout_is_bounded(self):
        start = time.monotonic()
        with self.assertRaises(upload.PlanError):
            upload.upload_items(self.master([]), Message("HEARTBEAT"), "fence", self.items, 0.02)
        self.assertLess(time.monotonic() - start, 0.5)

    def test_connect_waits_for_initialized_autopilot(self):
        beats = []
        for status in (0, 1, 2, 3):
            beat = Message("HEARTBEAT")
            beat.system_status = status
            beats.append(beat)
        stream = iter(beats)
        conn = SimpleNamespace(wait_heartbeat=lambda **kw: next(stream), close=lambda: None)
        with patch.object(upload, "load_mavutil", return_value=SimpleNamespace(mavlink=CONSTANTS, mavlink_connection=lambda *a, **kw: conn)):
            _, heartbeat = upload.connect("mock", 1)
            self.assertEqual(heartbeat.system_status, 3)

    def test_connect_filters_heartbeat_and_closes_timeout(self):
        heartbeats = iter([None, Message("HEARTBEAT", system=9), Message("HEARTBEAT", autopilot=8), Message("HEARTBEAT")])
        closed = []
        conn = SimpleNamespace(wait_heartbeat=lambda **kw: next(heartbeats), close=lambda: closed.append(True))
        with patch.object(upload, "load_mavutil", return_value=SimpleNamespace(mavlink=CONSTANTS, mavlink_connection=lambda *a, **kw: conn)):
            result, heartbeat = upload.connect("mock", 1)
            self.assertIs(result, conn)
            self.assertEqual(heartbeat.system, 1)
            self.assertEqual(closed, [])
            conn.wait_heartbeat = lambda **kw: None
            with self.assertRaises(upload.PlanError):
                upload.connect("mock", 0.02)
            self.assertEqual(closed, [True])

    def test_count_and_last_item_retries(self):
        messages = iter([None, None, Message("MISSION_REQUEST_INT", 0), None, Message("MISSION_ACK")])
        clock = [0.0]
        master = self.master([])
        def receive(**kw):
            clock[0] += 1.1
            return next(messages)
        master.recv_match = receive
        with patch.object(upload.time, "monotonic", side_effect=lambda: clock[0]):
            upload.upload_items(master, Message("HEARTBEAT"), "fence", self.items[:1], 10)
        self.assertGreaterEqual(len(self.counts), 2)
        self.assertGreaterEqual(len(self.sent), 2)

    def test_checked_in_artifacts_parse(self):
        examples = HERE.parent / "configs/examples"
        self.assertEqual(len(upload.parse_mission_file(examples / "mission/missions/simple-copter.waypoints")), 5)
        self.assertEqual(len(upload.parse_fence_file(examples / "plan-artifacts/fences/simple-polygon.json")), 4)

    def test_invalid_numbers_versions_coordinates(self):
        for value in (float("nan"), float("inf"), True):
            with self.assertRaises(upload.PlanError):
                upload.number(value, "test")
        with self.assertRaises(upload.PlanError):
            upload.validate_items([upload.PlanItem(0, "MAV_MISSION_TYPE_FENCE", 5, 5001, (3., 0., 0., 0.), 100., 0., 0.)], "test")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "fence.json"
            path.write_text('{"version":2,"fences":[]}')
            with self.assertRaises(upload.PlanError):
                upload.parse_fence_file(path)
            path.write_text('{"fences":[{"type":"circle_inclusion","lat":0,"lon":0,"radius":-1}]}')
            with self.assertRaises(upload.PlanError):
                upload.parse_fence_file(path)


if __name__ == "__main__":
    unittest.main()
