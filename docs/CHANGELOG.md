# Changelog

This changelog summarizes notable user-facing and developer-facing changes.
The initial entries were sourced from the git commit history, durable docs, and
`docs/SESSION_SUMMARY.md`.

The project does not currently maintain tagged releases, so entries are grouped
by development eras and notable commit ranges rather than semantic versions.


## Unreleased

- Made single-container ArduCopter/JSBSim the default deployment, with an isolated
  physics Python environment and common process supervision. Retained explicit
  split-container Compose and shared read-only model catalogs.

- Added read-only native JSBSim model catalogs with name-based selection and a
  starter F450 export command. Compatible quad-X variants can change physical
  XML assets without rebuilding ArduPilot; custom models require qualification.

- Added an experimental no-fork ArduCopter/JSBSim F450 adapter, separate images,
  Compose topology and physics-aware supervision. Internal dynamics remain default;
  installed normal-EKF takeoff/hover/yaw/landing and coupled process-failure checks
  pass for Copter 4.6.3 + JSBSim 1.3.3. Added host protocol/config tests and opt-in
  real-model/flight qualification commands; real-aircraft fidelity remains unvalidated.

- Defaulted both runtime Compose paths to localhost host publications, with an
  explicit LAN binding override. Added a supervised PX4 UDP relay for bridge-mode
  host clients and reconnection; native host networking remains available.

- Added lightweight GitHub PR/push host checks without firmware/image builds or
  live containers.
- Added PX4 verified heartbeat readiness, mission/fence/rally initialization on a
  private UDP link, bounded startup failure handling and installed health checks.

- Hardened qualification reporting so cleanup failures cannot report success,
  and independently checked read-back plan payloads with documented home and
  legacy-coordinate normalization.

- Built and qualified installed PX4 SIH 1.16.0 and pinned JSON-backed Copter
  4.8.0-dev (`c6a991d4`) packages; verified default entrypoints, ArduPilot Docker
  health checks and unchanged upstream metadata. Existing release tags remain
  untouched.
- Added opt-in Compose qualification with three real host TCP clients and checks
  for loopback bindings, distinct named volumes, retained resume and fresh reset.
- Fixed build-context exclusions for new helpers and added shallow exact-commit
  fetch/checkout support to the ArduPilot Dockerfile.

- Qualified mounted runtime helpers against existing Copter 4.6.3 and PX4 SIH
  1.16.0 images without image builds; added an opt-in real-firmware qualification
  suite and a versioned-results note in `docs/RUNTIME_QUALIFICATION.md`.
- Fixed integer speedup compatibility, boot-heartbeat mission upload races,
  headless MAVProxy stdin EOF, and PX4 1.16 explicit SYSID being overwritten
  before MAVLink startup. Added regression tests for the uncovered contracts.

- Replaced Dockerfile-generated launch logic with a validated single-vehicle
  runner, actual vehicle-process supervision, bounded shutdown and readiness.
- Added owned run roots with `work/`, archived `history/`, exclusive locking,
  fresh/resume state and effective configuration/status metadata. PX4 shares the
  state/process wrapper but does not yet advertise MAVLink readiness.
- Moved mounted vehicle metadata into a process-local overlay; upstream files
  are no longer overwritten. Added `--validate` and `--print-effective-config`.
- Added ordered `PARAM_FILES`; `PARAM_FILE` now layers over bundle parameters
  rather than suppressing them. Managed CLI flags are parsed before resolution;
  unsupported upstream passthrough flags now fail explicitly.
- Unified mission/fence/rally preload through MAVLink with target verification,
  retries and startup ACK requirements. Mission preload no longer needs Lua;
  removed the bundled mission loader and mission-enabling parameter example.
- Restage user scripts in the effective work directory on every launch,
  preventing stale scripts and fixing `--use-dir` interaction.
- Defaulted to direct TCP and loopback-only Compose port publication; added
  per-service retained run volumes, health checks and shutdown grace periods.
- Added host-only configuration, protocol and fake-process lifecycle tests.
  Live pinned-release SITL validation remains outstanding; no image build is
  implied by these checks.

- Moved the chronological session/dev log to `docs/SESSION_SUMMARY.md`.
- Added this changelog as the release-facing project history.
- Added `Dockerfile.px4-sih` as a v1 sibling image for prebuilt PX4
  Simulator-In-Hardware runtime.
- Added PX4 SIH runtime helpers with common env conventions for instance,
  optional system ID, home location, model, speedup, and run/artifact
  directories.
- Added `scripts/build-px4-sih-image.sh` for PX4 SIH model/ref image builds,
  including archive/local/registry output modes and zstd compression.
- Changed the PX4 SIH Dockerfile to avoid recursive clone and initialize only
  configurable SIH-relevant submodules by default.
