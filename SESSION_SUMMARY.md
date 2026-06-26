# Session Summary - 2026-06-26

This file summarizes the prompts, answers, and code changes from the Dockerized
ArduPilot SITL development session.


## Environment File

Prompt:

> Populate `env.list` with all environment variables available to
> `sim_vehicle.py` from the local `./ardupilot` repo, ideally with comments.

Answer and changes:

- Inspected `Tools/autotest/sim_vehicle.py`, `pysim/util.py`, and
  `run_in_terminal_window.sh`.
- Documented the existing runtime variables used by the Docker entrypoint:
  `INSTANCE`, `SYSID`, `VEHICLE`, `FRAME`, `LAT`, `LON`, `ALT`, `DIR`,
  `SPEEDUP`.
- Added commented optional variables read by ArduPilot tooling, including
  `ARDUPILOT_LOCATIONS`, `XDG_CONFIG_DIR`, `HOME`, `DISPLAY`,
  `MAVPROXY_CMD`, compiler overrides, `ASAN_OPTIONS`, `PYTHONPATH`,
  `SITL_RITW_*`, and terminal session variables.
- Left optional values commented so `docker run --env-file env.list` stays
  safe.


## Dockerfile Modernization

Prompt:

> Update `Dockerfile_new` with the necessary portions of the dev build
> Dockerfile in `./ardupilot/Dockerfile`. The image should include pre-built
> ArduPilot for easy SITL running.

Answer and changes:

- Reworked `Dockerfile_new` using ArduPilot's current dev Dockerfile patterns.
- Added configurable user/UID/GID setup.
- Added ArduPilot prereq installer flow.
- Added Java 17 setup and Micro-XRCE-DDS-Gen build support.
- Cloned ArduPilot, initialized submodules, configured `sitl`, and prebuilt
  waf targets.
- Added an entrypoint wrapper and `run-sitl.sh` for default SITL startup while
  still allowing commands such as `bash`.


## Lighter Base Image and Multi-Stage Build

Prompt:

> Is there a lighter base image than full Ubuntu?

Answer:

- Recommended trying `debian:bookworm-slim` because ArduPilot's prereq script
  explicitly supports Debian bookworm.
- Noted that `ubuntu:24.04` Docker image is already minimal, and the largest
  wins would come from a multi-stage build.

Prompt:

> Yes, let's do a multi-stage build.

Answer and changes:

- Converted `Dockerfile_new` to a `builder` stage and a `runtime` stage.
- Builder installs toolchains, Python deps, Micro-XRCE-DDS-Gen, and builds SITL.
- Runtime installs only runtime-oriented packages and copies:
  - prebuilt ArduPilot tree
  - `venv-ardupilot`
  - `.ardupilot_env`
  - Micro-XRCE-DDS-Gen scripts
- Set `DO_AP_STM_ENV=0` by default for SITL-only builds.
- Removed git metadata and transient caches before copying to runtime.


## Build Optimization

Prompt:

> Can we optimize layer ordering to reduce build time and size? What about
> BuildKit cache mounts?

Answer and changes:

- Added BuildKit cache mounts for apt, pip, Gradle, and ccache.
- Moved Micro-XRCE-DDS-Gen before ArduPilot checkout to preserve Gradle cache
  when changing ArduPilot refs.
- Added `.dockerignore` so the local `./ardupilot` checkout is not sent as
  Docker build context.
- Added `.gitignore` for `.buildx-cache/`, image archives, and exported tar
  files.

Prompt:

> We hit `you need to install empy` during build.

Answer and changes:

- Diagnosed that Docker `RUN` used `/bin/sh`, while `.ardupilot_env` contains
  bash `source` commands.
- Added bash `SHELL ["/bin/bash", "-o", "pipefail", "-c"]` in both stages.
- Set `DO_PYTHON_VENV_ENV=1`.
- Added `python3 -m pip show empy` before waf so environment failures are
  clearer.


## Waf Target and Parallelism

Prompt:

> Are we compiling/building with multiple cores?

Answer:

