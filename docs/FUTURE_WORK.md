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
  exposed ports, and image tag.
- Add Compose profiles for Copter, Plane, Rover, and Sub.
- Document direct TCP vs MAVProxy fan-out with a small diagram or table.


## Repository Hygiene

- Keep generated catalogs out of git by default.
- Periodically refresh checked-in example bundles from the pinned ArduPilot
  checkout.
- Consider splitting long README sections into task-focused docs if the README
  starts to feel crowded again.
