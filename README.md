SITL Docker Images
==================

This repository builds Docker images for running pre-built autopilot
Software-in-the-Loop (SITL) vehicles. The mature path is ArduPilot SITL. A v1
PX4 Simulator-In-Hardware (SIH) sibling image is also available for users who
want a PX4-native, headless runtime.

The ArduPilot image flow is centered on building ArduPilot in a heavy builder
stage and copying the pre-built SITL tree into a smaller runtime stage.

The runtime image is meant to start quickly with `--no-rebuild`. It does not
include a full compiler toolchain, so manual `sim_vehicle.py` runs inside the
container should also use `--no-rebuild`, or use the included `run-sitl.sh`
wrapper.


Quick Start
-----------

Build a Copter release image and export it as a compressed archive:

```bash
WAF_JOBS=8 scripts/build-release-image.sh copter 4.6.3
```

This creates an image named:

```text
ardupilot-sitl:copter-4.6.3
```

and exports it to:

```text
dist/images/ardupilot-sitl-copter-4.6.3.docker.tar.zst
```

Run the image with the default entrypoint:

```bash
docker run -it --rm --env-file env.list ardupilot-sitl:copter-4.6.3
```

Run headless without MAVProxy and expose direct SITL MAVLink TCP:

```bash
docker run -d --rm \
  --env-file env.list \
  -e NO_MAVPROXY=1 \
  -p 127.0.0.1:5760:5760/tcp \
  ardupilot-sitl:copter-4.6.3
```

Wait until Docker reports the container healthy, then connect from the host:

```bash
mavproxy.py --master=tcp:127.0.0.1:5760
```


Release Build Script
--------------------

Use `scripts/build-release-image.sh` to build one vehicle/release image.
By default it loads the image locally with zstd BuildKit compression options,
then saves a zstd-compressed Docker archive. It can also load the local image
without writing an archive, or push an OCI image with zstd-compressed layers.

```bash
scripts/build-release-image.sh <target> <version-or-ref>
```

Targets:

```text
copter -> Copter-<version>
plane  -> Plane-<version>
rover  -> Rover-<version>
sub    -> ArduSub-<version>
```

Examples:

```bash
WAF_JOBS=8 scripts/build-release-image.sh copter 4.6.3
WAF_JOBS=8 scripts/build-release-image.sh plane 4.6.3
WAF_JOBS=8 scripts/build-release-image.sh rover 4.6.3
WAF_JOBS=8 scripts/build-release-image.sh sub 4.5.7
```

You can also pass the full ArduPilot ref:

```bash
WAF_JOBS=8 scripts/build-release-image.sh copter Copter-4.6.3
```

Script environment overrides:

```text
IMAGE_REPO   Image repo/name. Default: ardupilot-sitl
IMAGE_OUTPUT Output mode: archive, local, or registry. Default: archive
OUTPUT_DIR   Archive output directory. Default: dist/images
CACHE_DIR    BuildKit local cache directory. Default: .buildx-cache
DOCKERFILE   Dockerfile path. Default: Dockerfile
BASE_IMAGE   Builder/runtime base image. Default: Dockerfile default
TAG          Builder/runtime base tag. Default: Dockerfile default
WAF_JOBS     Waf parallel jobs. Default: Dockerfile default
ZSTD_LEVEL   zstd compression level for image layers and archives. Default: 3
ZSTD_LONG    zstd --long window. Default: 27
```

Build and load a local image without exporting an archive:

```bash
IMAGE_OUTPUT=local \
WAF_JOBS=8 \
scripts/build-release-image.sh copter 4.6.3
```

Restore an exported image:

```bash
zstd -dc dist/images/ardupilot-sitl-copter-4.6.3.docker.tar.zst | docker load
```

Push a registry image with zstd-compressed OCI layers:

```bash
IMAGE_OUTPUT=registry \
IMAGE_REPO=ghcr.io/example/ardupilot-sitl \
WAF_JOBS=8 \
scripts/build-release-image.sh copter 4.6.3
```


Manual Docker Builds
--------------------

Build the default image:

```bash
docker buildx build -f Dockerfile \
  --build-arg WAF_JOBS=8 \
  -t ardupilot-sitl:latest \
  --load .
```

Build a single target:

```bash
docker buildx build -f Dockerfile \
  --build-arg ARDUPILOT_REF=Copter-4.6.3 \
  --build-arg WAF_TARGET=copter \
  --build-arg WAF_JOBS=8 \
  -t ardupilot-sitl:copter-4.6.3 \
  --load .
```

