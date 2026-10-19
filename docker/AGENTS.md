# Docker Helper DOX

## Purpose

Owns runtime configuration, lifecycle, state and artifact helper code copied into
the images, plus host-only regression and opt-in Docker qualification tests.

## Ownership

- `ardupilot-entrypoint.sh`, `run-sitl.sh`: command/debug dispatch and Python
  environment activation.
- `sitl_config.py`, `resolve-sitl-config.py`: side-effect-free configuration,
  effective-config output and managed CLI contracts.
- `run-sitl.py`: ArduPilot staging, supervision, initialization and readiness.
- `launch-sitl.py`: process-local upstream VehicleInfo overlay.
- `sitl-terminal.py`: upstream terminal hook, vehicle output and exit monitoring.
- `run_state.py`: exclusive owned state directories, atomic status, fresh/resume,
  Linux subreaping and bounded process-group shutdown; PX4 initialization and supervision.
- `upload-plan-artifacts.py`: full mission/fence/rally parsing and MAVLink upload.
- `px4-sih-entrypoint.sh`, `run-px4-sih.sh`: native PX4 env mapping and launch.
- `px4-rc.mavlink`: PATH-sourced hook applying explicit SYSID before native links
  and adding a private initialization link; no upstream mutation.
- `test_runtime.py`, `test_px4_relay.py`, `test_jsbsim.py`: host-only standard-library regression tests.
- `jsbsim_adapter.py`: project-owned JSON physics adapter for pinned JSBSim quad-X;
  packaged F450 is default. `JSBSIM_MODEL` selects a name from a read-only native
  aircraft/engine catalog (`JSBSIM_MODEL_DIR`); copy only the chosen aircraft and
  shared engines/systems into owned temporary storage, preserving custom XML.
  Export a starter catalog with `--export-models`; never overwrite an existing
  destination. Custom models must consume adapter/motor-0..3 in FR/AL/FL/AR order
  and contain four engines. Selection support is not flight qualification.
  Keep direct motor control separate from the bundled pilot controller/sensors.
  Copies model assets only into its owned temporary run tree; installed/upstream
  files stay unchanged. `qualify-jsbsim-model.py` checks real model force/sensor
  behavior separately from protocol tests. `qualify-jsbsim.py` owns opt-in installed
  helper/readiness/flight/physics-failure checks and isolated Compose cleanup.
- Managed JSBSim runs require fresh ArduCopter quad/instance 0 at speed 1.
  Local mode is the default: the autopilot supervisor owns a loopback adapter
  process using JSBSIM_PYTHON, with physics state under work/physics so fresh runs
  archive both sides together. Both processes share bounded shutdown; adapter exit
  fails readiness immediately. External mode retains a separate status mount and
  independently packaged simulator; only that mode accepts host/status overrides.
  The combined image isolates JSBSim dependencies in /opt/jsbsim-venv; base
  autopilot/internal physics does not require those dependencies.
  The final generated parameter layer fixes
  quad-X motor functions, PWM range, 800 Hz physics exchange and the normal EKF.
  Readiness includes fresh matching physics progress; stale/failed physics stops
  the autopilot. The adapter times out after loss of actuator progress.
  Backend/model switches require restarting both sides; resume/Lua pose injection
  are unsupported. Internal dynamics remain unchanged.
- `px4_jsbsim_adapter.py`: experimental PX4 simulator-MAVLink transport over the
  shared QuadX/catalog implementation in `jsbsim_adapter.py`. Keep sensor noise
  separate from truth. Match the 400 Hz sensor clock to PX4 IMU integration;
  require exact lockstep replies after sensor-first bootstrap. Validate actuator
  identity/range, geometry, and transport loss; resume/reconnection is unsupported.
  TCP loss invalidates physics readiness immediately. Allow at most the link
  timeout for Compose's subsequent stop signal; otherwise fail the physics run.
  `px4_jsbsim_runtime.py` prepares model-derived rotor/motor/clock parameters,
  verifies fresh matching physics identity, and integrates local/external physics
  into `run_state.py`. Local physics lives under work/physics and shares bounded
  shutdown. External physics is a single peer with a read-only status mount.
  `px4-rc.simulator` applies the generated contract before native simulator startup,
  without modifying PX4 files. The dedicated image defaults to JSBSim; selecting
  internal dynamics retains native SIH. Flight qualification remains separate.
  `test_px4_jsbsim.py` owns host-only protocol/geometry/configuration checks.
  `qualify-jsbsim.py --family px4` selects PX4 installed-image/lifecycle checks;
  `px4_jsbsim_flight.py` uses normal EKF/arming and PX4 takeoff, reposition/yaw,
  and landing commands. Collect exact images and noise-free truth separately.
