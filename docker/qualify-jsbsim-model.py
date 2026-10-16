#!/usr/bin/env python3
"""Opt-in real JSBSim model checks (not autopilot flight qualification)."""
import json
import math
from pathlib import Path
import tempfile

from jsbsim_adapter import QuadX, FT, EXCHANGE_HZ


def main():
    results = {}
    location = [37.1971467, -80.5780381, 618, 0]
    with tempfile.TemporaryDirectory() as tmp:
        m = QuadX(Path(tmp) / "rest", location)
        state = m.state()
        assert abs(state["imu"]["accel_body"][2] + 9.8) < .1, state
        assert max(abs(v) for v in state["velocity"]) < .01, state
        results["ground"] = state
        # Airborne zero-motor free fall should approach zero specific force.
        f = m.fdm
        f["ic/h-sl-ft"] = (location[2] + 100) / FT
        f["ic/theta-deg"] = 20
        f["ic/phi-deg"] = 10
        assert f.run_ic()
        for _ in range(4):
            m.step([1000] * 4)
        state = m.state()
        assert max(abs(v) for v in state["imu"]["accel_body"]) < .1, state
        assert state["velocity"][2] > 0, state
        assert abs(state["attitude"][0] - math.radians(10)) < .01, state
        assert abs(state["attitude"][1] - math.radians(20)) < .01, state
        results["tilted_freefall"] = state
        signs = [(-1, 1, 1), (1, -1, 1), (1, 1, -1), (-1, -1, -1)]
        for rotor, expected in enumerate(signs):
            m = QuadX(Path(tmp) / f"motor-{rotor}", location)
            pwm = [1000] * 4
            pwm[rotor] = 1600
            for _ in range(EXCHANGE_HZ // 10):
                m.step(pwm)
            moments = [m.fdm[f"moments/{axis}-prop-lbsft"] for axis in "lmn"]
            assert all(v * sign > .05 for v, sign in zip(moments, expected)), moments
            results[f"motor-{rotor + 1}"] = moments
        m = QuadX(Path(tmp) / "collective", location)
        for _ in range(EXCHANGE_HZ):
            state = m.step([1600] * 4)
        assert state["velocity"][2] < -1 and state["position"][2] < -1, state
        results["collective"] = state
    print(json.dumps({"passed": True, "checks": results}, indent=2))


if __name__ == "__main__":
    main()