Build all standard targets by omitting `WAF_TARGET`:

```bash
docker buildx build -f Dockerfile \
  --build-arg WAF_JOBS=8 \
  -t ardupilot-sitl:all \
  --load .
```

Use the lighter Debian slim base:

```bash
docker buildx build -f Dockerfile \
  --build-arg BASE_IMAGE=debian \
  --build-arg TAG=bookworm-slim \
  --build-arg WAF_TARGET=copter \
  --build-arg WAF_JOBS=8 \
  -t ardupilot-sitl:copter-bookworm \
  --load .
```


Build Args
----------

`Dockerfile` supports these main build args:

```text
BASE_IMAGE             Base image family. Default: ubuntu
TAG                    Base image tag. Default: 24.04
USER_NAME              Runtime user. Default: ardupilot
USER_UID               Runtime user UID. Default: 1000
USER_GID               Runtime user GID. Default: 1000
ARDUPILOT_REPO         ArduPilot git repository URL
ARDUPILOT_REF          Branch/tag/commit to checkout. Default: master
COPTER_TAG             Legacy alias that takes precedence over ARDUPILOT_REF
ARDUPILOT_CLONE_DEPTH  Shallow clone depth. Default: 1
WAF_TARGET             One target: copter, plane, rover, sub. Empty builds all
WAF_ALL_TARGETS        Targets built when WAF_TARGET is empty
WAF_JOBS               Parallel waf jobs. Default: 2
DO_AP_STM_ENV          Install STM32 toolchain. Default: 0
```

The Dockerfile uses BuildKit cache mounts for apt, pip, Gradle, and ccache. The repository also includes `.dockerignore` so the local `./ardupilot` checkout is not sent as Docker build context.


BuildKit Cache
--------------

For the first cached build, use only `--cache-to`:

```bash
docker buildx build -f Dockerfile \
  --build-arg WAF_TARGET=copter \
  --build-arg WAF_JOBS=8 \
  --cache-to type=local,dest=.buildx-cache,mode=max \
  -t ardupilot-sitl:copter \
  --load .
```

For later builds, use both cache flags:

```bash
docker buildx build -f Dockerfile \
  --build-arg WAF_TARGET=copter \
  --build-arg WAF_JOBS=8 \
  --cache-from type=local,src=.buildx-cache \
  --cache-to type=local,dest=.buildx-cache,mode=max \
  -t ardupilot-sitl:copter \
  --load .
```

The release build script handles this automatically: it imports the cache if
`.buildx-cache/index.json` exists and exports cache on every build.


PX4 SIH Image
-------------

`Dockerfile.px4-sih` builds a prebuilt PX4 Simulator-In-Hardware runtime. This
is a sibling image path, not a replacement for the ArduPilot image.

Use `scripts/build-px4-sih-image.sh` to build one PX4 SIH model/ref image.
It mirrors the ArduPilot release script's archive, local, registry, cache, and
zstd compression behavior.

```bash
scripts/build-px4-sih-image.sh <model> <version-or-ref>
```

Examples:

```bash
PX4_JOBS=8 scripts/build-px4-sih-image.sh sihsim_quadx v1.16.0
PX4_JOBS=8 scripts/build-px4-sih-image.sh sihsim_quadx 1.16.0
IMAGE_OUTPUT=local scripts/build-px4-sih-image.sh sihsim_quadx main
```

The numeric version form `1.16.0` is normalized to PX4's tag form `v1.16.0`.
The default archive output writes:

```text
dist/images/px4-sih-sihsim-quadx-v1.16.0.docker.tar.zst
```

Restore an exported PX4 image:

```bash
zstd -dc dist/images/px4-sih-sihsim-quadx-v1.16.0.docker.tar.zst | docker load
```

Push a registry image with zstd-compressed OCI layers:

```bash
IMAGE_OUTPUT=registry \
IMAGE_REPO=ghcr.io/example/px4-sih \
PX4_JOBS=8 \
scripts/build-px4-sih-image.sh sihsim_quadx v1.16.0
```

PX4 build script environment overrides:

