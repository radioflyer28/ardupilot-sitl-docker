ArduPilot SITL Docker Images
============================

This repository builds Docker images for running pre-built ArduPilot
Software-in-the-Loop (SITL) vehicles. The current image flow is centered on building ArduPilot in a heavy builder stage and copies the
pre-built SITL tree into a smaller runtime stage.

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
  -p 5760:5760/tcp \
  ardupilot-sitl:copter-4.6.3
```

Connect from the host:

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
PARAM_FILE      Optional file passed with --add-param-file
LUA_SCRIPT      Optional Lua script copied into ArduPilot scripts/ at startup
MISSION_FILE    Optional QGC WPL 110 mission loaded through Lua scripting
FENCE_FILE      Optional geofence JSON uploaded with MAVLink mission protocol
RALLY_FILE      Optional rally JSON uploaded with MAVLink mission protocol
PLAN_UPLOAD_MASTER Optional MAVLink endpoint for fence/rally upload
PLAN_UPLOAD_TIMEOUT Seconds to wait for fence/rally upload. Default: 60
LAT             Custom home latitude
LON             Custom home longitude
ALT             Custom home altitude in meters
DIR             Custom home heading in degrees
SPEEDUP         Simulation speed multiplier. Default: 1
NO_MAVPROXY     Set to 1 to append --no-mavproxy. Default: 0
PROXY           Optional extra MAVProxy args passed with -m/--mavproxy-args
JOBS            sim_vehicle.py -j value at runtime. Default: 2
```

`INSTANCE` does not automatically change `SYSID`. For multiple vehicles, set
both:

```bash
docker run ... -e INSTANCE=0 -e SYSID=1 -p 5760:5760/tcp ...
docker run ... -e INSTANCE=1 -e SYSID=2 -p 5770:5770/tcp ...
docker run ... -e INSTANCE=2 -e SYSID=3 -p 5780:5780/tcp ...
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

Relative `model` JSON paths and `default_params_filename` paths from the
mounted `vehicleinfo.json` are resolved relative to the mounted file's
directory. The wrapper copies the mounted `vehicleinfo.json` over
ArduPilot's runtime `Tools/autotest/pysim/vehicleinfo.json` before launching
`sim_vehicle.py`.

`MODEL` and `PARAM_FILE` still work with a mounted `vehicleinfo.json`. When
set, they override the model or params inferred from the mounted JSON.


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

When `$SITL_CONFIG_DIR/scripts/` exists, the wrapper copies its contents into
the ArduPilot working `scripts/` directory before launching `sim_vehicle.py`.

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

Absolute `MISSION_FILE` paths are used as-is. Relative paths are resolved under
`SITL_CONFIG_DIR`. The wrapper stages the selected mission into the ArduPilot
working `missions/` directory and installs an image-provided `load-mission.lua`
script before `sim_vehicle.py` starts.

Mission loading uses ArduPilot Lua scripting, so include `SCR_ENABLE 1` in the
selected params. Unlike MAVProxy `wp load`, this path also works when
`NO_MAVPROXY=1`.

This repo includes a copyable mission example:

```text
configs/examples/mission/
  mission.parm
  missions/
    simple-copter.waypoints
```

Run it against the stock Copter quad frame:

```bash
docker run -it --rm \
  --env-file env.list \
  -v "$PWD/configs/examples/mission:/configs:ro" \
  -e PARAM_FILE=mission.parm \
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

Override `PLAN_UPLOAD_MASTER` only when you want the uploader to connect to a
specific endpoint, for example `tcp:127.0.0.1:5761`. `PLAN_UPLOAD_TIMEOUT`
defaults to 60 seconds.

When combining fence/rally upload with custom MAVProxy outputs, prefer the
`PROXY` env var so the wrapper can add its private upload output too. If you
pass your own trailing `-m/--mavproxy-args` after the image name, set
`PLAN_UPLOAD_MASTER` to an endpoint exposed by those MAVProxy args.

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

Stop them:

```bash
docker compose -f compose.sitl.yml down
```


Passing sim_vehicle.py Args
---------------------------

Arguments placed after the image name are handled by the entrypoint.

If the first argument starts with `-`, the arguments are appended to
`sim_vehicle.py`:

```bash
docker run -it --rm \
  --env-file env.list \
  ardupilot-sitl:copter-4.6.3 \
  --no-mavproxy --udp
```

If the first argument does not start with `-`, it is run as a command instead:

```bash
docker run -it --rm ardupilot-sitl:copter-4.6.3 bash
```

Inside a debug shell, prefer the wrapper:

```bash
run-sitl.sh --no-mavproxy
```

If you call `sim_vehicle.py` manually in the runtime image, include
`--no-rebuild` because compilers are not installed in the final stage:

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
  -p 5760:5760/tcp \
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
  --out=tcpin:0.0.0.0:5761
```


Post-Run Logs
-------------

ArduPilot and MAVProxy produce different logs:

```text
.BIN   ArduPilot onboard/dataflash log, written by the vehicle logger
.tlog  MAVLink telemetry log, normally written by MAVProxy or another GCS
```

For `.BIN` logs, SITL's default filesystem logger writes under the run
directory's `logs/` directory. You can mount a host artifact directory and pass
`sim_vehicle.py --use-dir` after the image name:

```bash
mkdir -p artifacts/uav0

docker run -it --rm \
  --env-file env.list \
  -v "$PWD/artifacts/uav0:/artifacts/uav0" \
  ardupilot-sitl:copter-4.6.3 \
  --use-dir /artifacts/uav0
```

Add params such as `LOG_DISARMED 1` when you need logs before arming.

For `.tlog` logs, keep MAVProxy enabled and pass `--aircraft` to place
MAVProxy state and telemetry logs in a named directory:

```bash
docker run -it --rm \
  --env-file env.list \
  -v "$PWD/artifacts/uav0:/artifacts/uav0" \
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

Future improvements and backlog items live in `docs/FUTURE_WORK.md`.