- The Dockerfile was not explicitly passing `-j` to waf.
- Recommended adding `WAF_JOBS`.

Prompt:

> Add the `WAF_JOBS` arg.

Answer and changes:

- Added `ARG WAF_JOBS=2`.
- Changed waf builds to use `./waf -j "${WAF_JOBS}"`.

Prompt:

> Provide another build arg to only build the target of our choice: copter,
> plane, rover, sub.

Answer and changes:

- Discussed naming and chose `WAF_TARGET` instead of `SITL_TARGET`.
- Added `ARG WAF_TARGET=`.
- Added `ARG WAF_ALL_TARGETS="copter plane rover sub"`.
- Behavior:
  - empty `WAF_TARGET`: build all standard targets
  - set `WAF_TARGET`: build only that target
- Added validation for `copter`, `plane`, `rover`, and `sub`.


## Build and Archive Script

Prompt:

> Build separate images for different ArduPilot release versions such as 4.7.1
> and 4.6.0, and save final images to files with zstd compression.

Answer and changes:

- Added `scripts/build-release-image.sh`.
- It maps vehicle/version pairs to ArduPilot refs:
  - `copter 4.6.3` -> `Copter-4.6.3`
  - `plane 4.6.3` -> `Plane-4.6.3`
  - `rover 4.6.3` -> `Rover-4.6.3`
  - `sub 4.5.7` -> `ArduSub-4.5.7`
- It builds with `docker buildx`, uses local BuildKit cache automatically, loads
  the image locally, and exports it with `docker image save | zstd`.
- Added environment overrides:
  `IMAGE_REPO`, `OUTPUT_DIR`, `CACHE_DIR`, `DOCKERFILE`, `BASE_IMAGE`, `TAG`,
  `WAF_JOBS`, `ZSTD_LEVEL`, and `ZSTD_LONG`.

Prompt:

> What does zstd level default to? I don't think we need more than 9.

Answer and changes:

- Noted that zstd itself defaults to level 3.
- Changed script default from level 19 to level 9.

Prompt:

> The build image has `copter` twice in its archive name.

Answer and changes:

- Explained it used both target and full ref.
- Changed archive name from:
  `ardupilot-sitl-copter-copter-4.6.3.docker.tar.zst`
  to:
  `ardupilot-sitl-copter-4.6.3.docker.tar.zst`.


## Runtime Behavior

Prompt:

> Does the SITL script entrypoint allow non-interactive containers?

Answer:

- Yes, the entrypoint can run non-interactively.
- MAVProxy is the interactive piece; recommended `NO_MAVPROXY=1` for robust
  headless service use.

Prompt:

> If we run without MAVProxy, how do we control SITL via MAVLink from outside the container?

Answer:

- Connect directly to SITL TCP:
  - `INSTANCE=0` -> port 5760
  - `INSTANCE=1` -> port 5770
  - `INSTANCE=2` -> port 5780
- Example:
  `mavproxy.py --master=tcp:127.0.0.1:5760`.
- Noted that without MAVProxy there is no MAVProxy fan-out; use external
  MAVProxy if multiple consumers are needed.

Prompt:

> Add `NO_MAVPROXY=1` support.

Answer and changes:

- Added runtime env default `NO_MAVPROXY=0`.
- `run-sitl.sh` appends `--no-mavproxy` when `NO_MAVPROXY=1`.

Prompt:

> Can we still pass `--no-mavproxy` after the image name?

Answer:

- Yes. The entrypoint passes arguments beginning with `-` through to
  `sim_vehicle.py`.
- Non-dash arguments such as `bash` are executed as commands instead.

Prompt:

> Does `INSTANCE` automatically increment the MAVLink system ID?

Answer:

- No. `INSTANCE` affects SITL instance number, ports, and state.
- `SYSID` explicitly sets `MAV_SYSID`.
- Multiple vehicles should set both `INSTANCE` and `SYSID`.


## Defaults and Manual Debugging

Prompt:

> We should get rid of defaults like `PROXY` since `sim_vehicle.py` already has
> reasonable defaults.