```text
IMAGE_REPO          Image repo/name. Default: px4-sih
IMAGE_OUTPUT        Output mode: archive, local, or registry. Default: archive
OUTPUT_DIR          Archive output directory. Default: dist/images
CACHE_DIR           BuildKit local cache directory. Default: .buildx-cache/px4-sih
DOCKERFILE          Dockerfile path. Default: Dockerfile.px4-sih
PX4_BUILDER_IMAGE   PX4 build image. Default: Dockerfile default
RUNTIME_BASE_IMAGE  Runtime base image family. Default: Dockerfile default
RUNTIME_TAG         Runtime base tag. Default: Dockerfile default
PX4_REPO            PX4 git repository URL. Default: Dockerfile default
PX4_CLONE_DEPTH     Shallow clone depth. Default: Dockerfile default
PX4_SUBMODULE_PATHS Space-separated submodules to initialize. Default: Dockerfile default
PX4_BUILD_TARGET    PX4 build target. Default: inferred from PX4_REF
PX4_BUILD_DIR       PX4 build output directory. Default: inferred from target
PX4_JOBS            Parallel make jobs. Default: Dockerfile default
ZSTD_LEVEL          zstd compression level for image layers and archives. Default: 3
ZSTD_LONG           zstd --long window. Default: 27
```

Manual PX4 buildx example:

```bash
docker buildx build -f Dockerfile.px4-sih \
  --build-arg PX4_REF=v1.16.0 \
  --build-arg PX4_SIM_MODEL=sihsim_quadx \
  --build-arg PX4_JOBS=8 \
  -t px4-sih:sihsim-quadx-v1.16.0 \
  --load .
```

PX4-specific build args:

```text
PX4_BUILDER_IMAGE PX4 build image. Default: px4io/px4-dev-base-jammy:latest
RUNTIME_BASE_IMAGE Runtime base image family. Default: ubuntu
RUNTIME_TAG        Runtime base tag. Default: 22.04
PX4_REPO           PX4 git repository URL
PX4_REF            PX4 branch, tag, or commit. Default: main
PX4_CLONE_DEPTH    Shallow clone depth. Default: 1
PX4_SUBMODULE_PATHS Space-separated submodules initialized for the build
PX4_BUILD_TARGET   PX4 build target. Default: px4_sitl_sih in Dockerfile
PX4_BUILD_DIR      PX4 build output directory. Default: px4_sitl_sih
PX4_SIM_MODEL      Runtime PX4 SIH model default. Default: sihsim_quadx
PX4_JOBS           Parallel make jobs. Default: 2
```

The build script infers release-compatible defaults. For `main` or `master`,
it uses the newer `PX4_BUILD_TARGET=px4_sitl_sih` and
`PX4_BUILD_DIR=px4_sitl_sih`. For release refs such as `v1.16.0`, it uses
`PX4_BUILD_TARGET=px4_sitl` and `PX4_BUILD_DIR=px4_sitl_default`, matching the
PX4 v1.16 SIH docs.

During image build, the Dockerfile compiles only `PX4_BUILD_TARGET`. It does
not pass the model name to `make`, because PX4's documented
`make px4_sitl sihsim_quadx` style command is a build-and-run developer
workflow. The Docker image sets `PX4_SIM_MODEL` for runtime instead.

The PX4 Dockerfile intentionally avoids `git clone --recursive`. It initializes
only the submodules expected for a headless SIH build and skips simulator stacks
such as Gazebo Classic, Gazebo, jMAVSim, FlightGear, and JSBSim. This keeps the
first build faster and prevents unused simulator assets from influencing the
builder and final runtime image size. If a PX4 release needs a different set,
override `PX4_SUBMODULE_PATHS`.

Run with PX4's recommended simple Docker networking path:

```bash
docker run -it --rm --network host px4-sih:sihsim-quadx
```

PX4 SIH runtime envs intentionally reuse the common names where PX4 has native
equivalents:

```text
INSTANCE      PX4 instance number, passed as px4 -i. Default: 0
SYSID         Optional MAVLink system ID, mapped to PX4_PARAM_MAV_SYS_ID
MODEL         Optional PX4_SIM_MODEL override. Default: sihsim_quadx
LAT           Home latitude, mapped to PX4_HOME_LAT
LON           Home longitude, mapped to PX4_HOME_LON
ALT           Home altitude, mapped to PX4_HOME_ALT
SPEEDUP       Speed factor, mapped to PX4_SIM_SPEED_FACTOR. Default: 1
PX4_RUN_DIR   Explicit PX4 working directory
ARTIFACTS_DIR Parent artifact directory; wrapper uses instance_<INSTANCE>
```

When `SYSID` is unset, PX4 assigns `MAV_SYS_ID=INSTANCE+1`. Set `SYSID` only
when you want to override that native instance behavior.

PX4-native parameter overrides can be passed directly:

