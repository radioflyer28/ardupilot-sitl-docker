# PX4 SIH Runtime

This note captures the first PX4 Simulator-In-Hardware (SIH) Docker path and
how it maps onto this repo's existing SITL conventions.


## Status

V1 is implemented as a sibling image path:

- `Dockerfile.px4-sih` builds PX4's `px4_sitl_sih` target.
- `scripts/build-px4-sih-image.sh` builds, tags, loads/exports, or pushes PX4
  SIH images with the same output modes and zstd compression behavior as the
  ArduPilot release script.
- `docker/px4-sih-entrypoint.sh` mirrors the ArduPilot entrypoint pattern.
- `docker/run-px4-sih.sh` starts the prebuilt PX4 binary directly.

The PX4 path is intentionally smaller than the ArduPilot path. It does not
attempt to support shared scenario manifests yet, and it does not reuse
ArduPilot-only features such as `vehicleinfo.json`, `sim_vehicle.py`, MAVProxy,
or Lua mission loading.

The builder also avoids PX4's default recursive clone. SIH does not need
external simulator stacks, so `Dockerfile.px4-sih` clones PX4 source without
submodules and initializes only a configurable `PX4_SUBMODULE_PATHS` list. This
is both a build-time and image-size decision: Gazebo Classic, Gazebo, jMAVSim,
FlightGear, and JSBSim sources should not be fetched for the SIH image unless a
future mode explicitly needs them.


## Source Findings

Official PX4 SIH docs for `main` describe `make px4_sitl_sih sihsim_quadx` as
the normal quadrotor startup path. PX4 v1.16 docs use
`make px4_sitl sihsim_quadx`; that target writes to `build/px4_sitl_default`.
The build script infers the release-compatible target and build directory, with
`PX4_BUILD_TARGET` and `PX4_BUILD_DIR` available as overrides.

Those documented `make ... sihsim_quadx` commands are developer build-and-run
commands. The Docker builder intentionally compiles only `PX4_BUILD_TARGET` and
does not pass `PX4_SIM_MODEL` to `make`, because launching the model target
during `docker build` can leave the build step running indefinitely. The runtime
wrapper sets `PX4_SIM_MODEL` before starting the prebuilt `px4` binary.

PX4 SIH also supports `PX4_SIM_SPEED_FACTOR` for faster-than-realtime
simulation and `PX4_HOME_LAT`, `PX4_HOME_LON`, and `PX4_HOME_ALT` for custom
home location:

```text
https://docs.px4.io/main/en/sim_sih/
```

PX4's multi-instance helper starts already-built binaries with:

```text
build/<target>/bin/px4 -i <instance> -d build/<target>/etc
```

and exports `PX4_SIM_MODEL` before launch:

```text
https://github.com/PX4/PX4-Autopilot/blob/main/Tools/simulation/sitl_multiple_run.sh
```

PX4's POSIX startup script maps `PX4_SIM_MODEL` to an airframe, auto-sets
`MAV_SYS_ID` to `px4_instance + 1`, and applies environment variables named
`PX4_PARAM_<PARAM_NAME>` as parameter overrides:

```text
https://github.com/PX4/PX4-Autopilot/blob/main/ROMFS/px4fmu_common/init.d-posix/rcS
```

PX4's SIH module currently defines model targets for:

```text
sihsim_airplane
sihsim_quadx
sihsim_xvert
sihsim_standard_vtol
sihsim_hexa
sihsim_rover_ackermann
```

The docs currently present `sihsim_quadx` as the stable/default path. Treat the
other models as experimental unless validated for the chosen PX4 release.

The PX4 `main` SIH docs call out that `px4_sitl_sih` should be used for SIH
because `px4_sitl` also builds Gazebo libraries. For releases where
`px4_sitl_sih` does not exist, the script falls back to the documented
`px4_sitl` target while still keeping simulator submodules out of the default
checkout.


## Runtime Contract

The PX4 wrapper keeps the same low-level env names where PX4 has a direct
equivalent:

```text
INSTANCE  -> px4 -i <instance>
SYSID     -> PX4_PARAM_MAV_SYS_ID, only when SYSID is set
LAT       -> PX4_HOME_LAT
LON       -> PX4_HOME_LON
ALT       -> PX4_HOME_ALT
SPEEDUP   -> PX4_SIM_SPEED_FACTOR
MODEL     -> PX4_SIM_MODEL
```

`SYSID` intentionally defaults to empty for PX4. When it is unset, PX4's
instance system assigns `MAV_SYS_ID=INSTANCE+1`. Set `SYSID` only when an
explicit MAVLink system ID is needed.

`DIR` is reserved for cross-autopilot symmetry, but PX4 SIH does not currently
map it to a heading control in this wrapper.

Additional PX4-native overrides can be passed directly with env vars such as:

```text
PX4_PARAM_SIH_WIND_N=2
PX4_PARAM_SIH_WIND_E=0
PX4_PARAM_COM_RC_IN_MODE=1
```


## Runtime Files

PX4 SIH writes runtime state, params, and logs in the PX4 working directory. The
wrapper chooses that directory in this order:

```text
PX4_RUN_DIR
ARTIFACTS_DIR/instance_<INSTANCE>
/tmp/px4-sih/instance_<INSTANCE>
```

Mount `ARTIFACTS_DIR` when retaining PX4 logs or parameters after a container
exits.


## Networking

PX4 SITL is UDP-oriented. The most predictable v1 Docker workflow is host
networking:

```bash
docker run -it --rm --network host px4-sih:sihsim-quadx
```

PX4's docs list common single-instance endpoints such as UDP `14550` for QGC,
UDP `14540` for offboard tools, UDP `18570` as a local MAVLink endpoint, UDP
`19410` for SIH visualization, and UDP `8888` for uXRCE-DDS.

Bridge networking may need additional PX4 network configuration, depending on
which host-side GCS or offboard client is used. Keep host networking as the
documented v1 path until bridge-mode behavior is validated.


## Design Boundaries

ArduPilot and PX4 should share conventions where they are naturally equivalent,
but the wrapper should not hide meaningful autopilot differences:

- ArduPilot uses `sim_vehicle.py`; PX4 SIH starts the `px4` binary directly.
- ArduPilot has `VEHICLE`, `FRAME`, `MODEL`, and `PARAM_FILE`; PX4 SIH uses
  `PX4_SIM_MODEL` and `PX4_PARAM_*`.
- ArduPilot mission loading can use Lua in this image; PX4 mission/fence/rally
  loading should use MAVLink upload tooling in a future shared layer.
- ArduPilot custom physics config can use model JSON and `vehicleinfo.json`;
  PX4 SIH physics is primarily parameterized through PX4 params and airframes.

The future shared manifest should target both runtime families by generating
their native low-level env vars, mounts, ports, and artifact directories rather
than forcing one autopilot's concepts onto the other.
