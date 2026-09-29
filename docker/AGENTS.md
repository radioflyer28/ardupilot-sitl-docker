# Docker Helper DOX

## Purpose

Owns runtime configuration, lifecycle, state and artifact helper code copied into
the images, plus host-only regression tests.

## Ownership

- `ardupilot-entrypoint.sh`, `run-sitl.sh`: command/debug dispatch and Python
  environment activation.
- `sitl_config.py`, `resolve-sitl-config.py`: side-effect-free configuration,
  effective-config output and managed CLI contracts.
- `run-sitl.py`: ArduPilot staging, supervision, initialization and readiness.
- `launch-sitl.py`: process-local upstream VehicleInfo overlay.
- `sitl-terminal.py`: upstream terminal hook, vehicle output and exit monitoring.
- `run_state.py`: exclusive owned state directories, atomic status, fresh/resume,
  Linux subreaping and bounded process-group shutdown; PX4 process wrapper.
- `upload-plan-artifacts.py`: full mission/fence/rally parsing and MAVLink upload.
- `px4-sih-entrypoint.sh`, `run-px4-sih.sh`: native PX4 env mapping and launch.
- `test_runtime.py`: host-only standard-library unit and fake-process tests.

## Local Contracts

- Never mutate upstream ArduPilot source or its installed vehicle metadata.
  Keep upstream compatibility in explicit adapters; do not silently bypass
  unsupported managed options.
- Resolve CLI scalar overrides before deriving paths or ports. Validate the
  binary, selected files and full plan syntax before any staging/launch.
- Preserve native inputs: MODEL, mounted vehicleinfo, parameter files and Lua.
  Relative bundle metadata paths resolve against its JSON directory; direct
  artifact references resolve against SITL_CONFIG_DIR.
- Parameter order: native defaults, bundle files, PARAM_FILES JSON array,
  PARAM_FILE, repeated CLI --add-param-file. Later values win.
- Use one owned work directory per vehicle. Reject unowned nonempty roots and
  concurrent reuse. Fresh archives previous work; resume retains vehicle state.
  Replace scripts on every run; explicit LUA_SCRIPT wins by basename.
- Mission/fence/rally use separate MAVLink plan types, not a Lua preload helper.
  Empty selected plans clear; omitted plans do not. Validate before connecting,
  verify target SYSID/component, honor retries and require accepted ACKs within
  one bounded initialization deadline.
- Keep dry-run parsing independent of pymavlink on the host.
- ArduPilot readiness means expected heartbeat, selected plans acknowledged and
  live vehicle/launcher processes. Do not promise arming, EKF or Lua readiness.
- Monitor actual vehicle exit, not only sim_vehicle. Invalidate readiness on
  failure/stop and terminate/reap all owned process groups with bounded waits.
- PLAN_UPLOAD_MASTER changes the endpoint, not the expected vehicle identity.
  Direct TCP is a startup single-client handoff; private MAVProxy initialization
  ports are 20000 + INSTANCE, separate from SITL serial ports.
- PX4 keeps native MODEL, INSTANCE, home, speedup and optional SYSID mappings.
  Share fresh/resume state and process shutdown, but report running rather than
  MAVLink-ready until native PX4 initialization is implemented.

## Work Guidance

- Prefer explicit Python parsing and argument arrays over shell interpolation.
- Keep failures concise, nonzero and observable in status metadata.
- Do not claim host-only/mocked tests qualify real firmware or image behavior.
- Add regression coverage for lifecycle/config/protocol behavior changes.

## Verification

- `python3 -m unittest discover -s docker -p 'test_*.py'`
- `python3 -m py_compile docker/*.py`
- `bash -n docker/*.sh`
- `python3 docker/upload-plan-artifacts.py --dry-run --config-dir configs/examples/mission --mission missions/simple-copter.waypoints`
- `python3 docker/upload-plan-artifacts.py --dry-run --config-dir configs/examples/plan-artifacts --fence fences/simple-polygon.json --rally rally/recovery-points.json`
- Live pinned-release SITL/direct/MAVProxy checks are additional qualification,
  not replaced by the fake-process/transport suite.

## Child DOX Index

No child DOX files.