```bash
docker run -it --rm --network host \
  -e LAT=37.1971467 \
  -e LON=-80.5780381 \
  -e ALT=618 \
  -e SPEEDUP=2 \
  -e PX4_PARAM_SIH_WIND_N=2 \
  -e PX4_PARAM_SIH_WIND_E=0 \
  px4-sih:sihsim-quadx
```

Available SIH model names come from PX4 and include `sihsim_quadx`,
`sihsim_airplane`, `sihsim_hexa`, `sihsim_xvert`, `sihsim_standard_vtol`, and
`sihsim_rover_ackermann`. Treat models other than `sihsim_quadx` as
experimental until validated against the PX4 release you are using.

PX4 uses the same owned `work/` and `history/` layout and
`SITL_STATE=fresh|resume` policy. `PX4_RUN_DIR` must be empty or runner-owned;
existing unmarked directories are rejected without deletion. Its process status
is `running`, not MAVLink-ready: PX4 readiness and plan initialization remain
separate future work.

More PX4 SIH research and design notes live in `docs/PX4_SIH.md`.


Runtime Configuration
---------------------

The image entrypoint runs `run-sitl.sh` by default. Runtime settings can be
provided with `env.list` or `docker run -e`.

Common runtime environment variables:

```text
INSTANCE        SITL instance number. Default: 0
SYSID           MAVLink autopilot system ID. Default: 1
VEHICLE         sim_vehicle.py vehicle. Default: ArduCopter
FRAME           sim_vehicle.py frame/model. Default: quad
SITL_CONFIG_DIR Runtime config directory. Default: /configs
VEHICLEINFO_JSON Optional mounted vehicleinfo.json path
MODEL           Optional sim_vehicle.py --model override
PARAM_FILES     JSON array of ordered parameter file paths
PARAM_FILE      Optional final env parameter layer (after bundle/PARAM_FILES)
LUA_SCRIPT      Optional Lua script copied into ArduPilot scripts/ at startup
MISSION_FILE    Optional QGC WPL 110 mission uploaded through MAVLink
FENCE_FILE      Optional geofence JSON uploaded with MAVLink mission protocol
RALLY_FILE      Optional rally JSON uploaded with MAVLink mission protocol
PLAN_UPLOAD_MASTER Optional initialization endpoint, verified against SYSID/component 1
PLAN_UPLOAD_TIMEOUT Total initialization deadline in seconds. Default: 60
SITL_RUN_DIR    Owned run directory (CLI alias: --use-dir)
ARTIFACTS_DIR   Run directory parent; uses instance_<INSTANCE>
SITL_STATE      fresh (default) or resume
SITL_STOP_TIMEOUT Graceful process-group shutdown deadline. Default: 10 seconds
LAT             Custom home latitude
LON             Custom home longitude
ALT             Custom home altitude in meters
DIR             Custom home heading in degrees
SPEEDUP         Simulation speed multiplier. Default: 1
NO_MAVPROXY     1 selects direct TCP; 0 enables MAVProxy. Default: 1
PROXY           MAVProxy --out, --logfile, and --streamrate options only
```

The managed runner validates configuration before staging or launch. Scalar CLI
options override env values; parameter files layer in this order: native frame
defaults, bundle files, `PARAM_FILES`, `PARAM_FILE`, repeated CLI
`--add-param-file` options. Later values win. `PARAM_FILE` no longer discards
bundle parameters.

Use `--validate` to check inputs without launching, or
`--print-effective-config` to inspect the resolved JSON. Both require the
prebuilt vehicle binary to be present. No upstream files are overwritten.

Each run directory must be empty or previously initialized by this runner:

```text
work/                   current vehicle state, scripts, and logs
history/<id>/           previous work directories archived by fresh starts
effective-config.json   resolved launch configuration
status.json             lifecycle state and recent supervisor timestamp
```

The default is `/tmp/ardupilot-sitl/instance_<INSTANCE>`. `fresh` archives old
state and starts clean; `resume` preserves state. Both replace managed scripts
and re-upload explicitly selected plans. Retention is manual: archive history
can grow. Mount a writable run directory to retain it after container removal;
bind mounts must be writable by the image user (default UID 1000).