- Added separate `PX4_BUILD_TARGET` and `PX4_BUILD_DIR` handling so PX4 release
  refs such as `v1.16.0` can use `px4_sitl` and `build/px4_sitl_default`.
- Changed the PX4 SIH builder to compile only the build target and defer
  `PX4_SIM_MODEL` to runtime, avoiding build steps that launch SITL.
- Documented PX4 SIH design boundaries and future shared manifest direction.


## Current SITL Runtime And Config Architecture

Source commits include `2e61929`, `eec468b`, `616c982`, `8246746`, `6a051e2`,
`c2db748`, `a8668ba`, and `da6e731`.

### Added

- Added a multi-stage Docker build that prebuilds ArduPilot SITL in a builder
  stage and copies only runtime dependencies into the final image.
- Added BuildKit cache use for apt, pip, Gradle, and ccache to reduce rebuild
  time.
- Added `scripts/build-release-image.sh` for release-specific image builds and
  zstd-compressed Docker archive export.
- Added `WAF_TARGET` and `WAF_JOBS` build args so images can build a specific
  SITL target with configurable waf parallelism.
- Added `compose.sitl.yml` for launching multiple SITL containers with distinct
  `INSTANCE`, `SYSID`, and TCP ports.
- Added runtime config bundle support through `/configs`, `SITL_CONFIG_DIR`,
  mounted `vehicleinfo.json`, `MODEL`, and `PARAM_FILE`.
- Added `scripts/populate-config-bundles.py` to generate mountable frame/config
  bundles from the local ArduPilot checkout while keeping generated catalogs out
  of git by default.
- Added runtime Lua installation through `$SITL_CONFIG_DIR/scripts/` and
  `LUA_SCRIPT`.
- Added a copyable initial-state Lua example for starting SITL from a custom
  airborne or dynamic state.
- Added `MISSION_FILE` support for loading QGC WPL 110 mission files through an
  image-provided Lua mission loader.
- Added `FENCE_FILE` and `RALLY_FILE` support for uploading geofence and rally
  plan artifacts with MAVLink mission protocol.
- Added project-owned fence/rally JSON examples under
  `configs/examples/plan-artifacts/`.
- Added research and design docs for initial state, plan artifacts, runtime log
  output, future fleet/scenario config, and JSON manifest direction.
- Added the DOX/`AGENTS.md` hierarchy for repo-local agent instructions.

### Changed

- Kept runtime containers focused on running prebuilt SITL rather than acting as
  full ArduPilot development environments.
- Switched runtime parameter customization to a singular `PARAM_FILE` plus
  mounted `vehicleinfo.json` bundle support instead of comma-separated parameter
  env lists.
- Removed forced MAVProxy output defaults so `sim_vehicle.py` defaults are
  preserved unless `PROXY`, `NO_MAVPROXY`, or trailing args override them.
- Clarified direct SITL TCP behavior when `NO_MAVPROXY=1` and MAVProxy fan-out
  behavior when MAVProxy is enabled.
- Documented `.BIN` versus `.tlog` output paths for post-SITL analysis.
- Consolidated design rationale into `docs/DESIGN.md`, research routing into
  `docs/RESEARCH.md`, and backlog items into `docs/FUTURE_WORK.md`.


## Early Docker Compose And Runtime Docs

Source commits include `48cae9d`, `ee44adc`, `09084b7`, `76a2c7b`,
`ab20a20`, and merged community contributions through `cab9e80`, `581cec6`,
`6b3d308`, and `cea64b6`.

### Added

- Added Docker Compose usage documentation.
- Added documentation for reading logs from a running container.
- Added and refined `env.list` for Docker runtime configuration.

### Changed

- Refined the Dockerfile and README through community contributions and
  follow-up fixes.
- Updated runtime documentation for clearer container startup and usage.


## Vehicle Support And ArduPilot Version Selection

Source commits include `d6ab3b4`, `4ed8341`, `633693f`, `b00e3bc`,
`fc15752`, and `74fe2b8`.

### Added

- Added build-arg support for selecting the ArduPilot tag or branch to checkout.
- Added support for building and running multiple ArduPilot vehicle types.
- Added parameter support for starting simulations with custom runtime values.

### Changed

- Updated the image and docs for newer ArduPilot versions, including Copter
  4.0.3-era dependency path changes.
- Fixed case-sensitive vehicle-name handling.
- Switched rover handling to `pysim` for command compatibility.


## Initial Project Bootstrap

Source commits include `02ffd1d`, `f14515c`, `f127f69`, `ac9071f`, and
`8af4dff`.

### Added

- Added the first Dockerfile draft for running ArduPilot SITL in Docker.
- Added the first README and usage documentation.
- Added guidance for interactive `docker run -it` usage and automatic cleanup
  with `--rm`.

### Changed

- Fixed early documentation inconsistencies as the run commands stabilized.
