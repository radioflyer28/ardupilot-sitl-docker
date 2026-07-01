# Design: SITL Docker Images

This project builds Docker images that run pre-built SITL vehicles quickly and
predictably. ArduPilot SITL is the mature primary path; PX4 SIH is a sibling
runtime path that should follow the same user-facing conventions where the two
autopilots naturally overlap. The main tension is between rich upstream
developer environments and runtime images that should be small, repeatable, and
easy to start in automation.


## Goals

- Produce release-specific SITL images for Copter, Plane, Rover, and Sub.
- Keep runtime startup fast by prebuilding SITL binaries during image build.
- Keep the final image free of compilers and heavy build-only dependencies.
- Support headless and non-interactive container use.
- Let users run stock frames, direct model/param overrides, or mounted custom
  vehicle config bundles.
- Keep runtime plan artifacts service-local so fleets can start multiple SITLs
  with independent frame/model, params, mission, initial pose, geofence, rally,
  and networking settings.
- Preserve the ability to use SITL images as base images for larger simulation
  stacks, such as images that add ROS 2, MAVROS, companion nodes, or custom
  control logic on top of the prebuilt SITL runtime.
- Preserve a cross-autopilot low-level convention for common controls such as
  instance, system ID, home location, speedup, model selection, artifact
  directories, and future mission/fence/rally upload workflows.
- Keep the checked-in repository small while making larger generated catalogs
  easy to recreate
  (re: SITL physics config and corresponding ardupilot param files in configs/frames).


## Non-Goals

- Runtime images are not full upstream development environments.
- Runtime containers are not expected to rebuild the autopilot after startup.
- The project does not fork or patch upstream ArduPilot unless there is a clear
  benefit that cannot be achieved at the wrapper layer.
- The repo does not check in every generated frame bundle from ArduPilot.


## ArduPilot Image Architecture

The Dockerfile uses a multi-stage build:

- `builder` stage: installs build dependencies, clones ArduPilot, prepares the
  Python environment, initializes submodules, builds Micro-XRCE-DDS-Gen, and
  prebuilds selected SITL targets with waf.
- `runtime` stage: installs only runtime packages, then copies the prebuilt
  ArduPilot tree, Python virtual environment, environment setup, and wrapper
  scripts from the builder.

This keeps release images focused on running SITL. If a user opens a shell in
the runtime container and calls `sim_vehicle.py` manually, they should pass
`--no-rebuild` or use `run-sitl.sh`.


## PX4 SIH Image Architecture

`Dockerfile.px4-sih` is a sibling multi-stage build for PX4's
Simulator-In-Hardware runtime:

- `builder` stage: uses a PX4 development image, clones PX4-Autopilot, updates
  only the configured SIH-relevant submodules, and builds the configured SIH
  target without launching a simulator model.
- `runtime` stage: installs only lightweight runtime packages, copies the
  prebuilt PX4 build directory, and runs PX4 through
  `run-px4-sih.sh`.

The PX4 image is not a full PX4 development environment. It starts the prebuilt
`px4` binary directly rather than invoking `make` at runtime.

The builder compiles only `PX4_BUILD_TARGET`. It does not pass
`PX4_SIM_MODEL` as a make argument because PX4's documented
`make <target> <model>` commands launch the simulator model after compiling.
In this image, `PX4_SIM_MODEL` is a runtime setting consumed by PX4 startup.

The PX4 builder intentionally does not use recursive clone. The default
`PX4_SUBMODULE_PATHS` excludes external simulator stacks such as Gazebo Classic,
Gazebo, jMAVSim, FlightGear, and JSBSim because SIH runs physics inside PX4 and
does not need those assets. This keeps build time and image size aligned with
the SIH-only runtime goal. The script also distinguishes the make target from
the build directory because release refs such as PX4 v1.16 use
`PX4_BUILD_TARGET=px4_sitl` and `PX4_BUILD_DIR=px4_sitl_default`, while newer
PX4 `main` supports `px4_sitl_sih`.

PX4 shares the common env convention only where the mapping is native and
obvious:

- `INSTANCE` maps to `px4 -i`
- `SYSID` maps to `PX4_PARAM_MAV_SYS_ID` only when explicitly set
- `LAT`, `LON`, and `ALT` map to `PX4_HOME_LAT`, `PX4_HOME_LON`, and
  `PX4_HOME_ALT`
- `SPEEDUP` maps to `PX4_SIM_SPEED_FACTOR`
- `MODEL` maps to `PX4_SIM_MODEL`

PX4-specific parameters remain available through `PX4_PARAM_*`. The wrapper
does not pretend that PX4 has ArduPilot concepts such as `vehicleinfo.json`,
`sim_vehicle.py` frames, MAVProxy defaults, or ArduPilot Lua scripts.

Detailed research and source notes live in `docs/PX4_SIH.md`.


## Build Decisions

- `WAF_TARGET` selects a single vehicle target (`copter`, `plane`, `rover`,
  `sub`). When empty, `WAF_ALL_TARGETS` is built.
