#!/usr/bin/env python3
"""Run upstream sim_vehicle with a process-local vehicleinfo overlay.

Works with both Python-backed and JSON-backed VehicleInfo implementations;
never overwrites the installed ArduPilot source or bundled default metadata.
"""
import json
from pathlib import Path
import runpy
import sys

from sitl_config import merge_vehicleinfo


def main():
    config = json.loads(Path(sys.argv[1]).read_text())
    autotest = Path(config["root"]) / "Tools/autotest"
    sys.path.insert(0, str(autotest))
    from pysim import vehicleinfo

    original = vehicleinfo.VehicleInfo

    class RuntimeVehicleInfo(original):
        def __init__(self):
            super().__init__()
            self.options = merge_vehicleinfo(self.options, config["vehicleinfo_overrides"])

    vehicleinfo.VehicleInfo = RuntimeVehicleInfo
    script = str(autotest / "sim_vehicle.py")
    sys.argv = [script, *sys.argv[2:]]
    runpy.run_path(script, run_name="__main__")


if __name__ == "__main__":
    main()