Readiness requires the expected autopilot heartbeat, accepted uploads for every
requested plan, and a live vehicle process. It does **not** mean ready to arm,
GPS/EKF healthy, or user Lua completed. In direct TCP mode, connect external
clients only after the container becomes healthy; initialization temporarily
owns that single-client connection. `run-sitl.sh --healthcheck` checks the active
run. A vehicle/launcher crash fails the container. Shutdown terminates the owned
process group, waits up to `SITL_STOP_TIMEOUT`, then kills remaining processes.
Set Docker's stop timeout longer than that deadline (Compose uses 20 seconds).

`INSTANCE` does not automatically change `SYSID`. For multiple vehicles, set
both:

```bash
docker run ... -e INSTANCE=0 -e SYSID=1 -p 127.0.0.1:5760:5760/tcp ...
docker run ... -e INSTANCE=1 -e SYSID=2 -p 127.0.0.1:5770:5770/tcp ...
docker run ... -e INSTANCE=2 -e SYSID=3 -p 127.0.0.1:5780:5780/tcp ...
```


Runtime Model And Param File
----------------------------

The runtime image can use mounted model and parameter files without rebuilding
ArduPilot. Mount your config directory at `/configs`, then set `MODEL` and
`PARAM_FILE`.

For a JSON-backed Copter physics model:

```bash
docker run -it --rm \
  --env-file env.list \
  -v "$PWD/configs:/configs:ro" \
  -e MODEL="quad:/configs/my_quad.json" \
  -e PARAM_FILE="my_quad.parm" \
  ardupilot-sitl:copter-4.6.3
```

`MODEL` is passed directly to `sim_vehicle.py --model`. For Copter model JSON,
use the ArduPilot frame/model prefix plus the mounted path, such as
`quad:/configs/my_quad.json`, `x:/configs/my_quad_x.json`, or
`octa-quad-cwx:/configs/heavy_octa.json`.

`PARAM_FILE` is passed as one `--add-param-file` argument. Absolute paths are
used as-is. Relative paths are resolved under `SITL_CONFIG_DIR`, which defaults
to `/configs`.

Example with an absolute parameter file path:

```bash
docker run -it --rm \
  --env-file env.list \
  -v "$PWD/configs:/configs:ro" \
  -e MODEL="quad:/configs/my_quad.json" \
  -e PARAM_FILE="/configs/my_quad.parm" \
  ardupilot-sitl:copter-4.6.3
```

Mounted `vehicleinfo.json`
--------------------------

For reusable custom vehicles, mount a config directory containing
`vehicleinfo.json`, the model JSON, and the matching params. If
`$SITL_CONFIG_DIR/vehicleinfo.json` exists, the wrapper uses it automatically.

Example directory:

```text
configs/my_quad/
  vehicleinfo.json
  my_quad.json
  my_quad.parm
```

Example `vehicleinfo.json` frame entry:

```json
{
  "ArduCopter": {
    "default_frame": "my-quad",
    "frames": {
      "my-quad": {
        "waf_target": "bin/arducopter",
        "model": "quad:my_quad.json",
        "default_params_filename": "my_quad.parm"
      }
    }
  }
}
```

Run it:

```bash
docker run -it --rm \
  --env-file env.list \
  -v "$PWD/configs/my_quad:/configs:ro" \
  -e FRAME=my-quad \
  ardupilot-sitl:copter-4.6.3
```

Relative `model` JSON paths and `default_params_filename` paths resolve against
the mounted file's directory. A process-local overlay supplies the selected
vehicle/frame metadata to upstream `sim_vehicle.py`; installed upstream files
remain unchanged. Custom frame names must have an explicit bundle entry.

`MODEL` overrides the model. `PARAM_FILE` adds a final env parameter layer on
top of the bundle; `PARAM_FILES` accepts an ordered JSON array of paths.


Runtime Lua Scripts
-------------------

The wrapper can install Lua scripts at container start without rebuilding the
image. This is useful for SITL-only behavior such as initial-state injection,
mission setup, simulated sensor behavior, or other ArduPilot scripting
experiments.

Bundle layout:

```text
configs/my_quad/
  vehicleinfo.json
  my_quad.json
  my_quad.parm
  scripts/
    initial-state.lua
```

The wrapper replaces `<run-dir>/work/scripts/` from the mounted bundle on every
start, including resume. Removed scripts therefore cannot leak into a later run.
The vehicle uses that same work directory even when `--use-dir` is selected.

For one explicit script, set `LUA_SCRIPT`:

```bash
docker run -it --rm \
  --env-file env.list \
  -v "$PWD/configs/my_quad:/configs:ro" \
  -e LUA_SCRIPT=initial-state.lua \
  ardupilot-sitl:copter-4.6.3
```

