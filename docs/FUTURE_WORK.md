# Future Work

This file tracks likely improvements. Keep design rationale in
`docs/DESIGN.md`; keep this file action-oriented.


## Runtime Config

- Add validation in `run-sitl.sh` or `resolve-sitl-config.py` that checks model
  and param files before launch and prints concise errors.
- Add a short-name config selector such as `VEHICLE_CONFIG=arducopter-quad`
  that resolves to a bundle under a known config root.
- Generate env files or Compose overrides from config bundles.
- Consider supporting multiple parameter files explicitly if a clear user
  workflow appears. Keep the default direct path singular.
- Add first-class initial-state config support on top of the copyable Lua
  example. The current recommendation is generated or externally mounted config
  consumed by a Lua script that calls `sim:set_pose` on arm; see
  `docs/INITIAL_STATE.md`.
- Add optional mission-start controls such as `MISSION_START_INDEX` or
  `MISSION_MODE=auto`, if users need the wrapper to do more than preload the
  mission.
- Add import support for common ground-station fence/rally export formats after
  the project-owned JSON examples have had real use.
- Add a JSON Schema for a per-vehicle SITL manifest. The manifest should
  reference native artifacts such as params, model JSON, `vehicleinfo.json`,
  mission, fence, rally, and Lua script files rather than embedding or
  replacing those formats by default.
- In that schema, support either file references or inline definitions for
  mission, fence, and rally artifacts, but enforce mutual exclusion with
  `oneOf`-style validation. Reject ambiguous objects such as `mission.file`
  plus `mission.items`, `fence.file` plus `fence.fences`, or `rally.file` plus
  `rally.points`.
- Preserve params as the explicit layering exception: support ordered param
  `files` plus a final inline `set` map for overrides.
- Add checked-in manifest examples for a simple Copter bundle, an initial-state
  bundle, and mission/fence/rally bundles that demonstrate both file-backed and
  inline artifact forms.
- Add a validator/generator that reads a per-vehicle manifest and emits the
  current low-level runtime interface: env vars, `sim_vehicle.py` args, mounts,
  artifact paths, and any temporary generated params, plan artifacts, or Lua
  config.
- Consider a future `SCENARIO_FILE` or `SITL_MANIFEST` env var that points to a
  per-vehicle manifest, with direct env vars retained as explicit overrides.
- Add a fleet/scenario manifest format that can generate Compose services. Env
  vars should remain the low-level interface for one-off SITLs, while fleet
  config manages repeated per-vehicle settings and artifact paths.
- Extend the fleet/scenario manifest generator to target both ArduPilot SITL
  and PX4 SIH. The generator should emit native env vars and launch surfaces
  for each runtime rather than forcing a single autopilot's terminology across
  both.
- Add a first-class artifact output convention for generated Compose services,
  including per-vehicle `.BIN` log directories, MAVProxy `.tlog` directories
  when MAVProxy is enabled, stdout/stderr capture, and metadata that records the
  image tag, ArduPilot ref, config bundle, and env used for each run.


## ArduPilot Integration

- Evaluate an opt-in `sim_vehicle.py` patch or upstreamable option that allows
  runtime `vehicleinfo.json` entries to provide `default_params_filename`
  directly without wrapper-side resolution.
- Revisit whether copying mounted `vehicleinfo.json` into the ArduPilot tree is
  the best long-term mechanism, or whether an environment variable / CLI option
  can select an alternate file.


## Build And Release

- Add CI validation for Dockerfile syntax, shell scripts, JSON bundles, and the
  config-bundle generator.
- Add a smoke test that starts a tiny SITL run with `NO_MAVPROXY=1` and verifies
  the expected TCP port opens.
- Consider publishing prebuilt images in addition to zstd Docker archives.
- Document or automate multi-version batch builds.


## PX4 SIH

- Validate `Dockerfile.px4-sih` against pinned PX4 release tags, starting with
  the current stable PX4 release.
- Track when PX4 release tags adopt `px4_sitl_sih` so the script can infer the
  narrower target for more than `main`/`master`.
- Tighten `PX4_SUBMODULE_PATHS` after real build results identify the minimum
  submodule set required for `px4_sitl_sih`.
- Consider factoring shared image output/cache/archive helpers out of the
  ArduPilot and PX4 build scripts if their behavior continues to converge.
- Validate bridge-networked Docker operation for PX4 SIH and document the
  required PX4 network env vars or parameters. Host networking remains the v1
  recommendation.
- Add PX4-native examples for `PX4_PARAM_*` physics overrides, including SIH
  wind and mass/inertia-related params.
- Add MAVLink mission, fence, and rally upload support for PX4 through the
  future shared artifact uploader instead of ArduPilot Lua.


## Runtime And Networking

- Add Compose examples for mounted config bundles.
- Add derived-image examples that use an `ardupilot-sitl:*` image as a base and
  layer companion software on top, such as ROS 2, MAVROS, and custom control
  logic. Include an entrypoint pattern that starts `run-sitl.sh` alongside the
  companion node and handles shutdown cleanly.
- Add a Compose file builder that takes a fleet definition and generates a
  multi-SITL Compose file. It should let users define the number of vehicles and
  per-vehicle settings such as starting latitude/longitude, altitude, heading,
  frame type, vehicle type, system ID, instance number, mounted config bundle,
  exposed ports, image tag, params, mission, initial-state Lua, geofence, and
  rally plans. It should emit the low-level env vars and mounts rather than
  replacing them.
- Add Compose profiles for Copter, Plane, Rover, and Sub.
- Document direct TCP vs MAVProxy fan-out with a small diagram or table.


## Repository Hygiene

- Keep generated catalogs out of git by default.
- Periodically refresh checked-in example bundles from the pinned ArduPilot
  checkout.
- Consider splitting long README sections into task-focused docs if the README
  starts to feel crowded again.