Answer and changes:

- Removed forced `--no-extra-ports`.
- Removed default `ENV PROXY=...`.
- `PROXY` is now optional; if set, it is passed with `-m`.
- Updated `env.list` to leave `PROXY` commented.

Prompt:

> I started the container with bash and manually ran `sim_vehicle.py`; it failed
> with missing `pexpect`.

Answer and changes:

- Explained that overriding the entrypoint skipped env setup.
- Added runtime package `python3-pexpect`.
- Added `.bashrc` sourcing of `~/.ardupilot_env` for interactive shells.

Prompt:

> Manual `sim_vehicle.py -v ArduCopter` tried to configure waf and failed
> because no compiler exists.

Answer:

- This is expected in the slim runtime image.
- The image is prebuilt and does not include a compiler toolchain.
- Manual calls should include `--no-rebuild`, or use `run-sitl.sh`.


## Documentation

Prompt:

> Update the README with Dockerfile updates, builder script, arg flags, and
> anything relevant to a user/developer.

Answer and changes:

- Replaced the old README with current documentation for:
  - multi-stage Dockerfile
  - release image build/export script
  - manual Docker builds
  - BuildKit cache
  - build args
  - runtime env vars
  - passing `sim_vehicle.py` args
  - MAVLink access with and without MAVProxy
  - debug shell usage and `--no-rebuild` caveat


## Docker Compose

Prompt:

> Make a docker compose file that starts multiple SITL instances like:
> `INSTANCE=0 SYSID=1`, `INSTANCE=1 SYSID=2`, `INSTANCE=2 SYSID=3`.

Answer and changes:

- Added `compose.sitl.yml`.
- It starts three services:
  - `sitl-0`: `INSTANCE=0`, `SYSID=1`, `NO_MAVPROXY=1`, port `5760`
  - `sitl-1`: `INSTANCE=1`, `SYSID=2`, `NO_MAVPROXY=1`, port `5770`
  - `sitl-2`: `INSTANCE=2`, `SYSID=3`, `NO_MAVPROXY=1`, port `5780`
- Image is configurable with:
  `ARDUPILOT_SITL_IMAGE=ardupilot-sitl:copter-4.6.3`.
- README updated with Compose usage.

## Runtime Config Bundles

Prompt:

> Is there any way to parameterize the vehicle in `sim_vehicle.py`, with
> accessible configs for the physics model paired with an ArduPilot `.parm`
> file?

Answer:

- Explained that ArduPilot's native mechanism is the `--vehicle` and `--frame`
  pair backed by `Tools/autotest/pysim/vehicleinfo.json`.
- Noted that physics model JSON can be selected with `--model`, and parameter
  files can be layered with `--add-param-file`.
- Recommended two runtime paths:
  - direct ad hoc overrides with `MODEL` and `PARAM_FILE`
  - reusable mounted config bundles containing `vehicleinfo.json`, model JSON,
    and matching `.parm` files.

Prompt:

> Implement `MODEL + PARAM_FILE` in the wrapper, plus env-driven runtime config
> and mounting.

Answer and changes:

- Added `/configs` as the default runtime mount point.
- Added runtime env defaults:
  - `SITL_CONFIG_DIR=/configs`
  - `MODEL=`
  - `PARAM_FILE=`
- Updated the wrapper to pass `MODEL` as `--model`.
- Updated the wrapper to pass `PARAM_FILE` as `--add-param-file`, resolving
  relative paths under `SITL_CONFIG_DIR`.
- Documented the direct-file flow in `README.md` and `env.list`.

Prompt:

> The comma-separated list of param files feels confusing. Prefer either a
> mounted `vehicleinfo.json` directory or one arg for model JSON and one arg for
> params.

Answer and changes:

- Replaced the earlier `PARAM_FILES` list with singular `PARAM_FILE`.
- Clarified that `.parm` file contents keep ArduPilot's normal space/newline
  parameter format; only the wrapper env var changed.
- Kept the direct-file path deliberately simple.

Prompt:

> Support mounting a directory containing a custom `vehicleinfo.json` that
> points to param files in the same directory.

