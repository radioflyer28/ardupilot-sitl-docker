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
- `docker/run-px4-sih.sh` starts the prebuilt PX4 binary through the shared
  `run_state.py` process/state wrapper, without invoking make.

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


For external quad-X physics using the prebuilt v1.16.0 runtime, see
[PX4 + JSBSim](PX4_JSBSIM.md). It has combined and split packaging and shares
read-only catalogs with ArduCopter. The ordinary SIH image remains internal-only
by default; the dedicated JSBSim image supplies the adapter and physics environment.

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
explicit MAVLink system ID is needed. The managed `px4-rc.mavlink` PATH hook
reapplies it immediately before native MAVLink links start: v1.16 rcS otherwise
overwrites the initial `PX4_PARAM_MAV_SYS_ID` with `INSTANCE+1`. No upstream file
is changed. See [live qualification](RUNTIME_QUALIFICATION.md) for on-wire ID and
fresh/resume results; revalidate this startup hook for other releases.

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

These settings choose an owned run root; PX4 executes in its `work/`
subdirectory. The root must be empty or previously initialized by the runner.
Unmarked nonempty roots are rejected without deleting files.

`SITL_STATE=fresh` (default) archives existing work under `history/<id>/` and
starts clean. `resume` retains PX4 state. Mount `ARTIFACTS_DIR` when retaining logs
or parameters after a container exits. Ensure bind mounts are writable by the
image user; archive pruning remains an operator responsibility.

The wrapper monitors the binary, forwards shutdown to its process group, and
uses `SITL_STOP_TIMEOUT` (default 10 seconds) before killing survivors. Its status
becomes `ready` only after an initialized PX4 heartbeat from the expected SYSID,
component 1, and accepted mission/fence/rally uploads. Binary exit or bounded
initialization failure fails the run and terminates owned processes. The image
HEALTHCHECK checks fresh supervisor readiness, not continuous MAVLink reception,
GPS/EKF, arming, or mission feasibility.

`MISSION_FILE`, `FENCE_FILE`, and `RALLY_FILE` use the shared WPL/JSON parser;
relative paths resolve against `SITL_CONFIG_DIR` (default `/configs`). Validation
precedes state claiming and firmware launch. Omitted plans are not changed;
selected empty files clear that type. `PLAN_UPLOAD_TIMEOUT` defaults to 60 seconds
for the entire heartbeat/upload phase. `PLAN_UPLOAD_MASTER` can override transport,
not the expected SYSID, component or autopilot family.

PX4 v1.16 supports global/relative-altitude frames and common polygon/circle
fences and rally points. Firmware rejects unsupported commands/frames (including
ArduPilot-specific fence commands and terrain frames); rejection fails startup.
PX4 stores mission row 0 as an actual mission item, unlike ArduPilot's synthesized
home row. Use PX4-appropriate missions; upload acceptance does not prove safe flight.


## Networking

PX4 SITL is UDP-oriented. `compose.px4-sih.yml` defaults to Docker bridge
networking, publishing host UDP `127.0.0.1:18570` to the GCS relay's container port
18670. It requires an explicit `PX4_SIH_IMAGE` built with relay support. Connect
with an active UDP client such as `mavproxy.py --master=udpout:127.0.0.1:18570`.
Set `SITL_BIND_ADDRESS` to the host LAN IP (or `0.0.0.0`) to opt into LAN access.
`PX4_GCS_PORT` changes only the published host port.

PX4's native GCS peer learns a fixed source address. Directly publishing the
native UDP port can strand replies when a client reconnects from another port.
The optional `PX4_GCS_RELAY=1` byte relay binds native peer `127.0.0.1:14550`,
forwards client traffic to native `18570 + INSTANCE`, and listens inside the
container on `18670 + INSTANCE`. Native replies fan out to up to 64 peers that
sent traffic in the last 120 seconds; clients should send regular GCS heartbeats.
No MAVLink fields are rewritten. Relay exit or socket startup failure fails the
managed run. Internal listeners remain container-reachable for Docker forwarding;
only Docker's host publication defaults to localhost.

Native host networking remains opt-in and preserves UDP autodiscovery:

```bash
docker run -it --rm --network host -e PX4_GCS_RELAY=0 px4-sih:sihsim-quadx
```

PX4's docs list common single-instance endpoints such as UDP `14550` for QGC,
UDP `14540` for offboard tools, UDP `18570` as a local MAVLink endpoint, UDP
`19410` for SIH visualization, and UDP `8888` for uXRCE-DDS.

Managed initialization adds a non-forwarding, non-broadcast UDP link with loopback peer:
local `30000 + INSTANCE`, peer `31000 + INSTANCE`. The uploader binds the peer via
`udpin:127.0.0.1:<peer>` and releases it after initialization. GCS/offboard links are
not consumed by initialization. Coordinate these additional ports for host-networked
instances; the hook requires a free native MAVLink instance slot. PX4 v1.16 binds
its native UDP listener to all interfaces even with `-t 127.0.0.1`; that option
sets the peer, not an inbound ACL. The intended deployment is an office workstation
and local LAN, never public Internet exposure. Host-mode LAN reachability is
accepted; additional firewall rules are optional operator policy, not a runtime
prerequisite. Keep bridge initialization ports unpublished by default. MAVLink
identity checks are not authentication.
See the pinned [native UDP initialization](https://github.com/PX4/PX4-Autopilot/blob/v1.16.0/src/modules/mavlink/mavlink_main.cpp)
(`Mavlink::init_udp`) for the listener/peer distinction.

Bridge-mode clients must explicitly target the published endpoint and send
heartbeats; passive native UDP autodiscovery requires the host-network alternative.
Initialization ports are not published in the default Compose topology.


## Design Boundaries

ArduPilot and PX4 should share conventions where they are naturally equivalent,
but the wrapper should not hide meaningful autopilot differences:

- ArduPilot uses `sim_vehicle.py`; PX4 SIH starts the `px4` binary directly.
- ArduPilot has `VEHICLE`, `FRAME`, `MODEL`, and `PARAM_FILE`; PX4 SIH uses
  `PX4_SIM_MODEL` and `PX4_PARAM_*`.
- Mission/fence/rally initialization shares a MAVLink uploader, but each runtime
  owns its transport, native plan semantics and separately qualified capabilities.
- ArduPilot custom physics config can use model JSON and `vehicleinfo.json`;
  PX4 SIH physics is primarily parameterized through PX4 params and airframes.

The future shared manifest should target both runtime families by generating
their native low-level env vars, mounts, ports, and artifact directories rather
than forcing one autopilot's concepts onto the other.