- `WAF_JOBS` controls waf parallelism.
- BuildKit cache mounts are used for apt, pip, Gradle, and ccache.
- The release script applies zstd BuildKit compression options for local Docker
  output, defaults to exporting a zstd-compressed Docker archive, and can push
  OCI images with zstd-compressed layers through BuildKit registry output.
- `configs/generated-frames/`, `.buildx-cache/`, and exported archives are
  ignored so normal development stays quiet.


## Runtime Entrypoint

The image entrypoint has two modes:

- no args or first arg starts with `-`: run `run-sitl.sh`, passing dash args
  through to `sim_vehicle.py`
- first arg does not start with `-`: execute it as a command, such as `bash`

`run-sitl.sh` translates environment variables into `sim_vehicle.py` arguments:

- `INSTANCE`, `SYSID`, `VEHICLE`, `FRAME`, location, heading, and speedup
- `NO_MAVPROXY=1` appends `--no-mavproxy`
- `PROXY` appends custom MAVProxy args through `-m`
- runtime Lua scripts installed by `install-sitl-lua.sh`
- runtime config args resolved by `resolve-sitl-config.py`

Derived images may replace the entrypoint when they need to orchestrate SITL
alongside companion processes. The stable surface for that use case is
`/usr/local/bin/run-sitl.sh`, plus the runtime environment variables documented
in the README.


## Runtime Vehicle Config

There are two supported runtime config paths.

Direct file overrides:

- `MODEL` is passed as `--model`
- `PARAM_FILE` is passed as `--add-param-file`
- relative `PARAM_FILE` paths resolve under `SITL_CONFIG_DIR`
- `MISSION_FILE` stages a QGC WPL 110 mission file for the runtime Lua mission
  loader

Mounted config bundles:

- default mount point is `/configs`
- if `$SITL_CONFIG_DIR/vehicleinfo.json` exists, the wrapper uses it
- `VEHICLEINFO_JSON` can point to a specific file
- relative `model` JSON paths and `default_params_filename` entries resolve
  relative to the mounted `vehicleinfo.json`
- explicit `MODEL` or `PARAM_FILE` override values inferred from the mounted
  JSON

This preserves an ArduPilot-native shape for reusable vehicles while avoiding
runtime rebuilds.


## Runtime Plan Artifacts

Mission, fence, rally, Lua, params, model, and vehicleinfo files should be
organized as per-vehicle bundle artifacts under `SITL_CONFIG_DIR`. The intended
fleet shape is one container per SITL instance, with each service mounting its
own bundle at `/configs`.

Direct env vars remain the right low-level interface for one-off SITLs and
quick overrides. Multi-SITL workflows need a higher-level fleet/scenario layer
that generates per-service env vars, mounts, ports, and image tags from a
per-vehicle definition.

Implemented artifacts:

- `MISSION_FILE` for QGC WPL 110 mission files
- `LUA_SCRIPT` and `$SITL_CONFIG_DIR/scripts/` for Lua scripts
- `PARAM_FILE`, `MODEL`, and mounted `vehicleinfo.json`
- `FENCE_FILE` for geofence plans
- `RALLY_FILE` for rally point plans

Fence and rally do not use the Lua mission loader. ArduPilot exposes them as
separate MAVLink mission protocol plan types, and the local Lua bindings do not
expose write APIs for replacing fence/rally storage. The wrapper uses a small
Python/pymavlink uploader that runs after SITL accepts MAVLink and uploads
`MAV_MISSION_TYPE_FENCE` or `MAV_MISSION_TYPE_RALLY`.

When `NO_MAVPROXY=1`, fence/rally upload uses the direct SITL TCP endpoint by
default. When MAVProxy is enabled, the wrapper creates a private in-container
MAVProxy `tcpin` output unless `PLAN_UPLOAD_MASTER` explicitly points
elsewhere. This keeps host-facing ports under user control while still allowing
one-shot startup uploads.

Detailed research lives in `docs/PLAN_ARTIFACTS.md`.


## Scenario Manifest Direction

A project-owned JSON Schema is a good fit for the next layer of runtime config,
but it should be a manifest/orchestration layer rather than a replacement for
ArduPilot-native files.

The manifest should connect existing artifacts:

- vehicle, frame, instance, system ID, location, heading, speedup, and image tag
- model files and `vehicleinfo.json`
- parameter files and small inline parameter overrides
- mission, fence, and rally files or inline definitions
- Lua script files and optional structured script config
- artifact output locations for `.BIN`, `.tlog`, stdout/stderr, and metadata

Native artifacts should remain first-class files inside the mounted bundle.
This keeps ArduPilot formats inspectable, reusable in other tools, and close to
upstream expectations. The JSON manifest should validate references, provide a
stable shape for tooling, and generate the low-level runtime interface: env
vars, `sim_vehicle.py` args, mounts, ports, Compose services, and any temporary
generated files.

