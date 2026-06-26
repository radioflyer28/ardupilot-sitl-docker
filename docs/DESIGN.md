# Design: ArduPilot SITL Docker Images

This project builds Docker images that run pre-built ArduPilot SITL vehicles
quickly and predictably. The main tension is between ArduPilot's rich developer
environment and a runtime image that should be small, repeatable, and easy to
start in automation.


## Goals

- Produce release-specific SITL images for Copter, Plane, Rover, and Sub.
- Keep runtime startup fast by prebuilding SITL binaries during image build.
- Keep the final image free of compilers and heavy build-only dependencies.
- Support headless and non-interactive container use.
- Let users run stock frames, direct model/param overrides, or mounted custom
  vehicle config bundles.
- Preserve the ability to use SITL images as base images for larger simulation
  stacks, such as images that add ROS 2, MAVROS, companion nodes, or custom
  control logic on top of the prebuilt SITL runtime.
- Keep the checked-in repository small while making larger generated catalogs
  easy to recreate
  (re: SITL physics config and corresponding ardupilot param files in configs/frames).


## Non-Goals

- This image is not a full ArduPilot development environment.
- Runtime containers are not expected to rebuild ArduPilot.
- The project does not fork or patch upstream ArduPilot unless there is a clear
  benefit that cannot be achieved at the wrapper layer.
- The repo does not check in every generated frame bundle from ArduPilot.


## Image Architecture

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


## Runtime Lua And Initial State

ArduPilot SITL can be moved into an airborne state through Lua scripting rather
than through `sim_vehicle.py` alone. The image preserves that as a runtime
capability:

- mounted config bundles may include a `scripts/` directory
- `LUA_SCRIPT` selects one explicit script, with relative paths resolved under
  `SITL_CONFIG_DIR`
- selected scripts are copied into the ArduPilot working `scripts/` directory
  before `sim_vehicle.py` starts

The wrapper installs scripts only; params still control whether ArduPilot
scripting runs. Initial-state scripts that call `sim:set_pose` also need the
SITL AHRS backend selected by params.

The repo includes a small copyable initial-state example under
`configs/examples/initial-state/`.

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
- `docs/FUTURE_WORK.md`: actionable improvements and backlog.
- `SESSION_SUMMARY.md`: chronological dev log for this session.

Future work belongs in `docs/FUTURE_WORK.md`. The README should link there
rather than growing a long backlog section.