Answer and changes:

- Added `docker/resolve-sitl-config.py`.
- The resolver:
  - discovers `$VEHICLEINFO_JSON` or `$SITL_CONFIG_DIR/vehicleinfo.json`
  - copies mounted `vehicleinfo.json` over ArduPilot's runtime
    `Tools/autotest/pysim/vehicleinfo.json`
  - resolves relative `model` JSON paths and `default_params_filename` entries
    against the mounted directory
  - emits `--model` and `--add-param-file` args for `run-sitl.sh`
  - allows explicit `MODEL` and `PARAM_FILE` to override values inferred from
    mounted `vehicleinfo.json`
- Updated `Dockerfile`, `env.list`, and `README.md`.
- Avoided patching upstream `sim_vehicle.py`; the wrapper handles runtime
  resolution instead.

Prompt:

> Populate a repo-local config directory ready for `SITL_CONFIG_DIR`, using
> configs already inside the ArduPilot repo as references.

Answer and changes:

- Added checked-in example bundles:
  - `configs/frames/arducopter-quad`
  - `configs/frames/arduplane-plane`
- Each bundle contains a local `vehicleinfo.json` plus the relevant `.parm`
  copied from `./ardupilot/Tools/autotest`.
- Added `configs/README.md` and `configs/frames/MANIFEST.md`.

Prompt:

> Are there more than Callisto, freestyle, and plane? I want all models and
> params if they exist.

Answer and changes:

- Inventoried ArduPilot's `vehicleinfo.json`, `default_params`, and `models`
  directories.
- Found many frame/param combinations.
- Added `scripts/populate-config-bundles.py` to generate the full catalog on
  demand from the local `./ardupilot` checkout.
- Initially generated 95 bundles for validation, then trimmed the repo back to
  the two examples to avoid clutter.
- Changed the generator default output to ignored `configs/generated-frames/`.
- Added `.gitignore` entry for generated bundles.


## Documentation Structure

Prompt:

> Update the session summary, create a design doc with philosophy and
> decisions, and consider how future work should be tracked.

Answer and changes:

- Treated `SESSION_SUMMARY.md` as a dev log and appended recent runtime-config
  work.
- Added `docs/DESIGN.md` to capture architecture, philosophy, trade-offs, and
  major decisions.
- Added `docs/FUTURE_WORK.md` as the action-oriented backlog.
- Replaced the README's inline future-improvements block with links to the
  design and future-work docs.


## DOX / AGENTS Hierarchy

Prompt:

> Add the `AGENTS.md` doc from `agent0ai/dox` into the correct/logical spots.
> Copy/paste it first, then update it without rewriting away its original
> behavior.

Answer and changes:

- Added the upstream DOX `AGENTS.md` text at the repository root first.
- Updated it within the DOX framework by formatting the original contract,
  filling in the project-level contracts, and replacing the placeholder child
  index with a real index.
- Added scoped child DOX files:
  - `configs/AGENTS.md`
  - `docker/AGENTS.md`
  - `docs/AGENTS.md`
  - `scripts/AGENTS.md`
- Left `./ardupilot` alone because it is treated as an external checkout and
  has its own upstream `AGENTS.md`.
- Recorded the user preference to preserve external/framework instruction docs
  and adapt them within their own framework rather than rewriting from scratch.


## Validation Performed

Throughout the session, the following checks were run after changes:

```bash
docker buildx build --check -f Dockerfile .
docker buildx build --check -f Dockerfile --build-arg BASE_IMAGE=debian --build-arg TAG=bookworm-slim .
bash -n scripts/build-release-image.sh
docker compose -f compose.sitl.yml config
python3 -m py_compile scripts/populate-config-bundles.py docker/resolve-sitl-config.py
python3 -m json.tool configs/frames/arducopter-quad/vehicleinfo.json
python3 -m json.tool configs/frames/arduplane-plane/vehicleinfo.json
```

Full image builds were generally not run unless explicitly requested, because
they clone/build ArduPilot and download external dependencies.
