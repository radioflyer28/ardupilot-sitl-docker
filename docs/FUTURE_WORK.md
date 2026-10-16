# Future Work

This file tracks likely improvements. Keep design rationale in
`docs/DESIGN.md`; keep this file action-oriented.


## Runtime Config

- Add a short-name config selector such as `VEHICLE_CONFIG=arducopter-quad`
  that resolves to a bundle under a known config root.
- Generate env files or Compose overrides from config bundles.
- Add first-class initial-state config support on top of the copyable Lua
  example. The current recommendation is generated or externally mounted config
  consumed by a Lua script that calls `sim:set_pose` on arm for built-in dynamics;
  see `docs/INITIAL_STATE.md`. External FDM initialization/trim needs its own
  adapter contract, as described in `docs/RUNTIME_PROFILES.md`.
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
- Extend effective run metadata with image digest, autopilot ref and input file
  hashes; add optional archive retention limits. Generated Compose should reuse
  the owned run-root/work/history convention rather than invent another layout.


## ArduPilot Integration

- Qualify a stable JSON-backed ArduPilot release when available. The older
  Python-backed Copter 4.6.3 path and pinned 4.8.0-dev JSON-backed revision passed
  live checks; this is not a general newer-release compatibility guarantee.
- Consider upstreaming an explicit metadata-file option to replace the overlay
  adapter when upstream provides a stable equivalent.


## Build And Release

- Add lightweight per-PR CI for host regression tests, syntax, JSON bundles and
  config generation. Keep full firmware/image builds and live Docker suites
  opt-in, scheduled or release-triggered; reuse published qualification images
  where appropriate rather than rebuilding firmware on every PR.
- Extend the opt-in runtime/Compose live suites beyond Copter 4.6.3, pinned
  4.8.0-dev and PX4 SIH 1.16.0; integrate them with suitable CI. Installed
  entrypoint/health and ArduPilot Compose/host-port/volume checks now pass for the
  qualification image IDs in `docs/RUNTIME_QUALIFICATION.md`.
- Add startup-cancellation, transport-loss and interrupted-upload fault tests.
- Consider pinning base/package dependencies for more reproducible image builds;
  current qualification records exact tested image IDs, not hermetic rebuilds.
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
- Integrate PX4-native heartbeat readiness and mission/fence/rally initialization
  with the shared uploader; keep its current process-only `running` status
  distinct from ArduPilot's initialization `ready` status.


## External Dynamics and Runtime Profiles

Design/research handoff: [RUNTIME_PROFILES.md](RUNTIME_PROFILES.md).

- Select one initial ArduPilot/backend/model pairing and pin the autopilot,
  simulator, bridge and assets. Choose JSBSim or modern Gazebo based on the
  required dynamics, world interactions and sensor fidelity.
- Run the four qualification investigations in the design note; preserve exact
  configuration, commands, measured results and release-specific references.
- Define backend capabilities from that evidence: transport, clock ownership,
  signal mappings, initial conditions/trim, readiness, reset and resource needs.
- Add explicit managed adapters instead of unrestricted upstream flag forwarding;
  prevent duplicate simulator launch by upstream tooling.
- Add external simulator packaging/services and a PX4 external-simulation variant
  only after its native module/bridge requirements are identified. Four logical
  runtime profiles do not require four independent implementations.
- Extend scenario orchestration for coordinated failure/reset, shared-world
  identities and world-level clock settings. Keep persisted autopilot files
  distinct from checkpoint restoration.
- Qualify mixed-autopilot worlds, larger fleets, cross-host transport and
  checkpoint support separately; do not advertise them by inference.


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
- Consider a dedicated router/initialization channel to remove the direct TCP
  single-client startup handoff. Add optional user-Lua readiness handshakes.


## Repository Hygiene

- Keep generated catalogs out of git by default.
- Periodically refresh checked-in example bundles from the pinned ArduPilot
  checkout.
- Consider splitting long README sections into task-focused docs if the README
  starts to feel crowded again.