Absolute `LUA_SCRIPT` paths are used as-is. Relative paths are resolved under
`SITL_CONFIG_DIR`. `LUA_SCRIPT` is copied after `$SITL_CONFIG_DIR/scripts/`, so
an explicitly selected script can override a bundled script with the same
basename.

Installing a script is separate from enabling ArduPilot scripting. Include the
required parameters in your bundle params or selected `PARAM_FILE`; commonly
`SCR_ENABLE 1`, and for SITL pose injection with `sim:set_pose`,
`AHRS_EKF_TYPE 10`.

This repo includes a copyable initial-state example:

```text
configs/examples/initial-state/
  initial-state.parm
  scripts/
    initial-state.lua
```

Run it against the stock Copter quad frame:

```bash
docker run -it --rm \
  --env-file env.list \
  -v "$PWD/configs/examples/initial-state:/configs:ro" \
  -e PARAM_FILE=initial-state.parm \
  ardupilot-sitl:copter-4.6.3
```

The example script applies one pose when the vehicle arms. Edit
`scripts/initial-state.lua` to change the position, attitude, body-frame
velocity, body rates, trigger, or numeric flight mode.


Runtime Missions
----------------

Set `MISSION_FILE` to load a MAVLink plain-text mission at startup. The file
must use the `QGC WPL 110` mission format:

```text
configs/my_quad/
  my_quad.parm
  missions/
    survey.waypoints
```

Run it:

```bash
docker run -it --rm \
  --env-file env.list \
  -v "$PWD/configs/my_quad:/configs:ro" \
  -e PARAM_FILE=my_quad.parm \
  -e MISSION_FILE=missions/survey.waypoints \
  ardupilot-sitl:copter-4.6.3
```

Absolute `MISSION_FILE` paths are used as-is; relative paths resolve under
`SITL_CONFIG_DIR`. The entire file is validated before launch and uploaded using
`MAV_MISSION_TYPE_MISSION` before readiness. This works with or without MAVProxy
and does not require Lua or `SCR_ENABLE`.

Selected empty plans clear that plan type. Omitted plans are untouched by the
uploader (fresh state starts empty; resume retains vehicle state). Upload
failure fails startup; no automatic arming or mission start is performed.

This repo includes a copyable mission example:

```text
configs/examples/mission/
  missions/
    simple-copter.waypoints
```

Run it against the stock Copter quad frame:

```bash
docker run -it --rm \
  --env-file env.list \
  -v "$PWD/configs/examples/mission:/configs:ro" \
  -e MISSION_FILE=missions/simple-copter.waypoints \
  ardupilot-sitl:copter-4.6.3
```

The mission format is documented by MAVLink:
<https://mavlink.io/en/file_formats/>.


Runtime Fence And Rally Plans
-----------------------------

Set `FENCE_FILE` and/or `RALLY_FILE` to upload geofence and rally point plans
at startup. These are separate MAVLink mission-protocol plan types, so they use
JSON files instead of the `QGC WPL 110` mission format.

Example bundle:

```text
configs/my_quad/
  plan-artifacts.parm
  fences/
    operating-area.json
  rally/
    recovery-points.json
```

Run it:

```bash
docker run -it --rm \
  --env-file env.list \
  -v "$PWD/configs/my_quad:/configs:ro" \
  -e PARAM_FILE=plan-artifacts.parm \
  -e FENCE_FILE=fences/operating-area.json \
  -e RALLY_FILE=rally/recovery-points.json \
  ardupilot-sitl:copter-4.6.3
```

Absolute paths are used as-is. Relative `FENCE_FILE` and `RALLY_FILE` paths
are resolved under `SITL_CONFIG_DIR`.

Fence example:

```json
{
  "version": 1,
  "fences": [
    {
      "type": "polygon_inclusion",
      "points": [
        { "lat": 37.1961467, "lon": -80.5790381 },
        { "lat": 37.1981467, "lon": -80.5790381 },
        { "lat": 37.1981467, "lon": -80.5770381 },
        { "lat": 37.1961467, "lon": -80.5770381 }
      ]
    }
  ]
}
```

Supported fence types are `polygon_inclusion`, `polygon_exclusion`,
`circle_inclusion`, `circle_exclusion`, `home_circle_inclusion`, and
`return_point`. Circle fences use `radius`; non-home circles and return points
also use `lat` and `lon`.

Rally example:

```json
{
  "version": 1,
  "points": [
    {
      "lat": 37.1973467,
      "lon": -80.5782381,
      "alt": 35,
      "frame": "relative"
    }
  ]
}
```

