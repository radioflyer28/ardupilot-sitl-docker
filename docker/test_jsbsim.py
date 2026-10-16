"""Standard-library protocol tests; real model tests are explicitly opt-in."""
import json
import time
import sys
from pathlib import Path

from test_runtime import Fixture, runner
from run_state import atomic_json, RunDirectory
import struct
import unittest

from jsbsim_adapter import Exchange, decode_packet, motor_inputs, validate_selection, stage_catalog, model_hashes


def packet(frame=0, channels=16, rate=400, pwm=1500):
    return struct.pack(f"<HHI{channels}H", 18458 if channels == 16 else 29569,
                       rate, frame, *([pwm] * channels))


class ProtocolTests(unittest.TestCase):
    def test_both_channel_counts(self):
        for channels in (16, 32):
            frame, outputs = decode_packet(packet(7, channels))
            self.assertEqual(frame, 7)
            self.assertEqual(len(outputs), channels)

    def test_malformed_inputs(self):
        for data in (b"", packet()[:-1], packet() + b"x", b"xx" + packet()[2:],
                     packet(rate=0), packet(rate=4001), packet(pwm=65535)):
            with self.subTest(data=data), self.assertRaises(ValueError):
                decode_packet(data)

    def test_bootstrap_rate_is_advisory(self):
        for rate in (1200, 1199, 800, 400):
            self.assertEqual(decode_packet(packet(rate=rate))[0], 0)

    def test_pwm_clamping_and_order(self):
        self.assertEqual(motor_inputs([0, 1000, 1500, 2000]), [0, 0, .5, 1])
        self.assertEqual(motor_inputs([900, 1100, 1900, 2100]), [0, .1, .9, 1])

    def test_duplicate_does_not_step_and_wire_framing(self):
        exchange = Exchange()
        steps = []
        def step(pwm):
            steps.append(pwm)
            return {"timestamp": len(steps) / 400}
        first, advanced = exchange.receive(packet(), ("localhost", 1), step)
        self.assertTrue(advanced)
        self.assertTrue(first.startswith(b"\n") and first.endswith(b"\n"))
        self.assertEqual(json.loads(first)["timestamp"], .0025)
        self.assertEqual(exchange.receive(packet(), ("localhost", 1), step), (first, False))
        self.assertEqual(len(steps), 1)
        exchange.receive(packet(1), ("localhost", 1), step)
        self.assertEqual(len(steps), 2)

    def test_restart_gap_and_second_peer_fail(self):
        for frame, peer in ((0, ("a", 1)), (3, ("a", 1)), (2, ("b", 1))):
            exchange = Exchange()
            exchange.receive(packet(1), ("a", 1), lambda pwm: {})
            with self.assertRaises(ValueError):
                exchange.receive(packet(frame), peer, lambda pwm: {})

    def test_counter_wrap_and_nonfinite_output(self):
        exchange = Exchange()
        exchange.receive(packet(0xffffffff), ("a", 1), lambda pwm: {})
        self.assertTrue(exchange.receive(packet(0), ("a", 1), lambda pwm: {})[1])
        with self.assertRaises(ValueError):
            exchange.receive(packet(1), ("a", 1), lambda pwm: {"timestamp": float("nan")})


