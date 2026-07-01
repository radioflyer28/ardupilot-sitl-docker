# Docker Helper DOX


## Purpose

Owns helper code copied into the runtime image.


## Ownership

- `resolve-sitl-config.py`: resolves runtime SITL config environment into
  `sim_vehicle.py` arguments.
- `install-sitl-lua.sh`: installs runtime Lua scripts into the ArduPilot
  working `scripts/` directory before SITL starts, and stages mission files
  when `MISSION_FILE` is set.
- `upload-plan-artifacts.py`: uploads runtime fence and rally JSON artifacts
  through MAVLink mission protocol after SITL starts.
- `load-mission.lua`: image-provided ArduPilot Lua loader for staged QGC WPL
  110 mission files.
- `px4-sih-entrypoint.sh`: PX4 SIH entrypoint that runs the PX4 wrapper by
  default and executes explicit commands for debug shells.
- `run-px4-sih.sh`: starts the prebuilt PX4 SIH binary with this repo's shared
  low-level env conventions where PX4 has native equivalents.


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
- Preserve runtime mission behavior:
  - resolve relative `MISSION_FILE` paths under `$SITL_CONFIG_DIR`
  - fail fast when `MISSION_FILE` is missing or is not a QGC WPL 110 file
  - stage selected missions into the ArduPilot working `missions/` directory
  - install the image-provided `load-mission.lua` script when `MISSION_FILE` is
    set
- Preserve runtime fence/rally behavior:
  - resolve relative `FENCE_FILE` and `RALLY_FILE` paths under
    `$SITL_CONFIG_DIR`
  - keep fence and rally as separate MAVLink mission protocol plan types
  - use project-owned JSON as the checked-in example format
  - support dry-run parsing without requiring `pymavlink` on the host
  - connect through `PLAN_UPLOAD_MASTER` when set
- Preserve PX4 SIH runtime behavior:
  - `MODEL` selects `PX4_SIM_MODEL`
  - `INSTANCE` maps to `px4 -i`
  - `LAT`, `LON`, `ALT`, and `SPEEDUP` map to PX4's native env vars
  - `SYSID` maps to `PX4_PARAM_MAV_SYS_ID` only when explicitly set
  - `PX4_RUN_DIR` or `ARTIFACTS_DIR` chooses the PX4 working directory


## Work Guidance

- Prefer explicit, readable parsing over clever shell-heavy behavior.
- Emit one argument per output line so `run-sitl.sh` can consume output with
  `mapfile`.
- Keep errors concise and actionable.
- Keep image-provided Lua helpers deterministic and tied to staged runtime
  paths; user-selected paths should be resolved in shell before SITL starts.


## Verification

- Run:
  `python3 -m py_compile docker/resolve-sitl-config.py`
- Run:
  `python3 -m py_compile docker/upload-plan-artifacts.py`
- Run:
  `python3 docker/upload-plan-artifacts.py --dry-run --config-dir configs/examples/plan-artifacts --fence fences/simple-polygon.json --rally rally/recovery-points.json`
- Run:
  `bash -n docker/install-sitl-lua.sh`
- Run a Lua syntax check for `docker/load-mission.lua` when `lua` or `luac` is
  available.
- Run:
  `bash -n docker/px4-sih-entrypoint.sh docker/run-px4-sih.sh`
- Smoke-test against a temporary ArduPilot-like directory when changing
  resolution or Lua install behavior.


## Child DOX Index

No child DOX files.
