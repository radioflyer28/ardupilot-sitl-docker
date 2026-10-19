"""Host-only PX4 simulator transport/math contract checks; no flight claims."""
import math
import json
import random
import sys
import struct
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import unittest

from px4_jsbsim_adapter import ActuatorClock, magnetic_body, rotor_geometry, send_sensors, finish_disconnect
from px4_jsbsim_runtime import resolve, parameters, PhysicsSession
from run_state import RunDirectory, atomic_json


def actuator(stamp=1000000, **changes):
    values = dict(time_usec=stamp, flags=1, controls=[.1, .2, .3, .4], mode=128,
                  get_type=lambda: "HIL_ACTUATOR_CONTROLS", get_srcSystem=lambda: 1,
                  get_srcComponent=lambda: 1)
    values.update(changes)
    return SimpleNamespace(**values)


class PX4PhysicsTests(unittest.TestCase):
    def test_px4_bytewise_parameter_readback(self):
        from px4_jsbsim_flight import parameter_value
        for value in (-1, 1, 400, 104):
            wire = struct.unpack("<f", struct.pack("<i", value))[0]
            self.assertEqual(parameter_value(SimpleNamespace(param_type=6, param_value=wire)), value)
        self.assertEqual(parameter_value(SimpleNamespace(param_type=9, param_value=.1651)), .1651)

    def test_lockstep_identity_range_and_arming(self):
        self.assertEqual(ActuatorClock(1).accept(actuator(), 1000000), [.1, .2, .3, .4])
        self.assertEqual(ActuatorClock(1).accept(actuator(mode=1), 1000000), [0]*4)
        for changes in ({"flags": 0}, {"controls": [float("nan")]*4}, {"controls": [1.1]*4},
                        {"controls": [-.1]*4}, {"controls": []}, {"get_srcSystem": lambda: 2},
                        {"get_srcComponent": lambda: 200}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                ActuatorClock(1).accept(actuator(**changes), 1000000)

    def test_exact_clock_and_duplicate_rejection(self):
        clock = ActuatorClock(1)
        self.assertIsNone(clock.accept(actuator(999999), 1000000))
        self.assertIsNotNone(clock.accept(actuator(), 1000000))
        self.assertIsNone(clock.accept(actuator(), 1002500))
        self.assertIsNotNone(clock.accept(actuator(1002500), 1002500))
        for stamp in (1000000, 1007500):
            with self.assertRaises(ValueError):
                clock.accept(actuator(stamp), 1005000)

    def test_magnetic_ned_to_body(self):
        self.assertEqual(magnetic_body([0, 0, 0], [1, 2, 3]), [1, 2, 3])
        for actual, expected in zip(magnetic_body([0, 0, math.pi/2], [1, 0, 1]), [0, -1, 1]):
            self.assertAlmostEqual(actual, expected)
        for actual, expected in zip(magnetic_body([math.pi/2, 0, 0], [1, 0, 1]), [1, 1, 0]):
            self.assertAlmostEqual(actual, expected)

    def test_rotor_geometry_units_order_and_sense(self):
        f = {f"inertia/cg-{axis}-in": 0 for axis in "xyz"}
        for i, (x, y) in enumerate(((-6.5, 6.5), (6.5, -6.5), (-6.5, -6.5), (6.5, 6.5))):
            for key, value in {"x-position": x, "y-position": y, "z-position": 1,
                               "propeller-sense": 1 if i < 2 else -1,
                               "pitch-angle-rad": math.pi/2, "yaw-angle-rad": 0}.items():
                f[f"propulsion/engine[{i}]/{key}"] = value
        rotors = rotor_geometry(f)
        self.assertAlmostEqual(rotors[0]["position"][0], .1651)
        self.assertEqual(rotors[2]["km"], -.05)
        f["propulsion/engine[0]/pitch-angle-rad"] = 0
        with self.assertRaises(ValueError):
            rotor_geometry(f)


class PX4ManagedPhysicsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.args = SimpleNamespace(root=str(self.root/"run"), state="fresh", timeout=2)
        self.env = {"DYNAMICS_BACKEND": "jsbsim", "PX4_SIM_MODEL": "jsbsim_quadrotor_x",
                    "JSBSIM_PYTHON": sys.executable}
        self.rotors = [{"position": [x, y, 0], "km": .05 if i < 2 else -.05}
                       for i, (x, y) in enumerate(((1, 1), (-1, -1), (1, -1), (-1, 1)))]

    def test_config_preflight_and_internal_default(self):
        self.assertIsNone(resolve(self.args, 1, {}))
        config = resolve(self.args, 17, self.env)
        self.assertEqual(config["sysid"], 17)
        self.assertEqual(config["host"], "127.0.0.1")
        self.assertEqual(config["status_file"], str(self.root/"run/work/physics/status.json"))
        self.assertFalse(Path(self.args.root).exists())
        for change in ({"DYNAMICS_BACKEND": "typo"}, {"INSTANCE": "1"}, {"SPEEDUP": "2"},
                       {"JSBSIM_HOST": "physics"}, {"JSBSIM_STATUS_FILE": "/x"}, {"JSBSIM_MODEL": "Missing"},
                       {"JSBSIM_MODEL": "../F450"}, {"JSBSIM_PYTHON": "/missing/python"},
                       {"PX4_SIMULATOR": "sihsim"}, {"PX4_SIM_HOST_ADDR": "127.0.0.1"},
                       {"PX4_SYS_AUTOSTART": "10040"}, {"PX4_SIM_MODEL": "sihsim_quadx"},
                       {"LAT": "nan"}, {"LAT": "80"}, {"ALT": "20000"}, {"JSBSIM_DEPLOYMENT": "typo"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                resolve(self.args, 1, {**self.env, **change})
        self.args.state = "resume"
        with self.assertRaises(ValueError):
            resolve(self.args, 1, self.env)

    def test_venv_and_external_configuration(self):
        python = self.root/"venv/bin/python"
        python.parent.mkdir(parents=True)
        python.symlink_to(sys.executable)
        self.assertEqual(resolve(self.args, 1, {**self.env, "JSBSIM_PYTHON": str(python)})["python"], str(python))
        env = {**self.env, "JSBSIM_DEPLOYMENT": "external", "JSBSIM_MODEL": "HeavyQuad"}
        self.assertEqual(resolve(self.args, 1, env)["model"], "HeavyQuad")
        for change in ({"JSBSIM_HOST": "x:4560"}, {"JSBSIM_MODEL_DIR": "/models"},
                       {"JSBSIM_STATUS_FILE": str(self.root/"run/status.json")}):
            with self.assertRaises(ValueError):
                resolve(self.args, 1, {**env, **change})

    def test_parameters_and_local_model_handoff(self):
        config = resolve(self.args, 17, self.env)
        with RunDirectory(Path(self.args.root), "fresh") as directory:
            children = []
            session = PhysicsSession(config, directory, children)
            status = {"state": "listening", "updated": time.time(), "instance_id": "unique",
                      "backend": "jsbsim", "protocol": "px4-mavlink", "model": "F450",
                      "sysid": 17, "location": config["location"], "rotors": self.rotors}
            path = Path(config["status_file"])
            path.parent.mkdir(parents=True)
            atomic_json(path, status)
            with patch("px4_jsbsim_runtime.subprocess.Popen", return_value=SimpleNamespace(poll=lambda: None)) as launch:
                env = session.prepare(lambda: False)
            self.assertEqual(len(children), 1)
            command = launch.call_args.args[0]
            self.assertEqual(command[command.index("--listen")+1], "127.0.0.1")
            self.assertEqual(env["PX4_SIM_HOST_ADDR"], "127.0.0.1")
            text = Path(env["PX4_JSBSIM_PARAMS"]).read_text()
            self.assertIn("param set IMU_INTEG_RATE 400", text)
            self.assertIn("param set MAV_SYS_ID 17", text)
            self.assertIn("param set PWM_MAIN_FUNC5 0", text)
            self.assertFalse(session.ready())
            ready = {**status, "state": "ready", "frames": 3, "simulation_time": .01}
            atomic_json(path, ready)
            self.assertTrue(session.ready())
            for change in ({"instance_id": "restarted"}, {"protocol": "ardupilot-json"},
                           {"sysid": 1}, {"state": "failed"}, {"model": "Wrong"}):
                atomic_json(path, {**ready, **change})
                with self.assertRaises(RuntimeError):
                    session.ready()
            atomic_json(path, {**ready, "updated": time.time()-4})
            self.assertFalse(session.ready())
        with self.assertRaises(ValueError):
            parameters([], 1)
        with self.assertRaises(ValueError):
            parameters([{**self.rotors[0], "km": float("nan")}, *self.rotors[1:]], 1)

    def test_disconnect_drops_ready_and_allows_ordered_stop(self):
        states, stop = [], [False]
        directory = SimpleNamespace(status=lambda state, **kw: states.append(state))
        with patch("px4_jsbsim_adapter.time.sleep", side_effect=lambda delay: stop.__setitem__(0, True)):
            finish_disconnect(directory, {}, lambda: stop[0], 5, "peer closed")
        self.assertEqual(states, ["disconnected", "stopped"])
        states.clear()
        with self.assertRaises(ConnectionError):
            finish_disconnect(directory, {}, lambda: False, 0, "peer lost")
        self.assertEqual(states, ["disconnected", "failed"])

    def test_sensor_noise_is_seeded_and_separate_from_truth(self):
        state = {"imu": {"accel_body": [0, 0, -9.8], "gyro": [0, 0, 0]}, "attitude": [0, 0, 0]}
        model = SimpleNamespace(fdm={"position/h-sl-ft": 2000, "position/lat-geod-deg": 37,
                                     "position/long-gc-deg": -80})
        before = json.dumps(state)
        runs = []
        for _ in range(2):
            samples = []
            out = SimpleNamespace(hil_sensor_send=lambda *args: samples.append(args))
            rng = random.Random(0)
            for i in (1, 2):  # no GPS/truth emission; this test needs no pymavlink package
                send_sensors(out, model, state, i*2500, i, [.2, -.03, .4], rng)
            runs.append(samples)
        self.assertEqual(runs[0], runs[1])
        self.assertNotEqual(runs[0][0][1:10], runs[0][1][1:10])
        self.assertEqual(before, json.dumps(state))


if __name__ == "__main__":
    unittest.main()