The uploader waits until SITL accepts MAVLink, uploads the selected artifacts,
then leaves the container running normally. When `NO_MAVPROXY=1`, it uploads
to direct SITL TCP. When MAVProxy is enabled and `PLAN_UPLOAD_MASTER` is unset,
the wrapper adds a private in-container MAVProxy `tcpin` output for the upload.

The private MAVProxy upload/readiness port is `20000 + INSTANCE`, avoiding
SITL serial ports. `PLAN_UPLOAD_MASTER` can override the initialization endpoint;
its heartbeat must match `SYSID` and autopilot component 1. The 60-second
`PLAN_UPLOAD_TIMEOUT` is one overall startup deadline, not a fresh timeout per
artifact. The uploader retries count/item messages, honors repeated requests,
and filters acknowledgments by source, destination, and plan type.

Use `PROXY` or `-m/--mavproxy-args` for `--out`, `--logfile`, or `--streamrate`.
Managed master-link and startup-command overrides are rejected.

This repo includes a copyable plan-artifacts example:

```text
configs/examples/plan-artifacts/
  plan-artifacts.parm
  fences/
    simple-polygon.json
  rally/
    recovery-points.json
```

Run it against the stock Copter quad frame:

```bash
docker run -it --rm \
  --env-file env.list \
  -v "$PWD/configs/examples/plan-artifacts:/configs:ro" \
  -e PARAM_FILE=plan-artifacts.parm \
  -e FENCE_FILE=fences/simple-polygon.json \
  -e RALLY_FILE=rally/recovery-points.json \
  ardupilot-sitl:copter-4.6.3
```


Reference Config Bundles
------------------------

This repo includes small reference bundles under `configs/frames/`. They are
copied from ArduPilot's `Tools/autotest` model and default parameter files,
then flattened so each directory can be mounted directly as `SITL_CONFIG_DIR`.

Checked-in example bundles:

```text
configs/frames/arducopter-quad  ArduCopter quad params
configs/frames/arduplane-plane  ArduPlane plane params
```

Generate the full catalog on demand with:

```bash
scripts/populate-config-bundles.py
```

By default the generated catalog is written to ignored
`configs/generated-frames/`. It contains one mountable bundle per ArduPilot
`vehicleinfo.json` frame that references local model or parameter assets.

Run the checked-in Copter quad bundle:

```bash
docker run -it --rm \
  --env-file env.list \
  -v "$PWD/configs/frames/arducopter-quad:/configs:ro" \
  -e VEHICLE=ArduCopter \
  -e FRAME=quad \
  ardupilot-sitl:copter-4.6.3
```

Run the checked-in Plane bundle:

```bash
docker run -it --rm \
  --env-file env.list \
  -v "$PWD/configs/frames/arduplane-plane:/configs:ro" \
  -e VEHICLE=ArduPlane \
  -e FRAME=plane \
  ardupilot-sitl:plane-4.6.3
```

Copy one of these directories when creating a custom vehicle. Edit the local
`vehicleinfo.json`, model JSON, and `.parm` files together, then mount the copy
at `/configs`.


Docker Compose: Multiple SITL Instances
---------------------------------------

`compose.sitl.yml` starts three headless SITL containers with direct TCP MAVLink
ports:

```text
sitl-0 -> INSTANCE=0, SYSID=1, TCP 5760
sitl-1 -> INSTANCE=1, SYSID=2, TCP 5770
sitl-2 -> INSTANCE=2, SYSID=3, TCP 5780
```

Start them:

```bash
docker compose -f compose.sitl.yml up -d
```

Use a different image tag:

```bash
ARDUPILOT_SITL_IMAGE=ardupilot-sitl:copter-4.6.3 \
  docker compose -f compose.sitl.yml up -d
```

Connect from the host:

```bash
mavproxy.py --master=tcp:127.0.0.1:5760
mavproxy.py --master=tcp:127.0.0.1:5770
mavproxy.py --master=tcp:127.0.0.1:5780
```

Wait for readiness before connecting clients:

```bash
docker compose -f compose.sitl.yml up -d --wait
```

Ports bind to host loopback only. Change the bind address deliberately if remote
access is required. Each service has its own retained named run volume; the
volume target assumes the default image user/home. `SITL_STATE=fresh` archives
prior work on restart. Use a Compose override with `SITL_STATE: resume` to retain
active state instead. Configure per-service read-only `/configs` mounts for
different scenarios.