For PX4 SIH, the same manifest layer should generate PX4-native env vars such
as `PX4_SIM_MODEL`, `PX4_PARAM_*`, `PX4_HOME_*`, `PX4_RUN_DIR`, UDP port
expectations, and MAVLink upload steps. Shared manifests should standardize the
scenario shape without forcing PX4 to emulate ArduPilot's runtime files.

The schema should allow both file-backed and inline definitions for mission,
fence, and rally artifacts, but enforce exactly one form per artifact. For
example, `mission.file` and `mission.items` must be mutually exclusive. The
same rule applies to `fence.file` versus inline `fence.fences` / `fence.items`,
and `rally.file` versus inline `rally.points` / `rally.items`. Inline artifacts
should be normalized by tooling into generated runtime files, then fed into the
same low-level env vars as file-backed artifacts.

Parameter config is the deliberate exception to strict either-or. Params should
support both ordered `files` and a final inline `set` map because parameter
layering is native to the workflow and override order is clear.

Lua should be referenced as code files rather than embedded in JSON. Structured
Lua config can live in the manifest, then be rendered into a small config file
or parameter set consumed by project-provided scripts. This keeps code as code
and scenario data as data.

The same idea should scale from one vehicle bundle to a fleet manifest that
references many per-vehicle manifests and expands them into one Compose service
per SITL instance.


## Runtime Analysis Artifacts

Post-run analysis artifacts have separate producers:

- `.BIN` logs are ArduPilot onboard/dataflash logs written by the SITL vehicle
  logger. The SITL filesystem logger writes under the run directory's `logs/`
  directory, and `sim_vehicle.py --use-dir` can move that run directory under a
  mounted host artifact path.
- `.tlog` logs are MAVLink telemetry logs normally written by MAVProxy or a
  GCS. `sim_vehicle.py --aircraft` is passed through to MAVProxy and can place
  MAVProxy state and telemetry logs in a named artifact directory.

For `NO_MAVPROXY=1` runs, the image should not claim to create `.tlog` files.
Users who need telemetry logs in direct-SITL mode should run an external GCS or
logger against the published TCP/UDP endpoint.


## Runtime Lua, Missions, And Initial State

ArduPilot SITL can load missions and move into an airborne state through Lua
scripting rather than through `sim_vehicle.py` alone. The image preserves that
as a runtime capability:

- mounted config bundles may include a `scripts/` directory
- `LUA_SCRIPT` selects one explicit script, with relative paths resolved under
  `SITL_CONFIG_DIR`
- `MISSION_FILE` selects one QGC WPL 110 mission file, with relative paths
  resolved under `SITL_CONFIG_DIR`
- selected scripts are copied into the ArduPilot working `scripts/` directory
  before `sim_vehicle.py` starts
- selected missions are staged into the ArduPilot working `missions/`
  directory, and an image-provided Lua loader imports them through the mission
  API

The wrapper installs scripts only; params still control whether ArduPilot
scripting runs. Mission loading needs `SCR_ENABLE=1`; initial-state scripts
that call `sim:set_pose` also need the SITL AHRS backend selected by params.

The repo includes small copyable examples under `configs/examples/` for
initial state, mission loading, and plan artifacts.

The detailed research and recommended integration path live in
`docs/INITIAL_STATE.md`.


## Why The Wrapper Resolves Params

Newer ArduPilot SITL binaries can load per-frame defaults from embedded ROMFS
metadata. That is good for built-in frames, but it means a runtime-mounted
`vehicleinfo.json` does not automatically control the binary's embedded default
parameter stack.

The project handles this outside upstream ArduPilot:

1. Copy mounted `vehicleinfo.json` where `sim_vehicle.py` expects it.
2. Read the selected `VEHICLE` and `FRAME`.
3. Resolve `model` and `default_params_filename` paths from the mounted bundle.
4. Pass explicit `--model` and `--add-param-file` arguments to `sim_vehicle.py`.

This keeps the behavior understandable and avoids patching `sim_vehicle.py`.


## Config Bundle Philosophy

Checked-in bundles should be few and useful as examples. The repo currently
keeps:

- `configs/frames/arducopter-quad`
- `configs/frames/arduplane-plane`

The full catalog can be generated on demand from a local ArduPilot checkout:

```bash
scripts/populate-config-bundles.py
```

Generated output defaults to ignored `configs/generated-frames/`.

This approach keeps the repository small while still giving users a complete
path to all frames, params, and model assets when they need them.


## Documentation Philosophy

- `README.md`: user-facing workflow, commands, and examples.
- `docs/DESIGN.md`: architecture, philosophy, and why decisions were made.
- `docs/RESEARCH.md`: index of investigations, research status, and links to
  detailed research notes.
- `docs/INITIAL_STATE.md`: research and recommendations for airborne or custom
  SITL initial state.
- `docs/PX4_SIH.md`: PX4 SIH runtime research and design notes.
- `docs/FUTURE_WORK.md`: actionable improvements and backlog.
- `docs/CHANGELOG.md`: release-facing project history.
- `docs/SESSION_SUMMARY.md`: chronological dev log for this session.

Future work belongs in `docs/FUTURE_WORK.md`. The README should link there
rather than growing a long backlog section.
