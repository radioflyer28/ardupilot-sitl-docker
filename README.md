ArduPilot SITL Docker Images
============================

This repository builds Docker images for running pre-built ArduPilot
Software-in-the-Loop (SITL) vehicles. The current image flow is centered on
`Dockerfile_new`, which builds ArduPilot in a heavy builder stage and copies the
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

Use `scripts/build-release-image.sh` to build one vehicle/release image and
save it as a zstd-compressed Docker archive.

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
OUTPUT_DIR   Archive output directory. Default: dist/images
CACHE_DIR    BuildKit local cache directory. Default: .buildx-cache
DOCKERFILE   Dockerfile path. Default: Dockerfile_new
BASE_IMAGE   Builder/runtime base image. Default: Dockerfile default
TAG          Builder/runtime base tag. Default: Dockerfile default
WAF_JOBS     Waf parallel jobs. Default: Dockerfile default
ZSTD_LEVEL   zstd compression level. Default: 9
ZSTD_LONG    zstd --long window. Default: 27
```

Restore an exported image:

```bash
zstd -dc dist/images/ardupilot-sitl-copter-4.6.3.docker.tar.zst | docker load
```


Manual Docker Builds
--------------------

Build the default image:

```bash
docker buildx build -f Dockerfile_new \
  --build-arg WAF_JOBS=8 \
  -t ardupilot-sitl:latest \
  --load .
```

Build a single target:

```bash
docker buildx build -f Dockerfile_new \
  --build-arg ARDUPILOT_REF=Copter-4.6.3 \
  --build-arg WAF_TARGET=copter \
  --build-arg WAF_JOBS=8 \
  -t ardupilot-sitl:copter-4.6.3 \
  --load .
```

Build all standard targets by omitting `WAF_TARGET`:

```bash
docker buildx build -f Dockerfile_new \
  --build-arg WAF_JOBS=8 \
  -t ardupilot-sitl:all \
  --load .
```

Use the lighter Debian slim base:

```bash
docker buildx build -f Dockerfile_new \
  --build-arg BASE_IMAGE=debian \
  --build-arg TAG=bookworm-slim \
  --build-arg WAF_TARGET=copter \
  --build-arg WAF_JOBS=8 \
  -t ardupilot-sitl:copter-bookworm \
  --load .
```


Build Args
----------

`Dockerfile_new` supports these main build args:

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

The Dockerfile uses BuildKit cache mounts for apt, pip, Gradle, and ccache. The
repository also includes `.dockerignore` so the local `./ardupilot` checkout is
not sent as Docker build context.


BuildKit Cache
--------------

For the first cached build, use only `--cache-to`:

```bash
docker buildx build -f Dockerfile_new \
  --build-arg WAF_TARGET=copter \
  --build-arg WAF_JOBS=8 \
  --cache-to type=local,dest=.buildx-cache,mode=max \
  -t ardupilot-sitl:copter \
  --load .
```

For later builds, use both cache flags:

```bash
docker buildx build -f Dockerfile_new \
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
INSTANCE      SITL instance number. Default: 0
SYSID         MAVLink autopilot system ID. Default: 1
VEHICLE       sim_vehicle.py vehicle. Default: ArduCopter
FRAME         sim_vehicle.py frame/model. Default: quad
LAT           Custom home latitude
LON           Custom home longitude
ALT           Custom home altitude in meters
DIR           Custom home heading in degrees
SPEEDUP       Simulation speed multiplier. Default: 1
NO_MAVPROXY   Set to 1 to append --no-mavproxy. Default: 0
PROXY         Optional extra MAVProxy args passed with -m/--mavproxy-args
JOBS          sim_vehicle.py -j value at runtime. Default: 2
```

`INSTANCE` does not automatically change `SYSID`. For multiple vehicles, set
both:

```bash
docker run ... -e INSTANCE=0 -e SYSID=1 -p 5760:5760/tcp ...
docker run ... -e INSTANCE=1 -e SYSID=2 -p 5770:5770/tcp ...
docker run ... -e INSTANCE=2 -e SYSID=3 -p 5780:5780/tcp ...
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