Stop them (named volumes are retained):

```bash
docker compose -f compose.sitl.yml down
```

`down -v` explicitly deletes retained run volumes.


Passing sim_vehicle.py Args
---------------------------

Arguments placed after the image name are handled by the entrypoint.

If the first argument starts with `-`, the managed runner parses it before
resolving configuration. Supported options are shown by `--help`; unknown or
conflicting upstream flags are rejected rather than silently bypassing derived
ports, run paths, and initialization settings:

```bash
docker run -it --rm \
  --env-file env.list \
  ardupilot-sitl:copter-4.6.3 \
  --no-mavproxy --instance 2 --sysid 3
```

If the first argument does not start with `-`, it is run as a command instead:

```bash
docker run -it --rm ardupilot-sitl:copter-4.6.3 bash
```

Inside a debug shell, prefer the wrapper:

```bash
run-sitl.sh --no-mavproxy
```

For unsupported upstream features (UDP serial transport, debuggers, multi-vehicle
or peripheral launching), explicitly run upstream `sim_vehicle.py` in a debug
shell. This bypasses managed configuration, staging, supervision, and readiness.
Include `--no-rebuild` because compilers are not installed:

```bash
Tools/autotest/sim_vehicle.py -v ArduCopter --frame quad --no-rebuild
```


MAVLink Access
--------------

With MAVProxy enabled, `sim_vehicle.py` uses its MAVProxy defaults unless
`PROXY` or extra args override them.

Without MAVProxy:

```bash
docker run -d --rm \
  --env-file env.list \
  -e NO_MAVPROXY=1 \
  -p 127.0.0.1:5760:5760/tcp \
  ardupilot-sitl:copter-4.6.3
```

Connect to direct SITL TCP:

```bash
mavproxy.py --master=tcp:127.0.0.1:5760
```

Default direct SITL TCP ports are:

```text
INSTANCE=0 -> 5760
INSTANCE=1 -> 5770
INSTANCE=2 -> 5780
```

Without MAVProxy you usually get one direct TCP MAVLink client. To fan out to
multiple clients, run MAVProxy outside the container:

```bash
mavproxy.py \
  --master=tcp:127.0.0.1:5760 \
  --out=udp:127.0.0.1:14550 \
  --out=tcpin:127.0.0.1:5761
```


Post-Run Logs
-------------

ArduPilot and MAVProxy produce different logs:

```text
.BIN   ArduPilot onboard/dataflash log, written by the vehicle logger
.tlog  MAVLink telemetry log, normally written by MAVProxy or another GCS
```

For `.BIN` logs, the vehicle logger writes under `<run-dir>/work/logs/`.
Mount an empty writable host run directory and select it with `--use-dir`
(or `SITL_RUN_DIR`). This also stages Lua scripts in the correct work directory:

```bash
mkdir -p artifacts/uav0

docker run -it --rm \
  --env-file env.list \
  -v "$PWD/artifacts/uav0:/artifacts/uav0" \
  ardupilot-sitl:copter-4.6.3 \
  --use-dir /artifacts/uav0
```

Add params such as `LOG_DISARMED 1` when you need logs before arming.

For `.tlog` logs, enable MAVProxy explicitly (`env.list` defaults to direct mode)
and pass `--aircraft` to choose its log directory:

```bash
docker run -it --rm \
  --env-file env.list \
  -v "$PWD/artifacts/uav0:/artifacts/uav0" \
  -e NO_MAVPROXY=0 \
  ardupilot-sitl:copter-4.6.3 \
  --use-dir /artifacts/uav0/sitl \
  --aircraft /artifacts/uav0/mavproxy
```

When `NO_MAVPROXY=1` or `--no-mavproxy` is used, this image does not create a
MAVProxy `.tlog`; use an external GCS/logger if you still need a telemetry log.


Development Docs
----------------

Design rationale and trade-offs live in `docs/DESIGN.md`.

Research indexes and investigation status live in `docs/RESEARCH.md`.

SITL initial-state research and runtime Lua recommendations live in
`docs/INITIAL_STATE.md`.

Runtime mission, fence, rally, and fleet artifact decisions live in
`docs/PLAN_ARTIFACTS.md`.

PX4 SIH runtime research and design notes live in `docs/PX4_SIH.md`.

Notable project changes live in `docs/CHANGELOG.md`.

The chronological session/dev log lives in `docs/SESSION_SUMMARY.md`.

Future improvements and backlog items live in `docs/FUTURE_WORK.md`.
