# Docker Helper DOX


## Purpose

Owns helper code copied into the runtime image.


## Ownership

- `resolve-sitl-config.py`: resolves runtime SITL config environment into
  `sim_vehicle.py` arguments.
- `install-sitl-lua.sh`: installs runtime Lua scripts into the ArduPilot
  working `scripts/` directory before SITL starts.


## Local Contracts

- Keep helpers compatible with the runtime image's standard Python and Bash.
- Avoid patching upstream ArduPilot when wrapper-side resolution is sufficient.
- Preserve the direct override path:
  - `MODEL` emits `--model`
  - `PARAM_FILE` emits `--add-param-file`
- Preserve mounted bundle behavior:
  - use `$VEHICLEINFO_JSON` when set
  - otherwise use `$SITL_CONFIG_DIR/vehicleinfo.json` when present
  - resolve relative paths against the mounted `vehicleinfo.json` directory
- Preserve runtime Lua behavior:
  - copy `$SITL_CONFIG_DIR/scripts/` into the ArduPilot working `scripts/`
    directory when present
  - resolve relative `LUA_SCRIPT` paths under `$SITL_CONFIG_DIR`
  - copy `LUA_SCRIPT` after bundle scripts so explicit files can override by
    basename


## Work Guidance

- Prefer explicit, readable parsing over clever shell-heavy behavior.
- Emit one argument per output line so `run-sitl.sh` can consume output with
  `mapfile`.
- Keep errors concise and actionable.


## Verification

- Run:
  `python3 -m py_compile docker/resolve-sitl-config.py`
- Run:
  `bash -n docker/install-sitl-lua.sh`
- Smoke-test against a temporary ArduPilot-like directory when changing
  resolution or Lua install behavior.


## Child DOX Index

No child DOX files.