class ManagedConfigTests(Fixture):
    def setUp(self):
        super().setUp()
        self.env["JSBSIM_DEPLOYMENT"] = "external"

    def test_local_supervised_command_and_owned_paths(self):
        config = self.resolve(DYNAMICS_BACKEND="jsbsim", JSBSIM_DEPLOYMENT="local", JSBSIM_PYTHON=sys.executable)
        self.assertEqual(config["model"], "JSON:127.0.0.1")
        self.assertEqual(config["physics"]["status_file"], str(self.root / "run/work/physics/status.json"))
        command = runner.local_physics_command(config)
        self.assertEqual(command[0], str(Path(sys.executable).absolute()))
        self.assertEqual(command[command.index("--listen") + 1], "127.0.0.1")
        self.assertEqual(command[command.index("--model") + 1], "F450")
        self.assertIsNone(runner.local_physics_command(self.resolve()))
        self.assertIsNone(runner.local_physics_command(self.resolve(DYNAMICS_BACKEND="jsbsim")))

    def test_local_fresh_archives_physics_with_vehicle(self):
        root = self.root / "run"
        with RunDirectory(root, "fresh") as vehicle:
            with RunDirectory(vehicle.work / "physics", "fresh") as physics:
                (physics.work / "truth.jsonl").write_text("saved physics\n")
            (vehicle.work / "eeprom.bin").write_text("saved vehicle")
        with RunDirectory(root, "fresh") as vehicle:
            self.assertFalse((vehicle.work / "physics").exists())
        archives = list((root / "history").iterdir())
        self.assertEqual(len(archives), 1)
        self.assertEqual((archives[0] / "physics/work/truth.jsonl").read_text(), "saved physics\n")
        self.assertEqual((archives[0] / "eeprom.bin").read_text(), "saved vehicle")

    def test_local_venv_executable_symlink_is_preserved(self):
        python = self.root / "venv/bin/python3"
        python.parent.mkdir(parents=True)
        python.symlink_to(sys.executable)
        config = self.resolve(DYNAMICS_BACKEND="jsbsim", JSBSIM_DEPLOYMENT="local", JSBSIM_PYTHON=str(python))
        self.assertEqual(runner.local_physics_command(config)[0], str(python))

    def test_local_preflight_rejects_conflicting_or_missing_inputs(self):
        for override in ({"JSBSIM_HOST": "physics"}, {"JSBSIM_STATUS_FILE": "/physics/status.json"},
                         {"JSBSIM_MODEL": "Missing"}, {"JSBSIM_MODEL_DIR": str(self.root / "run")},
                         {"JSBSIM_PYTHON": "/missing/python"}, {"JSBSIM_DEPLOYMENT": "typo"}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                self.resolve(**{ "DYNAMICS_BACKEND": "jsbsim", "JSBSIM_DEPLOYMENT": "local",
                                 "JSBSIM_PYTHON": sys.executable, **override})
        self.assertFalse((self.root / "run").exists())

    def test_backend_default_and_selection(self):
        self.assertIsNone(self.resolve()["physics"])
        config = self.resolve(DYNAMICS_BACKEND="jsbsim")
        self.assertEqual(config["model"], "JSON:physics")
        self.assertEqual(config["physics"]["model"], "F450")

    def test_named_aircraft_and_identity(self):
        path = self.root / "physics.json"
        config = self.resolve(DYNAMICS_BACKEND="jsbsim", JSBSIM_MODEL="HeavyQuad", JSBSIM_STATUS_FILE=str(path))
        self.assertEqual(config["physics"]["model"], "HeavyQuad")
        status = {"state": "ready", "updated": time.time(), "frames": 3, "backend": "jsbsim",
                  "model": "HeavyQuad", "location": config["location"], "simulation_time": 1}
        atomic_json(path, status)
        self.assertTrue(runner.physics_ready(config, time.time() - 1))
        atomic_json(path, {**status, "model": "F450"})
        with self.assertRaises(RuntimeError):
            runner.physics_ready(config, time.time() - 1)
        for name in ("../F450", "/F450", "bad/name", "bad name"):
            with self.assertRaises(ValueError):
                self.resolve(DYNAMICS_BACKEND="jsbsim", JSBSIM_MODEL=name)

    def test_catalog_selection_preserves_inputs(self):
        catalog = self.root / "catalog"
        (catalog / "engine").mkdir(parents=True)
        (catalog / "engine/motor.xml").write_text("<engine/>")
        for name, mass in (("LightQuad", 1.4), ("HeavyQuad", 1.8)):
            aircraft = catalog / "aircraft" / name
            aircraft.mkdir(parents=True)
            (aircraft / f"{name}.xml").write_text('<fdm_config>' + ''.join(
                f'<input>adapter/motor-{i}</input>' for i in range(4)) + '</fdm_config>')
            (aircraft / "Mass.xml").write_text(f'<mass>{mass}</mass>')
        before = model_hashes(catalog)
        for name in ("LightQuad", "HeavyQuad"):
            staged = self.root / name
            hashes = stage_catalog(staged, catalog, name)
            self.assertEqual((staged / f"aircraft/{name}/Mass.xml").read_bytes(),
                             (catalog / f"aircraft/{name}/Mass.xml").read_bytes())
            self.assertEqual(list((staged / "aircraft").iterdir()), [staged / "aircraft" / name])
            self.assertIn("engine/motor.xml", hashes)
        self.assertEqual(model_hashes(catalog), before)
        with self.assertRaises(ValueError):
            validate_selection(catalog, "Missing")
        with self.assertRaises(ValueError):
            validate_selection(None, "HeavyQuad")
        (catalog / "aircraft/HeavyQuad/HeavyQuad.xml").write_text('<fdm_config/>')
        with self.assertRaises(ValueError):
            stage_catalog(self.root / "invalid", catalog, "HeavyQuad")

    def test_unsupported_combinations(self):
        for values in ({"SITL_STATE": "resume"}, {"SPEEDUP": "2"}, {"MODEL": "quad"},
                       {"INSTANCE": "1"}, {"FRAME": "hexa"}, {"JSBSIM_HOST": "bad:9002"},
                       {"JSBSIM_STATUS_FILE": str(self.root / "run/status.json")}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.resolve(DYNAMICS_BACKEND="jsbsim", **values)
        with self.assertRaises(ValueError):
            self.resolve(DYNAMICS_BACKEND="typo")
        (self.cfg / "scripts").mkdir()
        with self.assertRaises(ValueError):
            self.resolve(DYNAMICS_BACKEND="jsbsim")

    def test_physics_readiness_staleness_identity_and_failure(self):
        path = self.root / "physics-status.json"
        config = self.resolve(DYNAMICS_BACKEND="jsbsim", JSBSIM_STATUS_FILE=str(path))
        start = time.time() - 1
        self.assertFalse(runner.physics_ready(config, start))
        status = {"state": "ready", "updated": time.time(), "frames": 5,
                  "backend": "jsbsim", "model": "F450", "simulation_time": .01,
                  "location": config["location"]}
        atomic_json(path, status)
        self.assertTrue(runner.physics_ready(config, start))
        for changes in ({"updated": start - 1}, {"frames": 1}, {"simulation_time": 0}):
            atomic_json(path, {**status, **changes})
            self.assertFalse(runner.physics_ready(config, start))
        for changes in ({"state": "failed"}, {"model": "wrong"}, {"location": [0, 0, 0, 0]}):
            atomic_json(path, {**status, **changes})
            with self.assertRaises(RuntimeError):
                runner.physics_ready(config, start)


if __name__ == "__main__":
    unittest.main()
