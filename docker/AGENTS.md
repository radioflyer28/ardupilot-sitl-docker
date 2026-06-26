# Docker Helper DOX


## Purpose

Owns helper code copied into the runtime image.


## Ownership

- `resolve-sitl-config.py`: resolves runtime SITL config environment into
  `sim_vehicle.py` arguments.


## Local Contracts

- Keep helpers compatible with the runtime image's standard Python.
- Avoid patching upstream ArduPilot when wrapper-side resolution is sufficient.
- Preserve the direct override path:
  - `MODEL` emits `--model`
  - `PARAM_FILE` emits `--add-param-file`
- Preserve mounted bundle behavior:
  - use `$VEHICLEINFO_JSON` when set
  - otherwise use `$SITL_CONFIG_DIR/vehicleinfo.json` when present
  - resolve relative paths against the mounted `vehicleinfo.json` directory


## Work Guidance

- Prefer explicit, readable parsing over clever shell-heavy behavior.
- Emit one argument per output line so `run-sitl.sh` can consume output with
  `mapfile`.
- Keep errors concise and actionable.


## Verification

- Run:
  `python3 -m py_compile docker/resolve-sitl-config.py`
- Smoke-test against a temporary ArduPilot-like directory when changing
  resolution logic.


## Child DOX Index

No child DOX files.
