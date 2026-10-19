# Research

This file indexes research notes and investigations that inform the project.
Keep detailed writeups in dedicated docs when they are large enough to stand on
their own.

Research is not the same as design commitment. Once a recommendation becomes a
project decision, summarize the decision in `docs/DESIGN.md`. Once it becomes
planned work, track the action in `docs/FUTURE_WORK.md`.


## PX4 + JSBSim

[PX4_JSBSIM.md](PX4_JSBSIM.md) records the pinned-release simulator interface,
upstream bridge reuse assessment and implemented runtime. The existing PX4 1.16.0
binary already contains the required module/airframe. Combined and split images
passed normal-EKF takeoff/hover/yaw/landing and coupled-failure checks; a mounted
HeavyQuad variant also passed flight and clean shutdown in both topologies. SIH regression,
SYSID 17 and joint vehicle/physics archival checks pass. Shared model catalogs do
not imply shared transport or calibrated aircraft fidelity; exact evidence is in
[RUNTIME_QUALIFICATION.md](RUNTIME_QUALIFICATION.md#px4jsbsim-qualification).

## SITL Initial State

Status: runtime Lua support and a copyable initial-state script are
implemented; generated or externally mounted initial-state config is still
planned

Detailed note:

```text
docs/INITIAL_STATE.md
```

Summary:

ArduPilot SITL can be moved into an airborne or otherwise custom dynamic state
through Lua scripting. The native hook is `sim:set_pose(...)`, and the closest
upstream example is `libraries/AP_Scripting/examples/sim_arming_pos.lua`.

Key findings:

- `sim_vehicle.py` can set the home/origin, model, params, speed, instance,
  system ID, and start time, but not a complete airborne state by itself.
- `sim:set_pose(...)` can set position, velocity, attitude, and gyro rates.
- The pose injection path requires `AHRS_EKF_TYPE=10`.
- ArduPilot's own QuadPlane autotests use `sim_arming_pos.lua` for airborne
  recovery tests.
- Acceleration is not directly set by `sim:set_pose`; SITL derives it on later
  dynamics updates.
- Mission loading is separate and can be handled through Lua mission APIs,
  MAVLink, or MAVProxy.
- This repo implements `MISSION_FILE` through the shared MAVLink uploader for
  QGC WPL 110 mission files; Lua is not required for mission preload.

Implemented recommendations:

- Support runtime Lua installation from `$SITL_CONFIG_DIR/scripts/`.
- Add a singular `LUA_SCRIPT` env var for selecting one explicit Lua script.
- Provide a copyable `initial-state.lua` example that calls `sim:set_pose` once
  by default when the vehicle arms.

Remaining recommendation:

- Prefer generated or externally mounted initial-state config over direct
  reliance on `SIM_APOS_*` params when scaling this beyond hand-edited example
  scripts, because those params are created dynamically by Lua.

Feeds:

- `docs/DESIGN.md`: runtime Lua and initial-state decisions.
- `docs/FUTURE_WORK.md`: first-class initial-state feature backlog item.


## Runtime Plan Artifacts

Status: mission, fence, and rally low-level env loading implemented; fleet
scenario generation still planned

Detailed note:

```text
docs/PLAN_ARTIFACTS.md
```

Summary:

Missions, geofences, and rally points should be treated as separate runtime plan
artifacts. MAVLink carries them through the mission protocol with different
`mission_type` values. ArduPilot has C++ mission item protocol handlers for
mission, fence, and rally, but Lua scripting exposes only mission write APIs.
Fence/rally bindings are read/status oriented in the local checkout.

Key findings:

- `MISSION_FILE` now uses MAVLink for observable, blocking startup completion.
- `QGC WPL 110` should not be stretched to represent geofence or rally data.
- Fence and rally are uploaded through MAVLink mission protocol tooling with
  `MAV_MISSION_TYPE_FENCE` and `MAV_MISSION_TYPE_RALLY`.
- Multi-SITL use should be designed around one mounted config bundle per
  container, not shared global artifact files.

Implemented recommendations:

- Add `FENCE_FILE` and `RALLY_FILE` env vars with the same path semantics as
  `MISSION_FILE`.
- Use a small Python/pymavlink uploader for mission/fence/rally after a verified
  target heartbeat, with retries, identity filtering and accepted ACKs.
- Keep per-vehicle artifacts grouped under directories such as `missions/`,
  `fences/`, `rally/`, and `scripts/`.
- Keep env vars as the low-level interface for one-off SITLs and generated
  services.

Remaining recommendation:

- Let a future Compose builder generate one service per vehicle with its own
  bundle, `INSTANCE`, `SYSID`, ports, frame/model, params, mission, initial
  state, fence, and rally settings.

Feeds:

- `docs/DESIGN.md`: runtime artifact bundle design.
- `docs/FUTURE_WORK.md`: fleet config builder and artifact-output backlog
  items.


## Runtime Analysis Logs

Status: researched; README and design docs describe current usage

Summary:

SITL post-run analysis uses two different log producers. ArduPilot writes
onboard/dataflash `.BIN` logs through the filesystem logger. MAVProxy or
another GCS writes MAVLink telemetry `.tlog` files.

Key findings:

- SITL defaults to the filesystem logging backend for onboard logs.
- `LOG_DISARMED=1` enables `.BIN` logging before arming when startup analysis
  is needed.
- Managed `--use-dir` selects an owned run root; current vehicle state and
  `.BIN` logs live beneath `work/`, with fresh-start archives under `history/`.
- `sim_vehicle.py --aircraft` is passed to MAVProxy and is the practical
  MAVProxy-side directory selector for `.tlog` files.
- `NO_MAVPROXY=1` does not produce a MAVProxy `.tlog`; use an external GCS or
  logger when telemetry logs are needed without in-container MAVProxy.

Feeds:

- `README.md`: user-facing commands for mounted artifact directories.
- `docs/DESIGN.md`: durable distinction between `.BIN` and `.tlog` producers.


## ArduCopter + JSBSim Quad-X

Native multi-model catalogs are implemented with read-only mounting and name-based
selection. Packaged F450 and a mounted HeavyQuad variant (1.8 kg with increased
inertia) passed installed flight/failure checks; custom models remain separately
qualified. See the model-catalog section of `RUNTIME_QUALIFICATION.md`.

Combined-default and optional split deployment flight checks pass, including local
physics/autopilot process failures and graceful shutdown. The combined image uses
an isolated JSBSim virtualenv and archives nested physics state with the vehicle.
See `RUNTIME_QUALIFICATION.md` for exact topology/image evidence.

Status: experimental adapter, F450 model composition and combined/split images
implemented; host protocol/configuration, real-model and installed normal-EKF
hover/yaw/landing checks pass for Copter 4.6.3 + JSBSim 1.3.3. Both process-death
directions stop the coupled peer. Exact images and remaining limits are recorded
in [RUNTIME_QUALIFICATION.md](RUNTIME_QUALIFICATION.md#arducopterjsbsim-f450-qualification).

[ARDUCOPTER_JSBSIM.md](ARDUCOPTER_JSBSIM.md) specifies restart-based switching
between internal dynamics and JSBSim, using unmodified ArduCopter's JSON physics
interface. Project-owned adapter code stays outside the ArduPilot checkout. The
note records pinned source evidence for the existing fixed-wing JSBSim connector,
proposed motor/sensor/time/lifecycle contracts, open decisions and delivery gates.
[FUTURE_WORK.md](FUTURE_WORK.md) tracks the phased implementation.


## External Physics and Flight-Dynamics Simulators

Status: surveyed; experimental ArduCopter/JSBSim and PX4/JSBSim integrations are
packaged in combined and split forms with scoped installed qualification. Other
simulator catalog entries remain unimplemented/unqualified here.

Detailed note:

```text
docs/EXTERNAL_SIMULATORS.md
```

Summary:

Modern Gazebo is a documented external-simulator option for both autopilots;
JSBSim is another cross-autopilot FDM option, with PX4's integration
community-supported. Other options and support levels differ by autopilot.
External simulators require their own bridge, model, and dependencies; PX4 SIH
remains an internal uORB simulator rather than an external backend. FlightGear
used as ArduPilot's standard SITL viewer is not itself the physics backend.


## Live Internal-Dynamics Runtime Qualification

Status: existing-image checks passed for Copter 4.6.3/PX4 SIH 1.16.0; installed
image checks also passed for PX4 1.16.0 and pinned JSON-backed Copter 4.8.0-dev
`c6a991d4aa91e3834af333c0061533aa1009b431`. Three-service ArduPilot Compose health,
host TCP access and retained-volume fresh/resume checks passed. A newer PX4
1.16.0 package also passed verified heartbeat/plan readiness, installed health,
plan retention/clearing and rejected-frame/missing-heartbeat startup failures.
A separate relay-capable image passed localhost-published PX4 Compose tests with
real host UDP clients, reconnection, volume recreation and relay-failure detection;
ArduPilot localhost Compose regression also passed.

[RUNTIME_QUALIFICATION.md](RUNTIME_QUALIFICATION.md) records exact identities,
reproduction commands, real plan/Lua/state/lifecycle results, compatibility fixes
and remaining boundaries. Generated reports/logs stay in ignored `artifacts/`.
The host-only suite and the opt-in Docker live suite are distinct checks.


## Runtime Profiles and External Dynamics Architecture

Status: broader architecture remains design guidance. The first experimental
ArduCopter/JSBSim and sibling PX4/JSBSim adapters and images now exist; see their
dedicated guides for implemented scope and qualification status.

Detailed note: [RUNTIME_PROFILES.md](RUNTIME_PROFILES.md).

- Distinguishes the four autopilot/internal-or-external profiles from image,
  service, adapter and scenario counts.
- Defaults single-vehicle ArduCopter/JSBSim and PX4/JSBSim to colocated supervised processes with
  isolated dependencies, retaining optional split images. Shared-world backends
  may warrant separate services; capability/version/model contracts remain explicit.
- Captures clock ownership, readiness, coordinated reset, initial conditions and
  trim, container transport, signal mappings, fidelity/repeatability, rendering
  and asset/licensing questions with upstream sources.
- Defines four qualification investigations before generalizing: transport and
  isolation; clock and lifecycle; reset and initialization; signal/fidelity/cost.

Feeds: `DESIGN.md` for architectural direction and `FUTURE_WORK.md` for execution.


## PX4 SIH Runtime

Status: v1 sibling image implemented; shared manifest support still planned

Detailed note:

```text
docs/PX4_SIH.md
```

Summary:

PX4's Simulator-In-Hardware path can be packaged similarly to the ArduPilot
runtime image, but it should remain a native PX4 runtime rather than a
`sim_vehicle.py` clone. Newer PX4 `main` builds SIH with `px4_sitl_sih`; PX4
v1.16 uses `px4_sitl` and writes to `build/px4_sitl_default`. The runtime starts
a prebuilt `px4` binary directly with an instance number and runtime directory.

Key findings:

- `sihsim_quadx` is the stable/default SIH model in PX4's docs.
- The build target and build output directory are version-sensitive.
- PX4's `make <target> <model>` SIH commands are build-and-run workflows; image
  builds should compile only the target and set the model at runtime.
- PX4 uses `PX4_HOME_LAT`, `PX4_HOME_LON`, `PX4_HOME_ALT`, and
  `PX4_SIM_SPEED_FACTOR` for common location and speed controls.
- PX4's instance system offsets ports and assigns `MAV_SYS_ID=INSTANCE+1`
  unless explicitly overridden.
- PX4 applies env vars named `PX4_PARAM_<PARAM_NAME>` during POSIX startup.
- PX4 SIH is UDP-oriented; the default Compose workflow uses bridge networking
  with localhost publication and the supervised GCS relay. Native host networking
  remains an explicit alternative for UDP autodiscovery.

Implemented recommendations:

- Add `Dockerfile.px4-sih` as a sibling multi-stage image.
- Add PX4 SIH runtime helpers that preserve common env names where PX4 has
  native equivalents.

Remaining recommendation:

- Let future shared manifest tooling generate ArduPilot or PX4 native env vars,
  mounts, ports, artifact directories, and upload helpers from the same
  scenario definition.