- `px4-gcs-relay.py`: optional supervised UDP bridge preserving a fixed PX4 peer
  while supporting host-client reconnection and multiple heartbeat-active clients.
- `qualify-runtime.py`, `qualification-ready.lua`: opt-in mounted-helper or
  installed-image live firmware qualification and Lua execution witness.
- `qualify-compose.py`, `compose.qualification.yml`: isolated-project Compose
  health, real host-client and named-volume recreation qualification. Generated
  evidence goes in ignored artifacts/, not git.

## Local Contracts

- Never mutate upstream ArduPilot source or its installed vehicle metadata.
  Keep upstream compatibility in explicit adapters; do not silently bypass
  unsupported managed options.
- Emit integer SPEEDUP arguments for the upstream sim_vehicle release parser;
  reject fractional multipliers during preflight rather than at firmware launch.
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
- Wait for a target heartbeat beyond UNINIT/BOOT/CALIBRATING before uploads;
  early ArduPilot heartbeats can precede mission storage initialization.
- ArduPilot readiness means initialized expected heartbeat, selected plans acknowledged and
  live vehicle/launcher processes. Do not promise arming, EKF or Lua readiness.
- Monitor actual vehicle exit, not only sim_vehicle. Invalidate readiness on
  failure/stop and terminate/reap all owned process groups with bounded waits.
- Start managed MAVProxy non-interactively so closed container stdin cannot
  terminate the runtime before readiness.
- PLAN_UPLOAD_MASTER changes the endpoint, not the expected vehicle identity.
  Direct TCP is a startup single-client handoff; private MAVProxy initialization
  ports are 20000 + INSTANCE, separate from SITL serial ports.
- PX4 keeps native MODEL, INSTANCE, home, speedup and optional SYSID mappings.
  Its private UDP link targets loopback, using local 30000 + INSTANCE and peer 31000 + INSTANCE;
  native GCS/offboard links remain separate. PX4's listener still binds all
  interfaces; this is accepted for the intended office/LAN deployment, not a
  firewall prerequisite. Keep bridge initialization ports unpublished by default.
  The optional GCS relay uses native peer 14550 and container listener 18670 + INSTANCE;
  Compose publishes it on host localhost:18570 by default. Relay failure fails the
  managed run; its sockets must be bound before readiness. Keep host-network mode
  available without the relay. Preflight selected plans before claiming state. Require an initialized PX4 heartbeat from expected SYSID/component
  and accepted selected plans before ready; initialization failure or binary exit
  fails the run. Health checks are side-effect-free supervisor freshness checks,
  not continuous telemetry, GPS, arming or flight-feasibility checks.

## Work Guidance

- Prefer explicit Python parsing and argument arrays over shell interpolation.
- Keep failures concise, nonzero and observable in status metadata.
- Do not claim host-only/mocked tests qualify real firmware or image behavior.
- Add regression coverage for lifecycle/config/protocol behavior changes.

## Verification

- `python3 -m unittest discover -s docker -p 'test_*.py'`
- `python3 -m py_compile docker/*.py`
- `for script in docker/*.sh; do bash -n "$script"; done` and
  `for script in docker/px4-rc.*; do sh -n "$script"; done`
- `python3 docker/upload-plan-artifacts.py --dry-run --config-dir configs/examples/mission --mission missions/simple-copter.waypoints`
- `python3 docker/upload-plan-artifacts.py --dry-run --config-dir configs/examples/plan-artifacts --fence fences/simple-polygon.json --rally rally/recovery-points.json`
- Live pinned-release SITL/direct/MAVProxy checks are additional qualification,
  not replaced by the fake-process/transport suite. Run `qualify-runtime.py`
  explicitly (not unittest discovery); see `docs/RUNTIME_QUALIFICATION.md` for
  prerequisites, commands and tested versions. Mounted-helper qualification is
  distinct from `--installed` image-entrypoint/health qualification. Compose
  qualification requires a host pymavlink Python and free published test ports;
  clean up only the test project's containers/volumes. Cleanup failure must fail
  qualification and be retained in its report. Verify plan payload values, not
  only counts, when reading plans back from firmware.

## Child DOX Index

No child DOX files.
